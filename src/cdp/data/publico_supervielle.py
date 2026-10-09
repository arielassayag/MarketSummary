"""Perfil documental Supervielle observado: três NI owners, sem normalização.

Bytes/PDF/texto conferidos neste produtor; RegistroArquivo conserva recepção
nativa. BPA anual usa ponte específica no original, nunca regra saldo→fluxo.
"""

from __future__ import annotations

import hashlib
from collections.abc import Mapping
from copy import deepcopy
from io import BytesIO

import pandas as pd
from pypdf import PdfReader

from .publico_contexto_documental import (
    ExtracaoRecusada,
    _envelope,
    _instante,
    contexto_documental,
    dependencia,
)
from .publico_supervielle_documento import POLICY, decimal_lexeme, extrair_doc

ISSUER_ID = "AR_SUPERVIELLE"
EXTRATOR_ID = "supervielle_owners_jun2026/v1"
CONTEXTO_SCHEMA = "cdp.supervielle.contexto_documental/v1"
POLITICA = POLICY
PODER = "2026-06-30"
PINS = {
    "junho": {
        "documento": "SUPV_202606_COMPLETO.pdf",
        "sha256": "320a78c3c35e4c62cb957690435d130897f7e3d0ba0ca1696dbc11a427dc67ee",
        "bytes": 5477622,
        "pages": 90,
        "kind": "JUNE26",
        "url": "https://s26.q4cdn.com/426641508/files/doc_financials/2026/q2/Financial-Statements-06-30-26.pdf",
    },
    "anual": {
        "documento": "SUPV_202512_FS.pdf",
        "sha256": "8f58fc084261c11abb635c3bbfa8303ed2fbac0b6c9e56c1525e2a2e6285aea7",
        "bytes": 3345732,
        "pages": 135,
        "kind": "ANNUAL25",
        "url": "https://s26.q4cdn.com/426641508/files/doc_financials/2025/q4/FS-Grupo-Supervielle-31-12-2025.pdf",
    },
}
RUB_BS = "Net (loss) for the period"
RUB_DRE = "Net (loss) /income for the period attributable to owners of the parent"
RUB_ANUAL_BS = "Net (loss) / income for the year"
RUB_ANUAL_DRE = "Net (loss) /income for the year attributable to owners of the parent"
RUB_NUMERADOR = "NUMERATOR / Net income for the year attributable to owners of the parent"
_CELULAS = {
    "anual2025_reexpresso": ("2025-01-01", "2025-12-31", "BPA", 6, "12/31/2025", 1, RUB_BS),
    "H1_2026_owners": ("2026-01-01", "2026-06-30", "DRE", 7, "06/30/2026", 0, RUB_DRE),
    "H1_2025_comparativo_owners": ("2025-01-01", "2025-06-30", "DRE", 7, "06/30/2025", 1, RUB_DRE),
}

# Evidência visual encerrada separada do texto; não é OCR/recibo de aquisição novo.
LEITURA_VISUAL = {
    "metodo": "observacao_visual_assistida_fechada_separada_do_texto",
    "OCR": False,
    "parser_textual_IAS34_A7211": False,
    "documento_sha256": PINS["junho"]["sha256"],
    "leitura_fechada_sha256": "873f9914f3c4bdb7267de26b972367933fc246f2f03cd0ea800554826cee8598",
    "recebimento_ROOT_sha256": "d021d62ef414cab0d125a0efa60eeac21dd992a989af3ef336acaaa752eb0116",
    "itens": [
        {
            "pagina_fisica": 14,
            "anchor": "Nota1.1 Preparation basis / IAS34",
            "pixel_sha256": "62aa5090aba66d2c849501d877d70729211c7b6674d56af5b89005d0a2aca9a8",
            "declaracao": "IAS34 consta nos pixels, não completar texto omitido",
        },
        {
            "pagina_fisica": 15,
            "anchor": "Nota1.1.3 Comparative information / A7211",
            "pixel_sha256": "b4047d1cbcde275898dcf20dcb1661cd6286fa29f7420e24166a4360f68e9838",
            "declaracao": "IAS29/A7211 e comparativos reexpressos constam nos pixels",
        },
    ],
    "limite": "Contexto documental observado destes bytes exatos, não OCR ou regra IFRS universal",
}
_ANCORAS = {
    "documento_sha256": PINS["junho"]["sha256"],
    "paginas_fisicas": [14, 15],
    "metodo": "texto_extraido_validado",
    "politica_contabil_id": POLITICA,
    "poder_aquisitivo_data": PODER,
}


def _exigir(condition, message):
    if not condition:
        raise ExtracaoRecusada(message)


def validar_pdf_observado(conteudo, papel):
    pin = PINS[papel]
    _exigir(
        isinstance(conteudo, bytes)
        and len(conteudo) == pin["bytes"]
        and hashlib.sha256(conteudo).hexdigest() == pin["sha256"],
        "Bytes/SHA PDF divergentes",
    )
    try:
        pdf = PdfReader(BytesIO(conteudo), strict=True)
        _exigir(
            not pdf.is_encrypted and len(pdf.pages) == pin["pages"], "PDF completo incompatível"
        )
        # O núcleo recebido usa índices físicos zero; não fabricar texto omitido.
        pages = {i: pdf.pages[i].extract_text() or "" for i in (2, 3, 5, 6, 7, 13, 14)}
        return {"kind": pin["kind"], "pages": pages}
    except ExtracaoRecusada:
        raise
    except (ValueError, TypeError, OSError) as exc:
        raise ExtracaoRecusada("PDF não permite extração inequívoca") from exc


def validar_documentos(pdf_junho, pdf_anual):
    """Núcleo puro textual compartilhado e ponte específica; nenhuma recepção inventada."""
    try:
        return (
            extrair_doc(validar_pdf_observado(pdf_junho, "junho"), "pages"),
            extrair_doc(validar_pdf_observado(pdf_anual, "anual"), "pages"),
        )
    except (TypeError, ValueError) as exc:
        raise ExtracaoRecusada(str(exc)) from exc


def validar_catalogo(documento):
    _exigir(isinstance(documento, Mapping), "Catálogo estruturado exigido")
    _exigir(
        documento.get("extrator") == EXTRATOR_ID
        and documento.get("issuer_id") == ISSUER_ID
        and all(documento.get(k) == PINS["junho"][k] for k in ("documento", "sha256", "url"))
        and documento.get("disponibilidade_tipo") == "recepcao_observada"
        and documento.get("data_publicacao") is None,
        "Catálogo Supervielle observado incompatível",
    )
    dep = documento.get("dependencia_anual")
    _exigir(
        isinstance(dep, Mapping)
        and all(dep.get(k) == PINS["anual"][k] for k in ("documento", "sha256", "url")),
        "Ponte anual ausente/divergente no catálogo",
    )
    expected = [
        {
            "demonstrativo": "BPA",
            "pagina": 6,
            "colunas": [{"inicio": "2025-01-01", "fim": "2025-12-31", "rotulo": "12/31/2025"}],
        },
        {
            "demonstrativo": "DRE",
            "pagina": 7,
            "colunas": [
                {
                    "inicio": "2026-01-01",
                    "fim": "2026-06-30",
                    "rotulo": "Six-month period 06/30/2026",
                },
                {
                    "inicio": "2025-01-01",
                    "fim": "2025-06-30",
                    "rotulo": "Six-month period 06/30/2025",
                },
            ],
        },
    ]
    _exigir(documento.get("tabelas") == expected, "Estrutura/períodos catálogo divergentes")


def _ponte(anual):
    return {
        "regra_universal_saldo_fluxo": False,
        "sha256_original": PINS["anual"]["sha256"],
        "poder_aquisitivo_original": "2025-12-31",
        "period_start": "2025-01-01",
        "period_end": "2025-12-31",
        "escala_ars": "1000",
        "celulas_originais": [
            {
                "pagina_pdf": page,
                "indice_coluna_zero": 0,
                "rubrica": rubric,
                "origem": origin,
                "lexema": lexeme,
            }
            for page, rubric, origin, lexeme in (
                (6, RUB_ANUAL_BS, "patrimonio_owners_BS_original", anual["bs"][0]),
                (7, RUB_ANUAL_DRE, "DRE_owners_anual_original", anual["dre_owners"][0]),
                (
                    8,
                    RUB_NUMERADOR,
                    "numerador_monetario_original_nao_EPS",
                    anual["numerador_monetario"][0],
                ),
            )
        ],
    }


def validar_celula(ctx, row, roles, presente):
    cell = ctx.get("celula")
    _exigir(isinstance(cell, Mapping), "Célula documental estruturada ausente")
    keys = (
        "period_start",
        "period_end",
        "demonstrativo",
        "pagina_pdf",
        "coluna",
        "indice_coluna_zero",
        "rubrica",
    )
    _exigir(
        tuple(cell.get(k) for k in keys) == _CELULAS.get(cell.get("papel")),
        "Identidade/período documental divergente",
    )
    _exigir(
        ctx.get("ancoras_politica_unidade") == _ANCORAS
        and ctx.get("observacao_visual_fechada") == LEITURA_VISUAL,
        "Evidência textual/visual documental ausente/divergente",
    )
    _exigir(
        ctx.get("reportado_no_documento") is True
        and ctx.get("normalizado") is False
        and ctx.get("IFRS_integral") is False
        and ctx.get("perimetro_constante_certificado") is False
        and ctx.get("reclassificacoes_declaradas") is True,
        "Limites documentais não preservados",
    )
    _exigir(
        cell.get("escala_ars") == cell.get("quantum_ars") == "1000", "Escala/quantum divergentes"
    )
    try:
        value = decimal_lexeme(cell.get("lexema")) * 1000
        _exigir(str(value) == cell.get("valor_decimal_ars"), "Lexema/valor documental divergente")
    except (TypeError, ValueError, ArithmeticError) as exc:
        raise ExtracaoRecusada("Lexema/valor documental inválido") from exc
    _exigir(
        cell.get("politica_contabil_id") == POLITICA
        and cell.get("poder_aquisitivo_data") == PODER
        and cell.get("currency") == "ARS"
        and cell.get("owners") is True
        and cell.get("consolidado") is True
        and cell.get("sha256") == PINS["junho"]["sha256"],
        "Grão documental divergente",
    )
    for k, expected in (
        ("currency", "ARS"),
        ("consolidado", True),
        ("demonstrativo", cell["demonstrativo"]),
        ("item", "lucro_liquido_controladores"),
    ):
        if k in row:
            _exigir(
                presente(row[k]) and pd.api.types.is_scalar(row[k]) and row[k] == expected,
                "Grão nativo contradiz célula documental",
            )
    for k in ("period_start", "period_end"):
        if k in row and row[k] is not None:
            native = row[k].date().isoformat() if hasattr(row[k], "date") else str(row[k])
            _exigir(native == cell[k], "Período nativo contradiz célula documental")
    for k in ("value", "valor"):
        if k in row:
            from decimal import Decimal

            try:
                _exigir(Decimal(str(row[k])) == value, "Valor nativo contradiz célula documental")
            except (TypeError, ValueError, ArithmeticError) as exc:
                raise ExtracaoRecusada("Valor nativo inválido") from exc
    annual = cell["papel"] == "anual2025_reexpresso"
    _exigir(roles == (["junho", "anual"] if annual else ["junho"]), "Dependência anual incompleta")
    if annual:
        bridge = ctx.get("ponte_especifica")
        _exigir(isinstance(bridge, Mapping), "Ponte específica ausente")
        cells = bridge.get("celulas_originais")
        _exigir(isinstance(cells, list) and len(cells) == 3, "Ponte original incompleta")
        try:
            lexical = [c["lexema"] for c in cells]
            original = {
                "bs": [lexical[0]],
                "dre_owners": [lexical[1]],
                "numerador_monetario": [lexical[2]],
            }
            _exigir(bridge == _ponte(original), "Metadados ponte específica divergentes")
            from .publico_supervielle_documento import ponte_specifica

            ponte_specifica(*lexical)
        except (KeyError, TypeError, ValueError) as exc:
            raise ExtracaoRecusada("Ponte original contraditória") from exc
    else:
        _exigir(ctx.get("ponte_especifica") is None, "Ponte atribuída a H1 indevidamente")


def fatos_pdf_observado(pdf_junho, registro_junho, pdf_anual, registro_anual, documento):
    """Recepção nativa, sem status/início HTTP presumido ou UTC histórico fixado."""
    from .publico_cvm import FATO_COLUNAS

    validar_catalogo(documento)
    jdep, adep = (
        dependencia(reg, role, issuer_id=ISSUER_ID, pins=PINS)
        for reg, role in ((registro_junho, "junho"), (registro_anual, "anual"))
    )
    june, annual = validar_documentos(pdf_junho, pdf_anual)
    rows = []
    for role, lexical in (
        ("anual2025_reexpresso", june["bs"][1]),
        ("H1_2026_owners", june["dre_owners"][0]),
        ("H1_2025_comparativo_owners", june["dre_owners"][1]),
    ):
        start, end, dem, page, column, index, rubric = _CELULAS[role]
        bridge = _ponte(annual) if role == "anual2025_reexpresso" else None
        deps = [jdep, adep] if bridge else [jdep]
        available = max(_instante(dep["limite_captura"]) for dep in deps).isoformat()
        value = decimal_lexeme(lexical) * 1000
        cell = dict(
            papel=role,
            period_start=start,
            period_end=end,
            demonstrativo=dem,
            pagina_pdf=page,
            coluna=column,
            indice_coluna_zero=index,
            rubrica=rubric,
            lexema=lexical,
            escala_ars="1000",
            quantum_ars="1000",
            valor_decimal_ars=str(value),
            sha256=PINS["junho"]["sha256"],
            owners=True,
            consolidado=True,
            currency="ARS",
            politica_contabil_id=POLITICA,
            poder_aquisitivo_data=PODER,
        )
        ctx = dict(
            schema=CONTEXTO_SCHEMA,
            tipo="celula_primaria",
            celula=cell,
            ponte_especifica=bridge,
            dependencias=deps,
            reportado_no_documento=True,
            ancoras_politica_unidade=deepcopy(_ANCORAS),
            observacao_visual_fechada=deepcopy(LEITURA_VISUAL),
            normalizado=False,
            IFRS_integral=False,
            perimetro_constante_certificado=False,
            reclassificacoes_declaradas=True,
            publicacao_primaria=None,
            pit_certificado=False,
            disponivel_desde=available,
        )
        row = dict(
            entidade=f"RI:{ISSUER_ID}",
            demonstrativo=dem,
            item="lucro_liquido_controladores",
            period_start=pd.Timestamp(start),
            period_end=pd.Timestamp(end),
            currency="ARS",
            value=float(value),
            consolidado=True,
            anual=bridge is not None,
            received_date=registro_junho.data_coleta,
            version=1,
            documento=PINS["junho"]["documento"],
            url=PINS["junho"]["url"],
            fonte="RI",
            sha256=PINS["junho"]["sha256"],
            nota="NI owners reportado BCRA; não normalizado/PIT; ponte anual específica BPA",
            pit_estimado=False,
            politica_contabil_id=POLITICA,
            poder_aquisitivo_data=PODER,
            disponibilidade_tipo="recepcao_observada",
            disponivel_desde=available,
            data_recebimento_documento=None,
            data_publicacao_primaria=None,
            **_envelope(ctx),
        )
        contexto_documental(row)
        rows.append(row)
    return pd.DataFrame(
        rows,
        columns=FATO_COLUNAS
        + [
            "fonte",
            "sha256",
            "nota",
            "pit_estimado",
            "politica_contabil_id",
            "poder_aquisitivo_data",
            "disponibilidade_tipo",
            "disponivel_desde",
            "data_recebimento_documento",
            "data_publicacao_primaria",
            "contexto_documental",
            "contexto_documental_sha256",
        ],
    )
