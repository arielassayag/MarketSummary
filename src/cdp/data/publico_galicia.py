"""Produtor candidato Galicia observado: somente três células owners June2026.

Não coleta nem calcula TTM, IPC, lucro normalizado ou confiança. O coletor
normal exige opt-in; a ponte B/S anual é documental e específica aos dois PDFs.
"""

from __future__ import annotations

import hashlib
import re
from collections.abc import Mapping
from copy import deepcopy
from decimal import Decimal
from io import BytesIO

import pandas as pd
from pypdf import PdfReader

from .publico_contexto_documental import (
    CAMPOS_CONTEXTO,
    ExtracaoRecusada,
    _envelope,
    _instante,
    contexto_documental,
    dependencia,
)
from .publico_contexto_documental import (
    conferir_contexto_participantes as conferir_contexto_participantes,
)
from .publico_contexto_documental import (
    contexto_composicao as contexto_composicao,
)

ISSUER_ID = "AR_GALICIA"


def _dependencia(registro, papel):
    return dependencia(registro, papel, issuer_id=ISSUER_ID, pins=PINS)


POLITICA = "BCRA_NIIF_exclusao_IFRS9_5.5_setor_publico_nao_financeiro"
PODER = "2026-06-30"
ESCALA = Decimal(1000)
PINS = {
    "junho": {
        "documento": "GALICIA_202606_EEFF.pdf",
        "sha256": "ff2b65222f2591c8fd9354d05b50020ee8879528233e4b0cce8a9b5b83921886",
        "bytes": 1071745,
        "pages": 139,
        "url": "https://b.gfgsa.com/app/uploads/2026/09/EEFF-GFG-30-06-2026-INGLES.pdf",
    },
    "anual": {
        "documento": "GALICIA_202512_EEFF.pdf",
        "sha256": "5589b6bf1f3e695625f0ed85e8a841becb8610fd8f46101646000b5f3c5bacf2",
        "bytes": 1785153,
        "pages": 176,
        "url": "https://b.gfgsa.com/app/uploads/2026/03/GRUPO-FINANCIERO-GALICIA-SA-31-12-2025-BYMA.pdf",
    },
}
RUB_BS = "Income from the Period/Fiscal Year"
OWN_BS = "Shareholders' Equity Attributable to Parent Company's Owners"
NON_BS = "Shareholders' Equity attributable to Non-controlling Interests"
RUB_DRE = "Net Profit (Loss) Attributable to Parent Company's Owners"
NON_DRE = "Net Income (Loss) Attributable to Non- controlling Interests"
RUB_ANUAL_BS = "Resultado del ejercicio"
OWN_ANUAL_BS = "Patrimonio neto atribuible a los propietarios de la controladora"
NON_ANUAL_BS = "Patrimonio neto atribuible a participaciones no controladoras"
RUB_ANUAL_DRE = "Resultado neto atribuible a los propietarios de la controladora"
NON_ANUAL_DRE = "Resultado neto atribuible a participaciones no controladoras"
COL_DRE = (
    "Three months as of 06.30.26 Six months as of 06.30.26 "
    "Three months as of 06.30.25 Six months as of 06.30.25"
)


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _norm(text: str) -> str:
    return " ".join(text.split())


def _exige(text: str, *pieces: str) -> None:
    if any(piece not in text for piece in pieces):
        raise ExtracaoRecusada("Contexto documental incompleto: " + ", ".join(pieces))


def _pagina(pages: dict[int, str], page: int) -> str:
    if page not in pages or not isinstance(pages[page], str) or not pages[page].strip():
        raise ExtracaoRecusada(f"Página mínima ausente/inválida: {page}")
    return _norm(pages[page])


def _cabecalho(text: str, left: str, right: str, expected: str) -> None:
    if text.count(left) != 1 or right not in text:
        raise ExtracaoRecusada("Cabeçalho ausente ou ambíguo")
    header = text.split(left, 1)[1].split(right, 1)[0].strip()
    if header != expected:
        raise ExtracaoRecusada("Identidade/ordem/largura das colunas divergente: " + header)


def _linha(text: str, rubric: str, next_label: str, width: int, separator: str) -> dict:
    if text.count(rubric) != 1 or text.count(next_label) != 1:
        raise ExtracaoRecusada("Rubrica ou limite de linha ausente/ambíguo")
    if text.index(rubric) >= text.index(next_label):
        raise ExtracaoRecusada("Rubrica fora da posição documental")
    lexemes = text.split(rubric, 1)[1].split(next_label, 1)[0].strip().split()
    unsigned = r"\d{1,3}(?:" + re.escape(separator) + r"\d{3})+"
    pattern = r"(?:-?" + unsigned + r"|\(" + unsigned + r"\))"
    if len(lexemes) != width or any(re.fullmatch(pattern, v) is None for v in lexemes):
        raise ExtracaoRecusada("Linha incompleta ou lexema/escala inválido: " + rubric)
    values = []
    for token in lexemes:
        value = Decimal(token.strip("()").replace(separator, ""))
        values.append(-value if token.startswith("(") else value)
    return {
        "rubrica": rubric,
        "lexemas": lexemes,
        "valores_milhares": values,
        "texto_linha": rubric + " " + " ".join(lexemes),
        "escala_ars": "1000",
    }


def _owners(text: str, rubric: str, subtotal: str, noncontrolling: str) -> None:
    if any(text.count(label) != 1 for label in (rubric, subtotal, noncontrolling)):
        raise ExtracaoRecusada("Bloco owners ausente ou ambíguo")
    if not text.index(rubric) < text.index(subtotal) < text.index(noncontrolling):
        raise ExtracaoRecusada("Rubrica fora do subtotal owners")


def _extrair_tabelas_privadas(junho: dict[int, str], anual: dict[int, str]) -> dict:
    """Helper de texto sem autenticação/fatos; causais SIMULADOS não burlam SHA."""
    bs, dre = _pagina(junho, 5), _pagina(junho, 6)
    for text in (bs, dre):
        _exige(
            text,
            "January 1, 2026",
            "June 30, 2026",
            "in comparative format",
            "homogeneous currency",
            "thousand Argentine pesos",
        )
    _exige(
        bs,
        "CONSOLIDATED CONDENSED INTERIM STATEMENT OF FINANCIAL POSITION",
        "GRUPO FINANCIERO GALICIA S.A.",
    )
    _exige(dre, "CONSOLIDATED CONDENSED INTERIM STATEMENT OF INCOME")
    _cabecalho(bs, "Items Notes/ Schedule", "Liabilities", "06.30.26 12.31.25")
    _cabecalho(dre, "Items Notes/ Schedule", "Interest-related Income", COL_DRE)
    _owners(bs, RUB_BS, OWN_BS, NON_BS)
    jbs = _linha(bs, RUB_BS, OWN_BS, 2, ",")
    jdre = _linha(dre, RUB_DRE, NON_DRE, 4, ",")
    if jbs["valores_milhares"][0] != jdre["valores_milhares"][1]:
        raise ExtracaoRecusada("Ponte corrente B/S p5 != DRE owners p6")
    notes13, notes14, notes15 = [_pagina(junho, p) for p in (13, 14, 15)]
    _exige(
        notes13,
        "NOTE 1. ACCOUNTING STANDARDS AND BASIS FOR PREPARATION",
        "except for the provisions of Communication “A” 6847",
        "temporary exclusion",
        "point 5.5",
        "IFRS 9",
        "Non-Financial Public Sector",
        "accounting framework established by the Argentine Central Bank",
    )
    _exige(notes14, "INDEC", "December 2016", "Unit of Measurement")
    _exige(
        notes15,
        "Comparative information, as well as all the Statements and Schedules, "
        "is stated in homogeneous currency at closing.",
        "restated in closing currency",
        "presented in Argentine pesos",
    )
    ybs, ydre = _pagina(anual, 4), _pagina(anual, 5)
    # A DRE é segregada da seção LPA na mesma página; não usar EPS ou ações.
    ydre = ydre.split("ESTADO DE RESULTADOS CONSOLIDADO - GANANCIA POR ACCIÓN", 1)[0]
    for text in (ybs, ydre):
        _exige(
            text,
            "ejercicio iniciado el 1ro. de enero de 2025",
            "finalizado el 31 de diciembre de 2025",
            "moneda homogénea",
            "miles de pesos",
        )
    _exige(ybs, "ESTADO DE SITUACIÓN FINANCIERA CONSOLIDADO", "Grupo Financiero Galicia S.A.")
    _exige(ydre, "ESTADO DE RESULTADOS CONSOLIDADO")
    _cabecalho(ybs, "Conceptos Notas", "PATRIMONIO NETO", "31.12.25 31.12.24 01.01.24")
    _cabecalho(ydre, "Conceptos Notas", "Ingresos por intereses", "31.12.25 31.12.24")
    _owners(ybs, RUB_ANUAL_BS, OWN_ANUAL_BS, NON_ANUAL_BS)
    annual_bs = _linha(ybs, RUB_ANUAL_BS, OWN_ANUAL_BS, 3, ".")
    annual_dre = _linha(ydre, RUB_ANUAL_DRE, NON_ANUAL_DRE, 2, ".")
    if annual_bs["valores_milhares"][0] != annual_dre["valores_milhares"][0]:
        raise ExtracaoRecusada("Ponte específica anual original B/S p4 != DRE owners p5")
    _exige(
        _pagina(anual, 10),
        "Comunicación “A” 6847",
        "exclusión transitoria",
        "punto 5.5",
        "NIIF 9",
        "Sector Público no Financiero",
        "BCRA",
        "diciembre 2016",
    )
    _exige(
        _pagina(anual, 11),
        "información comparativa",
        "moneda homogénea de cierre",
        "presentan en pesos argentinos",
    )
    return {
        "junho_bs": jbs,
        "junho_dre": jdre,
        "annual_bs_original": annual_bs,
        "annual_dre_original": annual_dre,
        "politica_contabil_id": POLITICA,
        "poder_aquisitivo_data": PODER,
    }


# Fronteira nova: recibos de Arquivo, sem pins dos recibos históricos privados.
CONTEXTO_SCHEMA = "cdp.galicia.contexto_documental/v1"
EXTRATOR_ID = "galicia_owners_jun2026/v1"
_CELULAS = {
    "anual2025_reexpresso": ("2025-01-01", "2025-12-31", "BPA", 5, "12.31.25", 1, RUB_BS),
    "H1_2026_owners": (
        "2026-01-01",
        "2026-06-30",
        "DRE",
        6,
        "Six months as of 06.30.26",
        1,
        RUB_DRE,
    ),
    "H1_2025_comparativo_owners": (
        "2025-01-01",
        "2025-06-30",
        "DRE",
        6,
        "Six months as of 06.30.25",
        3,
        RUB_DRE,
    ),
}
_ANCORAS = [
    {
        "pagina_pdf": 13,
        "sha256": PINS["junho"]["sha256"],
        "trechos": [
            "NOTE 1. ACCOUNTING STANDARDS AND BASIS FOR PREPARATION",
            "Communication “A” 6847",
            "temporary exclusion",
            "point 5.5",
            "IFRS 9",
            "Non-Financial Public Sector",
        ],
    },
    {
        "pagina_pdf": 14,
        "sha256": PINS["junho"]["sha256"],
        "trechos": ["Unit of Measurement", "INDEC", "December 2016"],
    },
    {
        "pagina_pdf": 15,
        "sha256": PINS["junho"]["sha256"],
        "trechos": [
            "Comparative information, as well as all the Statements and Schedules, is stated in homogeneous currency at closing.",
            "restated in closing currency",
            "presented in Argentine pesos",
        ],
    },
]


def validar_pdf_observado(conteudo, papel):
    pin = PINS[papel]
    if (
        not isinstance(conteudo, bytes)
        or len(conteudo) != pin["bytes"]
        or _sha(conteudo) != pin["sha256"]
    ):
        raise ExtracaoRecusada("Bytes/SHA PDF divergem do filing fechado")
    try:
        pdf = PdfReader(BytesIO(conteudo), strict=True)
        if pdf.is_encrypted or len(pdf.pages) != pin["pages"]:
            raise ExtracaoRecusada("PDF completo incompatível")
        required = (5, 6, 13, 14, 15) if papel == "junho" else (4, 5, 10, 11)
        return {page: pdf.pages[page - 1].extract_text() for page in required}
    except ExtracaoRecusada:
        raise
    except Exception as exc:
        raise ExtracaoRecusada("PDF não permite extração inequívoca") from exc


def validar_documentos(pdf_junho, pdf_anual):
    """Valida os dois documentos do perfil antes do registro de recepção."""
    return _extrair_tabelas_privadas(
        validar_pdf_observado(pdf_junho, "junho"), validar_pdf_observado(pdf_anual, "anual")
    )


def validar_catalogo(documento):
    if (
        documento.get("extrator") != EXTRATOR_ID
        or documento.get("issuer_id") != "AR_GALICIA"
        or documento.get("documento") != PINS["junho"]["documento"]
        or documento.get("sha256") != PINS["junho"]["sha256"]
        or documento.get("url") != PINS["junho"]["url"]
        or documento.get("disponibilidade_tipo") != "recepcao_observada"
        or documento.get("data_publicacao") is not None
    ):
        raise ExtracaoRecusada("Catálogo Galicia observado incompatível")
    dep = documento.get("dependencia_anual", {})
    if any(dep.get(k) != PINS["anual"][k] for k in ("documento", "sha256", "url")):
        raise ExtracaoRecusada("Ponte anual ausente/divergente no catálogo")


def validar_celula(ctx, row, roles, presente):
    cell = ctx.get("celula", {})
    if not isinstance(cell, Mapping):
        raise ExtracaoRecusada("Célula documental estruturada ausente")
    keys = (
        "period_start",
        "period_end",
        "demonstrativo",
        "pagina_pdf",
        "coluna",
        "indice_coluna_zero",
        "rubrica",
    )
    if (
        tuple(cell.get(k) for k in keys) != _CELULAS.get(cell.get("papel"))
        or ctx.get("ancoras_politica_unidade") != _ANCORAS
    ):
        raise ExtracaoRecusada("Identidade/período/âncoras documentais divergentes")
    if cell.get("escala_ars") != "1000" or cell.get("quantum_ars") != "1000":
        raise ExtracaoRecusada("Escala/quantum documental divergente")
    try:
        lexical = Decimal(str(cell.get("lexema")).replace(",", "")) * ESCALA
        if not lexical.is_finite() or lexical != Decimal(cell.get("valor_decimal_ars", "NaN")):
            raise ValueError
    except (ValueError, ArithmeticError) as exc:
        raise ExtracaoRecusada("Lexema/valor documental contraditório") from exc
    annual = cell.get("papel") == "anual2025_reexpresso"
    if roles != (["junho", "anual"] if annual else ["junho"]):
        raise ExtracaoRecusada("Dependência da célula/ponte anual incompleta")
    if (
        cell.get("politica_contabil_id") != POLITICA
        or cell.get("poder_aquisitivo_data") != PODER
        or cell.get("currency") != "ARS"
        or cell.get("owners") is not True
        or cell.get("consolidado") is not True
        or cell.get("sha256") != PINS["junho"]["sha256"]
    ):
        raise ExtracaoRecusada("Grão documental incompleto/divergente")
    for key, expected in (
        ("currency", "ARS"),
        ("consolidado", True),
        ("demonstrativo", cell["demonstrativo"]),
        ("item", "lucro_liquido_controladores"),
    ):
        if key in row and (
            not presente(row[key])
            or not pd.api.types.is_scalar(row[key])
            or row[key] != expected
        ):
            raise ExtracaoRecusada("Grão nativo contradiz célula documental")
    for key in ("period_start", "period_end"):
        if key in row and row[key] is not None:
            native = row[key].date().isoformat() if hasattr(row[key], "date") else str(row[key])
            if native != cell.get(key):
                raise ExtracaoRecusada("Período nativo contradiz célula documental")
    for key in ("value", "valor"):
        if key in row:
            try:
                if Decimal(str(row[key])) != Decimal(cell.get("valor_decimal_ars", "NaN")):
                    raise ValueError
            except (TypeError, ValueError, ArithmeticError) as exc:
                raise ExtracaoRecusada("Valor nativo contradiz célula documental") from exc
    if annual:
        bridge = ctx.get("ponte_especifica", {})
        if not isinstance(bridge, Mapping):
            raise ExtracaoRecusada("Ponte estruturada ausente")
        if (
            bridge.get("regra_universal_saldo_fluxo") is not False
            or bridge.get("sha256_original") != PINS["anual"]["sha256"]
            or bridge.get("bs_pagina_pdf") != 4
            or bridge.get("dre_pagina_pdf") != 5
            or bridge.get("bs_rubrica") != RUB_ANUAL_BS
            or bridge.get("dre_rubrica") != RUB_ANUAL_DRE
            or not bridge.get("bs_lexema")
            or bridge.get("bs_lexema") != bridge.get("dre_lexema")
            or bridge.get("poder_aquisitivo_original") != "2025-12-31"
            or cell.get("demonstrativo") != "BPA"
        ):
            raise ExtracaoRecusada("Ponte específica anual ausente/contraditória")
    elif cell.get("demonstrativo") != "DRE" or ctx.get("ponte_especifica") is not None:
        raise ExtracaoRecusada("Origem documental da célula divergente")

def fatos_pdf_observado(pdf_junho, registro_junho, pdf_anual, registro_anual, documento):
    """Três células owners; fórmula TTM pertence ao seletor normal, não ao PDF."""
    from .publico_cvm import FATO_COLUNAS

    validar_catalogo(documento)
    jdep, ydep = _dependencia(registro_junho, "junho"), _dependencia(registro_anual, "anual")
    tables = _extrair_tabelas_privadas(
        validar_pdf_observado(pdf_junho, "junho"), validar_pdf_observado(pdf_anual, "anual")
    )
    bridge = {
        "regra_universal_saldo_fluxo": False,
        "sha256_original": PINS["anual"]["sha256"],
        "bs_pagina_pdf": 4,
        "dre_pagina_pdf": 5,
        "bs_rubrica": RUB_ANUAL_BS,
        "dre_rubrica": RUB_ANUAL_DRE,
        "bs_lexema": tables["annual_bs_original"]["lexemas"][0],
        "dre_lexema": tables["annual_dre_original"]["lexemas"][0],
        "poder_aquisitivo_original": "2025-12-31",
        "period_start": "2025-01-01",
        "period_end": "2025-12-31",
        "escala_ars": "1000",
        "reexpressao": "Célula B/S June26; ponte original anual é documental específica, não IPC.",
    }
    specs = [
        (
            "anual2025_reexpresso",
            "2025-01-01",
            "2025-12-31",
            "BPA",
            5,
            "12.31.25",
            tables["junho_bs"],
            1,
            bridge,
        ),
        (
            "H1_2026_owners",
            "2026-01-01",
            "2026-06-30",
            "DRE",
            6,
            "Six months as of 06.30.26",
            tables["junho_dre"],
            1,
            None,
        ),
        (
            "H1_2025_comparativo_owners",
            "2025-01-01",
            "2025-06-30",
            "DRE",
            6,
            "Six months as of 06.30.25",
            tables["junho_dre"],
            3,
            None,
        ),
    ]
    rows = []
    for role, start, end, dem, page, column, extracted, index, specific in specs:
        deps = [jdep, ydep] if specific else [jdep]
        available = max(_instante(d["limite_captura"]) for d in deps).isoformat()
        cell = {
            "papel": role,
            "period_start": start,
            "period_end": end,
            "demonstrativo": dem,
            "pagina_pdf": page,
            "coluna": column,
            "indice_coluna_zero": index,
            "rubrica": extracted["rubrica"],
            "linha_literal": extracted["texto_linha"],
            "lexema": extracted["lexemas"][index],
            "escala_ars": "1000",
            "quantum_ars": "1000",
            "valor_decimal_ars": str(extracted["valores_milhares"][index] * ESCALA),
            "sha256": PINS["junho"]["sha256"],
            "owners": True,
            "consolidado": True,
            "currency": "ARS",
            "politica_contabil_id": POLITICA,
            "poder_aquisitivo_data": PODER,
        }
        ctx = {
            "schema": CONTEXTO_SCHEMA,
            "tipo": "celula_primaria",
            "celula": cell,
            "ponte_especifica": specific,
            "dependencias": deps,
            "ancoras_politica_unidade": deepcopy(_ANCORAS),
            "publicacao_primaria": None,
            "pit_certificado": False,
            "disponivel_desde": available,
        }
        row = {
            "entidade": "RI:AR_GALICIA",
            "demonstrativo": dem,
            "item": "lucro_liquido_controladores",
            "period_start": pd.Timestamp(start),
            "period_end": pd.Timestamp(end),
            "currency": "ARS",
            "value": float(extracted["valores_milhares"][index] * ESCALA),
            "consolidado": True,
            "anual": specific is not None,
            "received_date": registro_junho.data_coleta,
            "version": 1,
            "documento": PINS["junho"]["documento"],
            "url": PINS["junho"]["url"],
            "fonte": "RI",
            "sha256": PINS["junho"]["sha256"],
            "nota": "NI owners reportado; BCRA com exclusão NIIF9; não normalizado/PIT",
            "pit_estimado": False,
            "politica_contabil_id": POLITICA,
            "poder_aquisitivo_data": PODER,
            "disponibilidade_tipo": "recepcao_observada",
            "disponivel_desde": available,
            "data_recebimento_documento": None,
            "data_publicacao_primaria": None,
            **_envelope(ctx),
        }
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
            *CAMPOS_CONTEXTO,
        ],
    )
