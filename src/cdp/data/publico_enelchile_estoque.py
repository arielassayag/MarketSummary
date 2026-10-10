"""Perfil anual SEC/USD fechado — candidato privado, não rota operacional.

DADOS SIMULADOS no exercício de integração; fontes públicas recebidas reais.
Ordinal é revisão LOCAL de um universo de um filing, sem ordem histórica SEC.
O contexto só funciona após receber os cinco corpos pinned neste processo.
"""
from __future__ import annotations

import hashlib
import json
import math
from collections.abc import Mapping
from copy import deepcopy
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from fractions import Fraction

import pandas as pd

from .publico_contexto_documental import ExtracaoRecusada

SCHEMA = "cdp.enelchile.estoque_anual/v1"
CIK = "0001659939"
END = "2025-12-31"
ACCESSION = "0001104659-26-050251"
XML_SHA = "fe0cb64242a503309cf75c5a4ed292569073ea6c0014ec351c5d5c2485566102"
ITEMS = ("divida_bruta", "arrendamentos")
DATA_ESTOQUE_COMPROVADA = True
SUPORTA_COMPOSICAO = False
MARCADOR = " [Enel estoque anual documental v1]"


@dataclass(frozen=True, slots=True)
class _FonteRecalculada:
    bodies: tuple[bytes, ...]
    cutoff: datetime
    generic_records: bytes
    anchors: bytes
    contexts: tuple[tuple[str, bytes], ...]


# Somente entradas reautenticadas por compor_fatos_enel. Nenhum PASS/DTO/callback.
_FONTES: dict[str, _FonteRecalculada] = {}


def _recusar(condition, message):
    if not condition:
        raise ExtracaoRecusada(message)


def _canon(value):
    try:
        return json.dumps(value, ensure_ascii=False, sort_keys=True,
                          separators=(",", ":"), allow_nan=False).encode()
    except (TypeError, ValueError, OverflowError, RecursionError) as exc:
        raise ExtracaoRecusada("Contexto Enel não canônico") from exc


def _sha(body):
    return hashlib.sha256(body).hexdigest()


def _instante(value):
    _recusar(isinstance(value, datetime) and value.tzinfo is not None
             and value.utcoffset() == timedelta(0), "Enel exige corte UTC explícito")
    _recusar(value <= datetime.now(UTC), "Corte Enel futuro")
    return value


def _presente(value):
    if value is None or value is pd.NA or value is pd.NaT:
        return False
    return not bool(pd.isna(value)) if pd.api.types.is_scalar(value) else True


def _data(value, *, optional=False):
    if optional and not _presente(value):
        return None
    try:
        stamp = pd.Timestamp(value)
        _recusar(pd.notna(stamp) and stamp.tzinfo is None and stamp == stamp.normalize(),
                 "Data civil Enel divergente")
        return stamp.date().isoformat()
    except (TypeError, ValueError, OverflowError) as exc:
        raise ExtracaoRecusada("Data civil Enel inválida") from exc


def _numero(value):
    _recusar(not isinstance(value, bool), "Número booleano Enel inválido")
    try:
        v = float(value)
        _recusar(math.isfinite(v), "Número Enel não finito")
        return v
    except (TypeError, ValueError, OverflowError) as exc:
        raise ExtracaoRecusada("Número Enel inválido") from exc


def _assinatura_generica(frame):
    from .publico_sec import FATO_SEC_COLUNAS

    _recusar(isinstance(frame, pd.DataFrame) and set(frame.columns) == set(FATO_SEC_COLUNAS),
             "Colunas genéricas SEC divergentes")
    records = []
    for row in frame.to_dict("records"):
        row = deepcopy(row)
        for key, value in row.items():
            if not _presente(value):
                row[key] = None
        for key in ("period_start", "period_end", "received_date"):
            row[key] = _data(row[key], optional=key == "period_start")
        row["value"] = _numero(row["value"])
        for key in ("anual", "consolidado"):
            _recusar(isinstance(row[key], bool), "Booleano genérico SEC inválido")
        row["nota"] = row["nota"] if _presente(row["nota"]) else None
        records.append(row)
    return _canon(sorted(records, key=lambda row: (row["item"], row["period_start"] or "")))


def _genericos(bodies):
    from .publico_sec import companyfacts_documento, fatos_sec

    recent = json.loads(bodies[2])["filings"]["recent"]
    indices = [i for i, acc in enumerate(recent["accessionNumber"]) if acc == ACCESSION]
    _recusar(len(indices) == 1, "Universo Enel exige exatamente um filing pinned")
    i = indices[0]
    metadata = {"accn": recent["accessionNumber"][i], "filed": recent["filingDate"][i],
                "form": recent["form"][i], "period_end": recent["reportDate"][i]}
    facts = fatos_sec(companyfacts_documento(bodies[0], CIK, metadata))
    return facts[facts["period_end"].eq(pd.Timestamp(END))].copy(), metadata


def _rederivar(bodies, cutoff):
    from enelchile_documental.leitor import InvalidStaging, preparar_enel_v4, receber_enel_v4

    _recusar(len(bodies) == 5 and all(type(b) is bytes for b in bodies),
             "Cinco fontes Enel exigem bytes imutáveis")
    cutoff = _instante(cutoff)
    try:
        body = preparar_enel_v4(*bodies, cutoff, enabled=True)
        checked = receber_enel_v4(body, _sha(body), *bodies, cutoff, enabled=True)
    except InvalidStaging as exc:
        raise ExtracaoRecusada("Fontes Enel recusadas pela rederivação V4b") from exc
    document = json.loads(checked.body)
    generic, filing = _genericos(bodies)
    records = json.loads(_assinatura_generica(generic))
    anchors = [r for r in records if r["period_start"] is not None
               and r["anual"] and r["period_end"] == END
               and 350 <= (pd.Timestamp(r["period_end"]) - pd.Timestamp(r["period_start"])).days + 1 <= 380]
    _recusar(bool(anchors), "Âncoras anuais Enel ausentes")
    identity = {"cik": CIK, "accession": ACCESSION, "source_XML_sha256": _sha(bodies[0]),
                "form": filing["form"], "period_end": filing["period_end"], "filed": filing["filed"]}
    universe = [identity]
    # Ordinal rederivado no universo unitário, não constante copiada do diagnóstico.
    versions = {entry["accession"]: ordinal for ordinal, entry in enumerate(universe, start=1)}
    key = _sha(_canon({"pins": document["source_pins"], "cutoff": cutoff.isoformat()}))
    contexts = []
    for proposed in document["proposed_contexts"]:
        ctx = {
            "schema": SCHEMA, "tipo": "estoque_calculado", "reportado_no_documento": False,
            "item": proposed["item"], "entidade": CIK, "period_start": None, "period_end": END,
            "currency": "USD", "consolidado": True, "escala": 1, "freq": "A",
            "value_USD": proposed["value_USD"], "fonte_documental_rederivada": proposed,
            "ancoras_anuais": anchors, "fontes_pinned": document["source_pins"], "fonte_cache_id": key,
            "versao": {"semantica": "revisao_local_universo_exatamente_um_filing_autenticado",
                       "universo": universe, "ordinal_local": versions[ACCESSION],
                       "ordem_republicacao_historica_conhecida": False, "source_version": None},
            "disponibilidade_tipo": "recepcao_observada",
            "disponivel_desde": document["documentary"]["provenance"]["temporal"]["availability_floor_utc"],
            "filingDate_primario": filing["filed"], "publicacao_primaria": None,
            "pit_certificado": False, "posse_executor_certificada": False,
        }
        contexts.append((ctx["item"], _canon(ctx)))
    _recusar({item for item, _ in contexts} == set(ITEMS), "Partição Enel incompleta")
    source = _FonteRecalculada(tuple(bodies), cutoff, _assinatura_generica(generic),
                              _canon(anchors), tuple(contexts))
    _FONTES[key] = source
    return generic, source


def compor_fatos_enel(fatos_genericos: pd.DataFrame, xml_body: bytes, xml_receipt_body: bytes,
                     submissions_body: bytes, index_receipts_body: bytes, metadata_receipt_body: bytes,
                     knowledge_cutoff: datetime, *, enabled: bool = False) -> pd.DataFrame:
    """Merge privado dos 20 fatos do período corrente com dois estoques autenticados.

    Default devolve cópia da entrada. Não é API de arquivamento/OP. Input genérico
    deve ser a reprodução integral deste período pela API normal SEC, sem extras.
    """
    _recusar(type(enabled) is bool, "Opt-in Enel exige bool explícito")
    _recusar(isinstance(fatos_genericos, pd.DataFrame), "Entrada genérica exige DataFrame")
    if not enabled:
        return deepcopy(fatos_genericos)
    bodies = (xml_body, xml_receipt_body, submissions_body, index_receipts_body, metadata_receipt_body)
    generic, source = _rederivar(bodies, knowledge_cutoff)
    _recusar(_assinatura_generica(fatos_genericos) == source.generic_records,
             "Fatos genéricos/leases conflitam com a fonte pinned")
    output = generic.copy(deep=True)
    example = output.iloc[0].to_dict()
    available = json.loads(source.contexts[0][1])["disponivel_desde"]
    # Todos os participantes desta instância recebem disponibilidade observada;
    # filed civil não vira recepção abril. Metadado filing permanece no contexto.
    output["fonte"] = "SEC"
    output["sha256"] = XML_SHA
    output["url"] = json.loads(source.contexts[0][1])["fonte_documental_rederivada"]["source_URL"]
    output["received_date"] = pd.Timestamp(available)
    output["data_recebimento_documento"] = available[:10]
    output["data_publicacao_primaria"] = None
    output["disponibilidade_tipo"] = "recepcao_observada"
    output["disponivel_desde"] = available
    output["contexto_documental"] = None
    output["contexto_documental_sha256"] = None
    new_rows = []
    for item, context_body in source.contexts:
        ctx = json.loads(context_body)
        value = Fraction(ctx["value_USD"])
        native_value = float(value)
        _recusar(Fraction.from_float(native_value) == value, "Valor Enel não representável exatamente no nativo")
        prior = output[output["item"].eq(item)]
        _recusar(len(prior) <= 1, "Grão genérico Enel duplicado")
        if not prior.empty:
            _recusar(_numero(prior.iloc[0]["value"]) == native_value, "Leases nativos/documentais divergem")
        output = output[~output["item"].eq(item)]
        row = {**example, "entidade": CIK, "demonstrativo": "BP", "item": item,
               "period_start": pd.NaT, "period_end": pd.Timestamp(END), "value": native_value,
               "currency": "USD", "received_date": pd.Timestamp(available),
               "version": ctx["versao"]["ordinal_local"], "documento": f"SEC 20-F {ACCESSION} ({item}){MARCADOR}",
               "consolidado": True, "anual": True, "nota": "estoque documental anual; revisão local de um filing",
               "fonte": "SEC", "sha256": XML_SHA,
               "url": ctx["fonte_documental_rederivada"]["source_URL"],
               "data_recebimento_documento": available[:10], "data_publicacao_primaria": None,
               "disponibilidade_tipo": "recepcao_observada", "disponivel_desde": available,
               "contexto_documental": ctx, "contexto_documental_sha256": _sha(context_body)}
        new_rows.append(row)
    result = pd.concat([output, pd.DataFrame(new_rows)], ignore_index=True)
    result.attrs["exercicio"] = "DADOS SIMULADOS — candidato privado; não adoção/PIT"
    validar_conjunto(result)
    return result


def _identificado(row):
    return (isinstance(row.get("documento"), str) and row["documento"].endswith(MARCADOR)) or (
        row.get("entidade") == CIK and row.get("item") == "divida_bruta" and row.get("sha256") == XML_SHA)


def validar_contexto(row):
    """Valida consumo contra contexto esperado derivado; SHA caller não dá autoridade."""
    ctx = row.get("contexto_documental")
    _recusar(isinstance(ctx, Mapping) and ctx.get("schema") == SCHEMA,
             "Contexto Enel anual ausente/inválido")
    _recusar(type(ctx.get("fonte_cache_id")) is str, "Identidade das fontes Enel inválida")
    source = _FONTES.get(ctx.get("fonte_cache_id"))
    _recusar(source is not None, "Cinco corpos Enel não recebidos neste processo")
    _recusar(type(ctx.get("item")) is str, "Item do contexto Enel inválido")
    expected = dict(source.contexts).get(ctx.get("item"))
    _recusar(expected is not None and _canon(ctx) == expected
             and row.get("contexto_documental_sha256") == _sha(expected),
             "Contexto/universo/versão Enel diverge da rederivação")
    _recusar([{"role": pin["role"], "sha256": _sha(body), "bytes": len(body)}
              for pin, body in zip(ctx["fontes_pinned"], source.bodies, strict=True)]
             == ctx["fontes_pinned"], "Fontes Enel preservadas divergem")
    _recusar(row.get("item") == ctx["item"], "Item consumido Enel divergente")
    if "entidade" in row:
        _recusar(row["entidade"] == CIK, "Entidade consumida Enel divergente")
    for key, expected_value in (("currency", "USD"), ("consolidado", True)):
        _recusar(key in row and row[key] == expected_value, "Grão consumido Enel divergente")
    _recusar("period_end" in row and _data(row["period_end"]) == END, "Fim consumido Enel divergente")
    if "period_start" in row:
        _recusar(not _presente(row["period_start"]), "Estoque Enel recebeu início de fluxo")
    values = [row[k] for k in ("value", "valor") if k in row]
    _recusar(bool(values) and all(Fraction.from_float(_numero(v)) == Fraction(ctx["value_USD"])
                                 for v in values), "Valor consumido Enel diverge dos componentes")
    if "version" in row:
        _recusar(type(row["version"]) is int and row["version"] == ctx["versao"]["ordinal_local"],
                 "Ordinal local consumido Enel divergente")
    if "freq" in row:
        _recusar(row["freq"] == "A", "Frequência consumida Enel divergente")
    for key in ("data_publicacao", "data_publicacao_primaria", "publicacao_primaria_utc"):
        if key in row:
            _recusar(not _presente(row[key]), "Publicação não é recepção observada Enel")
    _recusar(row.get("disponibilidade_tipo") == "recepcao_observada"
             and pd.Timestamp(row.get("disponivel_desde")) == pd.Timestamp(ctx["disponivel_desde"]),
             "Recepção consumida Enel divergente")
    for key in ("disponivel_desde", "received_date"):
        _recusar(key in row, "Recepção consumida Enel ausente")
        stamp = pd.Timestamp(row[key])
        _recusar(stamp.tzinfo is not None and stamp.utcoffset() == timedelta(0)
                 and stamp == pd.Timestamp(ctx["disponivel_desde"]), "Recepção consumida Enel não é UTC/floor")
    _recusar(row.get("data_recebimento_documento") == ctx["disponivel_desde"][:10],
             "Data de recepção consumida Enel divergente")
    if "escala" in row:
        _recusar(row["escala"] == 1 and not isinstance(row["escala"], bool), "Escala consumida Enel divergente")
    for key, expected_value in (("sha256", XML_SHA),
                                ("url", ctx["fonte_documental_rederivada"]["source_URL"]),
                                ("documento", f"SEC 20-F {ACCESSION} ({ctx['item']}){MARCADOR}")):
        _recusar(row.get(key) == expected_value, "Fonte consumida Enel divergente")
    return {"contexto_documental": deepcopy(ctx), "contexto_documental_sha256": _sha(expected)}


def validar_conjunto(frame):
    """Âncoras efetivamente disponíveis não podem ser removidas ou alteradas."""
    typed = []
    for row in frame.to_dict("records"):
        ctx = row.get("contexto_documental")
        if _identificado(row) or (isinstance(ctx, Mapping) and ctx.get("schema") == SCHEMA):
            validar_contexto(row)
            typed.append(row)
    if not typed:
        return
    _recusar({r["item"] for r in typed} == set(ITEMS) and len(typed) == len(ITEMS),
             "Estoques Enel/arrendamentos incompletos ou duplicados")
    _recusar_dl_previa(frame, {(r["entidade"], _data(r["period_end"])) for r in typed})
    # Conjunto bruto: contém os fluxos com intervalos reais; saída A não tem início.
    if "period_start" not in frame:
        return
    expected = json.loads(_FONTES[typed[0]["contexto_documental"]["fonte_cache_id"]].anchors)
    actual = []
    for anchor in expected:
        matches = frame[frame["item"].eq(anchor["item"])]
        _recusar(len(matches) == 1, "Âncora anual Enel ausente/duplicada")
        row = matches.iloc[0].to_dict()
        _recusar(_data(row["period_start"]) == anchor["period_start"]
                 and _data(row["period_end"]) == anchor["period_end"]
                 and _numero(row["value"]) == anchor["value"] and row["currency"] == anchor["currency"]
                 and row["entidade"] == CIK and row["anual"] is True and row["consolidado"] is True
                 and row["sha256"] == XML_SHA, "Âncora anual Enel contradiz fontes")
        actual.append(anchor)
    _recusar(_canon(actual) == _canon(expected), "Âncoras anuais Enel divergentes")


def conferir_vinculo_linha(row):
    if _identificado(row):
        validar_contexto(row)


def frequencia_estoque(row):
    validar_contexto(row)
    return "A"


def chaves_dl_recusadas(frame):
    keys = set()
    for row in frame.to_dict("records"):
        ctx = row.get("contexto_documental")
        if _identificado(row) or (isinstance(ctx, Mapping) and ctx.get("schema") == SCHEMA):
            validar_contexto(row)
            keys.add((row["entidade"], row["freq"], pd.Timestamp(row["period_end"])))
    _recusar_dl_previa(frame, {(ent, end.date().isoformat()) for ent, _, end in keys})
    return keys


def _recusar_dl_previa(frame, universe):
    """Não apaga DL; recusa a coleção somente no universo Enel comprovado."""
    entities = {entity for entity, _ in universe}
    for row in frame.to_dict("records"):
        if row.get("item") == "divida_liquida" and row.get("entidade") in entities:
            _recusar((row["entidade"], _data(row.get("period_end"))) not in universe,
                     "DL preexistente Enel sem composição autenticada dos participantes")


__all__ = ["compor_fatos_enel"]
