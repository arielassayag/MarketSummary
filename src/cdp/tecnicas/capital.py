"""Custo do patrimônio em USD sobre taxas decimais declaradas."""


def calcular_ke(rf: float, beta: float, erp: float, lam: float, crp: float) -> float:
    """Delega a fórmula nativa; não coleta taxa nem escolhe fonte ou prêmio."""
    from ..cobertura.custo_capital import ke_usd

    return ke_usd(rf, beta, erp, lam, crp)
