"""DADOS SIMULADOS: ausência ordinária de composição exige autoridade no opt-in."""
from dataclasses import replace

import pytest
from ri_fixture_portatil import BOUND
from test_ri_misto import base, params

from cdp.cobertura.etf import avaliar_etf, avaliar_etfs, calcular_etf, calcular_etfs, insumos_etf
from cdp.cobertura.motor import executar
from cdp.cobertura.ri_consumo import FornecedorConsumoRI


@pytest.fixture(scope="module")
def cadeia(tmp_path_factory):
    md, dados, p, provider = base(tmp_path_factory.mktemp("ETF-vazio-DADOS-SIMULADOS"))
    ex = executar(md, dados, p, md.as_of, ri_fornecedor=provider, conhecimento_ate=BOUND)
    return md, dados, p, provider, ex


def conjunto(ex, scope):
    if scope == "vazio":
        return {}, {}
    if scope == "legados":
        ids = set(ex.pacotes) - {"MX_AMX"}
        return ({k: ex.pacotes[k] for k in ids}, {k: ex.modelos[k] for k in ids})
    return ex.pacotes, ex.modelos


def plural(api, chain, scope, fornecedor, cut):
    md, dados, p, _, ex = chain
    pacotes, modelos = conjunto(ex, scope)
    if api == "calcular":
        return calcular_etfs({}, p, pacotes, modelos, ex.rf["valor"],
                             ri_fornecedor=fornecedor, conhecimento_ate=cut)
    # Configuração simulada sem ETFs: laço vazio normal. None nas composições
    # continua ausência, e não causa criação de ETF/composição ou zero.
    p = replace(p, etfs={**p.etfs, "etfs": []})
    dados = replace(dados, etfs={k: None for k in dados.etfs})
    return avaliar_etfs(md, dados, p, pacotes, modelos, ex.rf["valor"], ex.as_of,
                        ri_fornecedor=fornecedor, conhecimento_ate=cut)


@pytest.mark.parametrize("api", ["calcular", "avaliar"])
@pytest.mark.parametrize("scope", ["misto", "legados", "vazio"])
@pytest.mark.parametrize("ausente", ["fornecedor", "corte"])
def test_plural_vazio_exige_fornecedor_e_corte(cadeia, api, scope, ausente):
    _, _, _, provider, _ = cadeia
    fornecedor, cut = (None, BOUND) if ausente == "fornecedor" else (provider, None)
    match = "fornecedor externo ausente" if ausente == "fornecedor" else "datetime de conhecimento explícito"
    with pytest.raises(ValueError, match=match):
        plural(api, cadeia, scope, fornecedor, cut)


@pytest.mark.parametrize("api", ["calcular", "avaliar"])
@pytest.mark.parametrize("scope", ["misto", "legados", "vazio"])
def test_plural_vazio_com_autoridade_exata_preserva_vazio(cadeia, api, scope):
    _, _, _, provider, _ = cadeia
    assert plural(api, cadeia, scope, provider, BOUND) == ({} if api == "calcular" else ({}, {}))


@pytest.mark.parametrize("api", ["calcular", "avaliar"])
def test_plural_sem_optin_vazio_continua_legado(cadeia, api):
    md, dados, _, _, ex = cadeia
    p = params(False)
    pacotes = {k: v for k, v in ex.pacotes.items() if k != "MX_AMX"}
    modelos = {k: v for k, v in ex.modelos.items() if k != "MX_AMX"}
    if api == "calcular":
        assert calcular_etfs({}, p, pacotes, modelos, ex.rf["valor"]) == {}
    else:
        p = replace(p, etfs={**p.etfs, "etfs": []})
        assert avaliar_etfs(md, dados, p, pacotes, modelos, ex.rf["valor"], ex.as_of) == ({}, {})


def singular(api, chain, fornecedor, cut):
    md, dados, p, _, ex = chain
    cfg = next(c for c in p.etfs["etfs"] if c["ticker"] in md.benchmarks.columns)
    absent = replace(dados, etfs={**dados.etfs, cfg["ticker"]: None})
    if api == "insumos":
        return insumos_etf(cfg, md, absent, p, {}, ex.as_of,
                           ri_fornecedor=fornecedor, conhecimento_ate=cut)
    if api == "avaliar":
        return avaliar_etf(cfg, md, absent, p, {}, {}, ex.rf["valor"], ex.as_of,
                           ri_fornecedor=fornecedor, conhecimento_ate=cut)
    # Pacote de insumos simulado ordinário com composição explicitamente None.
    valid_provider = FornecedorConsumoRI(md, absent)
    ins = insumos_etf(cfg, md, absent, p, {}, ex.as_of,
                     ri_fornecedor=valid_provider, conhecimento_ate=BOUND)
    ins = {**ins, "composicao": None}
    return calcular_etf(ins, p, {}, {}, ex.rf["valor"],
                        ri_fornecedor=fornecedor, conhecimento_ate=cut)


@pytest.mark.parametrize("api", ["insumos", "calcular", "avaliar"])
@pytest.mark.parametrize("ausente", ["fornecedor", "corte"])
def test_singulares_composicao_none_exigem_autoridade(cadeia, api, ausente):
    _, _, _, provider, _ = cadeia
    fornecedor, cut = (None, BOUND) if ausente == "fornecedor" else (provider, None)
    match = "fornecedor externo ausente" if ausente == "fornecedor" else "datetime de conhecimento explícito"
    with pytest.raises(ValueError, match=match):
        singular(api, cadeia, fornecedor, cut)


@pytest.mark.parametrize("api", ["insumos", "calcular", "avaliar"])
def test_singulares_composicao_none_preservam_ausencia(cadeia, api):
    _, _, _, provider, _ = cadeia
    result = singular(api, cadeia, provider, BOUND)
    if api == "insumos":
        assert result["composicao"] == [] and result["composicao_aproximada"]
    else:
        assert not result["tem_alvo"]
        assert any(x["insumo"] == "composicao" for x in result["lacunas"])
