"""Núcleo textual finito derivado literalmente do estudo Supervielle fechado.

Não autentica bytes/recibos e não emite fatos. Causais em strings são DADOS SIMULADOS.
"""

import re
from decimal import Decimal

UNIT = "(Expressed in thousands of pesos in homogeneous currency)"
POLICY = "BCRA_NIIF_exclusoes_IFRS9_5.5_e_A7014"
NUM = re.compile(r"(?<![\w/])\(?\d{1,3}(?:,\d{3})+\)?(?![\w/])")


def require(condition, reason):
    if not condition:
        raise ValueError(reason)


def norm(value):
    return re.sub(r"\s+([,.;])", r"\1", " ".join(value.split()))


def decimal_lexeme(value):
    require(
        re.fullmatch(r"\(?\d{1,3}(?:,\d{3})+\)?", value) is not None, "lexema monetário inválido"
    )
    require(value.startswith("(") == value.endswith(")"), "sinal não pareado")
    negative = value.startswith("(")
    result = Decimal(value.strip("()").replace(",", ""))
    return -result if negative else result


def linha(page, anchor, until, count, numeric_start=False):
    text = norm(page)
    if numeric_start:
        starts = list(re.finditer(re.escape(anchor) + r"\s+(?=\(?\d)", text))
        require(len(starts) == 1, "rubrica total ausente/ambígua")
        start = starts[0].end()
    else:
        require(text.count(anchor) == 1, "rubrica ausente/ambígua")
        start = text.index(anchor) + len(anchor)
    require(text.count(until) == 1, "rubrica limite ausente/ambígua")
    end = text.index(until, start)
    values = NUM.findall(text[start:end])
    require(len(values) == count, "colunas monetárias incompletas/ambíguas")
    return values


def ponte_specifica(bs, dre, numerator):
    require(
        decimal_lexeme(bs) == decimal_lexeme(dre) == decimal_lexeme(numerator),
        "ponte anual B/S→DRE/numerador divergente",
    )


def validar_contexto(doc, engine):
    pp = doc[engine]
    title = norm(pp[2])
    identity = norm(pp[3])
    require(
        "GRUPO SUPERVIELLE S.A." in identity
        and "212,617" in identity
        and "Reconquista 330" in identity,
        "entidade/registro/endereço divergente",
    )
    require(
        "Consolidated" in title and "homogeneous currency" in title,
        "capa não consolidada/homogênea",
    )
    if doc["kind"] == "JUNE26":
        require(
            "June 30, 2026" in title and "six-month" in title, "capa/período corrente divergente"
        )
        require("51" in identity and "2026" in identity, "exercício corrente divergente")
    else:
        require(
            "December 31, 2025" in title and "financial year" in title,
            "capa/período anual divergente",
        )
        require("50" in identity and "2025" in identity, "exercício anual divergente")
    for index in [5, 6, 7]:
        page = norm(pp[index])
        require(
            "GRUPO SUPERVIELLE S.A." in page and "CONSOLIDATED" in page and "SEPARATE" not in page,
            "página não consolidada do Grupo",
        )
        require(UNIT in page, "unidade monetária divergente")
    for index in [13, 14]:
        require("NOTES TO THE CONSOLIDATED" in norm(pp[index]), "nota fora do grão consolidado")
    notes = norm(pp[13])
    require(
        "5.5." in notes
        and "IFRS 9" in notes
        and "Non-Financial Public Sector" in notes
        and "7014" in notes,
        "exceções BCRA ausentes",
    )
    measuring = norm(pp[14])
    require(
        "thousands of Argentine" in measuring and "pesos" in measuring,
        "moeda/quantum não identificado",
    )
    date = "June 30, 2026" if doc["kind"] == "JUNE26" else "December 31, 2025"
    require(
        f"consolidated financial as of {date} have been restated" in measuring
        and "drawn up in constant currency" in measuring,
        "data do poder aquisitivo divergente",
    )
    require(
        "IAS 29" in measuring and "homogeneous currency" in measuring,
        "IAS29/comparativos homogêneos ausentes",
    )
    # A7211/IAS34 na June26: confirmação separada nos pixels; os dois motores omitem texto colorido.
    if doc["kind"] == "JUNE26":
        require(
            "December 31, 2025, and the six months period ended June 30, 2025" in measuring,
            "comparativos expressos não identificados",
        )
    return {
        "entidade": "Grupo Supervielle S.A.",
        "grao": "consolidado_owners",
        "politica": POLICY,
        "moeda": "ARS",
        "escala": "1000",
        "poder_aquisitivo": "2026-06-30" if doc["kind"] == "JUNE26" else "2025-12-31",
    }


def extrair_doc(doc, engine):
    validar_contexto(doc, engine)
    pp = doc[engine]
    if doc["kind"] == "JUNE26":
        bs_dates = ["06/30/2026", "12/31/2025"]
        dre_dates = ["06/30/2026", "06/30/2025", "06/30/2026", "06/30/2025"]
        label_bs = "Net (loss) for the period"
        label_dre = "Net (loss) /income for the period attributable to owners of the parent"
        label_total = "Net (loss) /income for the period"
        label_nci = "Net (loss) /income for the period attributable to non-controlling"
        label_num = "Net income for the period attributable to owners of the parent"
        k = 4
    else:
        bs_dates = dre_dates = ["12/31/2025", "12/31/2024"]
        label_bs = "Net (loss) / income for the year"
        label_dre = "Net (loss) /income for the year attributable to owners of the parent"
        label_total = "Net (loss) /income for the year"
        label_nci = "Net (loss) /income for the year attributable to non-controlling interests"
        label_num = "Net income for the year attributable to owners of the"
        k = 2
    dates = re.compile(r"\d{2}/\d{2}/\d{4}")
    require(dates.findall(norm(pp[5])) == bs_dates, "coluna B/S divergente")
    require(dates.findall(norm(pp[6])) == dre_dates, "coluna DRE divergente")
    require(dates.findall(norm(pp[7])) == dre_dates, "coluna numerador divergente")
    if k == 4:
        head = norm(pp[6])
        require(
            "Six-month period" in head and "Three-month period" in head,
            "grupo semestral/trimestral ausente",
        )
        require(
            head.index("Six-month period")
            < head.index("Three-month period")
            < head.index("06/30/2026"),
            "grupo semestral/trimestral ausente/invertido",
        )
        require(
            "For the six and three-month period on June 30, 2026 and June 30, 2025" in head,
            "cabeçalho de período literal divergente",
        )
    bs = linha(
        pp[5], label_bs, "Shareholders' Equity attributable to owners of the parent company", 2
    )
    dre = linha(pp[6], label_dre, label_nci, k)
    total = linha(pp[6], label_total, label_dre, k, numeric_start=True)
    nci = linha(pp[6], label_nci, "The accompanying notes", k)
    numerator = linha(pp[7], "NUMERATOR", "DENOMINATOR", k * 2)
    require(label_num in norm(pp[7]), "numerador monetário owners ausente")
    require(numerator[:k] == numerator[k:] == dre, "numerador monetário não corrobora DRE")
    for x, y, z in zip(total, dre, nci, strict=True):
        require(
            decimal_lexeme(x) == decimal_lexeme(y) + decimal_lexeme(z),
            "total/owners/NCI documental divergente",
        )
    require(bs[0] == dre[0], "B/S corrente e DRE owners divergentes")
    if k == 2:
        ponte_specifica(bs[0], dre[0], numerator[0])
    return {
        "bs": bs,
        "dre_owners": dre,
        "dre_total": total,
        "dre_nci": nci,
        "numerador_monetario": numerator[:k],
        "bs_colunas_literais": bs_dates,
        "dre_colunas_literais": dre_dates,
        "quantum": "1000",
        "moeda": "ARS",
    }
