"""Notas HTML oficiais como dados; DADOS SIMULADOS, sem rede."""

from __future__ import annotations

from datetime import date

import pandas as pd
import pytest

from cdp.data.publico_fatos import selecionar_pit
from cdp.data.publico_fluxos import fatos_fluxos_html


def quadro(*, base="Consolidated", inicio="December 31, 2025", fim="June 30, 2026", add="29,070",
           scale="millions of reais", extra=""):
    return f"""<p>NOTES TO FINANCIAL STATEMENTS (Expressed in {scale})</p><table>
      <tr><td></td><td>{base}</td><td>Parent Company</td></tr>
      <tr><td></td><td>Land and buildings</td><td>Right-of-use assets</td><td>Total</td><td>Total</td></tr>
      <tr><td>Balance on {inicio}</td><td>1,000</td><td>2,000</td><td>3,000</td><td>9,000</td></tr>
      <tr><td>Additions</td><td>12</td><td>{add}</td><td>77,309</td><td>82,612</td></tr>
      {extra}
      <tr><td>Depreciation, amortization and depletion</td><td>(230)</td><td>(23,347)</td><td>(54,076)</td><td>(55,466)</td></tr>
      <tr><td>Balance on {fim}</td><td>13,029</td><td>208,587</td><td>961,265</td><td>974,799</td></tr>
    </table>""".encode()


def extrair(b):
    return fatos_fluxos_html(b, "BR_SIMULADO", documento="6-K simulado", url="https://example.test/dado",
                            data_publicacao=date(2026, 8, 7), data_referencia=date(2026, 6, 30))


def test_coluna_rou_consolidada_datas_duracao_escala_e_nao_total_do_imobilizado():
    rows = extrair(quadro())
    add, da = rows
    assert add["item"] == "adicoes_direito_uso" and add["value"] == 29_070_000_000
    assert da["item"] == "depreciacao_direito_uso" and da["value"] == 23_347_000_000
    assert add["period_start"] == date(2026, 1, 1) and add["period_end"] == date(2026, 6, 30)
    assert add["received_date"] == date(2026, 8, 7) and add["currency"] == "BRL"
    assert add["consolidado"] is True


@pytest.mark.parametrize("argumentos", [dict(base="Parent Company"), dict(scale="currency unknown"),
                                         dict(fim="September 30, 2026"), dict(fim="November 30, 2025")])
def test_quadro_incompativel_ou_futuro_nao_produz_fato(argumentos):
    assert extrair(quadro(**argumentos)) == []


def test_zero_publicado_e_celula_vazia_tem_semanticas_diferentes():
    rows = extrair(quadro(add="0"))
    assert rows[0]["value"] == 0
    for ausente in ("", "−", "–", "—", "-"):
        rows = extrair(quadro(add=ausente))
        assert all(r["item"] != "adicoes_direito_uso" for r in rows)


def test_adicao_divergente_no_mesmo_quadro_nao_e_resolvida_por_ultima_linha():
    rows = extrair(quadro(extra="<tr><td>Additions</td><td>12</td><td>19,000</td><td>77,309</td><td>82,612</td></tr>"))
    assert all(r["item"] != "adicoes_direito_uso" for r in rows)


def test_fato_suplementar_respeita_publicacao_e_nao_transforma_6_meses_em_ttm():
    f = pd.DataFrame(extrair(quadro()))
    f["sha256"], f["fonte"] = "abc", "SIMULADO"
    assert selecionar_pit(f, date(2026, 8, 6)).empty
    df = selecionar_pit(f, date(2026, 8, 7))
    assert not (df["freq"] == "TTM").any()
