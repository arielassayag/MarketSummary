"""Métodos de valuation (funções puras, vetorizadas para Monte Carlo e grades de sensibilidade).

Todas as funções aceitam escalares ou vetores ``numpy`` (difusão) e devolvem o valor intrínseco
de hoje ``V0`` por unidade da linha, na moeda do modelo. Pré-condições inválidas (``g ≥ ke``,
patrimônio negativo, prazo nulo) levantam ``ValueError`` — o chamador registra o método como
"indisponível" com o motivo, nunca um valor substituto.

| Função | Fórmula |
|---|---|
| :func:`rim_gls` | ``V0 = B0 + Σ_{t=1..T} (ROE_t − ke)·B_{t−1}/(1+ke)^t + (ROE_alvo − ke)·B_T/(ke·(1+ke)^T) + (ROE_T − ROE_alvo)·B_T·ω/((1+ke−ω)(1+ke)^T)``; caminho do ROE linear ou exponencial (``ROE_t = alvo + (ROE_2 − alvo)·ω^(t−2)``); termos reais com o patrimônio deflacionado |
| :func:`pb_gordon` | ``P/B* = (ROE − g)/(ke − g)`` |
| :func:`ddm_dois_estagios` | ``Σ_{t=1..n} DPS_t/(1+ke)^t + DPS_{n+1}/((ke − g)(1+ke)^n)`` |
| :func:`fcff_tres_estagios` | anos 1–2 por direcionadores e reinvestimento observado, 3–10 com fade φ e reinvestimento convergindo a ``g/RONIC``; ``VT = NOPAT_{T+1}(1 − g/RONIC)/(WACC − g)`` |
| :func:`pl_justificado` | ``P/L* = (1 − g/ROE)/(ke − g)`` |
| :func:`rolagem` | ``TP12 = V0·(1 + ke) − DPS12`` |
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

Arr = np.ndarray | float


def _a(x: Arr) -> np.ndarray:
    return np.asarray(x, dtype=float)


def _checa_ke_g(ke: Arr, g: Arr, estrito: bool = True) -> np.ndarray:
    """Máscara dos elementos válidos (``g < ke``); em modo estrito, qualquer inválido levanta."""
    ok = _a(g) < _a(ke)
    if estrito and not np.all(ok):
        raise ValueError("Crescimento na perpetuidade maior ou igual ao custo de capital (g ≥ ke).")
    return ok


def _mascara(valor: np.ndarray, ok: np.ndarray) -> np.ndarray:
    return np.where(ok, valor, np.nan)


# ============================================================ lucro residual

@dataclass(frozen=True)
class ResultadoRIM:
    valor: np.ndarray
    pv_explicito: np.ndarray
    pv_terminal: np.ndarray
    roe: np.ndarray          # (T, n)
    b: np.ndarray            # (T+1, n)
    ri: np.ndarray           # (T, n)
    pv_terminal_alvo: np.ndarray | float = 0.0     # parcela da perpetuidade ao ROE de convergência
    pv_terminal_cauda: np.ndarray | float = 0.0    # parcela do desvio residual que continua decaindo (ω)

    @property
    def fracao_terminal(self) -> np.ndarray:
        tot = self.valor
        with np.errstate(divide="ignore", invalid="ignore"):
            return np.where(tot != 0, self.pv_terminal / tot, np.nan)


def caminho_roe(roe1: Arr, roe2: Arr, roe_alvo: Arr, anos: int, omega: float | None = None) -> np.ndarray:
    """ROE_1, ROE_2 do consenso; depois fade linear até ``roe_alvo`` no ano ``anos`` ou, com
    ``omega``, decaimento exponencial ``ROE_t = alvo + (ROE_2 − alvo) × ω^(t−2)`` (persistência do
    desvio por classe de estabilidade)."""
    r1, r2, ra = np.broadcast_arrays(_a(roe1), _a(roe2), _a(roe_alvo))
    out = []
    for t in range(1, anos + 1):
        if t == 1:
            out.append(r1)
        elif t == 2:
            out.append(r2)
        elif omega is not None:
            out.append(ra + (r2 - ra) * float(omega) ** (t - 2))
        else:
            frac = (t - 2) / (anos - 2)
            out.append(r2 + (ra - r2) * frac)
    return np.stack(out)


def rim_gls(b0: Arr, roe1: Arr, roe2: Arr, roe_alvo: Arr, ke: Arr, payout: Arr,
            anos: int = 12, payout_final: Arr | None = None, omega: float | None = None,
            inflacao: float = 0.0) -> ResultadoRIM:
    """Lucro residual (Gebhardt–Lee–Swaminathan) com lucro limpo ``B_t = B_{t−1}(1 + ROE_t(1 − k_t))``.

    ``payout_final`` (opcional): o payout converge linearmente, dos anos 3 a ``anos``, ao payout
    sustentável ``1 − g/ROE_alvo`` (reinvestimento coerente com o crescimento de longo prazo);
    ausente ⇒ payout constante.

    Perpetuidade (patrimônio constante a partir de ``B_T``, convenção GLS): ao ROE de convergência,
    ``(ROE_alvo − ke) × B_T ÷ (ke × (1 + ke)^T)``, mais — com o decaimento exponencial ``ω`` — o desvio
    residual que continua decaindo, ``(ROE_T − ROE_alvo) × B_T × ω ÷ ((1 + ke − ω) × (1 + ke)^T)``.

    ``inflacao`` (termos reais): ROE e ke reais (Fisher) e patrimônio real deflacionado,
    ``B^r_t = B^r_{t−1} × (1 + ROE_nominal,t × (1 − k_t)) ÷ (1 + π)`` — o mesmo valor do modelo nominal
    nos anos explícitos (o lucro retido nominal repõe a erosão inflacionária do patrimônio)."""
    b0 = _a(b0)
    if np.any(b0 <= 0):
        raise ValueError("Patrimônio por ação não positivo: lucro residual indisponível.")
    ke = _a(ke)
    if np.any(ke <= 0):
        raise ValueError("Custo de capital não positivo.")
    k = np.clip(_a(payout), 0.0, 1.0)
    kf = k if payout_final is None else np.clip(_a(payout_final), 0.0, 1.0)
    shape = np.broadcast_shapes(_a(roe1).shape, _a(roe2).shape, _a(roe_alvo).shape, ke.shape, b0.shape,
                                k.shape, kf.shape)
    roe = caminho_roe(np.broadcast_to(_a(roe1), shape), np.broadcast_to(_a(roe2), shape),
                      np.broadcast_to(_a(roe_alvo), shape), anos, omega)
    pi = float(inflacao)
    b = np.empty((anos + 1, *shape))
    b[0] = np.broadcast_to(b0, shape)
    ri = np.empty((anos, *shape))
    pv = np.zeros(shape)
    for t in range(1, anos + 1):
        ri[t - 1] = (roe[t - 1] - ke) * b[t - 1]
        pv = pv + ri[t - 1] / (1 + ke) ** t
        # dividendos só sobre lucro positivo (prejuízo reduz o patrimônio integralmente)
        frac = 0.0 if t <= 2 else (t - 2) / (anos - 2)
        roe_nom = (1 + roe[t - 1]) * (1 + pi) - 1
        k_t = np.where(roe_nom > 0, k + (kf - k) * frac, 0.0)
        b[t] = b[t - 1] * (1 + roe_nom * (1 - k_t)) / (1 + pi)
    ra = np.broadcast_to(_a(roe_alvo), shape)
    disc_t = (1 + ke) ** anos
    pv_alvo = (ra - ke) * b[-1] / (ke * disc_t)
    if omega is not None:
        w = float(omega)
        pv_cauda = (roe[-1] - ra) * b[-1] * w / ((1 + ke - w) * disc_t)
    else:
        pv_cauda = np.zeros(shape) + (roe[-1] - ra) * b[-1] / (ke * disc_t)
    pv_term = pv_alvo + pv_cauda
    valor = b[0] + pv + pv_term
    return ResultadoRIM(valor=valor, pv_explicito=pv, pv_terminal=pv_term, roe=roe, b=b, ri=ri,
                        pv_terminal_alvo=pv_alvo, pv_terminal_cauda=pv_cauda)


# ============================================================ múltiplos justificados (Gordon)

def pb_gordon(roe: Arr, ke: Arr, g: Arr, estrito: bool = True) -> np.ndarray:
    """P/VPA justificado: ``(ROE − g)/(ke − g)`` (modo não estrito: inválidos ⇒ ``NaN``)."""
    ok = _checa_ke_g(ke, g, estrito)
    with np.errstate(divide="ignore", invalid="ignore"):
        return _mascara((_a(roe) - _a(g)) / (_a(ke) - _a(g)), ok)


def pl_justificado(roe: Arr, ke: Arr, g: Arr, estrito: bool = True) -> np.ndarray:
    """P/L à frente justificado: ``(1 − g/ROE)/(ke − g)`` (payout sustentável)."""
    ok = _checa_ke_g(ke, g, estrito)
    roe = _a(roe)
    ok2 = roe > _a(g)
    if estrito and not np.all(ok2):
        raise ValueError("ROE sustentável não supera o crescimento: payout sustentável não positivo.")
    with np.errstate(divide="ignore", invalid="ignore"):
        return _mascara((1 - _a(g) / roe) / (_a(ke) - _a(g)), ok & ok2)


def fator_h(g_curto: Arr, g: Arr, h: float) -> np.ndarray:
    """Modelo H (Fuller & Hsia, 1984): fator ``1 + H × (g_c − g) ÷ (1 + g)`` sobre o múltiplo de
    Gordon para um crescimento extraordinário ``g_c`` que decai linearmente em ``2H`` anos."""
    return 1 + float(h) * (_a(g_curto) - _a(g)) / (1 + _a(g))


# ============================================================ dividendos

def ddm_dois_estagios(dps1: Arr, g1: Arr, g2: Arr, ke: Arr, n: int = 5, estrito: bool = True) -> np.ndarray:
    """Dois estágios: ``n`` anos crescendo a ``g1`` e perpetuidade a ``g2``."""
    ok = _checa_ke_g(ke, g2, estrito)
    dps1, g1, g2, ke = (_a(x) for x in (dps1, g1, g2, ke))
    ok2 = dps1 > 0
    if estrito and not np.all(ok2):
        raise ValueError("Dividendo esperado não positivo: modelo de dividendos indisponível.")
    v = np.zeros(np.broadcast_shapes(dps1.shape, g1.shape, g2.shape, ke.shape))
    d = dps1
    for t in range(1, n + 1):
        v = v + d / (1 + ke) ** t
        if t < n:
            d = d * (1 + g1)
    d_next = d * (1 + g2)
    with np.errstate(divide="ignore", invalid="ignore"):
        return _mascara(v + d_next / ((ke - g2) * (1 + ke) ** n), ok & ok2)


# ============================================================ fluxo de caixa livre da firma

@dataclass(frozen=True)
class ResultadoFCFF:
    ev: np.ndarray
    pv_explicito: np.ndarray
    pv_terminal: np.ndarray
    receita: np.ndarray      # (T, n)
    nopat: np.ndarray
    fcff: np.ndarray
    g: np.ndarray
    reinvest: np.ndarray     # reinvestimento ÷ NOPAT, por ano
    ronic: np.ndarray        # (T,) retorno sobre o capital novo do caso-base
    limite_atingido: tuple[int, ...] = ()   # anos (1..T) em que o reinvestimento do caso-base foi limitado

    @property
    def fracao_terminal(self) -> np.ndarray:
        with np.errstate(divide="ignore", invalid="ignore"):
            return np.where(self.ev != 0, self.pv_terminal / self.ev, np.nan)


@dataclass(frozen=True)
class CenarioFCFF:
    """Choques de um cenário (ou de cada sorteio) sobre o caso-base do FCFF.

    ``g1``, ``g2``, ``g_term`` e ``wacc`` são os valores do cenário (não deltas); ``d_margem`` é
    um choque aditivo permanente na margem EBIT; ``d_margem_trans`` é um choque aditivo
    transitório por ano (forma ``(T, n)``, já multiplicado pelo perfil de reversão)."""

    g1: Arr
    g2: Arr
    g_term: Arr
    wacc: Arr
    d_margem: Arr = 0.0
    d_margem_trans: np.ndarray | None = None


def caminho_crescimento(g1: Arr, g2: Arr, g_term: Arr, phi: float, anos: int) -> np.ndarray:
    g1, g2, gt = np.broadcast_arrays(_a(g1), _a(g2), _a(g_term))
    out = []
    for t in range(1, anos + 1):
        if t == 1:
            out.append(g1)
        elif t == 2:
            out.append(g2)
        else:
            out.append(gt + (g2 - gt) * phi ** (t - 2))
    return np.stack(out)


def perfil_transitorio(anos: int, plenos: int = 3, zero_em: int = 5) -> np.ndarray:
    """Peso de um choque transitório por ano: 1 até ``plenos``, linear até 0 em ``zero_em``."""
    w = []
    for t in range(1, anos + 1):
        if t <= plenos:
            w.append(1.0)
        elif t >= zero_em:
            w.append(0.0)
        else:
            w.append(1.0 - (t - plenos) / (zero_em - plenos))
    return np.asarray(w, dtype=float)


def perfil_runoff(n_anos: int, fracao: float | None) -> np.ndarray:
    """Peso do encerramento de uma concessão por ano: 0 até o início do último ``fracao`` do prazo,
    crescendo linearmente até 1 no último ano (crescimento real e reinvestimento líquido → 0)."""
    w = np.zeros(n_anos)
    if not fracao or n_anos < 3:
        return w
    k0 = n_anos - max(int(round(n_anos * float(fracao))), 1)
    for t in range(k0 + 1, n_anos + 1):
        w[t - 1] = (t - k0) / (n_anos - k0)
    return w


def fcff_tres_estagios(receita0: float, g1: float, g2: float, g_term: float, phi: float, margem: Arr,
                       imposto: float, roic0: float, wacc: float, anos: int = 10,
                       vida: int | None = None, reinvest_lim: tuple[float, float] = (-0.5, 0.95),
                       ronic_final: float | None = None, reinvest_obs: float | None = None,
                       cenario: CenarioFCFF | None = None, runoff_fracao: float | None = None,
                       g_runoff: float = 0.0, ano_convergencia: int | None = None) -> ResultadoFCFF:
    """FCFF em três estágios (ou vida finita sem perpetuidade quando ``vida`` é dado).

    **Caso-base** (escalares): receita pelos direcionadores (anos 1–2) e fade geométrico φ até
    ``g_term``; NOPAT = receita × margem_t × (1 − t) (``margem`` escalar ou caminho anual, ex.: a
    margem corrente revertendo à do ciclo nas commodities). Reinvestimento ÷ NOPAT: nos anos 1–2 o
    reinvestimento observado ``reinvest_obs`` (1 − (CFO − capex) ÷ NOPAT, quando publicado); dos
    anos 3 a ``ano_convergencia`` (padrão: T) converge linearmente para ``g_{t+1} ÷ RONIC_t`` (coerência
    entre crescimento e reinvestimento), com o RONIC convergindo de
    ``roic0`` a ``ronic_final`` (padrão: WACC); sem reinvestimento observado, ``g_{t+1} ÷ RONIC_t``
    desde o ano 1. Limitado a ``reinvest_lim`` (anos limitados ficam em ``limite_atingido``).
    Perpetuidade ``NOPAT_{T+1} × (1 − g ÷ RONIC_final) ÷ (WACC − g)``. Vida finita (concessão):
    sem perpetuidade e, com ``runoff_fracao``, no último terço do prazo o crescimento converge
    linearmente a ``g_runoff`` (inflação: crescimento real zero) e o reinvestimento líquido a zero.

    **Cenário** (``cenario``, vetorizado): preserva a média do caso-base. A receita do cenário é
    a do caso-base × (1 + Σ desvios de crescimento ÷ (1 + g_base)) (aditiva, sem a convexidade
    da capitalização; nunca negativa); o NOPAT é ``R_base × (margem × fator_receita + Δmargem) ×
    (1 − t)`` (choques de margem sobre a receita-base, sem termo cruzado); o reinvestimento é o do
    caso-base mais o capital necessário para o crescimento adicional,
    ``ΔI_t = margem × (1 − t) × (ΔR_{t+1} − ΔR_t) ÷ máx(RONIC_t; WACC)`` (simétrico, sem limite)."""
    wacc = float(wacc)
    if vida is None:
        _checa_ke_g(wacc, g_term)
    elif vida < 1:
        raise ValueError("Prazo remanescente da concessão inferior a um ano.")
    if receita0 is None or float(receita0) <= 0:
        raise ValueError("Receita não positiva: fluxo de caixa indisponível.")
    receita0 = float(receita0)
    n_anos = anos if vida is None else vida
    w_ro = perfil_runoff(n_anos, runoff_fracao if vida is not None else None)
    gb = caminho_crescimento(g1, g2, g_term, phi, max(n_anos, 2))[:n_anos].astype(float)
    gb = gb * (1 - w_ro) + float(g_runoff) * w_ro
    rb = receita0 * np.cumprod(1 + gb)
    mg = np.broadcast_to(np.asarray(margem, dtype=float), (n_anos,)).astype(float) \
        if np.ndim(margem) == 0 else np.asarray(margem, dtype=float)[:n_anos]
    nb = rb * mg * (1 - imposto)
    rfin = wacc if ronic_final is None else max(float(ronic_final), wacc)
    t_idx = np.arange(1, n_anos + 1, dtype=float)
    frac = (t_idx - 1) / max(n_anos - 1, 1)
    ronic = float(roic0) + (rfin - float(roic0)) * frac
    ronic = np.where(ronic > 1e-6, ronic, 1e-6)
    g_next = np.empty(n_anos)
    g_next[:-1] = gb[1:]
    g_next[-1] = gb[-1] if vida is not None else float(g_term)
    rr_mod = g_next / ronic
    if reinvest_obs is not None and n_anos > 2:
        n_conv = n_anos if ano_convergencia is None else max(min(int(ano_convergencia), n_anos), 3)
        w = np.clip((t_idx - 2) / (n_conv - 2), 0.0, 1.0)
        rr_bruto = float(reinvest_obs) * (1 - w) + rr_mod * w
    elif reinvest_obs is not None:
        rr_bruto = np.full(n_anos, float(reinvest_obs))
    else:
        rr_bruto = rr_mod
    rr_bruto = rr_bruto * (1 - w_ro)
    rr = np.clip(rr_bruto, reinvest_lim[0], reinvest_lim[1])
    limitados = tuple(int(t) for t, a, b in zip(t_idx, rr_bruto, rr, strict=True) if abs(a - b) > 1e-12)
    ib = nb * rr
    fb = nb - ib
    disc_b = (1 + wacc) ** t_idx
    if cenario is None:
        pv = float(np.sum(fb / disc_b))
        if vida is None:
            gt = float(g_term)
            tv = nb[-1] * (1 + gt) * (1 - gt / rfin) / (wacc - gt)
            pv_tv = tv / (1 + wacc) ** n_anos
        else:
            pv_tv = 0.0
        return ResultadoFCFF(ev=np.asarray(pv + pv_tv), pv_explicito=np.asarray(pv),
                             pv_terminal=np.asarray(pv_tv), receita=rb, nopat=nb, fcff=fb, g=gb,
                             reinvest=rr, ronic=ronic, limite_atingido=limitados)
    # ---------------------------------------------------------------- cenário (média preservada)
    c = cenario
    wd = _a(c.wacc)
    gtd = _a(c.g_term)
    if vida is None and np.any(gtd >= wd):
        raise ValueError("Crescimento na perpetuidade maior ou igual ao WACC (g ≥ WACC).")
    shape = np.broadcast_shapes(_a(c.g1).shape, _a(c.g2).shape, gtd.shape, wd.shape, _a(c.d_margem).shape,
                                () if c.d_margem_trans is None else c.d_margem_trans.shape[1:])
    gd = caminho_crescimento(np.broadcast_to(_a(c.g1), shape), np.broadcast_to(_a(c.g2), shape),
                             np.broadcast_to(gtd, shape), phi, max(n_anos, 2))[:n_anos]
    col = (slice(None),) + (None,) * len(shape)
    gd = gd * (1 - w_ro)[col] + float(g_runoff) * w_ro[col]
    desvio = (gd - gb[col]) / (1 + gb[col])
    fator = np.maximum(1 + np.cumsum(desvio, axis=0), 0.0)
    rd = rb[col] * fator
    dm = np.broadcast_to(_a(c.d_margem), shape)
    mt = np.zeros((n_anos, *shape)) if c.d_margem_trans is None else np.broadcast_to(c.d_margem_trans, (n_anos, *shape))
    # NOPAT do cenário em primeira ordem: margem-base sobre a receita do cenário + choques de
    # margem sobre a receita-base (sem o termo cruzado, que deslocaria a média)
    nd = rb[col] * (mg[col] * fator + dm + mt) * (1 - imposto)
    d_r = rd - rb[col]
    if vida is None:
        d_r_next_ult = rd[-1] * (1 + np.broadcast_to(gtd, shape)) - rb[-1] * (1 + float(g_term))
    else:
        d_r_next_ult = rd[-1] * (1 + gd[-1]) - rb[-1] * (1 + gb[-1])
    d_r_next = np.concatenate([d_r[1:], d_r_next_ult[None, ...]], axis=0)
    ronic_inc = np.maximum(ronic, wacc)
    di = mg[col] * (1 - imposto) * (d_r_next - d_r) / ronic_inc[col]
    idd = ib[col] + di
    fd = nd - idd
    wdb = np.broadcast_to(wd, shape)
    disc = (1 + wdb)[None, ...] ** t_idx[col]
    pv = np.sum(fd / disc, axis=0)
    if vida is None:
        gtb = np.broadcast_to(gtd, shape)
        rfin_d = np.maximum(rfin, wdb)
        tv = nd[-1] * (1 + gtb) * (1 - gtb / rfin_d) / (wdb - gtb)
        pv_tv = tv / (1 + wdb) ** n_anos
    else:
        pv_tv = np.zeros(shape)
    with np.errstate(divide="ignore", invalid="ignore"):
        rr_d = np.where(nd != 0, idd / nd, np.nan)
    return ResultadoFCFF(ev=pv + pv_tv, pv_explicito=pv, pv_terminal=pv_tv, receita=rd, nopat=nd,
                         fcff=fd, g=gd, reinvest=rr_d, ronic=ronic, limite_atingido=limitados)


# ============================================================ alvo de 12 meses e retornos

def rolagem(v0: Arr, ke: Arr, dps12: Arr) -> np.ndarray:
    """Preço-alvo de 12 meses: ``TP12 = V0·(1 + ke) − DPS12`` (Damodaran)."""
    return _a(v0) * (1 + _a(ke)) - _a(dps12)


def retorno_esperado(tp12: Arr, dps12: Arr, p0: float) -> np.ndarray:
    """``ETR = (TP12 + DPS12)/P0 − 1``."""
    return (_a(tp12) + _a(dps12)) / p0 - 1


def swanson(r_p10: float, r_p50: float, r_p90: float,
            pesos: tuple[float, float, float] = (0.3, 0.4, 0.3)) -> float:
    """Retorno ponderado por probabilidade sem Monte Carlo (Swanson 30/40/30)."""
    return pesos[0] * r_p10 + pesos[1] * r_p50 + pesos[2] * r_p90


# ============================================================ custo de capital implícito (diagnóstico)

def _bissecao(f, lo: float, hi: float, it: int = 200) -> float | None:
    flo, fhi = f(lo), f(hi)
    if not (np.isfinite(flo) and np.isfinite(fhi)) or flo * fhi > 0:
        return None
    for _ in range(it):
        mid = 0.5 * (lo + hi)
        fm = f(mid)
        if flo * fm <= 0:
            hi, fhi = mid, fm
        else:
            lo, flo = mid, fm
    return 0.5 * (lo + hi)


def icc_gls(p0: float, b0: float, roe1: float, roe2: float, roe_alvo: float, payout: float,
            anos: int = 12, omega: float | None = None) -> float | None:
    """TIR do lucro residual ao preço atual (GLS), com o mesmo caminho do ROE do modelo."""
    def f(k: float) -> float:
        return float(rim_gls(b0, roe1, roe2, roe_alvo, k, payout, anos, omega=omega).valor) - p0
    try:
        return _bissecao(f, 0.005, 0.60)
    except ValueError:
        return None


def icc_mpeg(p0: float, eps1: float, eps2: float, dps1: float) -> float | None:
    """Easton (2004): ``r² − r·DPS1/P0 − (EPS2 − EPS1)/P0 = 0`` (raiz positiva)."""
    a = dps1 / p0
    c = (eps2 - eps1) / p0
    disc = a * a + 4 * c
    if disc < 0 or eps2 <= eps1:
        return None
    return (a + np.sqrt(disc)) / 2


def icc_peg(p0: float, eps1: float, eps2: float) -> float | None:
    """Caso PEG de Easton: ``r = √((EPS2 − EPS1)/P0)``."""
    if eps2 <= eps1:
        return None
    return float(np.sqrt((eps2 - eps1) / p0))


def icc_gode_mohanram(p0: float, eps1: float, eps2: float, dps1: float, g_perp: float) -> float | None:
    """Ohlson–Juettner / Gode–Mohanram: ``r = A + √(A² + (EPS1/P0)(g2 − (γ − 1)))``."""
    if eps1 <= 0 or eps2 <= 0:
        return None
    g2 = eps2 / eps1 - 1
    a = 0.5 * (g_perp + dps1 / p0)
    disc = a * a + (eps1 / p0) * (g2 - g_perp)
    if disc < 0:
        return None
    return float(a + np.sqrt(disc))


def icc_claus_thomas(p0: float, b0: float, eps: list[float], payout: float, g_ri: float) -> float | None:
    """Claus–Thomas: 5 anos de lucro residual explícitos e crescimento ``g_ri`` depois."""
    if b0 <= 0 or len(eps) < 5:
        return None

    def f(k: float) -> float:
        b, v = b0, b0
        for t, e in enumerate(eps[:5], start=1):
            v += (e - k * b) / (1 + k) ** t
            b = b + e * (1 - payout)
        ri6 = (eps[4] * (1 + g_ri) - k * b)
        if k <= g_ri:
            return np.inf
        v += ri6 / ((k - g_ri) * (1 + k) ** 5)
        return v - p0
    return _bissecao(f, max(g_ri + 0.002, 0.005), 0.60)


__all__ = ["CenarioFCFF", "ResultadoFCFF", "ResultadoRIM", "caminho_crescimento", "caminho_roe", "ddm_dois_estagios",
           "fator_h", "fcff_tres_estagios", "perfil_runoff", "icc_claus_thomas", "icc_gls", "icc_gode_mohanram", "icc_mpeg",
           "icc_peg", "pb_gordon", "perfil_transitorio", "pl_justificado", "retorno_esperado", "rim_gls",
           "rolagem", "swanson"]
