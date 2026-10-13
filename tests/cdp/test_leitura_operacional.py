"""Nove delegates nativos, offline, sem efeitos; corpus TESTE DADOS SIMULADOS."""

from __future__ import annotations

import hashlib
import json
import os
import socket
from datetime import datetime, tzinfo
from decimal import Decimal
from pathlib import Path

import numpy as np
import pandas as pd
import pytest
from fixture_leitura_operacional import AGORA, CORTE, DATA, criar_corpus

from cdp.leitura_arquivos import ativar_receptor, ler_texto
from cdp.workflow.leitura import LeitorOperacional, receber_contexto_leitura
from cdp.workflow.leitura_contratos import (
    ContextoLeituraInvalido,
    FerramentaLeitura,
    FonteLeituraIndisponivel,
    IngressoLeituraInvalido,
    TentativaDeEfeitoLeitura,
)
from cdp.workflow.leitura_serializacao import (
    hash_resultado,
    serializar_resposta,
    serializar_valor,
    validar_json_resposta,
    validar_schema_exato,
)

SOURCE = Path(__file__).resolve().parents[2]
CONFIGS = SOURCE / "configs/cdp"
LEGADO = Path(__file__).parent / "fixtures/fund_legado.yaml"


def guardar_corpo(nome, corpus, ingresso, response):
    """Evidência da emissão única deste focal; pasta privada explícita no comando."""
    raw = os.environ.get("CDP_LEITURA_CORPUS_OUTPUT")
    if raw is None:
        return
    output = Path(raw)
    if not output.is_absolute():
        raise ValueError("Saída de evidência exige path absoluto")
    output.mkdir(parents=True, exist_ok=True)
    emitted = serializar_resposta(response)
    record = {
        "aviso": "DADOS SIMULADOS — emissão de teste, sem autoridade/PIT",
        "origem_contexto": str(corpus["contexto"]),
        "contexto_corpo": corpus["contexto"].read_text(encoding="utf-8"),
        "ingresso": ingresso,
        "resposta": emitted,
    }
    body = json.dumps(record, ensure_ascii=False, sort_keys=True, allow_nan=False, indent=2) + "\n"
    with (output / (nome + ".json")).open("x", encoding="utf-8") as f:
        f.write(body)


def snapshot(root):
    """M6/SHA e nomes de diretórios, com atime explicitamente fora da comparação."""
    result = {}
    for p in sorted(root.rglob("*")):
        st = p.lstat()
        result[p.relative_to(root).as_posix()] = (
            st.st_dev,
            st.st_ino,
            st.st_size,
            st.st_mtime_ns,
            st.st_ctime_ns,
            st.st_mode,
            st.st_nlink,
            hashlib.sha256(p.read_bytes()).hexdigest() if p.is_file() else None,
        )
    return result


@pytest.fixture()
def corpus(tmp_path):
    return criar_corpus(tmp_path / "corpus", CONFIGS, LEGADO)


@pytest.mark.parametrize("tool", [x.value for x in FerramentaLeitura])
def test_nove_positivos_nativos_readset_integral_zero_efeito(corpus, tool, monkeypatch):
    ctx = receber_contexto_leitura(corpus["contexto"])
    reader = LeitorOperacional(ctx)
    before = snapshot(corpus["contexto"].parent)

    def denied(*a, **kw):
        raise AssertionError("Rede não autorizada")

    monkeypatch.setattr(socket.socket, "connect", denied)
    response = reader.consultar(tool, corpus["ingressos"][tool])
    guardar_corpo(tool, corpus, corpus["ingressos"][tool], response)
    assert response.status == "disponivel", response.falha
    assert response.autoridade_operacional is False
    assert response.resultado_sha256 == hash_resultado(response.resultado)
    emitted = serializar_resposta(response)
    assert validar_json_resposta(emitted) == emitted
    assert emitted["ferramenta"] == tool
    assert response.readset and len({r.membro_id for r in response.readset}) == len(
        response.readset
    )
    for r in response.readset:
        p = corpus["roots"][r.raiz_id] / r.path_relativo
        assert hashlib.sha256(p.read_bytes()).hexdigest() == r.sha256
    assert snapshot(corpus["contexto"].parent) == before


def test_paridade_integral_estado_agenda_factbook_track_risco_cobertura_pacote(corpus):
    from cdp.cobertura.livro import ultimo_snapshot
    from cdp.estado import estado
    from cdp.risk.analytics import risk_decomposition
    from cdp.workflow.agenda import agenda
    from cdp.workflow.pacote import construir_pacote, render_pacote
    from cdp.workflow.risco_diario import load, restore

    ctx = receber_contexto_leitura(corpus["contexto"])
    rt = ctx.runtime
    reader = LeitorOperacional(ctx)

    def native(tool):
        with ativar_receptor(ctx.receptor()):
            if tool == "consultar_estado":
                return estado(
                    rt,
                    raiz=corpus["roots"]["repositorio"],
                    agora=rt.now(),
                    rapido=True,
                    rede=False,
                    rot=ctx.rotinas,
                    env={"CDP_HARNESS": "codex"},
                )
            if tool == "consultar_agenda":
                return agenda(rt, now=rt.now())
            if tool == "verificar_integridade":
                return rt.track().verify()
            if tool == "ler_fatos":
                return corpus["factbook"]
            if tool == "ler_carteira":
                return rt.track().get(DATA)
            if tool == "decompor_risco_operacional":
                obj = load(rt.track(), rt.track().get(DATA))
                return risk_decomposition(
                    pd.Series(obj["weights"], dtype=float), restore(obj["models"]["base"])
                )
            if tool == "ler_modelo_cobertura":
                return ultimo_snapshot(
                    rt.book_root,
                    DATA,
                    conhecimento_ate=datetime.fromisoformat(CORTE.replace("Z", "+00:00")),
                ).modelo("SIM001")
            if tool == "ler_pacote_mente":
                p = construir_pacote(rt, "comentario-diario", data=DATA, mente="codex")
                return p, render_pacote(p, gerado_em=AGORA)
        raise AssertionError(tool)

    for tool in corpus["ingressos"]:
        if tool == "validar_documento":
            continue
        actual = reader.consultar(tool, corpus["ingressos"][tool])
        assert actual.resultado == serializar_valor(native(tool)), tool


def test_documento_negativo_legitimo_sem_template_nem_preparacao(corpus):
    raw = json.loads(corpus["contexto"].read_text())
    doc = corpus["roots"]["rascunhos"] / "comentario.json"
    obj = json.loads(doc.read_text())
    obj["headline"] = "Número livre 123456"
    doc.write_text(json.dumps(obj), encoding="utf-8")
    h = hashlib.sha256(doc.read_bytes()).hexdigest()
    mid = next(iter(raw["documentos"].values()))
    raw["documentos"] = {h: mid}
    raw["membros"][mid]["sha256"] = h
    corpus["contexto"].write_text(json.dumps(raw), encoding="utf-8")
    ctx = receber_contexto_leitura(corpus["contexto"])
    a = {
        **corpus["ingressos"]["validar_documento"],
        "contexto_sha256": ctx.sha256,
        "documento_sha256": h,
    }
    before = snapshot(corpus["contexto"].parent)
    r = LeitorOperacional(ctx).consultar("validar_documento", a)
    assert r.status == "disponivel" and r.semantica == "negativa_pelo_delegate"
    assert r.resultado["tipo"] == "dict"
    assert snapshot(corpus["contexto"].parent) == before


def test_ausencia_real_indisponivel_sem_zero(corpus):
    ctx = receber_contexto_leitura(corpus["contexto"])
    a = {**corpus["ingressos"]["ler_fatos"], "data": "2026-10-07"}
    before = snapshot(corpus["contexto"].parent)
    r = LeitorOperacional(ctx).consultar("ler_fatos", a)
    guardar_corpo("ausencia_real", corpus, a, r)
    assert r.status == "indisponivel" and r.resultado is None and r.resultado_sha256 is None
    assert snapshot(corpus["contexto"].parent) == before


def test_tamper_sha_e_m6_encerram_sem_retry(corpus):
    ctx = receber_contexto_leitura(corpus["contexto"])
    p = corpus["roots"]["relatorios"] / "daily" / str(DATA) / "factbook.json"
    p.write_text(p.read_text() + " ")
    before = snapshot(corpus["contexto"].parent)
    r = LeitorOperacional(ctx).consultar("ler_fatos", corpus["ingressos"]["ler_fatos"])
    guardar_corpo("tamper_sha", corpus, corpus["ingressos"]["ler_fatos"], r)
    assert r.status == "indisponivel" and r.falha.codigo == "INTEGRIDADE_DA_FONTE"
    assert r.resultado is None and snapshot(corpus["contexto"].parent) == before


def test_membro_dinamico_nao_pode_ser_omitido(corpus):
    raw = json.loads(corpus["contexto"].read_text())
    mid = next(k for k, v in raw["membros"].items() if v["relativo"].endswith("factbook.json"))
    del raw["membros"][mid]
    corpus["contexto"].write_text(json.dumps(raw))
    ctx = receber_contexto_leitura(corpus["contexto"])
    a = {**corpus["ingressos"]["ler_fatos"], "contexto_sha256": ctx.sha256}
    r = LeitorOperacional(ctx).consultar("ler_fatos", a)
    assert r.status == "indisponivel" and r.falha.codigo == "ARQUIVO_AUSENTE"


@pytest.mark.parametrize("field,value", [("offset_pc_minutos", 0.0), ("offset_pc_minutos", True)])
def test_inteiro_literal_repetido_na_folha(corpus, field, value):
    ctx = receber_contexto_leitura(corpus["contexto"])
    a = {**corpus["ingressos"]["consultar_agenda"], field: value}
    r = LeitorOperacional(ctx).consultar("consultar_agenda", a)
    assert r.status == "recusado" and not r.readset


def test_callbacks_ingresso_recusados_antes_de_igualdade_e_iteracao(corpus):
    class Evil(dict):
        def items(self):
            raise AssertionError("callback")

        def __iter__(self):
            raise AssertionError("callback")

    ctx = receber_contexto_leitura(corpus["contexto"])
    r = LeitorOperacional(ctx).consultar("consultar_estado", Evil())
    assert r.status == "recusado" and not r.readset

    class Eq:
        def __eq__(self, other):
            raise AssertionError("callback")

    a = {**corpus["ingressos"]["consultar_estado"], "rapido": Eq()}
    assert LeitorOperacional(ctx).consultar("consultar_estado", a).status == "recusado"


def test_autoria_do_cliente_nao_altera_contexto(corpus):
    ctx = receber_contexto_leitura(corpus["contexto"])
    a = {**corpus["ingressos"]["validar_documento"], "mente_esperada": "gemini"}
    r = LeitorOperacional(ctx).consultar("validar_documento", a)
    guardar_corpo("autoria_recusada", corpus, a, r)
    assert r.status == "recusado" and not r.readset


def test_schemas_refs_externos_e_false_inteiro_recusados():
    with pytest.raises(IngressoLeituraInvalido):
        validar_schema_exato(0, {"const": False})
    with pytest.raises(IngressoLeituraInvalido):
        validar_schema_exato({}, {"$ref": "https://example.com/x"})


def test_sem_fallback_path_explicito_contexto_invalido(tmp_path):
    with pytest.raises(ContextoLeituraInvalido):
        receber_contexto_leitura(tmp_path / "ausente.json")
    with pytest.raises(ContextoLeituraInvalido):
        receber_contexto_leitura("")
    assert list(tmp_path.iterdir()) == []


@pytest.mark.parametrize("modo", [1, "sim", None, object()])
def test_modo_bool_exato_antes_de_mkdir(tmp_path, modo):
    from cdp.data.store import MarketStore
    from cdp.workflow.book import Book
    from cdp.workflow.track_record import TrackRecord

    for constructor in (Book, TrackRecord, MarketStore):
        with pytest.raises(TypeError):
            constructor(tmp_path / "novo", somente_leitura=modo)
    assert list(tmp_path.iterdir()) == []


def test_readonly_construtores_e_writers_recusam_antes_de_efeito(tmp_path):
    from cdp.data.store import MarketStore
    from cdp.workflow.book import Book
    from cdp.workflow.track_record import TrackRecord

    b = Book(tmp_path / "book", somente_leitura=True)
    t = TrackRecord(tmp_path / "track", somente_leitura=True)
    m = MarketStore(tmp_path / "market", somente_leitura=True)
    assert list(tmp_path.iterdir()) == []
    for call in (
        lambda: b.save_proposal(None),
        lambda: t.append(None),
        lambda: b.audit.append("X", "X", {}),
    ):
        with pytest.raises(TentativaDeEfeitoLeitura):
            call()
    with pytest.raises(TentativaDeEfeitoLeitura):
        with m.write_lock():
            pass
    assert list(tmp_path.iterdir()) == []


def test_nan_inf_decimal_multiindex_e_ausencia_attrs_integrais():
    idx = pd.MultiIndex.from_arrays([["a", "a"], [1, 2]], names=["nome", None])
    frame = pd.DataFrame(
        [[float("nan"), float("inf")], [-float("inf"), 1.0]], index=idx, columns=["x", "x"]
    )
    frame.attrs = {"decimal": Decimal("1.2300"), "aviso": "DADOS SIMULADOS"}
    before = frame.copy(deep=True)
    encoded = serializar_valor(frame)
    assert encoded["indice"]["levels"]["tipo"] == "tuple"
    assert encoded["indice"]["codes"]["tipo"] == "tuple"
    assert encoded["valores"][0][0]["dtype"] == "<f8"
    assert encoded["valores"][0][0]["valor"]["categoria"] == "nan"
    assert encoded["valores"][0][1]["valor"]["categoria"] == "mais_infinito"
    assert encoded["valores"][1][0]["valor"]["categoria"] == "menos_infinito"
    assert encoded["indice"]["attrs"]["tipo"] == "atributo_ausente"
    pd.testing.assert_frame_equal(frame, before)


def test_tz_callback_e_subclass_nunca_sao_avaliados():
    class EvilTZ(tzinfo):
        def utcoffset(self, dt):
            raise AssertionError("callback")

    with pytest.raises(FonteLeituraIndisponivel):
        serializar_valor(datetime(2026, 10, 10, tzinfo=EvilTZ()))

    class EvilFrame(pd.DataFrame):
        @property
        def attrs(self):
            raise AssertionError("callback")

    with pytest.raises(FonteLeituraIndisponivel):
        serializar_valor(EvilFrame())


def test_readset_reabre_membro_e_recusa_mutacao_na_mesma_consulta(corpus):
    ctx = receber_contexto_leitura(corpus["contexto"])
    r = ctx.receptor()
    p = corpus["roots"]["rascunhos"] / "comentario.json"
    with ativar_receptor(r):
        ler_texto(p)
        p.write_bytes(p.read_bytes() + b" ")
        with pytest.raises(TentativaDeEfeitoLeitura):
            r.fechar()
    assert r.falha is not None


def test_etf_estado_recusado_pelo_contrato_antes_de_receber_membros(corpus):
    ctx = receber_contexto_leitura(corpus["contexto"])
    a = {
        **corpus["ingressos"]["ler_modelo_cobertura"],
        "instrumento_tipo": "etf",
        "instrumento_id": "ETF_ILF",
        "visao": "estado",
    }
    before = snapshot(corpus["contexto"].parent)
    r = LeitorOperacional(ctx).consultar("ler_modelo_cobertura", a)
    assert r.status == "recusado" and not r.readset
    assert snapshot(corpus["contexto"].parent) == before


def test_emissor_cobertura_fora_universo_recusado_antes_de_leitura(corpus):
    ctx = receber_contexto_leitura(corpus["contexto"])
    a = {**corpus["ingressos"]["ler_modelo_cobertura"], "instrumento_id": "DESCONHECIDO"}
    r = LeitorOperacional(ctx).consultar("ler_modelo_cobertura", a)
    assert r.status == "recusado"
    assert all(ref.raiz_id == "repositorio" for ref in r.readset)


def test_ausencia_modelo_nativo_retorna_excecao_estruturada(corpus):
    ctx = receber_contexto_leitura(corpus["contexto"])
    p = corpus["roots"]["livro"] / "cobertura" / str(DATA) / "modelos/SIM001.json"
    p.unlink()  # ausência real da fixture; não altera retorno para zero.
    before = snapshot(corpus["contexto"].parent)
    r = LeitorOperacional(ctx).consultar(
        "ler_modelo_cobertura", corpus["ingressos"]["ler_modelo_cobertura"]
    )
    assert r.status == "indisponivel" and r.resultado is None
    assert r.falha.codigo == "ARQUIVO_AUSENTE"
    assert r.falha.mensagem
    assert validar_json_resposta(serializar_resposta(r))["status"] == "indisponivel"
    assert snapshot(corpus["contexto"].parent) == before


def test_aliases_publicos_nao_mudam_contexto_nativo_da_consulta(corpus):
    from cdp.workflow.leitura import _REGISTRADOS

    ctx = receber_contexto_leitura(corpus["contexto"])
    reader = LeitorOperacional(ctx)
    registered = set(_REGISTRADOS)
    ctx.declaracoes["mente_esperada"] = "gemini"
    ctx.declaracoes["raizes"]["livro"] = "/raiz-inventada"
    ctx.nomes["SIM001"] = "NOME INVENTADO"
    ctx.universo.issuers.loc["SIM001", "issuer_name"] = "NOME INVENTADO"
    ctx.parametros.etfs["etfs"].clear()
    ctx.runtime.book_root = Path("/raiz-inventada")
    ctx.runtime.somente_leitura = False

    def callback():
        raise AssertionError("Relógio público não deve ser chamado")

    ctx.runtime.clock = callback
    before = snapshot(corpus["contexto"].parent)
    wrong = {**corpus["ingressos"]["validar_documento"], "mente_esperada": "gemini"}
    refused = reader.consultar("validar_documento", wrong)
    assert refused.status == "recusado" and not refused.readset
    r = reader.consultar("ler_carteira", corpus["ingressos"]["ler_carteira"])
    assert r.status == "disponivel"
    assert r.resultado == serializar_valor(corpus["record"])
    assert snapshot(corpus["contexto"].parent) == before
    assert set(_REGISTRADOS) == registered


def test_consultas_privadas_concorrentes_nao_trocam_contexto(corpus):
    from concurrent.futures import ThreadPoolExecutor

    ctx = receber_contexto_leitura(corpus["contexto"])
    reader = LeitorOperacional(ctx)
    with ThreadPoolExecutor(max_workers=2) as pool:
        future1 = pool.submit(reader.consultar, "ler_fatos", corpus["ingressos"]["ler_fatos"])
        future2 = pool.submit(reader.consultar, "ler_carteira", corpus["ingressos"]["ler_carteira"])
        a, b = future1.result(), future2.result()
    assert a.status == b.status == "disponivel"
    assert a.resultado == serializar_valor(corpus["factbook"])
    assert b.resultado == serializar_valor(corpus["record"])
    assert reader._contexto is ctx


def test_m6_entre_parser_privado_e_dispatch_nao_autentica_segundo_corpo(corpus, monkeypatch):
    import cdp.workflow.leitura as folha

    ctx = receber_contexto_leitura(corpus["contexto"])
    original = folha._receber_contexto_nativo
    path = corpus["roots"]["repositorio"] / "configs/cdp/universo.csv"

    def changed(p, selo=None):
        private = original(p, selo)
        st = path.stat()
        os.utime(path, ns=(st.st_atime_ns, st.st_mtime_ns + 1000000))
        return private

    monkeypatch.setattr(folha, "_receber_contexto_nativo", changed)
    r = LeitorOperacional(ctx).consultar("ler_fatos", corpus["ingressos"]["ler_fatos"])
    assert r.status == "indisponivel" and r.falha.codigo == "LEITURA_INSTAVEL"
    assert r.resultado is None and any(
        ref.path_relativo.endswith("universo.csv") for ref in r.readset
    )


def test_manifesto_divergente_recusado_antes_de_receber_nova_raiz(corpus, monkeypatch):
    import cdp.workflow.leitura as folha

    ctx = receber_contexto_leitura(corpus["contexto"])
    raw = json.loads(corpus["contexto"].read_text())
    raw["raizes"]["livro"] = "/raiz-inventada"
    corpus["contexto"].write_text(json.dumps(raw))

    def denied(*args, **kwargs):
        raise AssertionError("Manifesto divergente não deve criar receptor nem abrir entradas")

    monkeypatch.setattr(folha, "ReceptorArquivos", denied)
    r = LeitorOperacional(ctx).consultar("ler_fatos", corpus["ingressos"]["ler_fatos"])
    assert r.status == "indisponivel" and r.falha.codigo == "LEITURA_INSTAVEL"
    assert r.resultado is None and not r.readset


def test_data_semantica_invalida_recusada_antes_dos_parsers(corpus, monkeypatch):
    import cdp.workflow.leitura as folha

    ctx = receber_contexto_leitura(corpus["contexto"])

    def denied(*args, **kwargs):
        raise AssertionError("Ingresso inválido não deve reconstruir contexto")

    monkeypatch.setattr(folha, "_receber_contexto_nativo", denied)
    a = {**corpus["ingressos"]["ler_fatos"], "data": "2026-99-99"}
    r = LeitorOperacional(ctx).consultar("ler_fatos", a)
    assert r.status == "recusado" and r.falha.codigo == "INGRESSO_INVALIDO"
    assert not r.readset


@pytest.mark.parametrize("mutation", ["classe", "campo", "ordem"])
def test_catalogo_nominal_recusa_rehash_de_classe_ou_campos(corpus, mutation):
    ctx = receber_contexto_leitura(corpus["contexto"])
    payload = serializar_resposta(
        LeitorOperacional(ctx).consultar("ler_carteira", corpus["ingressos"]["ler_carteira"])
    )
    result = payload["resultado"]
    if mutation == "classe":
        result["classe"] = "cdp.inventado.Livre"
    elif mutation == "campo":
        result["campos"].pop()
    else:
        result["campos"].reverse()
    payload["resultado_sha256"] = hash_resultado(result)
    with pytest.raises(IngressoLeituraInvalido):
        validar_json_resposta(payload)


@pytest.mark.parametrize("mutation", ["shape", "dtypes", "indice", "indice_dtype", "cell"])
def test_shape_dtype_received_recusa_tamper_rehash_sem_runtime(corpus, mutation):
    ctx = receber_contexto_leitura(corpus["contexto"])
    payload = serializar_resposta(
        LeitorOperacional(ctx).consultar("ler_fatos", corpus["ingressos"]["ler_fatos"])
    )
    # Controle somente da representação/emissão: DataFrame nativo simulado, não delegate substituto.
    frame = pd.DataFrame([[1.0, float("nan")]], columns=["igual", "igual"])
    encoded = serializar_valor(frame)
    payload["resultado"] = encoded
    payload["resultado_sha256"] = hash_resultado(encoded)
    validar_json_resposta(payload)
    if mutation == "shape":
        encoded["shape"][0] = 2
    elif mutation == "dtypes":
        encoded["dtypes"][0] = "int64"
    elif mutation == "indice":
        encoded["indice"]["classe"] = "pandas.Inventado"
    elif mutation == "indice_dtype":
        encoded["indice"]["dtype"] = "float64"
    else:
        encoded["valores"][0].pop()
    payload["resultado_sha256"] = hash_resultado(encoded)
    with pytest.raises(IngressoLeituraInvalido):
        validar_json_resposta(payload)


@pytest.mark.parametrize("mutation", ["shape", "dtype", "signed_value"])
def test_numpy_array_forma_dtype_e_faixa_rehashados_recusados(corpus, mutation):
    ctx = receber_contexto_leitura(corpus["contexto"])
    payload = serializar_resposta(
        LeitorOperacional(ctx).consultar("ler_fatos", corpus["ingressos"]["ler_fatos"])
    )
    # Receita explícita da camada de representação, sem substituir o delegate financeiro.
    encoded = serializar_valor(np.array([[1, 2], [3, 4]], dtype=np.uint8))
    payload["resultado"] = encoded
    payload["resultado_sha256"] = hash_resultado(encoded)
    validar_json_resposta(payload)
    if mutation == "shape":
        encoded["shape"] = [2, 3]
    elif mutation == "dtype":
        encoded["dtype"] = "<f8"
    else:
        encoded["valores"][0]["valor"]["decimal"] = "-1"
    payload["resultado_sha256"] = hash_resultado(encoded)
    with pytest.raises(IngressoLeituraInvalido):
        validar_json_resposta(payload)


def test_enum_proprietario_literal_recebido_nao_aceita_membro_inventado(corpus):
    from cdp.contracts import Country

    ctx = receber_contexto_leitura(corpus["contexto"])
    payload = serializar_resposta(
        LeitorOperacional(ctx).consultar("ler_fatos", corpus["ingressos"]["ler_fatos"])
    )
    encoded = serializar_valor(Country.BR)
    payload["resultado"] = encoded
    payload["resultado_sha256"] = hash_resultado(encoded)
    validar_json_resposta(payload)
    encoded["membro"] = "INVENTADO"
    payload["resultado_sha256"] = hash_resultado(encoded)
    with pytest.raises(IngressoLeituraInvalido):
        validar_json_resposta(payload)


@pytest.mark.parametrize("mutation", ["numpy_na", "bool8", "float1", "int16", "plain_pandas_na"])
def test_dominio_dtype_impossivel_nao_passa_com_rehash(corpus, mutation):
    ctx = receber_contexto_leitura(corpus["contexto"])
    payload = serializar_resposta(
        LeitorOperacional(ctx).consultar("ler_fatos", corpus["ingressos"]["ler_fatos"])
    )
    if mutation == "plain_pandas_na":
        encoded = serializar_valor(pd.Series([1], dtype="int64"))
        encoded["valores"][0] = {"tipo": "pandas_na"}
    else:
        dtype = (
            np.bool_ if mutation == "bool8" else np.float32 if mutation == "float1" else np.int64
        )
        encoded = serializar_valor(np.array([1], dtype=dtype))
        if mutation == "numpy_na":
            encoded["valores"][0] = {"tipo": "pandas_na"}
        else:
            encoded["dtype"] = {"bool8": "|b8", "float1": "<f1", "int16": "<i16"}[mutation]
    payload["resultado"] = encoded
    payload["resultado_sha256"] = hash_resultado(encoded)
    with pytest.raises(IngressoLeituraInvalido):
        validar_json_resposta(payload)


def test_nullable_pandas_na_e_numpy_objeto_sao_representacoes_validas(corpus):
    ctx = receber_contexto_leitura(corpus["contexto"])
    payload = serializar_resposta(
        LeitorOperacional(ctx).consultar("ler_fatos", corpus["ingressos"]["ler_fatos"])
    )
    for native in (pd.Series([1, pd.NA], dtype="Int64"), np.array([1, pd.NA], dtype=object)):
        encoded = serializar_valor(native)
        assert encoded["valores"][1] == {"tipo": "pandas_na"}
        payload["resultado"] = encoded
        payload["resultado_sha256"] = hash_resultado(encoded)
        assert validar_json_resposta(payload)["resultado"] == encoded


def test_integridade_nativa_falsa_nao_vira_integro_e_leitor_continua(corpus):
    """Corrompe só corpus de TESTE próprio, antes de mint; corpo original é conservado."""
    folder = corpus["roots"]["livro"] / "track_record"
    csv = next(folder.glob("*.csv"))
    original = csv.read_bytes()
    (corpus["contexto"].parent / "csv_original_dados_simulados.bin").write_bytes(original)
    csv.write_bytes(original.splitlines(keepends=True)[0])
    raw = json.loads(corpus["contexto"].read_text())
    rel = csv.relative_to(corpus["roots"]["livro"]).as_posix()
    mid = next(
        k for k, v in raw["membros"].items() if v["raiz"] == "livro" and v["relativo"] == rel
    )
    raw["membros"][mid]["sha256"] = hashlib.sha256(csv.read_bytes()).hexdigest()
    corpus["contexto"].write_text(json.dumps(raw))
    ctx = receber_contexto_leitura(corpus["contexto"])
    reader = LeitorOperacional(ctx)
    a = {**corpus["ingressos"]["verificar_integridade"], "contexto_sha256": ctx.sha256}
    before = snapshot(corpus["contexto"].parent)
    r = reader.consultar("verificar_integridade", a)
    guardar_corpo("integridade_nativa_negativa", corpus, a, r)
    assert r.status == "disponivel" and r.integridade == "falho"
    assert r.resultado["itens"][0] == {"tipo": "bool", "valor": False}
    next_input = {**corpus["ingressos"]["ler_modelo_cobertura"], "contexto_sha256": ctx.sha256}
    continuation = reader.consultar("ler_modelo_cobertura", next_input)
    guardar_corpo("continuacao_apos_integridade_negativa", corpus, next_input, continuation)
    assert continuation.status == "disponivel" and continuation.autoridade_operacional is False
    assert snapshot(corpus["contexto"].parent) == before
