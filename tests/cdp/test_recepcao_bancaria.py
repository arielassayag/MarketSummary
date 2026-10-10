"""Metadados offline sobre cópias literais públicas; sem cálculo/modelo bancário."""
from __future__ import annotations

import hashlib
import json
import os
import shutil
from copy import deepcopy
from dataclasses import replace
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import pandas as pd
import pytest

from cdp.cobertura.disponibilidade_demonstrativos import (
    RegistroParticipantes,
    _identidade,
    conferir,
)
from cdp.cobertura.fontes import COLS_DEMONSTRATIVOS, DadosPublicos, _garantir
from cdp.cobertura.insumos import _prov_linha
from cdp.cobertura.temporal import construir
from cdp.data.publico_arquivo import Arquivo, data_local
from cdp.data.publico_fatos import _meta
from cdp.data.publico_yahoo import DEFASAGEM_DIAS
from cdp.data.recepcao_bancaria import (
    CAMPOS,
    ContextoBancario,
    _arquivo,
    _custodia_recibo,
    anotar_yahoo,
    autenticar,
    conferir_participantes,
    instante,
    texto,
)
from cdp.data.store import MarketStore

ROOT = Path(__file__).resolve().parents[2]
AS_OF = date(2026, 10, 8)
IID, DOMESTICA, ADR = "AR_GALICIA", "GGAL.BA", "GGAL"
DEM_SHA = "1039b5c67ffea6ecca5b70db99e26c7f1d788c6da2137193c3d44c74fc958b9b"
INFO_SHA = "8fa25be65dc0057ba07f548355485edd579ef5ca88c77987a9c845945135b3c2"


@pytest.fixture
def produto(tmp_path):
    """Os corpos reais são versionados; flags/manifests/índice ficam literais.

    As cinco linhas abaixo apenas transportam as células físicas do produto Yahoo
    já existente. Nenhuma TTM, contagem, BVPS, ROE, rating ou seleção é executada.
    """
    tmp_path = tmp_path.resolve()  # Namespace físico explícito; o leitor recusa links.
    market = tmp_path / "market"
    shutil.copytree(ROOT / "data/market", market)
    public = tmp_path / "fontes/publico"
    public.mkdir(parents=True)
    shutil.copy2(ROOT / "data/publico/indice.jsonl", public / "indice.jsonl")
    before = datetime.now(UTC)  # Corte anterior a ambas as novas recepções: negativo previsto.
    archive = Arquivo(tmp_path / "fontes", offline=True)
    dem = archive.buscar(f"YAHOO/demonstracoes/{DOMESTICA}.json", ate=before)
    info = archive.buscar(f"YAHOO/info/{DOMESTICA}.json", ate=before)
    assert dem is not None and info is not None
    assert dem.sha256 == DEM_SHA and info.sha256 == INFO_SHA
    for reg in (dem, info):
        dest = public / reg.caminho
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(ROOT / "data/publico" / reg.caminho, dest)
        assert hashlib.sha256(dest.read_bytes()).hexdigest() == reg.sha256
    md = MarketStore(market).load(AS_OF, recepcao_bancaria=True, conhecimento_ate=before)
    raw = json.loads(archive.ler(dem))
    currency = json.loads(archive.ler(info))["info"]["financialCurrency"]
    rows = []
    for table, positions in (("quarterly_balance_sheet", (0,)), ("balance_sheet", (0, 1, 2, 3))):
        frame = raw["demonstracoes"][table]
        for n in positions:
            period = pd.Timestamp(frame["colunas"][n])
            freq = "A" if table == "balance_sheet" else "Q"
            estimate = min(period.date() + timedelta(days=DEFASAGEM_DIAS[freq]), data_local(dem.data_coleta))
            rows.append({"entidade": f"YAHOO:{DOMESTICA}", "issuer_id": IID, "item": "acoes_em_circulacao",
                "demonstrativo": "BP", "freq": freq, "period_end": period, "period_start": pd.NaT,
                "value": frame["linhas"]["Ordinary Shares Number"][n], "currency": currency,
                "received_date": pd.Timestamp(estimate), "consolidado": True, "anual": freq == "A",
                "pit_estimado": True, "fonte": "YAHOO", "sha256": dem.sha256,
                "data_coleta": pd.Timestamp(dem.data_coleta), "url": f"https://finance.yahoo.com/quote/{DOMESTICA}/financials",
                "documento": f"Yahoo Finance {table}: Ordinary Shares Number", "nota": None})
    source = pd.DataFrame(rows)
    observed = anotar_yahoo(source, arquivo=archive, registro=dem, info=info, ticker=DOMESTICA,
        issuer_id=IID, universe=md.universe, contexto=md.contexto_bancario, conhecimento_ate=before)
    later = datetime.now(UTC)  # Consumidor posterior predefinido, sem selecionar pelo resultado.
    return md, archive, dem, info, source, observed, before, later


def pacote(produto):
    md, _, _, _, _, observed, _, later = produto
    ctx = md.contexto_bancario
    pac = {"issuer_id": IID, "as_of": data_local(later).isoformat(),
           "corte_temporal": construir(AS_OF, later), "historico": {"acoes_em_circulacao": {}}}
    registry = RegistroParticipantes(IID, contexto_bancario=ctx)
    for _, row in observed.iterrows():
        year = str(row.period_end.year)
        if row.freq == "A":
            dest = f"historico.acoes_em_circulacao.{year}"
            pac["historico"]["acoes_em_circulacao"][year] = row.value
        else:
            dest = "t.acoes_em_circulacao"
            pac[dest] = row.value
        registry.registrar(row, dest, fonte=_prov_linha(row))
    for item, freq in (("market_cap", "SNAPSHOT"), ("preco", "D")):
        encoded = ctx.mercado(md, ADR, item, period_end=AS_OF.isoformat())
        env = ctx.conferir(encoded)
        row = {"item": item, "freq": freq, "period_end": AS_OF.isoformat(),
               "disponivel_desde": env["disponivel_desde"], "recepcao_bancaria": encoded,
               "fonte": "YAHOO", "value": env["valor_original"], "currency": env["currency"]}
        source = {"fonte": "YAHOO", "url": f"https://finance.yahoo.com/quote/{ADR}",
                  "documento": "valor de mercado público ÷ fechamento" if item == "market_cap" else
                  "fechamento oficial (base de mercado do fundo)", "data_publicacao": AS_OF.isoformat(),
                  "data_coleta": None, "sha256": md.manifest.content_hash(),
                  "recepcao_bancaria": encoded, "disponivel_desde": env["disponivel_desde"]}
        dest = f"metadata.{item}"
        pac[dest] = env["valor_original"]
        registry.registrar(row, dest, origem="mercado", fonte=source)
    registry.finalizar(pac)
    return pac


def test_sete_recebidos_com_origens_e_instantes_distintos(produto):
    md, _, dem, info, source, observed, before, later = produto
    ctx = md.contexto_bancario
    assert observed.drop(columns=[*CAMPOS, "data_publicacao_primaria", "disponibilidade_tipo",
                                  "disponivel_desde", "data_recebimento_documento"]).equals(source)
    assert observed.pit_estimado.all()
    for _, row in observed.iterrows():
        env = ctx.conferir(row.recepcao_bancaria, conhecimento_ate=later)
        assert env["data_publicacao_primaria"] is None and env["point_in_time"] is False
        assert instante(env["recepcao_fisica_utc"]) > before
        assert env["registros"][0]["registro"] == dem.como_dict()
        assert env["registros"][1]["registro"] == info.como_dict()
        assert env["ticker"] == DOMESTICA and env["currency"] == "ARS"
        assert instante(env["disponivel_desde"]) == max(instante(env["recepcao_fisica_utc"]),
            dem.limite_captura, info.limite_captura)
    mcap = ctx.conferir(ctx.mercado(md, ADR, "market_cap", period_end=AS_OF.isoformat()))
    price = ctx.conferir(ctx.mercado(md, ADR, "preco", period_end=AS_OF.isoformat()))
    assert mcap["member"]["path"] == "daily/2026-10-05/fundamentals.parquet"
    assert price["member"]["path"] == "daily/2026-10-08/prices.parquet"
    assert mcap["source_record"]["source_id"] == "yahoo_fundamentals"
    assert price["source_record"]["source_id"] == "yahoo_prices"
    assert mcap["ticker"] == price["ticker"] == ADR
    assert "raw marketCap não arquivado" in mcap["limite"]
    assert conferir(pacote(produto), recepcao_bancaria=True, contexto_bancario=ctx)[0]


def test_corte_anterior_recusa_sem_alterar_recebimento_original(produto):
    md, archive, dem, info, source, observed, before, later = produto
    ctx = md.contexto_bancario
    with pytest.raises(ValueError, match="posterior ao corte"):
        ctx.conferir(observed.iloc[0].recepcao_bancaria, conhecimento_ate=before)
    reused = anotar_yahoo(source, arquivo=archive, registro=dem, info=info, ticker=DOMESTICA,
        issuer_id=IID, universe=md.universe, contexto=ctx, conhecimento_ate=later)
    assert reused.equals(observed)  # não carimba a releitura como nova recepção inicial.
    pac = pacote(produto)
    pac["as_of"] = data_local(before).isoformat()
    pac["corte_temporal"] = construir(AS_OF, before)
    assert not conferir(pac, recepcao_bancaria=True, contexto_bancario=ctx)[0]


def test_meta_projecao_attrs_fontes_manifesto_sem_ttm(produto):
    md, _, _, _, _, observed, _, _ = produto
    selected = []
    for row in observed.itertuples(index=False):
        meta = _meta(row)  # Projeção mecânica, sem selecionar_pit/derivados/TTM.
        assert meta["data_publicacao"] is None and meta["pit_estimado"] is True
        assert meta["data_publicacao_estimada"] == pd.Timestamp(row.received_date).date().isoformat()
        selected.append({"issuer_id": IID, "item": row.item, "freq": row.freq,
                         "period_end": row.period_end, "value": row.value, "escala": 1, **meta})
    frame = _garantir(pd.DataFrame(selected), COLS_DEMONSTRATIVOS)
    frame.attrs["contexto_bancario"] = md.contexto_bancario
    copied = frame.copy(deep=True)
    assert copied.attrs["contexto_bancario"] is md.contexto_bancario
    empty = pd.DataFrame()
    dados = DadosPublicos(copied, empty, empty, empty, empty, empty,
                          contexto_bancario=md.contexto_bancario)
    assert all(k in dados.tabelas()["demonstrativos"] for k in CAMPOS)
    assert all(_prov_linha(row)["recepcao_bancaria"] == row.recepcao_bancaria
               for _, row in copied.iterrows())


def test_default_literal_e_truncate_nativo_recusa_dto(produto):
    md, _, _, _, _, _, _, later = produto
    origin = md.contexto_bancario.conferir(md.contexto_bancario.mercado(md, ADR, "market_cap", period_end=AS_OF.isoformat()))
    default = MarketStore(Path(origin["member"]["root"])).load(AS_OF)
    assert default.contexto_bancario is None
    assert default.manifest.model_dump_json() == md.manifest.model_dump_json()
    for name in ("close", "adj_close", "volume", "fx", "fundamentals"):
        assert getattr(default, name).equals(getattr(md, name))
    child = md.truncate(date(2026, 10, 7))
    assert child.contexto_bancario is md.contexto_bancario
    encoded = child.contexto_bancario.mercado(child, ADR, "preco", period_end="2026-10-07")
    child.contexto_bancario.conferir(encoded, conhecimento_ate=later)
    with pytest.raises(ValueError, match="não recebido"):
        autenticar(md.contexto_bancario, replace(md))
    with pytest.raises(ValueError, match="não recebido"):
        replace(md).truncate(date(2026, 10, 7))
    with pytest.raises(TypeError):
        ContextoBancario()
    with pytest.raises(ValueError, match="não emitido"):
        autenticar(object.__new__(ContextoBancario))


@pytest.mark.parametrize("value", [None, 1, "true", [], {}])
def test_optin_bool_estrito_antes_io(tmp_path, value):
    with pytest.raises(ValueError, match="bool explícito"):
        MarketStore(tmp_path / "nao_existe").load(recepcao_bancaria=value)
    with pytest.raises(ValueError, match="bool explícito"):
        conferir({}, recepcao_bancaria=value)


def test_corte_utc_verify_e_wrapper_explicitos(tmp_path):
    for cut in (None, datetime(2026, 10, 10), date(2026, 10, 10)):
        with pytest.raises(ValueError, match="UTC|fuso"):
            MarketStore(tmp_path).load(recepcao_bancaria=True, conhecimento_ate=cut)
    with pytest.raises(ValueError, match="verify=True"):
        MarketStore(tmp_path).load(verify=False, recepcao_bancaria=True, conhecimento_ate=datetime.now(UTC))
    class Wrapper(MarketStore):
        pass
    with pytest.raises(ValueError, match="nativo"):
        Wrapper(tmp_path).load(recepcao_bancaria=True, conhecimento_ate=datetime.now(UTC))


@pytest.mark.parametrize("change", ["envelope", "recebimento", "readset", "ausencia", "downgrade", "dto"])
def test_manifesto_v4_adulterado_ou_contexto_ausente_recusado(produto, change):
    pac = pacote(produto)
    ctx = produto[0].contexto_bancario
    if change == "envelope":
        pac["disponibilidade_demonstrativos"][0]["recepcao_bancaria"] = "{}"
    elif change == "recebimento":
        pac["disponibilidade_demonstrativos"][0]["disponivel_desde"] = "2020-01-01T00:00:00+00:00"
    elif change == "readset":
        pac["manifesto_disponibilidade"]["readset_bancario"][0]["sha256"] = "a" * 64
    elif change == "ausencia":
        del pac["disponibilidade_demonstrativos"][0]["recepcao_bancaria"]
    elif change == "downgrade":
        pac["manifesto_disponibilidade"]["versao"] = "cdp.disponibilidade_participantes/v3"
    else:
        ctx = {"readset": ctx.readset()}
    assert not conferir(pac, recepcao_bancaria=True, contexto_bancario=ctx)[0]
    assert not conferir(pacote(produto))[0]  # JSON sem contexto nunca autentica v4.


@pytest.mark.parametrize("target", ["raw", "info", "indice", "manifest", "parquet", "mode"])
def test_origem_fisica_adulterada_recusada(produto, target):
    md, archive, dem, info, _, observed, _, _ = produto
    paths = {"raw": archive.base / dem.caminho, "info": archive.base / info.caminho,
             "indice": archive.base / "indice.jsonl"}
    mcap = md.contexto_bancario.conferir(md.contexto_bancario.mercado(md, ADR, "market_cap", period_end=AS_OF.isoformat()))
    for key, field in (("manifest", "manifest"), ("parquet", "member")):
        r = mcap[field]
        paths[key] = Path(r["root"]) / r["path"]
    if target == "mode":
        paths["raw"].chmod(0o400)
    else:
        paths[target].write_bytes(paths[target].read_bytes() + b" ")
    with pytest.raises(ValueError, match="custódia física"):
        md.contexto_bancario.conferir(observed.iloc[0].recepcao_bancaria)


def test_indice_mesmo_sha_coletas_distintas_e_locator(produto):
    md, archive, dem, info, source, observed, _, later = produto
    rows = [json.loads(x) for x in (archive.base / "indice.jsonl").read_bytes().splitlines() if x]
    same = [(n, r) for n, r in enumerate(rows, 1) if r.get("chave") == dem.chave and r.get("sha256") == dem.sha256]
    assert len(same) >= 2
    env = md.contexto_bancario.conferir(observed.iloc[0].recepcao_bancaria)
    assert env["registros"][0]["linha"] == same[-1][0]
    forged = deepcopy(source)
    forged.loc[0, "received_date"] = pd.Timestamp("2020-01-01")
    with pytest.raises(ValueError, match="estimativa"):
        anotar_yahoo(forged, arquivo=archive, registro=dem, info=info, ticker=DOMESTICA,
            issuer_id=IID, universe=md.universe, contexto=md.contexto_bancario, conhecimento_ate=later)
    altered = json.loads(observed.iloc[0].recepcao_bancaria)
    altered["envelope"]["ordinal"] = 3
    altered["sha256"] = hashlib.sha256(texto(altered["envelope"]).encode()).hexdigest()
    with pytest.raises(ValueError, match="não recebido"):
        md.contexto_bancario.conferir(texto(altered))


def test_falta_dependencia_ou_valor_nao_ganha_zero(produto):
    md, archive, dem, _, source, _, _, later = produto
    absent = anotar_yahoo(source, arquivo=archive, registro=dem, info=None, ticker=DOMESTICA,
        issuer_id=IID, universe=md.universe, contexto=md.contexto_bancario, conhecimento_ate=later)
    assert absent is source and "recepcao_bancaria" not in absent
    md.fundamentals.loc[ADR, "market_cap"] = float("nan")
    with pytest.raises(ValueError, match="view nativa adulterados"):
        md.contexto_bancario.mercado(md, ADR, "market_cap", period_end=AS_OF.isoformat())


def test_produto_sintetico_recusado_sem_reescrever_oficial(tmp_path):
    base = ROOT / "data/market/base/2026-10-02"
    dest = tmp_path / "market/base/2026-10-02"
    shutil.copytree(base, dest)
    # Negativo rotulado: cópia literal pública é explicitamente reclassificada TESTE,
    # jamais produto fictício marcado real, e não há incremento/cadeia a reancorar.
    path = dest / "manifest.json"
    body = json.loads(path.read_bytes())
    body.update(is_synthetic=True, data_notice="DADOS SIMULADOS — teste de recusa")
    path.write_text(json.dumps(body))
    with pytest.raises(ValueError, match="sintético"):
        MarketStore(tmp_path / "market").load(recepcao_bancaria=True, conhecimento_ate=datetime.now(UTC))


def test_civil_e_utc_separados_sem_executar_selector(produto):
    _, _, _, _, source, observed, _, later = produto
    civil = pd.to_datetime(observed.data_recebimento_documento, format="mixed")
    assert civil.dt.tz is None
    assert civil.dt.normalize().le(pd.Timestamp(data_local(later))).all()
    utc = pd.to_datetime(observed.recepcao_fisica_utc, format="mixed", utc=True)
    assert utc.dt.tz is not None
    assert civil.dt.date.tolist() == utc.dt.tz_convert("America/Sao_Paulo").dt.date.tolist()
    assert observed.received_date.equals(source.received_date)
    assert observed.pit_estimado.equals(source.pit_estimado)


@pytest.mark.parametrize("field", ["value", "currency", "freq", "entidade", "url", "documento", "sha256"])
def test_linha_recebida_modificada_antes_binding_recusada(produto, field):
    md, _, _, _, _, observed, _, _ = produto
    row = observed.iloc[0].copy(deep=True)
    changes = {"value": row.value + 1, "currency": "USD", "freq": "TTM", "entidade": "YAHOO:GGAL",
               "url": "https://finance.yahoo.com/quote/GGAL", "documento": "sem locator",
               "sha256": "a" * 64}
    row[field] = changes[field]
    registry = RegistroParticipantes(IID, contexto_bancario=md.contexto_bancario)
    with pytest.raises(ValueError, match="diverg"):
        registry.registrar(row, "t.acoes_em_circulacao", fonte=_prov_linha(row))


@pytest.mark.parametrize("field", ["valor", "currency", "freq", "fonte", "grao_original", "vinculo"])
def test_manifesto_autoconsistente_nao_reancora_raw(produto, field):
    pac = pacote(produto)
    member = pac["disponibilidade_demonstrativos"][0]
    if field == "valor":
        member["valor"] += 1
    elif field == "currency":
        member["currency"] = "USD"
    elif field == "freq":
        member["freq"] = "A"
    elif field == "fonte":
        member["fonte"]["sha256"] = "a" * 64
    elif field == "grao_original":
        member["grao_original"]["ordinal"] = 3
    else:
        binding = json.loads(member["vinculo_recepcao_bancaria"])
        binding["valor"] += 1
        member["vinculo_recepcao_bancaria"] = texto(binding)
    # Refeito pelo próprio caller: identidade/valor autoconsistentes continuam insuficientes.
    expected = pac["manifesto_disponibilidade"]["participantes_esperados"][0]
    expected.update(_identidade(member))
    pac[member["uso"]] = member.get("valor")
    pac["manifesto_disponibilidade"]["vinculos"][member["uso"]]["valor"] = member.get("valor")
    assert not conferir(pac, recepcao_bancaria=True, contexto_bancario=produto[0].contexto_bancario)[0]


@pytest.mark.parametrize("target", ["manifest", "close", "volume", "attrs", "universe", "child",
                                    "lines_attrs", "issuers_attrs", "lines_index", "issuers_index",
                                    "universe_pointer", "child_universe_pointer"])
def test_views_inteiras_seladas_recusam_mutacao(produto, target):
    md = produto[0]
    if target == "manifest":
        md.manifest.sources.pop()
    elif target == "universe":
        md.universe.lines.loc[ADR, "currency"] = "ARS"
    elif target == "attrs":
        md.close.attrs["captura_livre"] = "2000-01-01"
    elif target.endswith("_attrs"):
        getattr(md.universe, target.removesuffix("_attrs")).attrs["captura_livre"] = "2000-01-01"
    elif target.endswith("_index"):
        getattr(md.universe, target.removesuffix("_index")).index.name = "indice_livre"
    elif target == "universe_pointer":
        object.__setattr__(md, "universe", replace(md.universe))
    elif target in ("child", "child_universe_pointer"):
        child = md.truncate(date(2026, 10, 7))
    else:
        frame = getattr(md, target)
        frame.loc[frame[ADR].first_valid_index(), ADR] += 1
    if target == "child":
        child.close.loc[child.close[ADR].first_valid_index(), ADR] += 1
    elif target == "child_universe_pointer":
        object.__setattr__(child, "universe", replace(md.universe))
    with pytest.raises(ValueError, match="adulterad"):
        autenticar(md.contexto_bancario, md)


@pytest.mark.parametrize("ingress", ["registrar", "conferir", "conferir_sem_envelope"])
def test_item_mercado_desconhecido_nao_reutiliza_envelope_close(produto, ingress):
    md = produto[0]
    ctx = md.contexto_bancario
    pac = pacote(produto)
    member = next(row for row in pac["disponibilidade_demonstrativos"] if row["item"] == "preco")
    assert ctx.conferir(member["recepcao_bancaria"])["field"] == "close"
    if ingress == "registrar":
        row = {"item": "item_desconhecido", "freq": member["freq"], "period_end": member["period_end"],
               "value": member["valor"], "currency": member["currency"],
               "disponivel_desde": member["disponivel_desde"],
               "recepcao_bancaria": member["recepcao_bancaria"]}
        registry = RegistroParticipantes(IID, contexto_bancario=ctx)
        with pytest.raises(ValueError, match="item mercado fora do recorte"):
            registry.registrar(row, "metadata.item_desconhecido", origem="mercado", fonte=member["fonte"])
    else:
        member["item"] = "item_desconhecido"
        if ingress == "conferir_sem_envelope":
            del member["recepcao_bancaria"]
            assert ctx.conferir(member["fonte"]["recepcao_bancaria"])["field"] == "close"
        with pytest.raises(ValueError, match="item mercado fora do recorte"):
            conferir_participantes(pac, ctx)


@pytest.mark.parametrize("change", ["origem_mercado", "item_estoque", "fonte_estoque"])
def test_vestigio_recebido_nao_vira_legado_por_reclassificacao(produto, change):
    ctx = produto[0].contexto_bancario
    pac = pacote(produto)
    item = "preco" if change == "origem_mercado" else "acoes_em_circulacao"
    member = next(row for row in pac["disponibilidade_demonstrativos"] if row["item"] == item)
    original = member.pop("recepcao_bancaria")
    if change == "origem_mercado":
        member["origem"] = "demonstrativos"
    elif change == "item_estoque":
        member["item"] = "item_desconhecido"
    else:
        member["fonte"]["fonte"] = "OUTRA"
    assert member["fonte"]["recepcao_bancaria"] == original
    assert "vinculo_recepcao_bancaria" in member and "grao_original" in member
    with pytest.raises(ValueError, match="envelope superior ausente"):
        conferir_participantes(pac, ctx)


def test_contexto_limitado_nao_autentica_linha_fora_do_recorte_sem_vestigios(produto):
    ctx = produto[0].contexto_bancario
    pac = pacote(produto)
    # TESTE de delimitação: nenhum valor/publicação/autenticidade dessa linha é aprovado.
    # O gate de participantes completo conserva a responsabilidade por fora do recorte.
    pac["disponibilidade_demonstrativos"].append({"issuer_id": "FORA_DO_RECORTE_TESTE",
        "origem": "demonstrativos", "item": "item_legado", "fonte": {"fonte": "YAHOO"}})
    assert conferir_participantes(pac, ctx) is ctx


def test_contexto_novo_tem_recepcao_nova_sem_retroagir(produto):
    md, _, _, _, _, observed, _, later = produto
    old = md.contexto_bancario.conferir(observed.iloc[0].recepcao_bancaria)
    original = md.contexto_bancario.conferir(md.contexto_bancario.mercado(md, ADR, "market_cap", period_end=AS_OF.isoformat()))
    fresh = MarketStore(Path(original["member"]["root"])).load(AS_OF, recepcao_bancaria=True, conhecimento_ate=later)
    encoded = fresh.contexto_bancario.mercado(fresh, ADR, "market_cap", period_end=AS_OF.isoformat())
    new = fresh.contexto_bancario.conferir(encoded)
    assert instante(new["recepcao_fisica_utc"]) > later > instante(old["recepcao_fisica_utc"])
    assert new["member"] == original["member"]
    with pytest.raises(ValueError, match="posterior ao corte"):
        fresh.contexto_bancario.conferir(encoded, conhecimento_ate=later)


@pytest.mark.parametrize("duplicate", [False, True])
def test_indice_ordem_nativa_e_ordinal_fisico(produto, duplicate):
    md, archive, dem, _, source, _, _, later = produto
    path = archive.base / "indice.jsonl"
    lines = path.read_text().splitlines()
    chosen = next(i for i, line in enumerate(lines) if json.loads(line) == dem.como_dict())
    last = lines.pop(chosen)
    lines.insert(0, last)  # Coleta mais recente passa a ser a primeira linha física.
    if duplicate:
        lines.append(last)
    path.write_text("\n".join(lines) + "\n")
    native = Arquivo(archive.raiz, offline=True)
    selected = native.buscar(dem.chave, ate=later)
    info = native.buscar(f"YAHOO/info/{DOMESTICA}.json", ate=later)
    assert selected == dem
    # O contexto antigo não é reaproveitado depois da alteração do índice.
    market_root = archive.raiz.parent / "market"
    fresh = MarketStore(market_root).load(AS_OF, recepcao_bancaria=True, conhecimento_ate=later)
    kwargs = {"arquivo": native, "registro": selected, "info": info, "ticker": DOMESTICA,
              "issuer_id": IID, "universe": fresh.universe, "contexto": fresh.contexto_bancario,
              "conhecimento_ate": later}
    if duplicate:
        with pytest.raises(ValueError, match="indistinguível duplicada"):
            anotar_yahoo(source, **kwargs)
    else:
        result = anotar_yahoo(source, **kwargs)
        env = fresh.contexto_bancario.conferir(result.iloc[0].recepcao_bancaria)
        assert env["registros"][0]["linha"] == 1
        assert env["registros"][0]["registro"] == dem.como_dict()


@pytest.mark.parametrize("target", ["symlink", "hardlink", "parent_link", "mode", "swap_openat",
                                    "external_sibling", "external_directory_create",
                                    "external_directory_remove", "root_replace"])
def test_fd_custodia_completa_sem_financeiro(tmp_path, monkeypatch, target):
    root = tmp_path.resolve() / "root"
    parent = root / "parts"
    parent.mkdir(parents=True)
    member = parent / "body.json"
    raw = b'{"publico":"corpo literal de teste mecanico"}'
    member.write_bytes(raw)
    sibling = root.parent / "external_directory"
    if target == "external_directory_remove":
        sibling.mkdir()
    _, original = _arquivo(root, "parts/body.json")
    assert original["mode"] == member.stat().st_mode and original["nlink"] == 1
    assert original["ctime_ns"] == member.stat().st_ctime_ns
    assert all("mode" in row and ("nlink" in row or "nlink_observado" in row)
               for row in original["namespace"])
    if target == "symlink":
        destination = root / "same.json"
        member.rename(destination)
        member.symlink_to(destination)
    elif target == "hardlink":
        os.link(member, root / "same.json")
    elif target == "parent_link":
        destination = root / "physical"
        parent.rename(destination)
        parent.symlink_to(destination, target_is_directory=True)
    elif target == "mode":
        member.chmod(0o400)
        _, changed = _arquivo(root, "parts/body.json")
        assert changed != original and changed["sha256"] == original["sha256"]
        return
    elif target == "swap_openat":
        native_open = os.open
        def swapped(path, flags, **kwargs):
            if path == "body.json" and "dir_fd" in kwargs:
                replacement = parent / "replacement"
                replacement.write_bytes(raw)
                os.replace(replacement, member)
            return native_open(path, flags, **kwargs)
        monkeypatch.setattr(os, "open", swapped)
    else:
        native_read = os.read
        changed = False
        def changed_namespace(fd, length):
            nonlocal changed
            if not changed:
                changed = True
                if target == "external_sibling":
                    (root.parent / "external.json").write_bytes(raw)
                elif target == "external_directory_create":
                    sibling.mkdir()
                elif target == "external_directory_remove":
                    sibling.rmdir()
                else:
                    root.rename(root.parent / "original")
                    (root / "parts").mkdir(parents=True)
                    (root / "parts/body.json").write_bytes(raw)
            return native_read(fd, length)
        monkeypatch.setattr(os, "read", changed_namespace)
        if target in ("external_sibling", "external_directory_create", "external_directory_remove"):
            body, receipt = _arquivo(root, "parts/body.json")
            assert body == raw and _custodia_recibo(receipt) == _custodia_recibo(original)
            row = next(x for x in receipt["namespace"] if x["path"] == str(root.parent))
            assert row["nlink_observado"]["depois_fd"] == root.parent.stat().st_nlink
            assert row["nlink_observado"]["depois_caminho"] == root.parent.stat().st_nlink
            return
    with pytest.raises(ValueError, match="Recepção bancária"):
        _arquivo(root, "parts/body.json")


def test_v3_default_corpo_literal_sem_nova_autoridade(produto):
    row = produto[4].iloc[0]
    use = "t.acoes_em_circulacao"
    registry = RegistroParticipantes(IID)
    registry.registrar(row, use, fonte=_prov_linha(row))
    pac = {use: row.value}
    registry.finalizar(pac)
    source = {"fonte": "YAHOO", "url": f"https://finance.yahoo.com/quote/{DOMESTICA}/financials",
              "documento": "Yahoo Finance — balanço patrimonial trimestral: Ordinary Shares Number "
              "(BP, trimestral até 2026-06-30)", "data_publicacao": None,
              "data_coleta": row.data_coleta.isoformat(), "sha256": DEM_SHA, "data_estimada": True}
    identity = {"issuer_id": IID, "origem": "demonstrativos", "item": "acoes_em_circulacao",
                "freq": "Q", "period_end": "2026-06-30T00:00:00", "uso": use,
                "entidade": f"YAHOO:{DOMESTICA}", "identidade_declarada": {"issuer_id": IID}}
    assert pac["disponibilidade_demonstrativos"] == [{**identity, "disponivel_desde": None, "fonte": source}]
    assert pac["manifesto_disponibilidade"] == {
        "versao": "cdp.disponibilidade_participantes/v3", "issuer_id": IID,
        "participantes_esperados": [{**identity, "componentes": [], "grupos_componentes": []}],
        "vinculos": {use: {"usos": [use], "valor": row.value}}}


def test_diretorio_irmao_externo_nao_renova_receipt_ou_cache(produto):
    md, archive, dem, info, source, observed, _, later = produto
    ctx = md.contexto_bancario
    first = ctx.readset()
    sibling = archive.raiz.parent / "irmao_externo"
    sibling.mkdir()
    ctx.revalidar()
    assert ctx.readset() == first
    again = anotar_yahoo(source, arquivo=archive, registro=dem, info=info, ticker=DOMESTICA,
        issuer_id=IID, universe=md.universe, contexto=ctx, conhecimento_ate=later)
    assert again.equals(observed)
    sibling.rmdir()
    ctx.revalidar()
    assert ctx.readset() == first
