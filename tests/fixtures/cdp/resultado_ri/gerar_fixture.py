"""Gera PDFs mínimos originais DADOS SIMULADOS; não lê prosa dos PDFs RI reais."""

from __future__ import annotations

import hashlib
import json
from decimal import Decimal
from pathlib import Path

HERE = Path(__file__).parent
ENTITY = "DADOS_SIMULADOS_ENTIDADE"


def sha(b):
    return hashlib.sha256(b).hexdigest()


def pdf(pages):
    def esc(s):
        return s.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")

    kids = " ".join(f"{4 + 2 * i} 0 R" for i in range(len(pages)))
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        f"<< /Type /Pages /Kids [{kids}] /Count {len(pages)} >>".encode(),
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    ]
    for i, lines in enumerate(pages):
        stream = (
            "BT /F1 10 Tf 14 TL 40 780 Td "
            + " ".join("(" + esc(s) + ") Tj T*" for s in lines)
            + " ET"
        ).encode("ascii")
        objects.append(
            f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Resources << /Font << /F1 3 0 R >> >> /Contents {5 + 2 * i} 0 R >>".encode()
        )
        objects.append(
            b"<< /Length " + str(len(stream)).encode() + b" >>\nstream\n" + stream + b"\nendstream"
        )
    data = bytearray(b"%PDF-1.4\n")
    offsets = [0]
    for i, obj in enumerate(objects, 1):
        offsets.append(len(data))
        data.extend(str(i).encode() + b" 0 obj\n" + obj + b"\nendobj\n")
    at = len(data)
    data.extend(f"xref\n0 {len(objects) + 1}\n0000000000 65535 f \n".encode())
    for offset in offsets[1:]:
        data.extend(f"{offset:010d} 00000 n \n".encode())
    data.extend(
        f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\nstartxref\n{at}\n%%EOF\n".encode()
    )
    return bytes(data)


def col(start, end, freq):
    return {"inicio": start, "fim": end, "freq": freq}


def item(name, label, coef=1, **extra):
    return {"item": name, "rotulos": [label], "coeficiente": coef, **extra}


def table(page, title, header, columns, items, scale=1):
    return {
        "pagina": page,
        "ancoras": ["DADOS SIMULADOS", "Consolidado MXN", title],
        "cabecalho": header,
        "colunas": columns,
        "moeda": "MXN",
        "escala": scale,
        "itens": items,
    }


def doc_pages(title, header, rows):
    return ["DADOS SIMULADOS", "Consolidado MXN", title, header, *rows]


def main():
    # Valores inventados deliberadamente; não transcrição de nenhum emissor.
    annual_columns = [col(f"{y}-01-01", f"{y}-12-31", "A") for y in (2025, 2024, 2023)]
    annual_header = "2025 2024 2023"
    annual = pdf(
        [
            doc_pages(
                "DRE SIMULADA",
                annual_header,
                [
                    "Receita 300,000 250,000 200,000",
                    "Lucro bruto 240,000 190,000 150,000",
                    "Despesa operacional 50,000 40,000 30,000",
                    "Outro resultado (40,000) 0 0",
                    "EBIT 230,000 150,000 120,000",
                ],
            ),
            doc_pages(
                "DFC SIMULADA",
                annual_header,
                [
                    "D A 25,000 22,000 20,000",
                    "Reversao de alienacao (30,000) - -",
                    "CFO 120,000 110,000 100,000",
                    "CAPEX (10,000) (9,000) (8,000)",
                ],
            ),
            [
                "DADOS SIMULADOS",
                "Nota de evento simulado",
                "Ganho inclui EBIT simulado",
                "Objeto SUBSIDIARIA SIMULADA",
                "Contraparte COMPRADORA SIMULADA",
                "El 15 de agosto de 2025 se cumplieron condiciones simuladas",
            ],
            ["DADOS SIMULADOS", "Nota de escopo simulado", "Operacoes continuadas simuladas"],
        ]
    )
    ac = [
        item("receita", "Receita"),
        item("ebit", "EBIT"),
        item("lucro_bruto", "Lucro bruto"),
        item("despesas_operacionais", "Despesa operacional"),
        item("outros_ingressos", "Outro resultado", -1),
    ]
    dc = [
        item("d_a_dfc", "D A"),
        item("ganho_alienacao_controle", "Reversao de alienacao", -1),
        item("cfo", "CFO"),
        item("capex", "CAPEX", -1),
    ]
    half_columns = [
        col("2026-04-01", "2026-06-30", "Q"),
        col("2026-01-01", "2026-06-30", "H1"),
        col("2025-04-01", "2025-06-30", "Q"),
        col("2025-01-01", "2025-06-30", "H1"),
    ]
    half_header = "Q2026 H12026 Q2025 H12025"
    ttm_columns = [col("2025-07-01", "2026-06-30", "TTM"), col("2024-07-01", "2025-06-30", "TTM")]
    ttm_header = "TTM2026 TTM2025"
    cf_columns = [col("2026-01-01", "2026-06-30", "H1"), col("2025-01-01", "2025-06-30", "H1")]
    half = pdf(
        [
            ["DADOS SIMULADOS", "Publicacao simulada 23 de julio de 2026"],
            doc_pages(
                "DRE SEMESTRAL SIMULADA",
                half_header,
                [
                    "Receita 90,000,000 170,000,000 70,000,000 140,000,000",
                    "EBIT 50,000,000 110,000,000 45,000,000 90,000,000",
                ],
            ),
            doc_pages(
                "TTM SIMULADO",
                ttm_header,
                [
                    "Receita 330,000,000 280,000,000",
                    "EBIT 250,000,000 165,000,000",
                    "D A operacional 28,000,000 23,000,000",
                ],
            ),
            doc_pages(
                "DFC SEMESTRAL SIMULADA",
                "H12026 H12025",
                ["D A 15,000,000 12,000,000", "CFO 65,000,000 55,000,000"],
            ),
        ]
    )
    for name, data in (("anual_simulado.pdf", annual), ("semestre_simulado.pdf", half)):
        (HERE / name).write_bytes(data)
    da = {
        "issuer_id": ENTITY,
        "url": "https://example.invalid/DADOS_SIMULADOS/anual.pdf",
        "sha256": sha(annual),
        "provas": [
            {
                "pagina": 3,
                "papel": "inclusao_ebit",
                "ancoras": [
                    "Nota de evento simulado",
                    "Ganho inclui EBIT simulado",
                    "SUBSIDIARIA SIMULADA",
                    "COMPRADORA SIMULADA",
                ],
                "data_regex": r"El (\d{1,2}) de ([a-z]+) de (\d{4}) se cumplieron",
            },
            {
                "pagina": 4,
                "papel": "operacoes_continuadas",
                "ancoras": ["Nota de escopo simulado", "Operacoes continuadas simuladas"],
            },
        ],
        "tabelas": [
            table(1, "DRE SIMULADA", annual_header, annual_columns, ac, 1000),
            table(2, "DFC SIMULADA", annual_header, annual_columns, dc, 1000),
        ],
    }
    dh = {
        "issuer_id": ENTITY,
        "url": "https://example.invalid/DADOS_SIMULADOS/semestre.pdf",
        "sha256": sha(half),
        "publicacao": {
            "pagina": 1,
            "texto": "Publicacao simulada 23 de julio de 2026",
            "disponivel_desde": "2026-07-24T05:59:59+00:00",
            "tipo": "data_simulada_fim_dia",
        },
        "tabelas": [
            table(
                2,
                "DRE SEMESTRAL SIMULADA",
                half_header,
                half_columns,
                [item("receita", "Receita"), item("ebit", "EBIT")],
            ),
            table(
                3,
                "TTM SIMULADO",
                ttm_header,
                ttm_columns,
                [
                    item("receita", "Receita"),
                    item("ebit", "EBIT"),
                    item("d_a", "D A operacional", conceito="depreciacao_amortizacao_operacional"),
                ],
            ),
            table(
                4,
                "DFC SEMESTRAL SIMULADA",
                "H12026 H12025",
                cf_columns,
                [item("d_a_dfc", "D A"), item("cfo", "CFO")],
            ),
        ],
    }
    catalog = {
        "schema": "cdp.resultado_evidencias/v1",
        "documentos": [da, dh],
        "pontes_subtotal": [
            {
                "documento_id": sha(annual),
                "total": "ebit",
                "componentes": {
                    "lucro_bruto": 1,
                    "despesas_operacionais": -1,
                    "outros_ingressos": 1,
                },
            }
        ],
        "eventos": [
            {
                "issuer_id": ENTITY,
                "tipo": "alienacao_controle",
                "identidade": {
                    "entidade": ENTITY,
                    "objeto": "SUBSIDIARIA SIMULADA",
                    "contraparte": "COMPRADORA SIMULADA",
                    "contrato": "2025-07-01",
                },
                "medida_item": "ganho_alienacao_controle",
                "documentos_prova": [sha(annual)],
                "papeis_prova": ["inclusao_ebit", "operacoes_continuadas"],
                "medida_documentos": [sha(annual)],
                "medida_periodo": col("2025-01-01", "2025-12-31", "A"),
            }
        ],
    }
    (HERE / "catalogo_sintetico.json").write_text(
        json.dumps(catalog, ensure_ascii=False, indent=2) + "\n"
    )
    # Oráculo externo ao parser, aritmética Decimal dos valores simulados declarados.
    A, G, H, HP = (Decimal(x) for x in ("230000000", "30000000", "110000000", "90000000"))
    oracle = {
        "aviso": "DADOS SIMULADOS",
        "anual_reportado": str(A),
        "ganho_evento": str(G),
        "anual_ajustado": str(A - G),
        "ttm_reportado": str(A + H - HP),
        "ttm_ajustado": str(A + H - HP - G),
        "perda_ttm": str(A + H - HP + G),
        "da_ttm": str(Decimal(25000000) + Decimal(15000000) - Decimal(12000000)),
    }
    (HERE / "oraculos_independentes.json").write_text(json.dumps(oracle, indent=2) + "\n")
    print(
        json.dumps(
            {
                "aviso": "DADOS SIMULADOS",
                "pdfs": {"anual": sha(annual), "semestre": sha(half)},
                "oraculos": oracle,
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
