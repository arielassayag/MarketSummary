"""PDFs públicos reais; universo/transportes/novos recibos DADOS SIMULADOS.

O esperado financeiro vem do ledger documental independente fechado. Não usa
cálculos financeiros CDP para produzir esperados, nem inventa fluxo/ações/PIT.
"""

import os
from copy import deepcopy
from dataclasses import replace
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal, localcontext
from functools import lru_cache
from pathlib import Path
from types import SimpleNamespace

import pandas as pd
import pytest

from cdp.cobertura.disponibilidade_demonstrativos import RegistroParticipantes, conferir
from cdp.cobertura.insumos import Demonstrativos, _prov_linha
from cdp.cobertura.temporal import construir
from cdp.data import publico
from cdp.data import publico_patrimonio_owners as owners
from cdp.data.publico_arquivo import RegistroArquivo
from cdp.data.publico_contexto_documental import (
    ExtracaoRecusada,
    _envelope,
    contexto_documental,
    estoque_documental,
)
from cdp.data.publico_fatos import selecionar_pit
from cdp.universe import Universe

DIA = date(2026, 10, 9)
RECEBIDO = datetime(2026, 10, 9, 14, 0, 0, 123456, tzinfo=UTC)
CORTE = RECEBIDO + timedelta(minutes=2)
ISSUERS = ("AR_GALICIA", "AR_SUPERVIELLE")
# Oráculo independente: ledger 0a5d1f...; quatro lexemas originais × 1000 em Decimal.
LEXEMAS = {
    "AR_GALICIA": ("9,197,638,149", "9,074,888,664"),
    "AR_SUPERVIELLE": ("1,180,450,429", "1,176,945,446"),
}
POLITICAS = {
    "AR_GALICIA": "BCRA_NIIF_exclusao_IFRS9_5.5_setor_publico_nao_financeiro",
    "AR_SUPERVIELLE": "BCRA_NIIF_exclusoes_IFRS9_5.5_e_A7014",
}


def esperado(issuer):
    with localcontext() as ctx:
        ctx.prec = 80
        return [Decimal(v.replace(",", "")) * Decimal("1000") for v in LEXEMAS[issuer]]


@lru_cache(maxsize=2)
def body(issuer):
    root = Path(os.environ.get("CDP_OWNERS_PDFS", Path(__file__).parent / "fixtures"))
    nome = owners.PERFIS[issuer].PINS["junho"]["documento"]
    path = root / nome
    if not path.exists():
        path = root / ("galicia" if issuer == "AR_GALICIA" else "supervielle") / nome
    return path.read_bytes()


def registro(issuer, recebido=RECEBIDO, precisao="microseconds"):
    pin = owners.PERFIS[issuer].PINS["junho"]
    return RegistroArquivo(
        f"RI/demonstrativos/{issuer}/{pin['documento']}",
        "RI",
        pin["url"],
        "DADOS_SIMULADOS/" + pin["documento"],
        pin["sha256"],
        pin["bytes"],
        recebido,
        precisao,
    )


@lru_cache(maxsize=2)
def base_fatos(issuer):
    return owners.fatos_pdf_observado(body(issuer), registro(issuer), issuer)


def universo(issuers=ISSUERS):
    lines = pd.DataFrame(
        [
            dict(
                issuer_id=i,
                line_type="LOCAL",
                country="AR",
                currency="ARS",
                market="BYMA",
                primary_line=True,
                adr_ratio=1.0,
            )
            for i in issuers
        ],
        index=["GGAL.BA" if i == "AR_GALICIA" else "SUPV.BA" for i in issuers],
    )
    companies = pd.DataFrame(
        [
            dict(
                issuer_name="Grupo Financiero Galicia S.A."
                if i == "AR_GALICIA"
                else "Grupo Supervielle S.A.",
                country="AR",
                gics_sector="Financials",
                primary_ticker=lines.index[j],
                local_currency="ARS",
            )
            for j, i in enumerate(issuers)
        ],
        index=list(issuers),
    )
    return Universe(lines, companies, "DADOS SIMULADOS UNIVERSE - sem preços")


class ArquivoMemoria:
    """Apenas transporte: validação/parser/seletor/consumidor são os módulos normais."""

    offline = True

    def __init__(self, issuers=ISSUERS, *, recebido=RECEBIDO, extra=None):
        self.falhas, self.pedidos = [], []
        self.conhecimento_ate = CORTE
        self.registros = {i: registro(i, recebido) for i in issuers}
        self.extra = extra or {}

    def chaves(self, prefixo=""):
        return list(self.extra)

    def buscar(self, chave, *_args, **_kwargs):
        return self.extra.get(chave)

    def obter(self, chave, fonte, url, baixar, **kwargs):
        self.pedidos.append(chave)
        for issuer, reg in self.registros.items():
            if reg.chave == chave:
                data = body(issuer)
                kwargs["validar"](data)
                return reg, data
        if chave in self.extra:
            reg, data = self.extra[chave]
            kwargs["validar"](data)
            return reg, data
        return None  # Ausências reais no transporte não são zeros/fatos fictícios.


def coletor(monkeypatch, issuers=ISSUERS, *, arquivo=None, corte=CORTE, ativo=True):
    arq = arquivo or ArquivoMemoria(issuers)
    monkeypatch.setattr(publico, "_arquivo", lambda *_args: arq)

    def sem_rede(*_args, **_kwargs):
        raise AssertionError("rede proibida - transporte DADOS SIMULADOS")

    df = publico.demonstrativos(
        issuers,
        DIA,
        offline=True,
        universe=universo(issuers),
        complementar_yahoo=False,
        selecionar_ri_observado=ativo,
        patrimonio_owners_observado=ativo,
        conhecimento_ate=corte if ativo else None,
        http_get=sem_rede,
    )
    return df, arq


def pacote(rows, issuer, corte=CORTE, *, fontes=None):
    pac = dict(issuer_id=issuer, as_of=DIA.isoformat(), corte_temporal=construir(DIA, corte))
    reg = RegistroParticipantes(issuer)
    for j, row in enumerate(rows):
        uso = "t.patrimonio_" + str(j)
        reg.registrar(row, uso, fonte=None if fontes is None else fontes[j])
        pac[uso] = float(row.value)
    reg.finalizar(pac)
    return pac


def selecionados(issuer):
    return selecionar_pit(base_fatos(issuer).copy(deep=True), DIA, conhecimento_ate=CORTE)


@pytest.mark.parametrize("issuer", ISSUERS)
def test_api_pura_quatro_celulas_originais(issuer):
    raw = base_fatos(issuer)
    assert len(raw) == 2
    assert raw.period_start.isna().all()
    assert raw.period_end.dt.date.tolist() == [date(2026, 6, 30), date(2025, 12, 31)]
    assert [Decimal(str(v)) for v in raw.value] == esperado(issuer)
    assert raw.item.eq("patrimonio_controladores").all()
    assert raw.politica_contabil_id.eq(POLITICAS[issuer]).all()
    assert raw.poder_aquisitivo_data.eq("2026-06-30").all()
    assert raw.data_publicacao_primaria.isna().all()
    for _, row in raw.iterrows():
        ctx = row.contexto_documental
        assert ctx["celula"]["data_estoque"] == row.period_end.date().isoformat()
        assert [d["papel"] for d in ctx["dependencias"]] == ["junho"]
        assert ctx["reportado_no_documento"] and ctx["ponte_especifica"] is None
        assert ctx["normalizado"] is ctx["IFRS_integral"] is ctx["pit_certificado"] is False
        assert ctx["disponivel_desde"] == RECEBIDO.isoformat()


@pytest.mark.parametrize("issuer", ISSUERS)
def test_api_normal_seletor_consumidor_e_g2_completo(monkeypatch, issuer):
    df, arq = coletor(monkeypatch, (issuer,))
    assert len(df) == 2 and df.freq.eq("Q").all()  # Q canônico é estoque instantâneo.
    assert (
        "period_start" not in df or df.period_start.isna().all()
    ) and df.data_publicacao.isna().all()
    assert set(df.period_end.dt.date) == {date(2026, 6, 30), date(2025, 12, 31)}
    assert set(Decimal(str(v)) for v in df.value) == set(esperado(issuer))
    assert not any("anual" in d["papel"] for c in df.contexto_documental for d in c["dependencias"])
    assert Demonstrativos(df, issuer).valor("patrimonio_controladores")[0] == float(
        esperado(issuer)[0]
    )
    rows = [r for _, r in df.iterrows()]
    assert conferir(pacote(rows, issuer))[0]
    for _, row in df.iterrows():
        assert contexto_documental(row) and estoque_documental(row)
        source = _prov_linha(row)
        assert source["politica_contabil_id"] == POLITICAS[issuer]
        assert source["contexto_documental"] == row.contexto_documental
    assert arq.pedidos.count(registro(issuer).chave) == 1


@pytest.mark.parametrize("issuer", ISSUERS)
def test_registro_novo_tardio_nao_reutiliza_recibo_antigo(issuer):
    new = RECEBIDO + timedelta(minutes=1)
    raw = owners.fatos_pdf_observado(body(issuer), registro(issuer, new), issuer)
    assert raw.received_date.eq(new).all()
    assert raw.disponivel_desde.eq(new.isoformat()).all()
    assert selecionar_pit(raw, DIA, conhecimento_ate=RECEBIDO).empty
    assert len(selecionar_pit(raw, DIA, conhecimento_ate=new)) == 2


@pytest.mark.parametrize("issuer", ISSUERS)
@pytest.mark.parametrize("delta", (-1, 0, 1))
def test_corte_antes_exato_depois_microsegundo(issuer, delta):
    out = selecionar_pit(
        base_fatos(issuer), DIA, conhecimento_ate=RECEBIDO + timedelta(microseconds=delta)
    )
    assert len(out) == (0 if delta < 0 else 2)
    rows = [r for _, r in selecionados(issuer).iterrows()]
    assert conferir(pacote(rows, issuer, RECEBIDO + timedelta(microseconds=delta)))[0] == (
        delta >= 0
    )


@pytest.mark.parametrize("issuer", ISSUERS)
@pytest.mark.parametrize(
    "campo,valor",
    [
        ("data_coleta", datetime(2050, 1, 1, tzinfo=UTC)),
        ("data_coleta", RECEBIDO.replace(tzinfo=None)),
        ("sha256", "0" * 64),
        ("url", "https://example.invalid/"),
        ("bytes", 1),
        ("fonte", "SEC"),
    ],
)
def test_recebimento_invalido_recusado(issuer, campo, valor):
    with pytest.raises(ExtracaoRecusada):
        owners.fatos_pdf_observado(
            body(issuer), replace(registro(issuer), **{campo: valor}), issuer
        )


@pytest.mark.parametrize("issuer", ISSUERS)
@pytest.mark.parametrize("mutacao", ("append", "troca_emissor"))
def test_corpo_sha_e_grupo_exatos(issuer, mutacao):
    data = body(issuer) + b"\n" if mutacao == "append" else body(ISSUERS[1 - ISSUERS.index(issuer)])
    with pytest.raises(ExtracaoRecusada):
        owners.validar_pdf(data, issuer)


@pytest.mark.parametrize("issuer", ISSUERS)
@pytest.mark.parametrize(
    "campo,valor",
    [
        ("currency", "USD"),
        ("consolidado", False),
        ("item", "patrimonio_liquido"),
        ("demonstrativo", "DRE"),
        ("escala", 1000),
        ("received_date", RECEBIDO + timedelta(seconds=1)),
        ("freq", "TTM"),
        ("freq", "A"),
        ("period_start", pd.Timestamp("2026-01-01")),
        ("period_end", pd.Timestamp("2026-07-01")),
        ("politica_contabil_id", "IFRS_integral"),
        ("poder_aquisitivo_data", "2025-12-31"),
        ("value", Decimal("0")),
        ("value", "ausente"),
    ],
)
def test_grao_ou_valor_adulterado_recusado_antes_registro(issuer, campo, valor):
    row = selecionados(issuer).iloc[-1].copy()
    row[campo] = valor
    with pytest.raises(ExtracaoRecusada):
        contexto_documental(row)
    with pytest.raises(ExtracaoRecusada):
        pacote([row], issuer)


@pytest.mark.parametrize("issuer", ISSUERS)
@pytest.mark.parametrize(
    "campo,valor",
    [
        ("rubrica", "Share capital"),
        ("owners", False),
        ("escala_ars", "1"),
        ("pagina_pdf", 1),
        ("coluna", "ausente"),
        ("data_estoque", "2026-07-01"),
        ("lexema", "0"),
        ("valor_decimal_ars", "0"),
        ("sha256", "0" * 64),
        ("currency", "USD"),
    ],
)
def test_contexto_reassinado_nao_autentica_celula_mutada(issuer, campo, valor):
    row = selecionados(issuer).iloc[-1].copy()
    ctx = deepcopy(row.contexto_documental)
    ctx["celula"][campo] = valor
    for k, v in _envelope(ctx).items():
        row[k] = v
    with pytest.raises(ExtracaoRecusada):
        contexto_documental(row)


@pytest.mark.parametrize("issuer", ISSUERS)
@pytest.mark.parametrize(
    "campo,valor",
    [
        ("sha256", "0" * 64),
        ("url", "https://example.invalid"),
        ("politica_contabil_id", "IFRS_integral"),
        ("poder_aquisitivo_data", "2025-12-31"),
        ("value", 0),
        ("item", "acoes_em_circulacao"),
    ],
)
def test_fonte_efetiva_ultimo_participante_recusada(issuer, campo, valor):
    rows = [r for _, r in selecionados(issuer).iterrows()]
    sources = [_prov_linha(r) for r in rows]
    # Mutação só na segunda/última fonte; topo e contextos originais intactos.
    sources[-1][campo] = valor
    assert not conferir(pacote(rows, issuer, fontes=sources))[0]


@pytest.mark.parametrize("issuer", ISSUERS)
def test_fonte_sem_par_opcional_preserva_formato_legitimo(issuer):
    rows = [r for _, r in selecionados(issuer).iterrows()]
    sources = [_prov_linha(r) for r in rows]
    for s in sources:
        s.pop("politica_contabil_id")
        s.pop("poder_aquisitivo_data")
    assert conferir(pacote(rows, issuer, fontes=sources))[0]


@pytest.mark.parametrize("issuer", ISSUERS)
def test_pacote_adulterado_nao_passa_manifesto_ou_fonte(issuer):
    pac = pacote([r for _, r in selecionados(issuer).iterrows()], issuer)
    pac["disponibilidade_demonstrativos"][-1]["fonte"]["sha256"] = "0" * 64
    assert not conferir(pac)[0]
    pac = pacote([r for _, r in selecionados(issuer).iterrows()], issuer)
    pac["t.patrimonio_1"] += 1000
    assert not conferir(pac)[0]


@pytest.mark.parametrize("issuer", ISSUERS)
def test_nome_perfil_csv_sem_envelope_nao_admite_data(issuer):
    raw = base_fatos(issuer).copy(deep=True)
    raw.contexto_documental = None
    raw.contexto_documental_sha256 = None
    assert selecionar_pit(raw, DIA, conhecimento_ate=CORTE).empty
    row = base_fatos(issuer).iloc[0].to_dict()
    row["contexto_documental"] = {"schema": owners.PERFIS[issuer].CONTEXTO_SCHEMA}
    with pytest.raises(ExtracaoRecusada):
        contexto_documental(row)


def test_publico_optin_exige_disponibilidade_e_corte(monkeypatch):
    with pytest.raises(ValueError):
        publico.demonstrativos([], DIA, patrimonio_owners_observado=True)
    with pytest.raises(ValueError):
        publico.demonstrativos(
            [], DIA, patrimonio_owners_observado=True, selecionar_ri_observado=True
        )
    from cdp.cobertura.fontes import coletar

    md = SimpleNamespace(is_synthetic=False, universe=universo(), as_of=DIA)
    with pytest.raises(ValueError):
        coletar(md, DIA, [], [], [], patrimonio_owners_observado=True)


def test_coletor_normal_completo_preserva_campos(monkeypatch):
    from cdp.cobertura.fontes import coletar

    arq = ArquivoMemoria()
    monkeypatch.setattr(publico, "_arquivo", lambda *_args: arq)
    params = SimpleNamespace(
        sec=lambda section: (
            {"resultado_corte_metodo": "base_preco_conhecimento_explicitos"}
            if section == "projecao"
            else {"demonstrativos_disponibilidade_metodo": "recepcao_observada"}
        )
    )
    md = SimpleNamespace(is_synthetic=False, universe=universo(), as_of=DIA)
    dados = coletar(
        md,
        DIA,
        list(ISSUERS),
        [],
        [],
        offline=True,
        params=params,
        conhecimento_ate=CORTE,
        patrimonio_owners_observado=True,
    )
    assert len(dados.demonstrativos) == 4
    assert (
        "period_start" not in dados.demonstrativos or dados.demonstrativos.period_start.isna().all()
    )
    assert dados.demonstrativos.item.eq("patrimonio_controladores").all()
    for issuer in ISSUERS:
        df = dados.demonstrativos[dados.demonstrativos.issuer_id.eq(issuer)]
        assert set(Decimal(str(v)) for v in df.value) == set(esperado(issuer))
        assert conferir(pacote([r for _, r in df.iterrows()], issuer))[0]


@lru_cache(maxsize=2)
def paginas_originais(issuer):
    return owners.PERFIS[issuer].produto.validar_pdf_observado(body(issuer), "junho")


@pytest.mark.parametrize("issuer", ISSUERS)
@pytest.mark.parametrize(
    "alvo", ("rubrica", "owners", "unidade", "coluna", "data", "poder", "policy")
)
def test_causal_paginas_textuais_sem_burlar_autenticacao(issuer, alvo):
    perfil = owners.PERFIS[issuer]
    pages = deepcopy(paginas_originais(issuer))
    spec = owners.CELULAS_DOCUMENTAIS[issuer][0]
    if issuer == "AR_GALICIA":
        table, key = pages, spec["pagina_pdf"]
        changes = {
            "rubrica": (spec["rubrica"], "Share capital"),
            "owners": (spec["rubrica"], spec["rubrica"].replace("Owners", "Interests")),
            "unidade": ("thousand Argentine pesos", "Argentine pesos"),
            "coluna": ("06.30.26 12.31.25", "12.31.25 06.30.26"),
            "data": ("June 30, 2026", "June 30, 2025"),
        }
    else:
        table, key = pages["pages"], spec["pagina_pdf"] - 1
        changes = {
            "rubrica": (spec["rubrica"], "Share capital"),
            "owners": (
                spec["rubrica"],
                spec["rubrica"].replace("owners", "non-controlling interests"),
            ),
            "unidade": ("thousands of pesos", "pesos"),
            "coluna": ("06/30/2026 12/31/2025", "12/31/2025 06/30/2026"),
            "data": ("June 30, 2026", "June 30, 2025"),
        }
    if alvo in changes:
        old, new = changes[alvo]
        assert old in table[key]
        table[key] = table[key].replace(old, new)
    else:
        if issuer == "AR_GALICIA":
            key = 15 if alvo == "poder" else 13
            table = pages
            old, new = (
                ("stated in homogeneous currency at closing", "stated in currency at opening")
                if alvo == "poder"
                else ("IFRS 9", "IAS 1")
            )
        else:
            table = pages["pages"]
            key = 14 if alvo == "poder" else 13
            old, new = (
                ("June 30, 2026", "December 31, 2025") if alvo == "poder" else ("IFRS 9", "IAS 1")
            )
        assert old in table[key]
        table[key] = table[key].replace(old, new)
    with pytest.raises((ExtracaoRecusada, ValueError)):
        owners.extrair_paginas(perfil, pages)


@pytest.mark.parametrize("issuer", ISSUERS)
@pytest.mark.parametrize(
    "campo,valor",
    [
        ("sha256", "0" * 64),
        ("url", "https://example.invalid"),
        ("issuer_id", "AR_DESCONHECIDO"),
        ("data_publicacao", "2026-09-01"),
        ("disponibilidade_tipo", None),
    ],
)
def test_catalogo_nao_autodeclara_documento(issuer, campo, valor):
    doc = deepcopy(
        next(
            d
            for d in publico.ri_pdf.documentos_ri(issuer, DIA)
            if d.get("extrator") == owners.PERFIS[issuer].produto.EXTRATOR_ID
        )
    )
    doc[campo] = valor
    with pytest.raises(ExtracaoRecusada):
        owners.validar_catalogo(doc)


@pytest.mark.parametrize("issuer", ISSUERS)
def test_stock_nao_vira_A_ou_TTM_com_outros_fluxos(issuer):
    raw = base_fatos(issuer).copy(deep=True)
    # Outros fluxos DADOS SIMULADOS não autorizam transformar o estoque em fluxo.
    flow = raw.iloc[1].copy()
    flow["item"] = "receita"
    flow["period_start"] = pd.Timestamp("2025-01-01")
    flow["value"] = 1000.0
    flow["anual"] = True
    flow["contexto_documental"] = None
    flow["contexto_documental_sha256"] = None
    out = selecionar_pit(
        pd.concat([raw, pd.DataFrame([flow])], ignore_index=True), DIA, conhecimento_ate=CORTE
    )
    stock = out[out.item.eq("patrimonio_controladores")]
    assert len(stock) == 2 and stock.freq.eq("Q").all()
    assert "period_start" not in stock or stock.period_start.isna().all()


@pytest.mark.parametrize("issuer", ISSUERS)
def test_fonte_com_par_parcial_e_contexto_omitido_recusada(issuer):
    row = selecionados(issuer).iloc[-1]
    source = _prov_linha(row)
    source.pop("poder_aquisitivo_data")
    assert not conferir(pacote([row], issuer, fontes=[source]))[0]
    source = _prov_linha(row)
    source["contexto_documental_sha256"] = None
    assert not conferir(pacote([row], issuer, fontes=[source]))[0]


def test_default_sem_opcao_continua_sem_os_estoques(monkeypatch):
    out, _ = coletor(monkeypatch, ativo=False)
    assert out.empty and "contexto_documental" not in out


@pytest.mark.parametrize("issuer", ISSUERS)
def test_precedencia_SEC_em_chave_presente_e_lacuna_especifica(monkeypatch, issuer):
    import hashlib
    import json

    cik = "0001234567"  # Cadastro e Companyfacts inteiramente DADOS SIMULADOS.
    ticker = "GGAL" if issuer == "AR_GALICIA" else "SUPV"
    ticks = json.dumps(
        {
            "fields": ["cik", "name", "ticker", "exchange"],
            "data": [[1234567, "DADOS SIMULADOS", ticker, "NYSE"]],
        }
    ).encode()

    def annual(y):
        return dict(
            start=f"{y}-01-01",
            end=f"{y}-12-31",
            val=1000,
            filed="2026-01-31",
            form="20-F",
            fy=y,
            fp="FY",
            accn="0001234567-26-000001",
        )

    data = json.dumps(
        {
            "cik": 1234567,
            "entityName": "DADOS SIMULADOS",
            "facts": {
                "ifrs-full": {
                    "ProfitLoss": {"units": {"ARS": [annual(2024), annual(2025)]}},
                    "EquityAttributableToOwnersOfParent": {
                        "units": {
                            "ARS": [
                                dict(
                                    end="2025-12-31",
                                    val=1234567000,
                                    filed="2026-01-31",
                                    form="20-F",
                                    fy=2025,
                                    fp="FY",
                                    accn="0001234567-26-000001",
                                )
                            ]
                        }
                    },
                }
            },
        }
    ).encode()

    def got(key, data):
        reg = RegistroArquivo(
            key,
            "SEC",
            "https://www.sec.gov/DADOS_SIMULADOS",
            "DADOS_SIMULADOS",
            hashlib.sha256(data).hexdigest(),
            len(data),
            datetime(2026, 2, 1, tzinfo=UTC),
            "microseconds",
        )
        return reg, data

    extra = {
        "SEC/mapa/company_tickers_exchange.json": got(
            "SEC/mapa/company_tickers_exchange.json", ticks
        ),
        f"SEC/companyfacts/CIK{cik}.json": got(f"SEC/companyfacts/CIK{cik}.json", data),
    }
    arq = ArquivoMemoria((issuer,), extra=extra)
    # Universo cadastral da fixture mantém ações/capital/preço ausentes.
    uni = universo((issuer,))
    uni.lines.index = [ticker]
    uni.lines["line_type"] = "ADR"
    uni.issuers["primary_ticker"] = ticker
    monkeypatch.setattr(publico, "_arquivo", lambda *_: arq)
    out = publico.demonstrativos(
        (issuer,),
        DIA,
        offline=True,
        universe=uni,
        selecionar_ri_observado=True,
        patrimonio_owners_observado=True,
        conhecimento_ate=CORTE,
        complementar_yahoo=False,
    )
    stock = out[out.item.eq("patrimonio_controladores")]
    current = stock[stock.period_end.eq(pd.Timestamp("2026-06-30"))]
    old = stock[stock.period_end.eq(pd.Timestamp("2025-12-31"))]
    assert len(current) == 1 and current.fonte.eq("RI").all()
    assert Decimal(str(current.value.iloc[0])) == esperado(issuer)[0]
    assert not old.empty and old.fonte.eq("SEC").all() and old.value.eq(1234567000).all()
    assert out[out.item.eq("lucro_liquido")].fonte.eq("SEC").all()


# Regressões portáveis derivadas dos 12 contraexemplos não autores, teste literal
# SHA13d1a5... de BANCOS_OWNERS_NAO_AUTOR. Não são valores financeiros novos.
@pytest.mark.parametrize("issuer", ISSUERS)
@pytest.mark.parametrize("origem", ("SEC", "CVM", "YAHOO"))
def test_v2_origem_nativa_vinculada_ao_registro_RI(issuer, origem):
    row = selecionados(issuer).iloc[-1].copy()
    row["fonte"] = origem
    with pytest.raises(ExtracaoRecusada):
        contexto_documental(row)


@pytest.mark.parametrize("issuer", ISSUERS)
@pytest.mark.parametrize("origem", ("SEC", "CVM", "YAHOO"))
def test_v2_origem_da_ultima_fonte_vinculada_ao_registro_RI(issuer, origem):
    rows = [r for _, r in selecionados(issuer).iterrows()]
    sources = [_prov_linha(r) for r in rows]
    sources[-1]["fonte"] = origem
    assert not conferir(pacote(rows, issuer, fontes=sources))[0]


@pytest.mark.parametrize("issuer", ISSUERS)
@pytest.mark.parametrize("posicao", ("topo", "ultima_fonte"))
@pytest.mark.parametrize("ausencia", ("campo_ausente", "pd_NA"))
def test_v2_origem_opcional_ausente_nao_e_inferida(issuer, posicao, ausencia):
    rows = [r.copy() for _, r in selecionados(issuer).iterrows()]
    if posicao == "topo":
        row = rows[-1]
        row = row.drop(labels=["fonte"]) if ausencia == "campo_ausente" else row.copy()
        if ausencia == "pd_NA":
            row["fonte"] = pd.NA
        assert contexto_documental(row) == contexto_documental(rows[-1])
        assert "fonte" not in row or row["fonte"] is pd.NA
    else:
        sources = [_prov_linha(r) for r in rows]
        if ausencia == "campo_ausente":
            sources[-1].pop("fonte")
        else:
            sources[-1]["fonte"] = pd.NA
        assert conferir(pacote(rows, issuer, fontes=sources))[0]
        assert "fonte" not in sources[-1] or sources[-1]["fonte"] is pd.NA


# Derivação portátil dos quatro contraexemplos da revisão V2 recebida.
@pytest.mark.parametrize("issuer", ISSUERS)
def test_v3_identificador_interno_objeto_vazio_nao_e_ausencia(issuer):
    row = selecionados(issuer).iloc[-1].copy()
    row["fonte"] = deepcopy(_prov_linha(row))
    assert row["fonte"]["fonte"] == "RI"
    row["fonte"]["fonte"] = {}
    with pytest.raises(ExtracaoRecusada):
        contexto_documental(row)


@pytest.mark.parametrize("issuer", ISSUERS)
def test_v3_identificador_objeto_vazio_ultimo_participante_nao_e_ausencia(issuer):
    rows = [row for _, row in selecionados(issuer).iterrows()]
    sources = [_prov_linha(row) for row in rows]
    assert sources[-1]["fonte"] == "RI"
    sources[-1]["fonte"] = {}
    assert not conferir(pacote(rows, issuer, fontes=sources))[0]


@pytest.mark.parametrize("issuer", ISSUERS)
@pytest.mark.parametrize("posicao", ("topo_estruturado", "ultima_fonte"))
def test_v3_identificador_omitido_none_pdNA_continua_opcional(issuer, posicao):
    # As únicas representações exercidas são ausência, None e pd.NA,
    # no mesmo caminho real do contraexemplo; não infere rótulo de origem.
    for ausencia in ("omissao", None, pd.NA):
        rows = [row.copy() for _, row in selecionados(issuer).iterrows()]
        if posicao == "topo_estruturado":
            row = rows[-1]
            row["fonte"] = deepcopy(_prov_linha(row))
            if ausencia is None or ausencia is pd.NA:
                row["fonte"]["fonte"] = ausencia
            else:
                row["fonte"].pop("fonte")
            assert contexto_documental(row)
        else:
            sources = [_prov_linha(row) for row in rows]
            if ausencia is None or ausencia is pd.NA:
                sources[-1]["fonte"] = ausencia
            else:
                sources[-1].pop("fonte")
            assert conferir(pacote(rows, issuer, fontes=sources))[0]
