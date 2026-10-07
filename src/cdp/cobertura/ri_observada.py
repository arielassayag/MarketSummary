"""Seleção RI privada anterior a Demonstrativos; sem modelagem ou escrita oficial."""
from __future__ import annotations

from decimal import Decimal, InvalidOperation

import pandas as pd

from ..data.ri_captura.adapter import autenticar, texto, validar_tabelas
from ..data.ri_captura.observado import sha

METODO = "captura_observada_identidade"


def ativo(params):
    method = params.sec("qualidade").get("ri_disponibilidade_metodo")
    if method not in (None, METODO):
        raise ValueError(f"RI: método de disponibilidade desconhecido: {method!r}")
    return method == METODO


def _truth(x):
    return str(x).lower() in ("true", "1")


def _base(row):
    value = str(row.get("consolidado")).lower()
    if value in ("true", "1"):
        return "consolidado"
    if value in ("false", "0"):
        return "individual"
    return None


def _amount(row):
    try:
        amount = Decimal(str(row["value"])) * Decimal(str(row.get("escala", 1)))
    except (InvalidOperation, TypeError, ValueError):
        return None
    return amount if amount.is_finite() else None


def _primary(row):
    # O contrato legado admite essas três origens primárias; lacunas não são prova.
    return (str(row.get("fonte")) in ("CVM", "SEC", "RI") and not _truth(row.get("pit_estimado"))
            and pd.notna(row.get("data_publicacao")) and pd.notna(row.get("sha256"))
            and bool(str(row.get("sha256"))) and str(row.get("url", "")).startswith("https://"))


def selecionar_demonstrativos(md, dados, params, issuer_id):
    from .insumos import NOTA_CONFERENCIA
    from .temporal import ativo as temporal_ativo
    from .temporal import validar
    if not ativo(params):
        return dados.demonstrativos, None
    contexto = autenticar(dados.ri_contexto, md)
    if issuer_id != contexto.document.issuer_id:
        return dados.demonstrativos, None
    if not temporal_ativo(params):
        raise ValueError("RI: exige a política temporal explícita .8")
    cut = validar(dados.corte_temporal)
    table, catalog = validar_tabelas(md, dados.ri_observados, dados.ri_evidencias,
                                    dados.ri_contexto, cut["conhecimento_ate"])
    raw = dados.demonstrativos.copy(deep=True)
    observed = table[table["issuer_id"] == issuer_id]
    decisions = []
    remove = set()
    additions = []
    for _, row in observed.iterrows():
        same = raw[(raw["issuer_id"] == issuer_id) & (raw["item"] == row["item"])
                   & (raw["freq"] == row["freq"])
                   & (pd.to_datetime(raw["period_end"], format="mixed", errors="coerce") == pd.Timestamp(row["period_end"]))]
        eligible = same[same["value"].notna()]
        compatible = eligible[(eligible["currency"] == row["currency"])
                              & (eligible.apply(_base, axis=1) == row["base"])]
        incompatible = eligible.drop(index=compatible.index)
        primary = compatible[compatible.apply(_primary, axis=1)]
        uncertain = compatible[~compatible.apply(_primary, axis=1)]
        estimada = uncertain[uncertain.apply(lambda r: str(r.get("fonte")) == "YAHOO"
                                             or _truth(r.get("pit_estimado")), axis=1)]
        unknown = uncertain.drop(index=estimada.index)
        observed_value = _amount(row)
        conflict = (not incompatible.empty or not unknown.empty
                    or any(_amount(r) != observed_value for _, r in primary.iterrows()))
        state = "conflito" if conflict else "selecionado" if observed_value is not None else "ausente"
        reason = ("base_moeda_ou_fonte_incompativel" if not incompatible.empty or not unknown.empty
                  else "primaria_discordante" if conflict else "saldo_primario_igual" if not primary.empty
                  else "substitui_estimada" if not estimada.empty else "completa_lacuna")
        prior = [{"fonte": str(r.get("fonte")), "sha256": None if pd.isna(r.get("sha256")) else str(r.get("sha256")),
                  "value": str(r["value"]), "currency": str(r.get("currency")), "base": _base(r)}
                 for _, r in same.iterrows()]
        decisions.append({"issuer_id": issuer_id, "item": row["item"], "freq": row["freq"],
                          "fim": row["period_end"], "base": row["base"], "moeda": row["currency"],
                          "coluna": row["coluna"], "estado": state, "motivo": reason,
                          "fato_id": row["fato_id"], "valor_bruto": row["value"], "anteriores": prior,
                          "data_publicacao": row["data_publicacao"], "received_date": row["received_date"],
                          "data_coleta": row["data_coleta"], "disponivel_desde": row["disponivel_desde"]})
        if observed_value is None:
            continue
        remove.update(same.index)
        item = row.to_dict()
        if conflict:
            item["value"] = None
            item["nota"] = NOTA_CONFERENCIA + ": conflito primário RI observado"
        additions.append(item)
    selected = raw.drop(index=list(remove))
    if additions:
        selected = pd.concat([selected, pd.DataFrame(additions)], ignore_index=True)
        # O legado arquivado pode usar ISO com hora; não deixar o parser inferir um
        # único formato e converter as datas civis autenticadas em NaT.
        selected["period_end"] = pd.to_datetime(selected["period_end"], format="mixed", errors="coerce")
        selected["data_publicacao"] = pd.to_datetime(selected["data_publicacao"], format="mixed", errors="coerce")
    trace = {"schema": "cdp.ri.selecao_privada/v2", "politica": METODO,
             "conhecimento_ate": cut["conhecimento_ate"], "issuer_id": issuer_id,
             "catalogo_sha256": catalog["catalogo_sha256"], "universe_sha256": catalog["universe_sha256"],
             "estado": catalog["envelope"]["result"]["state"] if observed.empty else "selecao_explicita",
             "disponivel_desde": catalog["envelope"]["result"]["available_since"],
             "razoes": catalog["envelope"]["result"]["reasons"], "selecao": decisions}
    return selected, trace


def finalizar_pacote(pacote, trace):
    if trace is None:
        return pacote
    evidence = dict(trace)
    evidence["fator_moeda"] = pacote.get("fator_moeda")
    evidence["moeda_modelo"] = pacote.get("moeda")
    evidence["consumidos"] = {key: pacote.get(key) for key in (
        "t.patrimonio_controladores", "t.patrimonio_liquido", "t.participacao_minoritarios",
        "item_patrimonio", "bvps", "minoritarios", "historico", "historico_fontes",
        "historico_periodos", "historico_bases", "historico_moedas", "pit_ok", "datas_estimadas")}
    evidence["fontes_consumidas"] = {key: value for key, value in pacote.get("fontes", {}).items()
                                     if key in ("t.patrimonio_controladores", "t.patrimonio_liquido",
                                                "t.participacao_minoritarios", "bvps", "minoritarios")}
    evidence["traco_sha256"] = sha(texto(evidence).encode())
    pacote["ri_observada"] = evidence
    return pacote


def validar_pacote(pacote, md, dados, params):
    """Reconstroi seleção/conversões/pacote com o fornecedor externo; hash próprio não basta."""
    if not ativo(params):
        return pacote
    from datetime import date

    from .insumos import preparar_emissor
    expected = preparar_emissor(md, dados, params, pacote["issuer_id"], date.fromisoformat(pacote["as_of"]))
    if texto(pacote) != texto(expected):
        raise ValueError("RI: pacote difere da reextração/seleção/conversão no mesmo corte")
    return pacote
