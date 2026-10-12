"""Qualificação instalada: recursos, três kernels e nove consultas STDIO em corpus privado.

Executar com o Python instalado e -I, fora do clone. A receita recebida é exclusivamente
DADOS SIMULADOS; não é parte do wheel, não estima modelos nem autoriza operação.
"""
from __future__ import annotations

import argparse
import asyncio
import hashlib
import importlib.metadata
import importlib.util
import json
import os
import sys
from pathlib import Path


def sha(body: bytes) -> str:
    return hashlib.sha256(body).hexdigest()


def gravar(path: Path, value) -> None:
    with path.open("x", encoding="utf-8") as file:
        json.dump(value, file, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False)
        file.write("\n")


def inventario(root: Path) -> dict:
    return {p.relative_to(root).as_posix(): sha(p.read_bytes())
            for p in sorted(root.rglob("*")) if p.is_file()}


def categorias_nao_finitas(value) -> set[str]:
    """Percorre somente a representação JSON recebida, sem reconstruir valores."""
    if type(value) is dict:
        own = {value["categoria"]} if value.get("tipo") == "float" and value.get("categoria") in {"nan", "mais_infinito", "menos_infinito"} else set()
        return own.union(*(categorias_nao_finitas(x) for x in value.values()))
    if type(value) is list:
        return set().union(*(categorias_nao_finitas(x) for x in value))
    return set()


def codigo_instalado(source: Path) -> dict:
    import cdp

    prefix = Path(sys.prefix).resolve()
    installed = Path(cdp.__file__).resolve().parent
    if not installed.is_relative_to(prefix) or "site-packages" not in installed.parts:
        raise ValueError("CDP deve ser instalado, sem editable ou origem no clone")
    if installed.is_relative_to(source) or any(Path(p).resolve() == source / "src" for p in sys.path):
        raise ValueError("Fonte do clone entrou no runtime instalado")
    if importlib.metadata.version("fechamento") != cdp.__version__:
        raise ValueError("Versão instalada diverge do pacote recebido")
    if importlib.metadata.version("mcp") != "2.3.0":
        raise ValueError("SDK MCP recebido deve ser 2.3.0")
    expected = {p.relative_to(source / "src/cdp").as_posix(): sha(p.read_bytes())
                for p in sorted((source / "src/cdp").rglob("*"))
                if p.is_file() and "__pycache__" not in p.parts}
    actual = {p.relative_to(installed).as_posix(): sha(p.read_bytes())
              for p in sorted(installed.rglob("*"))
              if p.is_file() and "__pycache__" not in p.parts}
    if expected != actual:
        raise ValueError("Payload CDP instalado diferente da fonte literal recebida")
    for name in ("painel_template.html", "painel_cobertura.js", "painel_modelo.js",
                 "dashboard_cases.js", "dashboard_cases.css"):
        if "workflow/" + name not in actual:
            raise ValueError("Asset nativo ausente do wheel: " + name)
    dist = importlib.metadata.distribution("fechamento")
    record = dist.read_text("RECORD")
    if not record:
        raise ValueError("Instalação sem RECORD")
    direct = dist.read_text("direct_url.json")
    if direct and json.loads(direct).get("dir_info", {}).get("editable"):
        raise ValueError("Instalação editable recusada")
    return {"versao": cdp.__version__, "sdk": "2.3.0", "prefix": str(prefix),
            "cdp_path": str(installed), "payload": actual, "record_sha256": sha(record.encode())}


def importar_receita(path: Path):
    spec = importlib.util.spec_from_file_location("fixture_instalada_privada", path)
    if spec is None or spec.loader is None:
        raise ValueError("Receita física ausente")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


async def qualificar_kernels(area: Path, empty: Path, env: dict) -> None:
    import numpy as np
    from mcp import Client, StdioServerParameters

    from cdp.mcp_readonly import server
    from cdp.tecnicas import avaliar_pb_justificado, calcular_ke, estimar_preenchimento

    executable = Path(sys.executable).with_name("cdp-tecnicas-mcp")
    args = {
        "calcular_ke": {"rf": 0.01, "beta": 1.0, "erp": 0.05, "lam": 1.0, "crp": 0.02},
        "avaliar_pb_justificado": {"roe": {"tipo": "escalar", "valor": 0.15},
                                  "ke": {"tipo": "escalar", "valor": 0.1},
                                  "g": {"tipo": "escalar", "valor": 0.02}},
        "estimar_preenchimento": {"ordem_acoes": -7, "capacidade_usd": 15.0, "preco_usd": 3.0},
    }
    params = StdioServerParameters(command=str(executable), args=[], cwd=str(empty), env=env)
    async with Client(params, raise_exceptions=True) as client:
        names = {t.name for t in (await client.list_tools()).tools}
        if names != set(args):
            raise ValueError("Catálogo STDIO dos kernels divergente")
        for name, arguments in args.items():
            result = await client.call_tool(name, arguments)
            payload = result.structured_content
            gravar(area / (name + ".json"), {"ingresso": arguments, "is_error": result.is_error,
                                            "resposta": payload})
            if result.is_error:
                raise ValueError("Kernel positivo recusado: " + name)
            value = payload["resultado"]
            if name == "calcular_ke":
                assert value["custo"]["valor"] == calcular_ke(**arguments)
            elif name == "avaliar_pb_justificado":
                assert value["valores"] == np.asarray(avaliar_pb_justificado(0.15, 0.1, 0.02)).reshape(-1).tolist()
            else:
                assert value["acoes"] == estimar_preenchimento(**arguments)
        resources = (await client.list_resources()).resources
        assert len(resources) == 11
        for i, resource in enumerate(resources):
            result = await client.read_resource(resource.uri)
            text = result.contents[0].text
            gravar(area / f"recurso-{i:02d}.json", {"uri": str(resource.uri),
                                                  "corpo": text, "sha256": sha(text.encode())})
        assert set(str(r.uri) for r in resources) == {server.CATALOGO_URI, *server.RECURSOS}
        for label, name, arguments in (
            ("unknown", "shell", {}),
            ("bool", "calcular_ke", {**args["calcular_ke"], "beta": True}),
            ("nonfinite", "calcular_ke", {**args["calcular_ke"], "erp": 1e308, "beta": 1e308}),
        ):
            result = await client.call_tool(name, arguments)
            gravar(area / ("controle-" + label + ".json"), {"is_error": result.is_error,
                                                          "resposta": result.structured_content})
            if label == "nonfinite":
                assert not result.is_error
                assert result.structured_content["resultado"]["custo"] == {"estado": "mais_infinito", "valor": None}
            else:
                assert result.is_error
        assert not (await client.call_tool("calcular_ke", args["calcular_ke"])).is_error


async def qualificar_operacional(area: Path, empty: Path, env: dict, corpus: dict) -> None:
    from mcp import Client, StdioServerParameters

    from cdp.workflow.leitura import LeitorOperacional, receber_contexto_leitura
    from cdp.workflow.leitura_serializacao import serializar_resposta, validar_json_resposta

    context_path = corpus["contexto"]
    baseline = inventario(context_path.parent)
    reader = LeitorOperacional(receber_contexto_leitura(context_path))
    expected = {}
    for name, arguments in corpus["ingressos"].items():
        payload = serializar_resposta(reader.consultar(name, arguments))
        gravar(area / ("nativo-" + name + ".json"), payload)
        assert payload["status"] == "disponivel"
        assert payload["autoridade_operacional"] is False
        assert payload["readset"]
        expected[name] = payload
    executable = Path(sys.executable).with_name("cdp-mcp-operacional")
    params = StdioServerParameters(command=str(executable), args=["--contexto", str(context_path)],
                                  cwd=str(empty), env=env)
    async with Client(params, raise_exceptions=True) as client:
        assert {t.name for t in (await client.list_tools()).tools} == set(expected)
        for name, arguments in corpus["ingressos"].items():
            result = await client.call_tool(name, arguments)
            payload = validar_json_resposta(result.structured_content)
            gravar(area / ("stdio-" + name + ".json"), {"ingresso": arguments, "resposta": payload,
                                                       "is_error": result.is_error})
            assert not result.is_error
            for field in ("status", "resultado", "resultado_sha256", "autoridade_operacional"):
                assert payload[field] == expected[name][field]
            if name == "ler_modelo_cobertura":
                assert categorias_nao_finitas(payload["resultado"]) == {"nan", "mais_infinito", "menos_infinito"}
            native_refs = {(r["membro_id"], r["sha256"], r["bytes"]) for r in expected[name]["readset"]}
            assert {(r["membro_id"], r["sha256"], r["bytes"]) for r in payload["readset"]} == native_refs
        for label, name, changes, status in (
            ("ausencia", "ler_modelo_cobertura", {"instrumento_id": "AUSENTE"}, "indisponivel"),
            ("autoria", "validar_documento", {"mente_esperada": "outro"}, "recusado"),
        ):
            arguments = {**corpus["ingressos"][name], **changes}
            result = await client.call_tool(name, arguments)
            payload = validar_json_resposta(result.structured_content)
            gravar(area / ("controle-" + label + ".json"), {"ingresso": arguments,
                                                          "resposta": payload, "is_error": result.is_error})
            assert result.is_error and payload["status"] == status
        result = await client.call_tool("ler_modelo_cobertura", corpus["ingressos"]["ler_modelo_cobertura"])
        assert not result.is_error
    assert inventario(context_path.parent) == baseline, "Consulta modificou corpus recebido"
    assert not list(empty.iterdir()), "STDIO modificou cwd vazio"
    gravar(area / "CORPUS_APOS.json", baseline)
    # Controle causal em input TESTE privado: o corpo mudou sem alterar seu manifesto.
    # Não se restaura nem reaproveita esse contexto; o recibo registra o negativo terminal.
    source = corpus["roots"]["livro"] / "cobertura/2026-10-08/modelos/SIM001.json"
    raw = source.read_bytes()
    async with Client(params, raise_exceptions=True) as client:
        # Inicialização recebe o contexto íntegro; a alteração acontece depois no controle.
        source.write_bytes(raw + b"\n")
        gravar(area / "TAMPER_PREPARADO.json", {"path": str(source), "antes": sha(raw),
                                              "depois": sha(source.read_bytes()), "aviso": "DADOS SIMULADOS"})
        name = "ler_modelo_cobertura"
        result = await client.call_tool(name, corpus["ingressos"][name])
        payload = validar_json_resposta(result.structured_content)
        gravar(area / "controle-tamper.json", {"is_error": result.is_error, "resposta": payload})
        assert result.is_error and payload["status"] == "recusado"


def main() -> int:
    sys.dont_write_bytecode = True
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fonte", type=Path, required=True)
    parser.add_argument("--saida", type=Path, required=True)
    args = parser.parse_args()
    if not sys.flags.isolated or not args.fonte.is_absolute() or not args.saida.is_absolute():
        raise ValueError("Use Python -I e caminhos absolutos recebidos")
    args.fonte = args.fonte.resolve(strict=True)
    args.saida = args.saida.resolve()
    if args.saida.exists() or args.saida.is_relative_to(args.fonte):
        raise ValueError("Saída nova fora do clone é obrigatória")
    args.saida.mkdir(parents=True)
    empty = args.saida / "cwd-vazio"
    empty.mkdir()
    os.chdir(empty)
    env = {k: v for k, v in os.environ.items() if k not in {"PYTHONPATH", "CDP_EXECUTOR", "CDP_HARNESS"}}
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    for key in ("TMPDIR", "TEMP", "TMP"):
        temp = args.saida / "tmp"
        temp.mkdir(exist_ok=True)
        env[key] = str(temp)
    payload = codigo_instalado(args.fonte)
    gravar(args.saida / "INSTALACAO.json", payload)
    recipe_path = args.fonte / "tests/cdp/fixture_leitura_operacional.py"
    gravar(args.saida / "RECEITA.json", {"path": str(recipe_path), "sha256": sha(recipe_path.read_bytes()),
                                       "aviso": "DADOS SIMULADOS; sem autoridade operacional/PIT"})
    recipe = importar_receita(recipe_path)
    corpus = recipe.criar_corpus(args.saida / "corpus", args.fonte / "configs/cdp",
                                args.fonte / "configs/cdp/fund.yaml")
    kernels, operational = args.saida / "kernels", args.saida / "nove"
    kernels.mkdir()
    operational.mkdir()
    asyncio.run(qualificar_kernels(kernels, empty, env))
    asyncio.run(qualificar_operacional(operational, empty, env, corpus))
    gravar(args.saida / "POSITIVO.json", {"kernels": 3, "recursos": 11, "consultas": 9,
                                         "aviso": "DADOS SIMULADOS", "instalacao": payload["versao"],
                                         "limites": "Qualifica esta instalação/corpus; não é autoridade financeira ou prova OS de ausência de rede."})
    print(json.dumps({"estado": "POSITIVO", "saida": str(args.saida)}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
