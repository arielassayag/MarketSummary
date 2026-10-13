"""Contratos reais MCP em memória e STDIO — operandos dos ensaios DADOS SIMULADOS."""
# ruff: noqa: E402 -- extra opcional: a ausência do SDK pula este arquivo antes dos imports.
import builtins
import hashlib
import io
import json
import os
import socket
import subprocess
import sys
from pathlib import Path

import numpy as np
import pytest
from pydantic import ValidationError

pytest.importorskip("mcp")
from jsonschema import Draft202012Validator
from mcp import Client, MCPError, StdioServerParameters
from mcp.types import CallToolRequestParams

from cdp.mcp_readonly import server
from cdp.mcp_readonly.schemas import (
    EntradaPB,
    NumeroObservado,
    SaidaKE,
    SucessoKE,
)
from cdp.tecnicas import avaliar_pb_justificado, calcular_ke, estimar_preenchimento

KE = {"rf": 0.01, "beta": 1.0, "erp": 0.05, "lam": 1.0, "crp": 0.02}
FILL = {"ordem_acoes": -7, "capacidade_usd": 15.0, "preco_usd": 3.0}


def escalar(value):
    return {"tipo": "escalar", "valor": value}


PB = {"roe": escalar(0.15), "ke": escalar(0.1), "g": escalar(0.02)}


def capturar_pb(monkeypatch):
    calls = []
    original = server.avaliar_pb_justificado

    def spy(*operands, estrito):
        calls.append(([np.asarray(v).copy() for v in operands], estrito))
        return original(*operands, estrito=estrito)

    monkeypatch.setattr(server, "avaliar_pb_justificado", spy)
    return calls


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.fixture(autouse=True)
def sem_rede(monkeypatch):
    def negar(*args, **kwargs):
        pytest.fail("MCP tentou acessar rede no ensaio offline")

    monkeypatch.setattr(socket, "create_connection", negar)
    monkeypatch.setattr(socket, "getaddrinfo", negar)
    monkeypatch.setattr(socket.socket, "connect", negar)
    monkeypatch.setattr(socket.socket, "connect_ex", negar)
    monkeypatch.setattr(sys, "dont_write_bytecode", True)


@pytest.fixture
async def client():
    async with Client(server.build_server(), raise_exceptions=True) as c:
        yield c


@pytest.mark.anyio
async def test_whitelist_schemas_e_capabilities(client):
    listed = await client.list_tools()
    assert {t.name for t in listed.tools} == set(server.TECNICAS)
    for tool in listed.tools:
        assert tool.input_schema["type"] == "object"
        assert tool.input_schema["additionalProperties"] is False
        assert tool.output_schema["additionalProperties"] is False
        assert tool.annotations.read_only_hint is True
        assert tool.annotations.open_world_hint is False
        Draft202012Validator.check_schema(tool.input_schema)
        Draft202012Validator.check_schema(tool.output_schema)
        for model in tool.input_schema.get("$defs", {}).values():
            if model.get("type") == "object":
                assert model["additionalProperties"] is False


@pytest.mark.anyio
@pytest.mark.parametrize("name,arguments", [
    ("calcular_ke", KE), ("avaliar_pb_justificado", PB), ("estimar_preenchimento", FILL),
])
async def test_delegates_e_saida_schema(client, name, arguments):
    result = await client.call_tool(name, arguments)
    data = result.structured_content
    assert not result.is_error
    assert json.loads(result.content[0].text) == data
    tools = await client.list_tools()
    Draft202012Validator(next(t.output_schema for t in tools.tools if t.name == name)).validate(data)
    got = data["resultado"]
    if name == "calcular_ke":
        assert got["custo"]["valor"] == calcular_ke(**arguments)
    elif name == "avaliar_pb_justificado":
        expected = avaliar_pb_justificado(0.15, 0.1, 0.02)
        assert got["forma"] == list(expected.shape)
        np.testing.assert_array_equal(got["valores"], expected.reshape(-1))
    else:
        assert got["acoes"] == estimar_preenchimento(**arguments)


@pytest.mark.anyio
@pytest.mark.parametrize("name", ["publish", "weekly_decide", "kill_switch", "shell", "estado", "x"])
async def test_unknown_e_writers_nunca_delegam(client, monkeypatch, name):
    def negar(*a, **kw):
        pytest.fail("Nome desconhecido alcançou delegate")

    monkeypatch.setattr(server, "calcular_ke", negar)
    result = await client.call_tool(name, KE)
    assert result.is_error
    assert result.structured_content["resultado"]["codigo"] == "TECNICA_DESCONHECIDA"


@pytest.mark.anyio
@pytest.mark.parametrize("field", list(KE))
@pytest.mark.parametrize("value", [True, "0.1", None, float("nan"), float("inf")])
async def test_numero_invalido_nao_chega_delegate(client, monkeypatch, field, value):
    def negar(*a, **kw):
        pytest.fail("Entrada inválida alcançou delegate")

    monkeypatch.setattr(server, "calcular_ke", negar)
    result = await client.call_tool("calcular_ke", {**KE, field: value})
    assert result.is_error
    assert result.structured_content["resultado"]["codigo"] == "ENTRADA_INVALIDA"


@pytest.mark.anyio
@pytest.mark.parametrize("arguments", [None, {}, {**KE, "writer": True}])
async def test_ausencia_e_extra(client, arguments):
    assert (await client.call_tool("calcular_ke", arguments)).is_error


@pytest.mark.anyio
@pytest.mark.parametrize("order", [True, 7.0, "7", None, 2**53])
async def test_quantidade_inteira_estrita(client, order):
    assert (await client.call_tool("estimar_preenchimento", {**FILL, "ordem_acoes": order})).is_error


@pytest.mark.anyio
@pytest.mark.parametrize("order", [0, 7, -7])
@pytest.mark.parametrize("value", [None, True, float("nan"), float("inf")])
async def test_operando_ausente_recusado_inclusive_zero(client, order, value):
    for field in ("capacidade_usd", "preco_usd"):
        args = {**FILL, "ordem_acoes": order, field: value}
        assert (await client.call_tool("estimar_preenchimento", args)).is_error


@pytest.mark.anyio
@pytest.mark.parametrize("order,cap,price", [(7, 0.0, 3.0), (-7, -1.0, 3.0), (7, 15.0, 0.0)])
async def test_nao_positivos_conservam_nativo(client, order, cap, price):
    args = {"ordem_acoes": order, "capacidade_usd": cap, "preco_usd": price}
    result = await client.call_tool("estimar_preenchimento", args)
    assert not result.is_error
    assert result.structured_content["resultado"]["acoes"] == estimar_preenchimento(**args)


@pytest.mark.anyio
async def test_pb_broadcast_nan_estrito_e_operandos(client):
    args = {"roe": {"tipo": "array", "forma": [2, 1], "valores": [0.15, 0.20]},
            "ke": {"tipo": "array", "forma": [2], "valores": [0.1, 0.03]},
            "g": {"tipo": "array", "forma": [2], "valores": [0.02, 0.03]}, "estrito": False}
    before = json.dumps(args, sort_keys=True)
    result = await client.call_tool("avaliar_pb_justificado", args)
    got = result.structured_content["resultado"]
    expected = avaliar_pb_justificado(np.array([[0.15], [0.20]]), np.array([0.1, 0.03]),
                                      np.array([0.02, 0.03]), estrito=False)
    assert got["forma"] == list(expected.shape)
    np.testing.assert_array_equal([v if v is not None else np.nan for v in got["valores"]],
                                  expected.reshape(-1))
    assert got["estados"] == ["finito" if np.isfinite(v) else "nan" for v in expected.reshape(-1)]
    assert json.dumps(args, sort_keys=True) == before
    refused = await client.call_tool("avaliar_pb_justificado", {**args, "estrito": True})
    assert refused.is_error and refused.structured_content["resultado"]["codigo"] == "KERNEL_RECUSOU"


@pytest.mark.anyio
@pytest.mark.parametrize("field", ["roe", "ke", "g"])
@pytest.mark.parametrize("estrito", [True, False])
async def test_pb_ausencia_declarada_nao_vira_zero(client, monkeypatch, field, estrito):
    calls = capturar_pb(monkeypatch)
    result = await client.call_tool("avaliar_pb_justificado", {
        **PB, field: {"tipo": "ausente"}, "estrito": estrito})
    native = [np.nan if key == field else PB[key]["valor"] for key in ("roe", "ke", "g")]
    assert len(calls) == 1 and calls[0][1] is estrito
    for received, expected_operand in zip(calls[0][0], native, strict=True):
        np.testing.assert_array_equal(received, expected_operand)
    if estrito and field in ("ke", "g"):
        with pytest.raises(ValueError):
            avaliar_pb_justificado(*native, estrito=estrito)
        assert result.is_error
        assert result.structured_content["resultado"]["codigo"] == "KERNEL_RECUSOU"
        return
    expected = avaliar_pb_justificado(*native, estrito=estrito)
    assert np.isnan(expected).all()
    assert result.structured_content["resultado"]["valores"] == [None]
    assert result.structured_content["resultado"]["estados"] == ["nan"]


@pytest.mark.anyio
@pytest.mark.parametrize("field", ["roe", "ke", "g"])
@pytest.mark.parametrize("estrito", [True, False])
async def test_pb_celula_ausente_broadcast_nativo(client, monkeypatch, field, estrito):
    calls = capturar_pb(monkeypatch)
    args = {**PB, field: {"tipo": "array", "forma": [2],
                          "valores": [0.04, {"tipo": "ausente"}]}, "estrito": estrito}
    result = await client.call_tool("avaliar_pb_justificado", args)
    native = [np.array([0.04, np.nan]) if key == field else args[key]["valor"]
              for key in ("roe", "ke", "g")]
    assert len(calls) == 1 and calls[0][1] is estrito
    for received, expected_operand in zip(calls[0][0], native, strict=True):
        np.testing.assert_array_equal(received, expected_operand)
    if estrito and field in ("ke", "g"):
        with pytest.raises(ValueError):
            avaliar_pb_justificado(*native, estrito=estrito)
        assert result.is_error
        assert result.structured_content["resultado"]["codigo"] == "KERNEL_RECUSOU"
        return
    expected = avaliar_pb_justificado(*native, estrito=estrito)
    got = result.structured_content["resultado"]
    assert got["forma"] == list(expected.shape)
    np.testing.assert_array_equal([v if v is not None else np.nan for v in got["valores"]], expected)
    assert got["estados"][-1] == "nan"


@pytest.mark.anyio
@pytest.mark.parametrize("field", ["roe", "ke", "g"])
@pytest.mark.parametrize("operand", [
    {"tipo": "escalar", "valor": True}, {"tipo": "escalar", "valor": float("nan")},
    {"tipo": "escalar", "valor": float("inf")}, {"tipo": "escalar", "valor": None},
    {"tipo": "escalar", "valor": 0.1, "extra": 0},
    {"tipo": "ausente", "valor": None}, {"tipo": "ausente", "extra": float("nan")},
    {"tipo": "array", "forma": [1], "valores": [float("nan")]},
    {"tipo": "array", "forma": [1], "valores": [float("inf")]},
    {"tipo": "array", "forma": [1], "valores": [None]},
    {"tipo": "array", "forma": [1], "valores": [True]},
    {"tipo": "array", "forma": [1], "valores": [{"tipo": "ausente", "extra": 0}]},
    {"tipo": "array", "forma": [2], "valores": [0.1]},
    {"tipo": "array", "forma": [0], "valores": []},
    {"tipo": "array", "forma": [True], "valores": [0.1]},
    {"tipo": "array", "forma": [129], "valores": [0.1]},
])
async def test_pb_recusas_aninhadas(client, monkeypatch, field, operand):
    monkeypatch.setattr(server, "avaliar_pb_justificado",
                        lambda *a, **kw: pytest.fail("Operando inválido alcançou PB"))
    assert (await client.call_tool("avaliar_pb_justificado", {**PB, field: operand})).is_error


@pytest.mark.anyio
@pytest.mark.parametrize("name,arguments", [
    ("calcular_ke", {**KE, "rf": float("nan")}),
    ("calcular_ke", {**KE, "beta": True}),
    ("calcular_ke", {**KE, "extra": 0}),
    ("avaliar_pb_justificado", {**PB, "roe": escalar(float("nan"))}),
    ("avaliar_pb_justificado", {**PB, "ke": escalar(float("inf"))}),
    ("avaliar_pb_justificado", {**PB, "g": escalar(True)}),
    ("avaliar_pb_justificado", {**PB, "extra": 0}),
    ("avaliar_pb_justificado", {**PB, "g": {"tipo": "array", "forma": [1],
                                           "valores": [float("nan")]}}),
    ("estimar_preenchimento", {**FILL, "ordem_acoes": True}),
    ("estimar_preenchimento", {**FILL, "preco_usd": float("nan")}),
    ("estimar_preenchimento", {**FILL, "extra": 0}),
])
async def test_handler_raw_recusa_antes_delegate(monkeypatch, name, arguments):
    def negar(*a, **kw):
        pytest.fail("Raw inválido alcançou delegate")

    for delegate in ("calcular_ke", "avaliar_pb_justificado", "estimar_preenchimento"):
        monkeypatch.setattr(server, delegate, negar)
    params = CallToolRequestParams(name=name, arguments=arguments)
    result = await server._chamar(None, params)
    assert result.is_error
    assert result.structured_content["resultado"]["codigo"] == "ENTRADA_INVALIDA"


def test_pb_limite_antes_alocacao_e_saida_strict():
    args = {**PB, "roe": {"tipo": "array", "forma": [128, 1], "valores": [0.1] * 128},
            "ke": {"tipo": "array", "forma": [1, 128], "valores": [0.2] * 128}}
    with pytest.raises(ValidationError, match="Broadcast excede"):
        EntradaPB.model_validate(args, strict=True)
    invalid = SaidaKE.model_construct(versao_motor="teste", resultado=SucessoKE.model_construct(
        custo=NumeroObservado.model_construct(valor=float("inf"), estado="finito")))
    with pytest.raises(ValidationError):
        server._resposta(invalid)


@pytest.mark.anyio
async def test_saida_nao_finita_e_json_legal(client, monkeypatch):
    monkeypatch.setattr(server, "calcular_ke", lambda **kw: float("inf"))
    result = await client.call_tool("calcular_ke", KE)
    assert result.structured_content["resultado"]["custo"] == {
        "valor": None, "estado": "mais_infinito"}
    json.loads(result.content[0].text, parse_constant=lambda x: pytest.fail(x))


@pytest.mark.anyio
async def test_recursos_exemplo_corpos_e_hashes(client):
    from cdp.tecnicas.recursos import carregar_exemplo

    expected = carregar_exemplo("latam_simulado_v1")
    listed = await client.list_resources()
    assert {str(r.uri) for r in listed.resources} == {server.CATALOGO_URI, *server.RECURSOS}
    for uri, name in server.RECURSOS.items():
        result = await client.read_resource(uri)
        data = json.loads(result.contents[0].text)
        assert data["aviso"] == "DADOS SIMULADOS" and data["origem"] == "EXEMPLO"
        body = data["conteudo_utf8"].encode()
        assert hashlib.sha256(body).hexdigest() == data["sha256"]
        if name != "manifesto":
            assert body == expected.arquivos.corpos[name]
    catalogue = json.loads((await client.read_resource(server.CATALOGO_URI)).contents[0].text)
    assert {x["nome"] for x in catalogue["tecnicas"]} == set(server.TECNICAS)


@pytest.mark.anyio
@pytest.mark.parametrize("uri", ["file:///etc/passwd", "https://example.com", server.EXEMPLO_URI + "../x",
                                   server.CATALOGO_URI + "?x=1", server.EXEMPLO_URI + "%66und.yaml"])
async def test_uri_fechado(client, uri):
    with pytest.raises(MCPError):
        await client.read_resource(uri)


@pytest.mark.anyio
async def test_cwd_vazio_sem_writes_ou_processos(client, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    real_open, real_io, real_os = builtins.open, io.open, os.open

    def open_ro(file, mode="r", *a, **kw):
        if any(c in mode for c in "wax+"):
            pytest.fail("Gravação por open")
        return real_open(file, mode, *a, **kw)

    def io_ro(file, mode="r", *a, **kw):
        if any(c in mode for c in "wax+"):
            pytest.fail("Gravação por io.open")
        return real_io(file, mode, *a, **kw)

    def os_ro(file, flags, *a, **kw):
        if flags & (os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_TRUNC | os.O_APPEND):
            pytest.fail("Gravação por os.open")
        return real_os(file, flags, *a, **kw)

    def deny(*a, **kw):
        pytest.fail("Mutação/processo fora da superfície de leitura")

    with monkeypatch.context() as m:
        m.setattr(builtins, "open", open_ro)
        m.setattr(io, "open", io_ro)
        m.setattr(os, "open", os_ro)
        for name in ("mkdir", "remove", "unlink", "rename", "replace", "rmdir"):
            m.setattr(os, name, deny)
        m.setattr(subprocess, "Popen", deny)
        m.setattr(subprocess, "run", deny)
        assert not (await client.call_tool("calcular_ke", KE)).is_error
        assert not (await client.call_tool("avaliar_pb_justificado", PB)).is_error
        assert not (await client.call_tool("estimar_preenchimento", FILL)).is_error
        for uri in (server.CATALOGO_URI, *server.RECURSOS):
            await client.read_resource(uri)
    assert not list(tmp_path.iterdir())


@pytest.mark.anyio
async def test_stdio_instalado_offline_cwd_vazio(tmp_path):
    guard = tmp_path / "guard"
    guard.mkdir()
    (guard / "sitecustomize.py").write_text('''import os, sys
def audit(event, args):
    if event in ("socket.connect", "socket.getaddrinfo", "subprocess.Popen", "os.mkdir",
                 "os.remove", "os.rename", "os.rmdir"):
        raise RuntimeError("MCP readonly guard: " + event)
    if event == "open":
        path, mode, flags = args
        if isinstance(path, (str, bytes)) and path != os.devnull:
            if (isinstance(mode, str) and any(x in mode for x in "wax+")) or flags & (
                os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_TRUNC | os.O_APPEND):
                raise RuntimeError("MCP readonly guard: write")
sys.addaudithook(audit)
''')
    cwd = tmp_path / "empty"
    cwd.mkdir()
    executable = Path(sys.executable).with_name("cdp-tecnicas-mcp")
    assert executable.is_file()
    params = StdioServerParameters(command=str(executable), args=[], cwd=str(cwd),
                                   env={"PYTHONPATH": str(guard), "PYTHONDONTWRITEBYTECODE": "1"})
    async with Client(params, raise_exceptions=True) as remote:
        assert {t.name for t in (await remote.list_tools()).tools} == set(server.TECNICAS)
        result = await remote.call_tool("calcular_ke", KE)
        assert result.structured_content["resultado"]["custo"]["valor"] == calcular_ke(**KE)
        assert (await remote.call_tool("shell", {})).is_error
        data = json.loads((await remote.read_resource(server.EXEMPLO_URI + "fund.yaml")).contents[0].text)
        assert data["aviso"] == "DADOS SIMULADOS"
    assert not list(cwd.iterdir())


def test_entrada_sem_sdk_nao_instala(monkeypatch, capsys):
    from cdp.mcp_readonly.__main__ import main

    original = builtins.__import__

    def missing(name, *a, **kw):
        if name == "mcp.server.stdio":
            raise ModuleNotFoundError("ausente", name="mcp")
        return original(name, *a, **kw)

    monkeypatch.setattr(builtins, "__import__", missing)
    assert main() == 2
    out = capsys.readouterr()
    assert not out.out and "extra mcp" in out.err


@pytest.mark.anyio
@pytest.mark.parametrize("ordem_acoes", [7, -7])
async def test_overflow_finito_preenchimento_envelope_e_recuperacao(
    client, monkeypatch, capsys, caplog, ordem_acoes,
):
    """DADOS SIMULADOS: razão extrema finita recusa sem encerrar o Client."""
    calls = []
    original = server.estimar_preenchimento

    def spy(**arguments):
        calls.append(dict(arguments))
        return original(**arguments)

    monkeypatch.setattr(server, "estimar_preenchimento", spy)
    extreme = {"ordem_acoes": ordem_acoes, "capacidade_usd": 1e308, "preco_usd": 1e-308}
    refused = await client.call_tool("estimar_preenchimento", extreme)
    assert calls == [extreme]
    assert refused.is_error
    data = refused.structured_content
    assert data["resultado"] == {
        "tipo": "erro", "codigo": "KERNEL_RECUSOU",
        "mensagem": "Pré-condição do kernel recusada",
    }
    text = refused.content[0].text
    assert json.loads(text, parse_constant=lambda value: pytest.fail(value)) == data
    tools = await client.list_tools()
    schema = next(t.output_schema for t in tools.tools if t.name == "estimar_preenchimento")
    Draft202012Validator(schema).validate(data)
    for detail in ("Traceback", "OverflowError", str(Path(__file__)), "1e+308", "1e-308"):
        assert detail not in text

    accepted = await client.call_tool("estimar_preenchimento", FILL)
    assert not accepted.is_error
    assert accepted.structured_content["resultado"]["acoes"] == estimar_preenchimento(**FILL)
    assert calls == [extreme, FILL]
    captured = capsys.readouterr()
    assert "Traceback" not in captured.out + captured.err
    assert all(record.exc_info is None for record in caplog.records)
