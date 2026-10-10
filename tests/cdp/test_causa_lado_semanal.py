"""DADOS SIMULADOS: mesma frase/FactBook contra base literal e candidato físico."""
from datetime import date

import pytest

from cdp.contracts import Fact, FactBook
from cdp.research.comentario_semanal import ComentarioSemanal, verificar_comentario


@pytest.mark.parametrize(("weight", "claim"), [(-0.2, "comprada"), (0.2, "vendida"), (0.0, "comprada")])
def test_canonical_claim_rejected_before_immutable_seal(weight, claim):
    fid = "mud.BR_SIMULADA.depois"
    fb = FactBook(as_of=date(2026, 10, 9), snapshot_id="DADOS SIMULADOS", is_synthetic=True,
                  facts={fid: Fact(fact_id=fid, issuer_id="BR_SIMULADA", name="Peso recebido",
                                   value=weight, unit="pct", formatted="DADOS SIMULADOS",
                                   formula="Peso de teste, sem cálculo financeiro")})
    comment = ComentarioSemanal(mind="codex", resumo="DADOS SIMULADOS: comentário de teste.",
        desempenho_semana=["Resultado conforme os fatos publicados."],
        atribuicao=["Atribuição conforme os fatos publicados."],
        risco_nova_carteira=["Risco conforme os fatos publicados."],
        execucao=["Execução conforme os fatos publicados."],
        mudancas_carteira=[{"emissor": "BR_SIMULADA", "tipo": "entrada",
                            "racional": f"Empresa simulada entrou {claim}; fatos publicados."}])
    assert any("direcional" in issue for issue in verificar_comentario(
        comment, fb, [{"emissor": "BR_SIMULADA", "tipo": "entrada"}]))
