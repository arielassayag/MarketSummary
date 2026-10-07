"""Guarda privada RI dos consumidores; autoridades não viajam no JSON financeiro."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime

from ..data.ri_captura.adapter import autenticar, texto
from ..data.ri_captura.observado import instant, sha
from .ri_observada import ativo

CHAVE = "ri_observada_consumo"
HASH = "ri_contexto_sha256"


@dataclass(frozen=True, slots=True)
class FornecedorConsumoRI:
    """Objeto externo de execução, exigido novamente após serialização/reabertura.

    DadosPublicos contém ContextoRI e as autoridades exatas do v4. O fornecedor
    não é reconstruído a partir do pacote, tabela ou assinatura do contexto.
    """
    md: object
    dados: object


def emissores_autorizados(fornecedor):
    """Vínculos reautenticados externos; nunca inferidos do pacote/modelo/JSON."""
    if type(fornecedor) is not FornecedorConsumoRI:
        raise ValueError("RI consumo: fornecedor externo ausente")
    contexto = autenticar(fornecedor.dados.ri_contexto, fornecedor.md)
    return frozenset((contexto.document.issuer_id,))


def aplicavel(params, pacote):
    # Só usado depois das guardas externas nas entradas públicas dos consumidores.
    return ativo(params) and "ri_observada" in pacote


def _corte(params, fornecedor, conhecimento_ate):
    from .temporal import ativo as temporal_ativo
    from .temporal import validar
    if type(fornecedor) is not FornecedorConsumoRI:
        raise ValueError("RI consumo: fornecedor externo ausente")
    if not temporal_ativo(params) or params.versao != "2026-10.8":
        raise ValueError("RI consumo: recorte exige opt-in .8 e dois relógios explícitos")
    if not isinstance(conhecimento_ate, datetime):
        raise ValueError("RI consumo: datetime de conhecimento explícito obrigatório")
    emissores_autorizados(fornecedor)
    cut = validar(fornecedor.dados.corte_temporal)
    if instant(conhecimento_ate).isoformat() != cut["conhecimento_ate"]:
        raise ValueError("RI consumo: datetime difere do fornecedor externo")
    return cut


def validar_consumo(pacote, params, *, fornecedor=None, conhecimento_ate=None):
    """Reextrai desde o fornecedor e compara o pacote completo antes do consumo."""
    if not ativo(params):
        if "ri_observada" in pacote or any(f.get("fonte") == "RI_OBSERVADA"
                                          for f in pacote.get("fontes", {}).values() if isinstance(f, dict)):
            raise ValueError("RI consumo: pacote observado exige a política e o fornecedor explícitos")
        return pacote
    from .insumos import preparar_emissor
    from .resultado import visao
    cut = _corte(params, fornecedor, conhecimento_ate)
    issuer_id = pacote.get("issuer_id")
    if issuer_id not in emissores_autorizados(fornecedor):
        if "ri_observada" in pacote or any(f.get("fonte") == "RI_OBSERVADA"
                for f in pacote.get("fontes", {}).values() if isinstance(f, dict)):
            raise ValueError("RI consumo: emissor sem vínculo externo não recebe RI")
        return pacote
    if pacote.get("as_of") != cut["data_modelo"] or pacote.get("corte_temporal") != cut:
        raise ValueError("RI consumo: base/modelo/conhecimento incompatíveis; não retropreencher a base")
    expected = preparar_emissor(fornecedor.md, fornecedor.dados, params, issuer_id,
                               date.fromisoformat(cut["data_modelo"]))
    if "visao_resultado" in pacote:
        expected = visao(expected, params)
    if texto(pacote) != texto(expected):
        raise ValueError("RI consumo: pacote não corresponde à reextração externa e à conversão comum")
    trace = expected["ri_observada"]
    selected = [d for d in trace["selecao"] if d["freq"] == "Q" and d["estado"] == "selecionado"]
    if (any(d["item"] == "patrimonio_controladores" for d in selected)
            and expected.get("bvps") is not None
            and expected.get("item_patrimonio") != "patrimonio_controladores"):
        raise ValueError("RI consumo: PL atribuível observado não pode virar PL total silenciosamente")
    return pacote


def validar_conjunto(pacotes, params, *, fornecedor=None, conhecimento_ate=None):
    if not ativo(params):
        for p in pacotes.values():
            validar_consumo(p, params)
        return pacotes
    _corte(params, fornecedor, conhecimento_ate)
    for p in pacotes.values():
        validar_consumo(p, params, fornecedor=fornecedor, conhecimento_ate=conhecimento_ate)
    return pacotes


def _hash_contexto(ctx):
    # Evita ciclo com a assinatura EBIT, que continua cobrindo o contexto inteiro.
    return sha(texto({k: v for k, v in ctx.items()
                      if k not in (HASH, "resultado_contexto_sha256")}).encode())


def selar_contexto(ctx, pacotes, params, *, fornecedor=None, conhecimento_ate=None):
    if not ativo(params):
        return ctx
    validar_conjunto(pacotes, params, fornecedor=fornecedor, conhecimento_ate=conhecimento_ate)
    new = dict(ctx)
    new[CHAVE] = {"schema": "cdp.ri.consumo_privado/v3", "politica": "captura_observada_identidade",
                  "conhecimento_ate": instant(conhecimento_ate).isoformat(),
                  "tracos": {iid: p["ri_observada"]["traco_sha256"] for iid, p in pacotes.items()
                             if iid in emissores_autorizados(fornecedor)},
                  "fornecedor_externo_obrigatorio": True}
    new[HASH] = _hash_contexto(new)
    return new


def validar_contexto(pacote, ctx, params, *, fornecedor=None, conhecimento_ate=None):
    validar_consumo(pacote, params, fornecedor=fornecedor, conhecimento_ate=conhecimento_ate)
    if not ativo(params):
        if CHAVE in ctx:
            raise ValueError("RI consumo: contexto observado exige a política e o fornecedor explícitos")
        return pacote
    marker = ctx.get(CHAVE)
    tracos = marker.get("tracos", {}) if isinstance(marker, dict) else {}
    authorized = emissores_autorizados(fornecedor)
    iid = pacote.get("issuer_id")
    expected_trace = pacote["ri_observada"]["traco_sha256"] if iid in authorized else None
    if (not isinstance(marker, dict) or marker.get("conhecimento_ate") != instant(conhecimento_ate).isoformat()
            or not isinstance(tracos, dict) or set(tracos) - authorized
            or tracos.get(iid) != expected_trace
            or ctx.get(HASH) != _hash_contexto(ctx)):
        raise ValueError("RI consumo: contexto não corresponde aos saldos e ao corte autenticados")
    return pacote


def traco_modelo(pacote, params):
    """Regra econômica explícita; só código escolhe conceitos e calcula montantes."""
    trace = dict(pacote["ri_observada"])
    mode = params.valuation.get("minoritarios", "contabil")
    ctrl, nci = pacote.get("t.patrimonio_controladores"), pacote.get("minoritarios")
    applicable = mode if nci is not None and (mode != "proporcional" or ctrl is not None and ctrl > 0 and nci >= 0) else "indisponivel"
    trace["consumo_modelo"] = {
        "arquetipo": pacote.get("arquetipo"),
        "base_por_acao": None if pacote.get("bvps") is None else pacote.get("item_patrimonio"),
        "item_patrimonio_pacote": pacote.get("item_patrimonio"),
        "patrimonio_atribuivel": "t.patrimonio_controladores",
        "patrimonio_total": "t.patrimonio_liquido",
        "nao_controladores": "t.participacao_minoritarios",
        "b0_regra": "PL atribuível / unidades; PL total inclui NCI e não substitui o atribuível observado",
        "nci_regime_configurado": mode,
        "nci_regime_aplicavel": applicable,
        "ev_regra": "proporcional: (EV-DL)*PL_atribuivel/(PL_atribuivel+NCI)/N; contábil: (EV-DL-NCI)/N",
        "patrimonio_total_uso": "identidade contábil/diagnóstico; distinto de PL atribuível e NCI",
        "publicacao_certificada": False,
        "pit_ok": bool(pacote.get("pit_ok")),
    }
    trace["consumo_modelo_sha256"] = sha(texto(trace).encode())
    return trace


def validar_saida(modelo, pacote, ctx, params, *, fornecedor=None, conhecimento_ate=None):
    validar_contexto(pacote, ctx, params, fornecedor=fornecedor, conhecimento_ate=conhecimento_ate)
    if not ativo(params):
        if "ri_observada" in modelo:
            raise ValueError("RI consumo: saída observada exige a política e o fornecedor explícitos")
        return modelo
    if not aplicavel(params, pacote):
        if "ri_observada" in modelo:
            raise ValueError("RI consumo: saída de emissor não vinculado não recebe RI")
        return modelo
    if texto(modelo.get("ri_observada")) != texto(traco_modelo(pacote, params)):
        raise ValueError("RI consumo: saída não preserva o traço e os conceitos dos saldos autenticados")
    return modelo


def validar_modelos_etf(pacotes, modelos, params, *, fornecedor=None, conhecimento_ate=None):
    """ETFs recebem modelos já guardados; pacote RI é refeito desde autoridades."""
    validar_conjunto(pacotes, params, fornecedor=fornecedor, conhecimento_ate=conhecimento_ate)
    for iid, modelo in modelos.items():
        if iid not in pacotes:
            continue
        pacote = pacotes[iid]
        if aplicavel(params, pacote):
            if texto(modelo.get("ri_observada")) != texto(traco_modelo(pacote, params)):
                raise ValueError("RI ETF: modelo não preserva o traço externo autenticado")
        elif "ri_observada" in modelo:
            raise ValueError("RI ETF: emissor não vinculado recebeu traço RI")
    return modelos
