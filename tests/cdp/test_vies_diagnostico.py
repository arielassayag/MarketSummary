"""Oráculos de metrologia NIST e protocolo puro; pares são DADOS SIMULADOS."""

import builtins
import math
import socket
from dataclasses import FrozenInstanceError, replace
from datetime import UTC, datetime, timedelta, timezone, tzinfo
from pathlib import Path

import pytest

from cdp.risk.vies_diagnostico import (
    ParRisco,
    PoliticaVies,
    ReferenciaCorpo,
    diagnosticar_vies_risco,
    intervalo_desvio_nist,
)

NIST = (15.83, 16.01, 16.24, 16.42, 15.33, 15.44, 16.88, 16.31)
INICIO = datetime(2026, 11, 13, tzinfo=UTC)
CORTE = datetime(2026, 11, 30, tzinfo=UTC)
REF = ReferenciaCorpo("corpo-teste", "a" * 64, "tupla-em-memoria", "SIMULATED_TEST_ONLY")


def politica(**mudancas):
    return replace(PoliticaVies(CORTE, 2, "nist_bonett_iid_floor_v1",
                                "DECLARADA_NAO_PROVADA", 0.05), **mudancas)


def par(i=0, z=1.0, **mudancas):
    inicio = INICIO + timedelta(days=i)
    return replace(ParRisco(
        id=f"simulado-{i}", inicio_utc=inicio, fim_utc=inicio + timedelta(days=1),
        previsao_selada_utc=inicio - timedelta(hours=1),
        modelo_as_of_utc=inicio - timedelta(days=1),
        carteira_abertura_hash="b" * 64, previsao_carteira_hash="b" * 64,
        forecast_body_ref=REF, outcome_body_ref=REF,
        retorno_precos_usd=z * 0.01, sigma_periodo=0.01,
        horizonte_sessoes=1, unidade="fracao_USD_mesmo_periodo",
        nao_reprecificadas=0, motivo_ausencia=None, origem="SIMULADA_TESTE",
    ), **mudancas)


def pares(valores=NIST):
    return tuple(par(i, z) for i, z in enumerate(valores))


class TextoCallback(str):
    def __eq__(self, outro):
        raise AssertionError("Não chamar igualdade de string fornecida")

    def __ne__(self, outro):
        raise AssertionError("Não chamar desigualdade de string fornecida")

    def strip(self):
        raise AssertionError("Não chamar strip de string fornecida")


class FloatCallback(float):
    def __truediv__(self, outro):
        raise AssertionError("Não chamar aritmética fornecida")


class TuplaCallback(tuple):
    def __iter__(self):
        raise AssertionError("Não iterar contêiner fornecido")


class FusoCallback(tzinfo):
    def utcoffset(self, dt):
        raise AssertionError("Não chamar fuso fornecido")


class DataCallback(datetime):
    def __le__(self, outro):
        raise AssertionError("Não comparar data fornecida")


def test_oraculo_nist_publicado_quatro_casas():
    """NIST informa s=.5168 e intervalo Bonett de σ [.3263,1.0841]."""
    r = intervalo_desvio_nist(NIST, alpha=0.05)
    assert r.estado == "CONDICIONAL_IID"
    assert r.desvio == pytest.approx(0.5168, abs=0.00005)
    assert r.inferior == pytest.approx(0.3263, abs=0.00005)
    assert r.superior == pytest.approx(1.0841, abs=0.00005)
    assert r.cortadas_por_cauda == 2
    assert r.proporcao_corte == 0.25
    assert r.media_aparada == pytest.approx((15.83 + 16.01 + 16.24 + 16.31) / 4)
    assert "floor CDP" in r.limite


@pytest.mark.parametrize("multiplicador,deslocamento", [(2.0, 0.0), (1.0, 100.0), (-1.0, 0.0)])
def test_equivariança_escala_e_translacao(multiplicador, deslocamento):
    original = intervalo_desvio_nist(NIST, alpha=0.05)
    r = intervalo_desvio_nist(tuple(multiplicador * v + deslocamento for v in NIST),
                              alpha=0.05)
    assert r.desvio == pytest.approx(abs(multiplicador) * original.desvio)
    assert r.inferior == pytest.approx(abs(multiplicador) * original.inferior)
    assert r.superior == pytest.approx(abs(multiplicador) * original.superior)
    assert r.curtose_ajustada == pytest.approx(original.curtose_ajustada)


def test_permutacao_e_caudas_originais_nao_descartadas():
    r = intervalo_desvio_nist(NIST, alpha=0.05)
    assert r == intervalo_desvio_nist(tuple(reversed(NIST)), alpha=0.05)
    # O desvio do miolo é muito menor; o intervalo usa todas as oito observações.
    assert r.desvio > 0.5
    assert r.media_aparada != sum(NIST) / len(NIST)


@pytest.mark.parametrize("n", range(5))
def test_amostra_curta_preserva_ausencia(n):
    r = intervalo_desvio_nist(NIST[:n], alpha=0.05)
    assert r.estado == "INSUFICIENTE" and r.motivo == "N_ATE_QUATRO"
    assert r.n == n and r.inferior is None and r.superior is None
    assert r.curtose_ajustada is None


def test_variancia_nula_nao_gera_intervalo_falso():
    r = intervalo_desvio_nist((0.0,) * 8, alpha=0.05)
    assert r.desvio == 0.0
    assert r.estado == "INSUFICIENTE" and r.motivo == "VARIANCIA_NULA"
    assert r.inferior is None and r.superior is None


@pytest.mark.parametrize("alpha", [0.0, -0.05, 0.5, 1.0, math.nan, math.inf, 1, True, "0.05"])
def test_alpha_invalido_recusado(alpha):
    with pytest.raises(ValueError):
        intervalo_desvio_nist(NIST, alpha=alpha)


@pytest.mark.parametrize("v", [math.nan, math.inf, -math.inf, 1, True, None, FloatCallback(1.0)])
def test_amostra_exige_float_finito_exato(v):
    with pytest.raises(ValueError, match="float nativo"):
        intervalo_desvio_nist((v,) + NIST, alpha=0.05)


@pytest.mark.parametrize("amostra", [list(NIST), TuplaCallback(NIST), None])
def test_amostra_exige_tupla_sem_callback(amostra):
    with pytest.raises(ValueError, match="tupla nativa"):
        intervalo_desvio_nist(amostra, alpha=0.05)


@pytest.mark.parametrize("amostra,alpha", [(NIST, 1e-300), ((1.7e308, -1.7e308) * 4, 0.05)])
def test_aritmetica_nao_representavel_e_insuficiencia(amostra, alpha):
    r = intervalo_desvio_nist(amostra, alpha=alpha)
    assert r.estado == "INSUFICIENTE"
    assert r.motivo == "ARITMETICA_NAO_REPRESENTAVEL"
    assert r.inferior is None and r.superior is None
    for v in (r.desvio, r.curtose_ajustada, r.proporcao_corte, r.media_aparada):
        assert v is None or math.isfinite(v)


def test_diagnostico_condicional_preserva_mask_ref_e_entradas():
    entradas, cfg = pares(), politica()
    r = diagnosticar_vies_risco(entradas, cfg)
    assert r.n_total == r.n == 8
    assert r.incluidos == tuple(p.id for p in entradas) and r.excluidos == ()
    assert r.estado == "CONDICIONAL_IID" and r.interpretacao == "INCONCLUSIVO"
    assert r.intervalo.inferior == pytest.approx(0.3263, abs=0.00005)
    assert r.intervalo.superior == pytest.approx(1.0841, abs=0.00005)
    assert r.vinculos_declarados[0][1:5] == (REF.body_id, REF.sha256, REF.locator, REF.kind)
    assert any("DADOS SIMULADOS" in s for s in r.limites)
    assert any("não autenticam" in s for s in r.limites)
    assert entradas == pares() and cfg == politica()


@pytest.mark.parametrize("escala,interpretacao", [(0.1, "SOBREPREVISAO_CONDICIONAL"),
                                                 (10.0, "SUBPREVISAO_CONDICIONAL")])
def test_interpretacao_condicional_sem_promover_mandato(escala, interpretacao):
    r = diagnosticar_vies_risco(pares(tuple(v * escala for v in NIST)), politica())
    assert r.interpretacao == interpretacao
    assert "não foi comprovada" in r.intervalo.limite


def test_zero_legitimo_incluido_sem_imputacao():
    r = diagnosticar_vies_risco(pares((0.0,) * 8), politica())
    assert r.n == 8 and not r.excluidos
    assert r.media_z == r.sd_z == r.rms_z == 0.0
    assert r.intervalo.motivo == "VARIANCIA_NULA"
    assert r.excesso_curtose_descritivo is None
    assert r.interpretacao == "SEM_INFERENCIA"


@pytest.mark.parametrize("mudancas", [dict(retorno_precos_usd=None), dict(sigma_periodo=None),
                                      dict(nao_reprecificadas=1)])
def test_ausente_excluido_com_motivo_sem_zero(mudancas):
    entrada = par(8, motivo_ausencia="BARRA_AUSENTE", **mudancas)
    r = diagnosticar_vies_risco(pares() + (entrada,), politica())
    assert r.n_total == 9 and r.n == 8
    assert r.excluidos == ((entrada.id, "BARRA_AUSENTE"),)
    assert entrada.id not in r.incluidos
    assert r.media_z == diagnosticar_vies_risco(pares(), politica()).media_z


@pytest.mark.parametrize("mudancas", [dict(retorno_precos_usd=None), dict(sigma_periodo=None),
                                      dict(motivo_ausencia="inventado")])
def test_mascara_incoerente_recusada(mudancas):
    with pytest.raises(ValueError, match="Motivo de ausência"):
        diagnosticar_vies_risco((par(**mudancas),), politica())


@pytest.mark.parametrize("hipotese", ["DEPENDENCIA_CONHECIDA", "DESCONHECIDA"])
def test_iid_nao_declarada_somente_descricao(hipotese):
    r = diagnosticar_vies_risco(pares(), politica(hipotese_iid=hipotese))
    assert r.estado == "DESCRITIVO" and r.intervalo is None
    assert r.motivo == "IID_NAO_DECLARADA_SEM_INFERENCIA"
    assert r.n == 8 and r.sd_z > 0.5


def test_sobreposicao_bloqueia_inferencia_sem_apagar_descricao():
    entradas = pares()
    entradas = (replace(entradas[0], fim_utc=INICIO + timedelta(days=1, hours=1)),) + entradas[1:]
    r = diagnosticar_vies_risco(entradas, politica())
    assert r.sobreposicao and r.estado == "DESCRITIVO"
    assert r.motivo == "SOBREPOSICAO_SEM_INFERENCIA_IID" and r.intervalo is None
    assert r.n == 8
    assert not diagnosticar_vies_risco(pares(), politica()).sobreposicao


def test_metodo_descritivo_nao_exige_iid_nem_inventa_intervalo():
    r = diagnosticar_vies_risco(pares(), politica(metodo_inferencia="descritivo",
                                               hipotese_iid="DESCONHECIDA"))
    assert r.estado == "DESCRITIVO" and r.motivo is None
    assert r.intervalo is None and r.interpretacao == "SEM_INFERENCIA"


@pytest.mark.parametrize("n", [0, 1])
def test_pares_insuficientes_preservam_contagem(n):
    r = diagnosticar_vies_risco(pares()[:n], politica())
    assert r.estado == "INSUFICIENTE" and r.n == r.n_total == n
    assert r.media_z is None and r.sd_z is None and r.intervalo is None


def test_minimo_declarado_nao_e_relaxado():
    r = diagnosticar_vies_risco(pares(), politica(minimo_descritivo=9))
    assert r.estado == "INSUFICIENTE" and r.n == 8


@pytest.mark.parametrize("mudancas", [
    dict(sigma_periodo=0.0), dict(sigma_periodo=-0.01), dict(sigma_periodo=True),
    dict(retorno_precos_usd=math.nan), dict(retorno_precos_usd=FloatCallback(0.01)),
    dict(horizonte_sessoes=True), dict(nao_reprecificadas=-1),
    dict(unidade="percentual"), dict(unidade=TextoCallback("fracao_USD_mesmo_periodo")),
    dict(id=TextoCallback("simulado-0")), dict(origem="publica"),
    dict(carteira_abertura_hash="A" * 64), dict(previsao_carteira_hash="c" * 64),
    dict(forecast_body_ref=replace(REF, kind="ORIGINAL_REF_NOT_REVALIDATED")),
    dict(outcome_body_ref=replace(REF, locator="")),
    dict(retorno_precos_usd=1e308, sigma_periodo=1e-308),
])
def test_par_malformado_recusado_sem_coercao(mudancas):
    with pytest.raises(ValueError):
        diagnosticar_vies_risco((par(**mudancas),), politica())


@pytest.mark.parametrize("campo", ["inicio_utc", "fim_utc", "previsao_selada_utc", "modelo_as_of_utc"])
@pytest.mark.parametrize("data", [INICIO.replace(tzinfo=None),
                                 INICIO.replace(tzinfo=timezone(timedelta(hours=1))),
                                 INICIO.replace(tzinfo=FusoCallback()),
                                 INICIO.replace(fold=1),
                                 DataCallback(2026, 11, 13, tzinfo=UTC)])
def test_datas_exatas_utc_sem_callback(campo, data):
    with pytest.raises(ValueError, match="datetime nativo em UTC"):
        diagnosticar_vies_risco((par(**{campo: data}),), politica())


@pytest.mark.parametrize("mudancas", [
    dict(previsao_selada_utc=INICIO + timedelta(seconds=1)),
    dict(modelo_as_of_utc=INICIO + timedelta(seconds=1)),
    dict(fim_utc=INICIO), dict(fim_utc=CORTE + timedelta(seconds=1)),
])
def test_ordem_temporal_recusada(mudancas):
    with pytest.raises(ValueError):
        diagnosticar_vies_risco((par(**mudancas),), politica())


def test_modelo_entre_selo_e_inicio_e_contradicao_recusada():
    entrada = par(modelo_as_of_utc=INICIO - timedelta(minutes=30))
    assert entrada.previsao_selada_utc < entrada.modelo_as_of_utc < entrada.inicio_utc
    with pytest.raises(ValueError, match="Modelo posterior ao selo"):
        diagnosticar_vies_risco((entrada,), politica())
    # Igualdade de selo e as-of é cronologia válida, sem prova de disponibilidade.
    valido = replace(entrada, modelo_as_of_utc=entrada.previsao_selada_utc)
    r = diagnosticar_vies_risco((valido,), politica())
    assert r.n == 1 and r.estado == "INSUFICIENTE"


@pytest.mark.parametrize("alvo", ["id", "periodo", "horizonte"])
def test_duplicata_ou_horizonte_incompativel_recusado(alvo):
    entrada = par(1)
    if alvo == "id":
        entrada = replace(entrada, id="simulado-0")
    elif alvo == "periodo":
        entrada = replace(entrada, inicio_utc=INICIO, fim_utc=INICIO + timedelta(days=1),
                          previsao_selada_utc=INICIO)
    else:
        entrada = replace(entrada, horizonte_sessoes=2)
    with pytest.raises(ValueError):
        diagnosticar_vies_risco((par(), entrada), politica())


@pytest.mark.parametrize("mudancas", [dict(minimo_descritivo=1), dict(minimo_descritivo=True),
                                      dict(corte_utc=CORTE.replace(tzinfo=None)),
                                      dict(metodo_inferencia=TextoCallback("descritivo")),
                                      dict(hipotese_iid="comprovada"), dict(alpha=True)])
def test_politica_malformada_recusada(mudancas):
    with pytest.raises(ValueError):
        diagnosticar_vies_risco(pares(), politica(**mudancas))


def test_objetos_subclasses_nao_viram_autoridade():
    class PoliticaLivre(PoliticaVies):
        def __getattribute__(self, nome):
            raise AssertionError("Não ler atributo de política livre")

    class RefLivre(ReferenciaCorpo):
        def __getattribute__(self, nome):
            raise AssertionError("Não ler atributo de referência livre")

    class ParLivre(ParRisco):
        def __getattribute__(self, nome):
            raise AssertionError("Não ler atributo de par livre")

    cfg = PoliticaLivre(CORTE, 2, "descritivo", "DESCONHECIDA", 0.05)
    ref = RefLivre("corpo", "a" * 64, "locator", "SIMULATED_TEST_ONLY")
    p = par()
    livre = object.__new__(ParLivre)
    for obj, pol in ((pares(), cfg), ((replace(p, forecast_body_ref=ref),), politica()),
                     ((livre,), politica()), (TuplaCallback(pares()), politica())):
        with pytest.raises(ValueError):
            diagnosticar_vies_risco(obj, pol)


def test_refs_publicas_sao_apenas_declaracoes_nao_revalidadas():
    ref = replace(REF, kind="ORIGINAL_REF_NOT_REVALIDATED")
    # Nenhum número financeiro é declarado público neste controle de ausência.
    entrada = par(origem="PUBLICA_RECEBIDA", forecast_body_ref=ref, outcome_body_ref=ref,
                  retorno_precos_usd=None, sigma_periodo=None,
                  motivo_ausencia="DECLARACAO_SEM_CORPO")
    r = diagnosticar_vies_risco((entrada,), politica())
    assert r.n == 0 and r.estado == "INSUFICIENTE"
    assert any("não autenticam" in s for s in r.limites)
    assert not any("DADOS SIMULADOS" in s for s in r.limites)
    assert r.vinculos_declarados[0][-1] == "PUBLICA_RECEBIDA"


def test_api_sem_io_e_resultados_frozen(monkeypatch):
    def proibido(*args, **kwargs):
        raise AssertionError("API pura não pode fazer I/O")

    entradas, cfg = pares(), politica()
    with monkeypatch.context() as patch:
        patch.setattr(builtins, "open", proibido)
        patch.setattr(socket, "socket", proibido)
        patch.setattr(Path, "read_bytes", proibido)
        patch.setattr(Path, "read_text", proibido)
        r = diagnosticar_vies_risco(entradas, cfg)
        ic = intervalo_desvio_nist(NIST, alpha=0.05)
    for obj, campo in ((r, "n"), (ic, "n"), (entradas[0], "id"), (cfg, "alpha"), (REF, "locator")):
        with pytest.raises(FrozenInstanceError):
            setattr(obj, campo, None)
    assert type(r.incluidos) is type(r.excluidos) is type(r.vinculos_declarados) is tuple
    assert type(r.limites) is tuple
