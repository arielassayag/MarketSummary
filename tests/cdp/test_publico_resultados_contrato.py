"""Contratos gerais RI: PDF próprio DADOS SIMULADOS, sem mock do parser."""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime

from cdp.data import publico_resultados as R

CORTE = datetime(2026, 10, 7, 8, tzinfo=UTC)


def _pdf(linhas):
    def esc(s):
        return s.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")

    stream = (
        "BT /F1 10 Tf 14 TL 40 780 Td " + " ".join("(" + esc(s) + ") Tj T*" for s in linhas) + " ET"
    ).encode("ascii")
    objetos = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >>",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
        b"<< /Length " + str(len(stream)).encode() + b" >>\nstream\n" + stream + b"\nendstream",
    ]
    dados = bytearray(b"%PDF-1.4\n")
    offsets = [0]
    for i, obj in enumerate(objetos, 1):
        offsets.append(len(dados))
        dados.extend(str(i).encode() + b" 0 obj\n" + obj + b"\nendobj\n")
    pos = len(dados)
    dados.extend(b"xref\n0 6\n0000000000 65535 f \n")
    for o in offsets[1:]:
        dados.extend(f"{o:010d} 00000 n \n".encode())
    dados.extend(f"trailer\n<< /Size 6 /Root 1 0 R >>\nstartxref\n{pos}\n%%EOF\n".encode())
    return bytes(dados)


def _primario(nome, colunas, valores, captura, publicacao=None):
    cab = "PERIODOS " + " ".join(c["inicio"] + "/" + c["fim"] for c in colunas)
    linhas = [
        "DADOS SIMULADOS",
        "Consolidado MXN",
        nome,
        cab,
        "Revenue " + " ".join(str(v) for v in valores),
    ]
    if publicacao:
        linhas.insert(0, "Publicacao declarada DADOS SIMULADOS")
    dados = _pdf(linhas)
    doc = {
        "issuer_id": "DADOS_SIMULADOS",
        "url": "https://example.invalid/DADOS_SIMULADOS/" + nome,
        "sha256": hashlib.sha256(dados).hexdigest(),
        "tabelas": [
            {
                "pagina": 1,
                "ancoras": ["DADOS SIMULADOS", "Consolidado MXN", cab],
                "cabecalho": cab,
                "colunas": colunas,
                "moeda": "MXN",
                "escala": 1,
                "itens": [{"item": "receita", "rotulos": ["Revenue"]}],
            }
        ],
    }
    if publicacao:
        doc["publicacao"] = {
            "pagina": 1,
            "texto": "Publicacao declarada DADOS SIMULADOS",
            "disponivel_desde": publicacao,
        }
    return R.extrair(dados, doc, datetime.fromisoformat(captura), CORTE)


def _col(ini, fim, freq):
    return {"inicio": ini, "fim": fim, "freq": freq}


def _partes():
    anual = _primario(
        "annual",
        [_col("2025-01-01", "2025-12-31", "A"), _col("2024-01-01", "2024-12-31", "A")],
        [100, 80],
        "2026-10-07T06:10:00+00:00",
    )
    semestre = _primario(
        "semester",
        [_col("2026-01-01", "2026-06-30", "H1"), _col("2025-01-01", "2025-06-30", "H1")],
        [60, 40],
        "2026-10-07T06:20:00+00:00",
        "2026-07-24T05:59:59+00:00",
    )
    return anual, semestre


def test_pdf_real_uma_coluna_preserva_celula_inteira_sinal_e_ausencia():
    for texto, esperado in [("100", "100"), ("(100)", "-100"), ("- ", None)]:
        p = _primario(
            "single", [_col("2025-01-01", "2025-12-31", "A")], [texto], "2026-10-07T06:10:00+00:00"
        )
        assert p["fatos"][0]["valor"] == esperado
        assert p["fatos"][0]["valor_bruto"] == esperado


def test_ttm_coleta_fisica_max_componentes_separada_da_disponibilidade():
    anual, semestre = _partes()
    cat = R.construir([anual, semestre], {}, CORTE)
    f = next(f for f in cat["fatos"] if f.get("componentes"))
    r = R.tabela_fatos(cat).query("freq == 'TTM'").iloc[0]
    assert f["valor"] == "120" and f["inicio"] == "2025-07-01"
    assert f["disponivel_desde"] == "2026-10-07T06:10:00+00:00"
    assert r["data_coleta"] == "2026-10-07T06:20:00+00:00"
    assert len(f["componentes"]) == 3


def test_ttm_reportado_tardio_usado_como_prova_leva_max_publicacao_e_coleta():
    anual, semestre = _partes()
    reportado = _primario(
        "reported",
        [_col("2025-07-01", "2026-06-30", "TTM"), _col("2024-07-01", "2025-06-30", "TTM")],
        [120, 80],
        "2026-10-07T06:40:00+00:00",
        "2026-10-07T06:30:00+00:00",
    )
    cat = R.construir([anual, semestre, reportado], {}, CORTE)
    f = next(f for f in cat["fatos"] if f.get("componentes"))
    assert f["valor"] == "120" and f["ttm_reportado_fato_ids"]
    assert f["disponivel_desde"] == "2026-10-07T06:30:00+00:00"
    r = R.tabela_fatos(cat).query("freq == 'TTM' and period_end == '2026-06-30'").iloc[0]
    assert r["data_coleta"] == "2026-10-07T06:40:00+00:00"


def test_semestre_deslocado_preserva_reportado_sem_fabricar_janela_ttm():
    anual, _ = _partes()
    deslocado = _primario(
        "offset",
        [_col("2026-02-01", "2026-07-31", "H1"), _col("2025-02-01", "2025-07-31", "H1")],
        [60, 40],
        "2026-10-07T06:20:00+00:00",
    )
    cat = R.construir([anual, deslocado], {}, CORTE)
    assert not any(f.get("componentes") for f in cat["fatos"])
    assert sum(f["freq"] == "H1" for f in cat["fatos"]) == 2
    assert not any(f["freq"] == "TTM" for f in cat["fatos"])
    assert all(f["freq"] == "A" for f in R.tabela_fatos(cat).to_dict("records"))


def test_continuidade_fiscal_explicita_deriva_inicio_sem_mes_presumido():
    anual = _primario(
        "fiscalannual", [_col("2024-07-01", "2025-06-30", "A")], [100], "2026-10-07T06:10:00+00:00"
    )
    semestre = _primario(
        "fiscalhalf",
        [_col("2025-07-01", "2025-12-31", "H1"), _col("2024-07-01", "2024-12-31", "H1")],
        [60, 40],
        "2026-10-07T06:20:00+00:00",
    )
    cat = R.construir([anual, semestre], {}, CORTE)
    f = next(f for f in cat["fatos"] if f.get("componentes"))
    assert f["inicio"] == "2025-01-01" and f["fim"] == "2025-12-31"
    assert f["valor"] == "120"
