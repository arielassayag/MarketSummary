"""κ em sombra: DADOS SIMULADOS fixos, sem solver, aquisição ou escrita operacional."""

from __future__ import annotations

import builtins
import copy
import socket
from dataclasses import FrozenInstanceError, replace
from datetime import date, datetime
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from cdp.config import FundConfig
from cdp.risk import idio
from cdp.risk.diagnostico import comparar_kappa_sombra
from cdp.risk.types import RiskModel

CORTE = date(2026, 10, 8)


def _retornos(n: int = 240, k: int = 3) -> pd.DataFrame:
    """Receita fixa DADOS SIMULADOS; amplitude em fração diária decimal."""
    rng = np.random.default_rng(41)
    return pd.DataFrame(rng.standard_t(5, size=(n, k)) * 0.01,
                        index=pd.bdate_range(end=CORTE, periods=n),
                        columns=[f"fator_{i}" for i in range(k)])


def _modelo(fr: pd.DataFrame | None = None) -> RiskModel:
    fatores = ["fator_0", "fator_1", "fator_2"]
    return RiskModel(
        as_of=CORTE,
        exposures=pd.DataFrame([[1.0, 0.2, -0.1]], index=["SIMULADO"], columns=fatores),
        factor_cov=pd.DataFrame(np.diag([0.04, 0.03, 0.02]), index=fatores, columns=fatores),
        specific_var=pd.Series([0.01], index=["SIMULADO"]),
        factor_returns=fr,
        specific_returns=pd.DataFrame({"SIMULADO": [np.nan, 0.001]},
                                      index=pd.bdate_range(end=CORTE, periods=2)),
        factor_groups={"fator_0": "market"},
        r_squared=pd.Series([0.5], index=["SIMULADO"]),
        meta={"aviso": "DADOS SIMULADOS", "aninhado": {"campos": [1, None]}},
    )


def _cfg(**risk) -> FundConfig:
    return FundConfig().with_overrides({"risk": {"second_order_inflation": 1.45, **risk}})


def _comparar(model: RiskModel, cfg: FundConfig | None = None):
    return comparar_kappa_sombra(model, _cfg() if cfg is None else cfg,
                                unidade_retornos="decimal_diario")


@pytest.mark.parametrize("modo", ["config", "analytic"])
def test_valores_e_origens_sao_os_ramos_nativos(modo):
    model = _modelo(_retornos())
    cfg = _cfg(second_order_inflation_mode=modo)
    sombra_cfg = cfg.with_overrides({"risk": {"second_order_inflation_mode": "analytic"}})
    atual, atual_info = idio.kappa_f(model, cfg)
    sombra, sombra_info = idio.kappa_f(model, sombra_cfg)
    out = _comparar(model, cfg)
    assert out.kappa_vigente == atual
    assert out.origem_vigente == atual_info["fonte"]
    assert out.valor_nativo_sombra == sombra
    assert out.origem_sombra == sombra_info["fonte"] == "analitico"
    assert out.candidato_disponivel and out.candidato_analitico == sombra
    assert out.config_hash == cfg.config_hash()
    assert out.config_sombra_hash == sombra_cfg.config_hash()
    assert out.corte == CORTE and out.unidade_retornos == "decimal_diario"
    assert type(out.unidade_retornos) is str
    assert out.n_observacoes == len(model.factor_returns)
    assert out.motivo is None


@pytest.mark.parametrize("limites", [(1.0, 1.01), (2.0, 2.5)])
def test_bruto_formula_clip_e_truncamento_preservam_native(limites):
    model = _modelo(_retornos())
    cfg = _cfg(second_order_inflation_bounds=limites)
    _, info = idio.kappa_f(model, cfg.with_overrides(
        {"risk": {"second_order_inflation_mode": "analytic"}}))
    out = _comparar(model, cfg)
    assert out.curtose_mediana == info["curtose_mediana"]
    assert out.curtose_usada == min(max(out.curtose_mediana, idio.KURTOSIS_CLIP[0]),
                                   idio.KURTOSIS_CLIP[1])
    bruto, t_ef = idio.kappa_formula(info["k"], cfg.risk_model.halflife_factor_corr,
                                   cfg.risk_model.newey_west_lags, out.curtose_usada)
    assert out.formula_bruta == bruto and out.t_ef == t_ef
    assert out.candidato_analitico == min(max(bruto, limites[0]), limites[1])
    assert out.limites_sombra == limites


@pytest.mark.parametrize("ausente", [None, pd.DataFrame(),
                                    pd.DataFrame(index=pd.DatetimeIndex([]))])
def test_historico_ausente_preserva_fallback_nao_candidato(ausente):
    out = _comparar(_modelo(ausente))
    assert out.valor_nativo_sombra == 1.45 and out.origem_sombra == "fallback"
    assert not out.candidato_disponivel and out.candidato_analitico is None
    assert out.formula_bruta is None and out.t_ef is None and out.k is None
    assert out.curtose_mediana is None and out.curtose_usada is None
    assert out.n_observacoes == (None if ausente is None else 0)
    assert out.motivo == "historico_ausente"


@pytest.mark.parametrize("clip", [3.0, 8.0])
def test_clip_de_curtose_e_o_nativo_em_ambas_as_extremidades(clip):
    valores = np.tile([-0.01, 0.01], 120)
    if clip == 8.0:
        valores[-1] = 1.0  # Outlier declarado da fixture; não busca por resultado.
    fr = pd.DataFrame({"fator": valores}, index=pd.bdate_range(end=CORTE, periods=240))
    out = _comparar(_modelo(fr))
    assert out.curtose_usada == clip
    if clip == 3.0:
        assert out.curtose_mediana < clip
    else:
        assert out.curtose_mediana > clip


@pytest.mark.parametrize("fr", [_retornos(n=19), _retornos().mul(0)])
def test_historico_curto_ou_constante_tem_curtose_indisponivel(fr):
    out = _comparar(_modelo(fr))
    assert out.motivo == "curtose_indisponivel"
    assert out.k == len(fr.columns) and out.n_observacoes == len(fr)
    assert out.candidato_analitico is None and out.valor_nativo_sombra == 1.45


def test_nan_total_e_nan_parcial_continuam_ausentes_sem_zero():
    total = _retornos().mul(np.nan)
    out = _comparar(_modelo(total))
    assert out.k == 0 and out.motivo == "sem_fatores_na_ultima_data"
    assert out.formula_bruta is None and out.candidato_analitico is None
    parcial = _retornos()
    parcial.iloc[0, 0] = np.nan
    parcial.iloc[-1, 1] = np.nan
    model = _modelo(parcial)
    antes = parcial.copy(deep=True)
    out = _comparar(model)
    val, info = idio.kappa_f(model, _cfg(second_order_inflation_mode="analytic"))
    assert out.k == 2 and out.valor_nativo_sombra == val
    assert out.curtose_mediana == info["curtose_mediana"]
    pd.testing.assert_frame_equal(parcial, antes)
    assert pd.isna(parcial.iloc[0, 0]) and pd.isna(parcial.iloc[-1, 1])


def test_T_ef_insuficiente_retem_origem_e_formula_indisponivel():
    model = _modelo(_retornos(k=30))
    cfg = _cfg().with_overrides({"risk_model": {"halflife_factor_corr": 5,
                                               "newey_west_lags": 3}})
    _, info = idio.kappa_f(model, cfg.with_overrides(
        {"risk": {"second_order_inflation_mode": "analytic"}}))
    out = _comparar(model, cfg)
    assert info["fonte"] == out.origem_sombra == "fallback"
    assert out.t_ef == info["t_ef"] and out.k == 30
    assert out.t_ef <= out.k and out.formula_bruta is None
    assert out.candidato_analitico is None and not out.candidato_disponivel
    assert out.motivo == "T_ef_insuficiente" and out.valor_nativo_sombra == 1.45


def test_unidade_e_obrigatoria_e_nao_tem_default():
    with pytest.raises(TypeError, match="unidade_retornos"):
        comparar_kappa_sombra(_modelo(_retornos()), _cfg())


@pytest.mark.parametrize("unidade", ["percentual_diario", "decimal_anual", "", None])
def test_recusa_unidade_incorreta(unidade):
    with pytest.raises(ValueError, match="Unidade"):
        comparar_kappa_sombra(_modelo(_retornos()), _cfg(), unidade_retornos=unidade)


@pytest.mark.parametrize("forma", ["objeto", "subclasse"])
def test_recusa_unidade_livre_antes_de_callback(forma):
    def proibido(*args):
        raise AssertionError("Callback de unidade livre foi avaliado")

    class UnidadeLivre:
        __eq__ = proibido
        __ne__ = proibido

    class TextoCustomizado(str):
        __eq__ = proibido
        __ne__ = proibido

    unidade = UnidadeLivre() if forma == "objeto" else TextoCustomizado("decimal_diario")
    with pytest.raises(ValueError, match="Unidade"):
        comparar_kappa_sombra(_modelo(_retornos()), _cfg(), unidade_retornos=unidade)


@pytest.mark.parametrize("valor", [np.inf, -np.inf])
def test_recusa_inf_sem_transformar_em_nan(valor):
    fr = _retornos()
    fr.iloc[0, 0] = valor
    with pytest.raises(ValueError, match="infinito"):
        _comparar(_modelo(fr))
    assert fr.iloc[0, 0] == valor


@pytest.mark.parametrize("dtype", [str, bool, complex])
def test_recusa_texto_bool_complexo_sem_coercao(dtype):
    fr = _retornos().astype(dtype)
    with pytest.raises(ValueError, match="dtypes"):
        _comparar(_modelo(fr))


def test_dtype_nullable_numerico_preserva_pd_NA():
    fr = _retornos().astype("Float64")
    fr.iloc[0, 0] = pd.NA
    before = fr.copy(deep=True)
    assert _comparar(_modelo(fr)).candidato_disponivel
    pd.testing.assert_frame_equal(fr, before)
    assert fr.iloc[0, 0] is pd.NA


@pytest.mark.parametrize("colunas", [["a", "a", "b"], [1, 2, 3]])
def test_recusa_colunas_ambiguas(colunas):
    fr = _retornos()
    fr.columns = colunas
    with pytest.raises(ValueError, match="nomes textuais únicos"):
        _comparar(_modelo(fr))


@pytest.mark.parametrize("problema", ["texto", "fuso", "hora", "NaT", "duplicado",
                                      "desordenado", "futuro"])
def test_recusa_indice_sem_corte_diario_inequivoco(problema):
    fr = _retornos()
    if problema == "texto":
        fr.index = fr.index.strftime("%Y-%m-%d")
    elif problema == "fuso":
        fr.index = fr.index.tz_localize("UTC")
    elif problema == "hora":
        fr.index = fr.index + pd.Timedelta(hours=1)
    elif problema == "NaT":
        fr.index = pd.DatetimeIndex([pd.NaT, *fr.index[1:]])
    elif problema == "duplicado":
        fr.index = pd.DatetimeIndex([fr.index[1], *fr.index[1:]])
    elif problema == "desordenado":
        fr = fr.iloc[::-1]
    else:
        fr.index = fr.index + pd.Timedelta(days=1)
    with pytest.raises(ValueError, match="Índice|posterior"):
        _comparar(_modelo(fr))


def test_recusa_subclasse_de_indice_antes_de_normalize():
    class IndiceCustomizado(pd.DatetimeIndex):
        def normalize(self):
            raise AssertionError("Callback de índice livre foi avaliado")

    fr = _retornos()
    fr.index = IndiceCustomizado(fr.index)
    assert type(fr.index) is IndiceCustomizado
    with pytest.raises(ValueError, match="DatetimeIndex"):
        _comparar(_modelo(fr))


def test_recusa_corte_datetime_e_objetos_alheios():
    model = _modelo(_retornos())
    with pytest.raises(ValueError, match="data civil"):
        _comparar(replace(model, as_of=datetime(2026, 10, 8)))
    with pytest.raises(ValueError, match="tipos nativos"):
        _comparar(object())
    with pytest.raises(ValueError, match="tipos nativos"):
        comparar_kappa_sombra(model, object(), unidade_retornos="decimal_diario")
    with pytest.raises(ValueError, match="DataFrame"):
        _comparar(replace(model, factor_returns=np.array([[0.01]])))


@pytest.mark.parametrize("campo", ["kappa", "banda"])
def test_recusa_configuracao_infinita_antes_produtor(campo, monkeypatch):
    cfg = _cfg(**({"second_order_inflation": float("inf")} if campo == "kappa" else
                  {"second_order_inflation_bounds": (1.2, float("inf"))}))

    def proibido(*args, **kwargs):
        raise AssertionError("Produtor chamado antes de recusar insumo não finito")

    monkeypatch.setattr(idio, "kappa_f", proibido)
    with pytest.raises(ValueError, match="configuração consumidos"):
        _comparar(_modelo(_retornos()), cfg)


def test_nao_muta_modelo_cfg_ou_campos_nao_consumidos_e_retorno_e_imutavel():
    model = _modelo(_retornos())
    antes = copy.deepcopy(model)
    cfg = _cfg()
    cfg_antes = cfg.model_dump(mode="python")
    hash_antes = cfg.config_hash()
    out = _comparar(model, cfg)
    for campo in ("exposures", "factor_cov", "factor_returns", "specific_returns"):
        pd.testing.assert_frame_equal(getattr(model, campo), getattr(antes, campo))
    for campo in ("specific_var", "r_squared"):
        pd.testing.assert_series_equal(getattr(model, campo), getattr(antes, campo))
    assert model.as_of == antes.as_of
    assert model.factor_groups == antes.factor_groups and model.meta == antes.meta
    assert cfg.model_dump(mode="python") == cfg_antes and cfg.config_hash() == hash_antes
    assert cfg.risk.second_order_inflation_mode == "config"
    assert out.config_sombra_hash != hash_antes
    with pytest.raises(FrozenInstanceError):
        out.kappa_vigente = 9.0
    assert not hasattr(out, "__dict__")


def test_comparacao_nao_acessa_arquivo_rede_ou_diretorio(monkeypatch):
    model, cfg = _modelo(_retornos()), _cfg()

    def proibido(*args, **kwargs):
        raise AssertionError("I/O inesperado na comparação")

    with monkeypatch.context() as m:
        m.setattr(builtins, "open", proibido)
        m.setattr(Path, "open", proibido)
        m.setattr(Path, "cwd", proibido)
        m.setattr(socket, "socket", proibido)
        out = _comparar(model, cfg)
    assert out.candidato_disponivel
