"""Envelope e conferência comum de dois perfis documentais finitos de NI owners.

Nenhum cálculo financeiro novo. Perfis autenticam suas células/ponte; ausência
integral mantém o legado. Derivado é composição calculada, não célula reportada.
"""

from __future__ import annotations

import hashlib
import json
import math
from collections.abc import Mapping
from copy import deepcopy
from datetime import UTC, datetime, timedelta

import pandas as pd

CAMPOS_CONTEXTO = ("contexto_documental", "contexto_documental_sha256")


class ExtracaoRecusada(ValueError):
    """Contrato documental incompleto, contraditório ou não suportado."""


def _sha(data):
    return hashlib.sha256(data).hexdigest()


def _perfil(schema):
    # Import tardio evita ciclo; allowlist fechada, nunca import determinado por payload.
    if schema == "cdp.enelchile.estoque_anual/v1":
        from . import publico_enelchile_estoque

        return publico_enelchile_estoque
    if schema == "cdp.galicia.contexto_documental/v1":
        from . import publico_galicia

        return publico_galicia
    if schema == "cdp.supervielle.contexto_documental/v1":
        from . import publico_supervielle

        return publico_supervielle
    if schema in {"cdp.galicia.patrimonio_owners/v1", "cdp.supervielle.patrimonio_owners/v1"}:
        from .publico_patrimonio_owners import perfil_schema

        return perfil_schema(schema)
    raise ExtracaoRecusada("Perfil documental desconhecido")


def _canonico(contexto):
    try:
        return json.dumps(
            contexto, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False
        ).encode()
    except (TypeError, ValueError) as exc:
        raise ExtracaoRecusada("Contexto não permite serialização canônica") from exc


def _envelope(contexto):
    return {
        "contexto_documental": deepcopy(contexto),
        "contexto_documental_sha256": _sha(_canonico(contexto)),
    }


def _instante(valor):
    try:
        dt = datetime.fromisoformat(valor) if isinstance(valor, str) else valor
        if not isinstance(dt, datetime) or dt.tzinfo is None or dt.utcoffset() != timedelta(0):
            raise ValueError
    except (TypeError, ValueError) as exc:
        raise ExtracaoRecusada("Recepção exige instante UTC explícito") from exc
    if dt > datetime.now(UTC):
        raise ExtracaoRecusada("Recepção/limite de captura futuro")
    return dt


def _validar_dependencia(dep, papel, *, issuer_id, pins):
    pin = pins[papel]
    if not isinstance(dep, Mapping) or not isinstance(dep.get("registro"), Mapping):
        raise ExtracaoRecusada("RegistroArquivo estruturado ausente/inválido")
    reg = dep["registro"]
    if (
        dep.get("papel") != papel
        or dep.get("documento") != pin["documento"]
        or reg.get("chave") != f"RI/demonstrativos/{issuer_id}/{pin['documento']}"
        or reg.get("fonte") != "RI"
        or reg.get("url") != pin["url"]
        or reg.get("sha256") != pin["sha256"]
        or reg.get("bytes") != pin["bytes"]
    ):
        raise ExtracaoRecusada("Dependência documental/RegistroArquivo divergente")
    precision = reg.get("precisao_temporal", "seconds")
    if precision not in {"seconds", "microseconds"}:
        raise ExtracaoRecusada("Precisão temporal desconhecida")
    recebido = _instante(reg.get("data_coleta"))
    limite = recebido + timedelta(seconds=1) if precision == "seconds" else recebido
    if _instante(dep.get("limite_captura")) != limite:
        raise ExtracaoRecusada("Limite não corresponde à precisão do RegistroArquivo")
    return limite


def dependencia(registro, papel, *, issuer_id, pins):
    # Validar o objeto antes de como_dict: a serialização não pode atribuir fuso a naive.
    _instante(registro.data_coleta)
    dep = {
        "papel": papel,
        "documento": pins[papel]["documento"],
        "registro": registro.como_dict(),
        "limite_captura": registro.limite_captura.isoformat(),
    }
    _validar_dependencia(dep, papel, issuer_id=issuer_id, pins=pins)
    return dep


def _conferir_fonte_documental(row, perfil, presente, *, primaria):
    """Identificadores presentes não podem contradizer a célula do perfil finito.

    Nos dois perfis, as três células reportadas vêm do PDF de junho; a ponte
    anual é dependência separada. ``documento`` da proveniência pode ser rótulo
    formatado por ``_prov_linha`` e o agregado tem rótulo de composição.
    Na fonte do componente, aceitar filename ou o rótulo determinístico normal
    dos campos nativos presentes/contexto; não usar regex ou substring livre.
    """
    pin = perfil.PINS["junho"]
    for key in ("sha256", "url"):
        if presente(row.get(key)) and row[key] != pin[key]:
            raise ExtracaoRecusada("Fonte nativa contradiz documento do perfil")
    if primaria and any(k in row for k in ("value", "valor")) and presente(row.get("documento")):
        if row["documento"] != pin["documento"]:
            raise ExtracaoRecusada("Documento nativo contradiz célula primária")
    fonte = row.get("fonte")
    if not isinstance(fonte, Mapping):
        return
    for key in ("sha256", "url"):
        if presente(fonte.get(key)) and fonte[key] != pin[key]:
            raise ExtracaoRecusada("Fonte estruturada contradiz documento do perfil")
    if primaria and "valor" in row and "coeficiente" in row and presente(fonte.get("documento")):
        if fonte["documento"] != pin["documento"]:
            # O outro produtor normal de componentes usa _prov_linha(r), com
            # rótulo formatado. Comparação exata pela mesma função; nenhum
            # começo/frequência ausente é criado ou transportado para a fonte.
            if "freq" not in row or "period_end" not in row:
                raise ExtracaoRecusada("Documento do componente contradiz célula primária")
            from ..cobertura.insumos import documento_proveniencia

            cell = row["contexto_documental"]["celula"]
            label = documento_proveniencia({
                "documento": pin["documento"], "demonstrativo": cell["demonstrativo"],
                "freq": row["freq"], "period_end": row["period_end"],
                "consolidado": cell["consolidado"],
            })
            if fonte["documento"] != label:
                raise ExtracaoRecusada("Documento do componente contradiz célula primária")


def _conferir_valor_composto(row, parts):
    """Confere valores transmitidos, na ordem/representação float nativa.

    Não cria campo ausente nem recalcula valuation. Nestes perfis finitos, a
    composição do seletor é atual + anual - comparativo (ou anual de 12 meses).
    Cada parcela mantém o valor e o coeficiente que o seletor transmitiu.
    """
    keys = [k for k in ("value", "valor") if k in row]
    if not keys:
        return

    def numero(value):
        if isinstance(value, bool):
            raise ValueError
        number = float(value)
        if not math.isfinite(number):
            raise ValueError
        return number

    try:
        valores = [numero(c["valor"]) * numero(c["coeficiente"]) for c in parts]
        calculado = valores[0]
        for valor in valores[1:]:
            calculado += valor
        if not math.isfinite(calculado) or any(numero(row[k]) != calculado for k in keys):
            raise ValueError
    except (KeyError, IndexError, TypeError, ValueError, OverflowError) as exc:
        raise ExtracaoRecusada("Valor nativo contradiz componentes da composição documental") from exc


def contexto_documental(row):
    """Coerência e vínculo por hash; não substitui autenticação dos PDFs no produtor."""

    from .publico_enelchile_estoque import conferir_vinculo_linha

    conferir_vinculo_linha(row)

    def presente(v):
        if v is None or v is pd.NA or v is pd.NaT:
            return False
        return not bool(pd.isna(v)) if pd.api.types.is_scalar(v) else True

    has = [presente(row.get(k)) for k in CAMPOS_CONTEXTO]
    if not any(has):
        return {}
    if not all(has):
        raise ExtracaoRecusada("Contexto/hash documental parcial")
    ctx, sha = [row.get(k) for k in CAMPOS_CONTEXTO]
    if not isinstance(ctx, Mapping) or sha != _sha(_canonico(ctx)):
        raise ExtracaoRecusada("Contexto documental/hash divergente")
    if ctx.get("schema") == "cdp.enelchile.estoque_anual/v1":
        from .publico_enelchile_estoque import validar_contexto

        return validar_contexto(row)
    perfil = _perfil(ctx.get("schema"))
    if not getattr(perfil, "SUPORTA_COMPOSICAO", True) and ctx.get("tipo") != "celula_primaria":
        raise ExtracaoRecusada("Perfil de estoque não autoriza composição financeira")
    if ctx.get("tipo") not in {
        "celula_primaria",
        "composicao",
    }:
        raise ExtracaoRecusada("Contexto documental desconhecido")
    if ctx.get("publicacao_primaria") is not None or ctx.get("pit_certificado") is not False:
        raise ExtracaoRecusada("Contexto observado não certifica publicação/PIT")
    for key in ("data_publicacao", "data_publicacao_primaria", "publicacao_primaria_utc"):
        if presente(row.get(key)):
            raise ExtracaoRecusada("Publicação nativa contradiz ausência documental")
    if "disponibilidade_tipo" in row and (
        not isinstance(row["disponibilidade_tipo"], str)
        or row["disponibilidade_tipo"] != "recepcao_observada"
    ):
        raise ExtracaoRecusada("Contexto exige recepção observada explícita")
    dependencies = ctx.get("dependencias")
    if not isinstance(dependencies, list) or not dependencies:
        raise ExtracaoRecusada("Dependências documentais ausentes")
    roles = [d.get("papel") for d in dependencies if isinstance(d, Mapping)]
    if (
        len(roles) != len(dependencies)
        or len(set(roles)) != len(roles)
        or not set(roles) <= set(getattr(perfil, "PAPEIS_DEPENDENCIA", ("junho", "anual")))
    ):
        raise ExtracaoRecusada("Dependências documentais incompletas/duplicadas")
    available = max(
        _validar_dependencia(d, d["papel"], issuer_id=perfil.ISSUER_ID, pins=perfil.PINS)
        for d in dependencies
    )
    if _instante(ctx.get("disponivel_desde")) != available:
        raise ExtracaoRecusada("Disponibilidade não cobre todas as dependências")
    if row.get("disponivel_desde") is not None and _instante(row["disponivel_desde"]) != available:
        raise ExtracaoRecusada("Disponibilidade nativa contradiz contexto")
    from .dimensoes_contabeis import dimensoes

    if dimensoes(row) != {
        "politica_contabil_id": perfil.POLITICA,
        "poder_aquisitivo_data": perfil.PODER,
    }:
        raise ExtracaoRecusada("Dimensões nativas contradizem documento do perfil")
    if ctx.get("tipo") == "celula_primaria":
        perfil.validar_celula(ctx, row, roles, presente)
    else:
        parts = ctx.get("componentes")
        if (
            ctx.get("reportado_no_documento") is not False
            or not isinstance(parts, list)
            or not parts
        ):
            raise ExtracaoRecusada("Agregado calculado não é célula reportada")
        # Os três fatos deste contrato documentam NI owners em ARS consolidado.
        # Filhos íntegros não legitimam outro grão no agregado consumido. Fontes
        # opcionais podem omitir esses campos; declarações explícitas devem conferir.
        for key, expected in (
            ("currency", "ARS"),
            ("consolidado", True),
            ("item", "lucro_liquido_controladores"),
        ):
            if key in row and (
                not presente(row[key])
                or not pd.api.types.is_scalar(row[key])
                or row[key] != expected
            ):
                raise ExtracaoRecusada("Grão nativo contradiz composição documental")
        all_deps = {}
        for part in parts:
            sub = contexto_documental(part)
            if not sub:
                raise ExtracaoRecusada("Composição com contexto ausente")
            for dep in part["contexto_documental"]["dependencias"]:
                prior = all_deps.setdefault(dep["papel"], dep)
                if prior != dep:
                    raise ExtracaoRecusada("Recepções conflitantes da mesma dependência")
        _conferir_valor_composto(row, parts)
        if "period_end" in row:
            try:
                # Os contextos primários comprovam os períodos; não criar início
                # ou frequência que o seletor/consumidor normal não transmitiu.
                fim_documental = max(pd.Timestamp(p["period_end"]).date() for p in parts)
                fim_nativo = pd.Timestamp(row["period_end"]).date()
                if fim_nativo != fim_documental:
                    raise ValueError
            except (KeyError, TypeError, ValueError, OverflowError) as exc:
                raise ExtracaoRecusada("Período nativo contradiz composição documental") from exc
        if list(all_deps.values()) != dependencies:
            raise ExtracaoRecusada("Dependências não cobrem a composição efetiva")
    _conferir_fonte_documental(row, perfil, presente, primaria=ctx["tipo"] == "celula_primaria")
    fonte = row.get("fonte")
    if isinstance(fonte, Mapping) and any(presente(fonte.get(k)) for k in CAMPOS_CONTEXTO):
        if contexto_documental(
            {
                **fonte,
                "politica_contabil_id": perfil.POLITICA,
                "poder_aquisitivo_data": perfil.PODER,
            }
        ) != _envelope(ctx):
            raise ExtracaoRecusada("Fonte estruturada contradiz contexto nativo")
    return _envelope(ctx)


def contexto_composicao(componentes):
    """Somente proveniência da composição; nenhum cálculo financeiro novo."""
    entries = [contexto_documental(c) for c in componentes]
    if not any(entries):
        return {}
    if not all(entries):
        raise ExtracaoRecusada("Composição documental tipada com participante ausente")
    schemas = {e["contexto_documental"]["schema"] for e in entries}
    if len(schemas) != 1:
        raise ExtracaoRecusada("Composição documental com perfis incompatíveis")
    dependencies = {}
    parts = []
    for member, fields in zip(componentes, entries, strict=True):
        parts.append(
            {
                k: deepcopy(member[k])
                for k in (
                    "item",
                    "period_start",
                    "period_end",
                    "freq",
                    "valor",
                    "coeficiente",
                    "currency",
                    "consolidado",
                    "politica_contabil_id",
                    "poder_aquisitivo_data",
                    "disponivel_desde",
                )
                if k in member
            }
            | fields
        )
        for dep in fields["contexto_documental"]["dependencias"]:
            prior = dependencies.setdefault(dep["papel"], dep)
            if prior != dep:
                raise ExtracaoRecusada("Recepções conflitantes na composição")
    deps = list(dependencies.values())
    ctx = {
        "schema": entries[0]["contexto_documental"]["schema"],
        "tipo": "composicao",
        "reportado_no_documento": False,
        "componentes": parts,
        "dependencias": deps,
        "publicacao_primaria": None,
        "pit_certificado": False,
        "disponivel_desde": max(_instante(d["limite_captura"]) for d in deps).isoformat(),
    }
    return _envelope(ctx)


def estoque_documental(row):
    """Coluna instantânea explicitamente comprovada; não cria período de fluxo."""
    envelope = contexto_documental(row)
    return bool(envelope and getattr(
        _perfil(envelope["contexto_documental"]["schema"]), "DATA_ESTOQUE_COMPROVADA", False
    ))


def frequencia_estoque_documental(row):
    """Decisão anual finita; perfis sem esta extensão mantêm a regra histórica."""
    fields = contexto_documental(row)
    if fields and fields["contexto_documental"]["schema"] == "cdp.enelchile.estoque_anual/v1":
        from .publico_enelchile_estoque import frequencia_estoque

        return frequencia_estoque(row)
    return None


def conferir_estoques_no_conjunto(fatos):
    from .publico_enelchile_estoque import validar_conjunto

    validar_conjunto(fatos)


def conferir_contexto_participantes(row):
    fields = contexto_documental(row)
    members = row.get("componentes", [])
    members_context = [contexto_documental(c) for c in members]
    if any(members_context) and not fields:
        raise ExtracaoRecusada("Contexto agregado ausente")
    if not fields:
        return
    ctx = fields["contexto_documental"]
    if ctx["tipo"] == "composicao":
        if not members:
            raise ExtracaoRecusada("Composição sem participantes efetivamente consumidos")
        def identidade(member, contrato):
            # O hash autentica o contexto do filho, não o grão do seu uso.
            # Comparar também os campos nativos que a composição transmitiu;
            # intervalos sem frequência não ganham A/Q/TTM por inferência.
            keys = ("contexto_documental_sha256", "coeficiente", "valor") + tuple(
                key for key in ("freq", "period_end") if key in contrato
            )
            values = []
            for key in keys:
                value = member.get(key)
                if key == "period_end":
                    try:
                        end = pd.Timestamp(value)
                        if pd.isna(end) or end.tzinfo is not None or end != end.normalize():
                            raise ValueError
                        value = end.date().isoformat()
                    except (TypeError, ValueError, OverflowError) as exc:
                        raise ExtracaoRecusada("Fim explícito do componente inválido") from exc
                values.append(value)
            return tuple(values)

        expected = [identidade(c, c) for c in ctx["componentes"]]
        for group in row.get("grupos_componentes", []):
            consumed = [members[i] for i in group["indices"]]
            if len(consumed) != len(ctx["componentes"]):
                raise ExtracaoRecusada("Contexto não cobre os componentes consumidos")
            actual = [identidade(c, contrato) for c, contrato in
                      zip(consumed, ctx["componentes"], strict=True)]
            if actual != expected:
                raise ExtracaoRecusada("Contexto não corresponde aos componentes consumidos")
