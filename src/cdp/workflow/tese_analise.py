"""Tese de investimento da carteira — analytics determinísticos da semana decidida.

Tudo aqui é código (a mente nunca calcula): a tese só cita os números produzidos por este módulo
via ``{{fact:id}}``. Regras:

- **Sem reotimizar.** Os pesos são lidos da proposta APROVADA da semana
  (``book/<semana>/proposal_v<k>.json``, mesma regra do painel: a efetivada; senão a última
  ``APPROVE``). O mercado é reconstruído com ``Runtime.market_for_week(record=False)`` (todos os
  hashes conferidos) e o contexto com ``prepare_week`` no estado do livro NO MOMENTO da decisão
  (booking anterior, pesos marcados do último registro diário anterior à semana e drawdown
  desse registro) — nunca com o estado vivo do livro.
- **Conferência.** O ``RiskSummary`` recalculado é comparado ao gravado (vol ex-ante, beta e
  participação fatorial). Divergência ⇒ os valores GRAVADOS prevalecem nos campos gravados e uma
  nota de código registra a diferença (deriva de código ou de configuração).
- **Configuração da decisão.** O contexto é reconstruído com a configuração vigente no
  ``decide`` (``book/<semana>/config_decisao.json``; na falta dela, o mandato arquivado
  ``configs/cdp/historico/<config_hash>.json``), aceita só se o hash do JSON bruto conferir com o
  ``config_hash`` da proposta (:func:`decision_config`). Sem ela e com o mandato recalibrado, o
  que dependeria da configuração atual (alpha quantitativo, visões, sinais, dimensionamento,
  grupos e fatores de risco) sai ``None`` com nota explícita — nunca é atribuído às visões.
- **Decisão do PM verificada.** Visões, diário e postura do PM vêm da saída VERIFICADA que o
  ``decide`` usou (:meth:`Runtime.decision_pm_output`, conferida pelo ``pm_decision_hash``),
  nunca do ``pm_decision.json`` bruto; sem conferência ⇒ ausentes, com nota.
- **Ausente nunca vira zero.** ``NaN`` ⇒ ``None`` em toda a saída; séries sem dados são puladas
  e registradas nas notas.

Papel de cada posição (``role``), com α = alpha esperado da proposta (após visões) e a
participação de Euler na variância:

- ``alpha``: sinal(w)·α > 0 e participação ≥ 0 — "Geradora de alpha";
- ``alpha_div``: sinal(w)·α > 0 e participação < 0 — "Alpha que diversifica";
- ``hedge``: sinal(w)·α ≤ 0 (ou α ausente) — "Hedge / neutralidade".

Dimensionamento (``sizing``): a tabela de limites por emissor do ``decide`` é reconstruída sem
otimizar (``build_asset_constraints`` com as visões da semana → ``apply_liquidity_minimums`` →
``apply_specific_risk_caps`` com a meta de vol aplicada). Para cada nome, com tolerância
relativa ``SIZING_TOL``:

1. |w| no teto estático do lado ⇒ o componente que define o teto: ``teto_risco`` (teto convexo de
   risco específico), ``squeeze`` (multiplicador de squeeze MÉDIO/sem dados nos shorts),
   ``teto_nome`` (peso máximo do mandato), ``liquidez`` (participação × ADTV × dias) ou
   ``teto_visao`` (``max_abs_weight`` de visão/sentinela);
2. abaixo do teto estático, mas com ``max_long:<id>``/``max_short:<id>`` entre as restrições
   ativas do otimizador (``binding_constraints``) ⇒ ``teto_risco`` (teto reduzido pelo reparo de
   risco por nome, ``weekly._repair_single_name_risk``);
3. ``max_trade``/``max_trade_liq`` ativo (ou |Δw| no limite de negociação) ⇒ ``liquidez``;
4. nenhum teto ativo ⇒ ``interior`` (o tamanho sai do ótimo alpha × risco × custos sob as
   neutralidades da carteira);
5. tabela de limites indisponível ⇒ ``indeterminado``.

``aluguel`` não é produzido pelo conjunto atual de limites (o aluguel entra no objetivo, não como
teto); o rótulo existe para o contrato do painel.
"""

from __future__ import annotations

import json
import math
import re
import unicodedata
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import date, timedelta
from pathlib import Path
from typing import TYPE_CHECKING, Any

import numpy as np
import pandas as pd

from ..contracts import Decision, DecisionType, Proposal, ResearchNote, ResearchPack
from ..risk.types import TRADING_DAYS

if TYPE_CHECKING:  # pragma: no cover
    from ..config import ConfigDecisao, FundConfig
    from ..research.pm_agent import PMDecisionOutput
    from .runtime import Runtime
    from .weekly import WeekContext

ANALYSIS_SCHEMA = "cdp-tese-analise/1"
SIZING_TOL = 1e-3
"""Tolerância relativa para considerar um peso "no teto" (solver e arredondamento)."""
RISK_CHECK_TOL = 1e-6
"""Tolerância relativa da conferência recalculado × gravado (vol, beta, participação)."""
HIST_LOOKBACK = 504
MIN_SENS_OBS = 60
SHOCK_MARKET = -0.10
SHOCK_COMMODITY = 0.10
SIGMA_HORIZONS: tuple[tuple[str, str, int], ...] = (
    ("dia", "Um dia", 1), ("semana", "Uma semana (5 pregões)", 5),
    ("mes", "Um mês (21 pregões)", 21))
LIQ_HORIZONS = (1.0, 3.0)
CATALYST_GROUP_MIN = 3
"""Catalisadores da pesquisa na mesma data para ao menos tantos nomes viram um único item."""
MACRO_COUNTRY_SHARE = 0.20
"""Eventos macro da pesquisa entram no calendário para o escopo global e os países com ao menos
esta fração do gross (evita listar a agenda de todos os países)."""

SIGNALS: tuple[tuple[str, str, str], ...] = (
    ("residual_momentum", "mom", "momentum residual"),
    ("value", "val", "valor"),
    ("quality", "qual", "qualidade"),
    ("low_risk", "lowrisk", "baixo risco"),
    ("analyst_revision", "rev", "revisões de analistas"),
)
"""(sinal do alpha, código curto usado em ``z_<c>``/``c_<c>``/``contrib.<c>``, rótulo pt-BR)."""

COUNTRY_PT = {"BR": "Brasil", "MX": "México", "CL": "Chile", "CO": "Colômbia", "PE": "Peru",
              "AR": "Argentina", "UY": "Uruguai", "PA": "Panamá",
              "LATAM": "Regional (América Latina)", "US": "Estados Unidos", "GLOBAL": "Global",
              "OTHER": "Outros"}
"""Rótulos de país iguais aos do painel (``countryName``): o mesmo balde tem um único nome."""
GROUP_CODE = {"market": "mercado", "country": "pais", "sector": "setor", "style": "estilo",
              "specific": "especifico"}
GROUP_LABEL = {"mercado": "Mercado LatAm", "pais": "Países", "setor": "Setores",
               "estilo": "Estilos", "especifico": "Específico (seleção de ações)"}
ROLE_PT = {"alpha": "Geradora de alpha", "alpha_div": "Alpha que diversifica",
           "hedge": "Hedge / neutralidade"}
SIZING_PT = {"interior": "Ótimo interior (sem teto ativo)", "teto_nome": "Teto de peso por nome",
             "teto_risco": "Teto de risco por nome", "teto_visao": "Teto da visão/sentinela",
             "liquidez": "Liquidez", "squeeze": "Teto por risco de squeeze",
             "aluguel": "Custo de aluguel", "indeterminado": "Indeterminado"}
STRESS_KIND = {"histórico": "historico", "hipotético": "hipotetico",
               "idiossincrático": "idiossincratico"}
EXCLUSION_PT = {
    "sem_linha_short": "Sem linha para venda a descoberto",
    "sem_linha_long": "Sem linha para compra",
    "squeeze_alto": "Risco de squeeze alto (venda vetada)",
    "squeeze_medio_teto": "Risco de squeeze médio (teto de venda reduzido)",
    "squeeze_na_teto": "Squeeze sem dados (teto de venda reduzido)",
    "visao_no_long": "Visão ou exclusão: compra vetada",
    "visao_no_short": "Visão ou exclusão: venda vetada",
    "visao_teto_peso": "Visão com teto de peso",
    "sem_aluguel": "Sem disponibilidade de aluguel",
    "aluguel_acima_limite": "Aluguel acima do limite do mandato",
    "mcap_ausente_short": "Valor de mercado ausente (venda vetada)",
    "mcap_baixo_short": "Valor de mercado abaixo do mínimo para venda",
    "adtv_long_ausente": "Liquidez da linha de compra ausente",
    "adtv_short_ausente": "Liquidez da linha de venda ausente",
    "sem_adtv_negociacao": "Sem liquidez de negociação",
    "fora_do_painel": "Fora do universo",
    "fora_do_modelo_risco": "Fora do modelo de risco",
    "alpha_ausente": "Sem sinal quantitativo",
    "excluido_gestor": "Excluído pelo gestor",
    "inelegivel": "Inelegível pelos filtros do universo",
    "liquidez_minima_long": "Liquidez abaixo do mínimo do mandato para compra",
    "liquidez_minima_short": "Liquidez abaixo do mínimo do mandato para venda",
}
CHECK_PT = {"ex_ante_vol": "volatilidade ex-ante", "beta": "beta",
            "factor_risk_share": "participação fatorial"}
BINDING_PT = {"net_exposure": "exposição líquida", "beta": "beta", "vol_target": "meta de vol",
              "gross": "gross máximo", "turnover": "giro semanal"}

SENS_SERIES: tuple[tuple[str, str, str, str, float], ...] = (
    ("ILF", "América Latina (ILF)", "bench", "ILF", SHOCK_MARKET),
    ("EWZ", "Brasil (EWZ)", "bench", "EWZ", SHOCK_MARKET),
    ("EWW", "México (EWW)", "bench", "EWW", SHOCK_MARKET),
    ("SPY", "EUA (SPY)", "bench", "SPY", SHOCK_MARKET),
    ("EEM", "Emergentes (EEM)", "bench", "EEM", SHOCK_MARKET),
    ("DXY", "Dólar global (DXY)", "bench", "DX-Y.NYB", 0.05),
    ("BRL", "Real (BRL)", "fx", "BRL", SHOCK_MARKET),
    ("MXN", "Peso mexicano (MXN)", "fx", "MXN", SHOCK_MARKET),
    ("CLP", "Peso chileno (CLP)", "fx", "CLP", SHOCK_MARKET),
    ("COP", "Peso colombiano (COP)", "fx", "COP", SHOCK_MARKET),
    ("PEN", "Sol peruano (PEN)", "fx", "PEN", SHOCK_MARKET),
    ("ARS", "Peso argentino (ARS)", "fx", "ARS", SHOCK_MARKET),
    ("BRENT", "Petróleo Brent", "bench", "BZ=F", SHOCK_MARKET),
    ("COBRE", "Cobre", "bench", "HG=F", SHOCK_MARKET),
    ("OURO", "Ouro", "bench", "GC=F", SHOCK_MARKET),
)
"""Séries da sensibilidade realizada: (código, rótulo, fonte, coluna, choque ilustrativo).
Câmbio em USD por unidade da moeda local: choque −10% = moeda local 10% mais fraca."""


# ==========================================================
# Utilidades
# ==========================================================

def _f(x: object) -> float | None:
    """Float finito ou ``None`` (ausente nunca vira zero)."""
    if x is None or isinstance(x, bool):
        return None
    try:
        v = float(x)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None
    return v if math.isfinite(v) else None


def _mul(a: float | None, b: float | None) -> float | None:
    return None if a is None or b is None else a * b


def clean_json(obj: Any) -> Any:
    """Estrutura JSON estrita: NaN/inf ⇒ ``None``; datas em ISO; numpy ⇒ Python."""
    if isinstance(obj, Mapping):
        return {str(k): clean_json(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [clean_json(v) for v in obj]
    if isinstance(obj, bool) or obj is None or isinstance(obj, str):
        return obj
    if isinstance(obj, (int, np.integer)):
        return int(obj)
    if isinstance(obj, (float, np.floating)):
        return _f(obj)
    if isinstance(obj, date):
        return obj.isoformat()
    if hasattr(obj, "model_dump"):
        return clean_json(obj.model_dump(mode="json"))
    return str(obj)


def code_slug(text: object) -> str:
    """Código ASCII estável para ids (``"Gap BR -10%"`` ⇒ ``gap_br_menos_10``)."""
    s = re.sub(r"([+\-−])(?=\d)", lambda m: " mais " if m.group(1) == "+" else " menos ",
               str(text))
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode("ascii").lower()
    s = re.sub(r"[^a-z0-9]+", "_", s).strip("_")
    return s or "na"


def sector_label(sector: str) -> str:
    from .painel import SECTOR_PT

    if str(sector).upper() == "OTHER":  # balde ``sector:Other`` do modelo de risco
        return "Outros"
    return SECTOR_PT.get(sector, sector)


def style_label(style: str) -> str:
    from .painel import STYLE_PT

    return STYLE_PT.get(style, style)


def commodity_label(code: str) -> str:
    from .painel import COMMODITY_PT

    text = COMMODITY_PT.get(code, code)
    return text[:1].upper() + text[1:]


def theme_label(code: str) -> str:
    from .painel import THEME_PT

    text = THEME_PT.get(code, code)
    return text[:1].upper() + text[1:]


def country_label(code: str) -> str:
    return COUNTRY_PT.get(code, code)


def factor_label(name: str) -> tuple[str, str]:
    """(rótulo pt-BR, código do grupo) de um fator do modelo de risco."""
    if name == "market":
        return "Mercado LatAm", "mercado"
    if name.startswith("country:"):
        return f"País — {country_label(name[8:])}", "pais"
    if name.startswith("sector:"):
        return f"Setor — {sector_label(name[7:])}", "setor"
    return f"Estilo — {style_label(name)}", "estilo"


# ==========================================================
# Insumos da semana decidida
# ==========================================================

@dataclass
class ThesisInputs:
    """Insumos (somente leitura) e estado recalculado da semana decidida."""

    week: date
    cfg: FundConfig
    proposal: Proposal
    decision: Decision
    ctx: WeekContext
    weights: pd.Series
    pack: ResearchPack | None
    pm: PMDecisionOutput | None
    shadow: Proposal | None
    briefing_facts: dict[str, str]
    drawdown: float | None
    fund_name: str
    notes: list[str] = field(default_factory=list)
    config_drift: bool = False
    """Mandato recalibrado desde a decisão e configuração da decisão indisponível."""
    pm_verified: bool = False
    """``pm`` é a saída verificada que o ``decide`` usou (conferida pelo hash da decisão)."""


def approved_proposal(book: Any, week: date) -> tuple[Proposal, Decision]:
    """Proposta aprovada da semana (a efetivada; senão a última APPROVE) e a sua decisão.

    Sem decisão ``APPROVE`` ⇒ ``ValueError`` (nada é gravado). A proposta precisa conferir com o
    ``proposal_hash`` da decisão (arquivo alterado ⇒ erro).
    """
    proposals = book.list_proposals(week)
    decisions = book.list_decisions(week)
    approved: list[tuple[Proposal, Decision]] = []
    for p in proposals:
        d = decisions.get(p.version)
        if d is not None and d.proposal_id == p.proposal_id and d.decision == DecisionType.APPROVE:
            approved.append((p, d))
    if not approved:
        raise ValueError(f"A semana {week} não tem decisão aprovada: rode `cdp weekly decide` "
                         "antes da tese.")
    try:
        booked = book.load_booked(week)
    except ValueError:
        booked = None
    chosen = approved[-1]
    if booked is not None:
        chosen = next(((p, d) for p, d in approved if p.proposal_id == booked.proposal_id),
                      chosen)
    p, d = chosen
    if p.proposal_hash() != d.proposal_hash:
        raise ValueError(f"A proposta v{p.version} de {week} não confere com o hash da decisão "
                         "(arquivo alterado); tese recusada.")
    if is_hold(p):
        raise HoldWeekError(f"A decisão de {week} manteve a carteira vigente (sem carteira nova): "
                            "a tese vigente é a da semana em que a carteira foi montada; não há "
                            "tese a publicar nesta semana.")
    return p, d


class HoldWeekError(ValueError):
    """Semana em que a decisão manteve a carteira vigente: não há carteira nova a explicar."""


def is_hold(p: Proposal) -> bool:
    """Proposta ``manter`` (ou sem posições): a carteira da semana é a anterior, não uma nova."""
    return p.overrides.get("label") == "manter" or not p.positions


def issuer_weights(p: Proposal) -> pd.Series:
    """Pesos por emissor (soma das linhas), ordenados por |peso| decrescente e id."""
    w: dict[str, float] = {}
    for t in p.positions:
        w[t.issuer_id] = w.get(t.issuer_id, 0.0) + float(t.weight)
    s = pd.Series(w, dtype=float)
    s = s[s != 0]
    order = sorted(s.index, key=lambda i: (-abs(float(s[i])), str(i)))
    return s.reindex(order)


def _briefing_facts(week_dir: Path) -> dict[str, str]:
    path = week_dir / "briefing" / "context.json"
    if not path.is_file():
        return {}
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    facts = raw.get("facts") if isinstance(raw, dict) else None
    if not isinstance(facts, dict):
        return {}
    return {str(k): str(v.get("formatted", "n/d")) for k, v in facts.items()
            if isinstance(v, dict)}


def decision_config(week_dir: Path, config_hash: str, *,
                    historico: Path | None = None) -> ConfigDecisao | None:
    """Configuração vigente no ``decide`` da semana, autenticada pelo ``config_hash`` da proposta.

    Ordem: ``book/<semana>/config_decisao.json`` → ``configs/cdp/historico/<config_hash>.json``
    do repositório que contém o livro (:func:`cdp.config.book_historico_dir`; ``historico``
    substitui a pasta). O hash do JSON BRUTO é conferido ANTES da validação
    (:func:`cdp.config.load_archived_config`), então campos acrescentados ao esquema depois da
    decisão não tornam o arquivo "divergente". Quem compara com um hash gravado usa
    ``ConfigDecisao.hash``; ``None`` se nenhuma fonte confere."""
    from ..config import archived_config, book_historico_dir, load_archived_config
    from .runtime import DECISION_CONFIG

    found = load_archived_config(week_dir / DECISION_CONFIG, config_hash)
    if found is not None:
        return found
    return archived_config(config_hash,
                           historico if historico is not None
                           else book_historico_dir(week_dir.parent))


def _load_shadow(week_dir: Path) -> Proposal | None:
    path = week_dir / "shadow_quant.json"
    if not path.is_file():
        return None
    try:
        return Proposal.model_validate(json.loads(path.read_text(encoding="utf-8")))
    except (OSError, ValueError):
        return None


def load_inputs(rt: Runtime, week: date) -> ThesisInputs:
    """Reconstrói (com hashes conferidos) o estado da semana decidida, sem reotimizar.

    Usa a configuração da decisão quando disponível e a decisão do PM VERIFICADA que o
    ``decide`` usou (ver docstring do módulo).
    """
    from dataclasses import replace

    from .weekly import prepare_week

    book = rt.book
    p, d = approved_proposal(book, week)
    wdir = rt.week_dir(week)
    md, info = rt.market_for_week(week, live=False, briefing_dir=wdir / "briefing",
                                  record=False)
    if md.manifest.content_hash() != p.snapshot_hash:
        raise ValueError(f"O snapshot reconstruído de {week} difere do usado na proposta "
                         "aprovada; tese recusada.")
    notes: list[str] = []
    cfg, drift = rt.cfg, False
    if rt.cfg.config_hash() != p.config_hash:
        archived = decision_config(wdir, p.config_hash)
        if archived is not None:
            cfg = archived.cfg
        else:
            drift = True
            notes.append("O mandato foi recalibrado depois da decisão e a configuração da época "
                         "não está disponível: alpha quantitativo, contribuições dos sinais, "
                         "inclinação das visões, motivo do tamanho de cada posição e "
                         "decomposição do risco por grupo e fator não são exibidos; limites "
                         "exibidos são os do mandato atual e os números de risco registrados "
                         "na decisão prevalecem.")
    rt_dec = rt if cfg is rt.cfg else replace(rt, cfg=cfg)
    entry, drifted, drawdown = rt_dec.decision_state(week)
    # Mesmo estado do ``_context`` da decisão: sem registro diário o drawdown entra como 0,0.
    ctx = prepare_week(md, cfg, week, nav=p.nav_usd, current_entry=entry,
                       current_drifted_w=drifted,
                       drawdown=drawdown if drawdown is not None else 0.0)
    pm = rt_dec.decision_pm_output(week, md, ctx, info, d)
    if pm is None:
        notes.append("A decisão do PM da semana não pôde ser reproduzida exatamente como foi "
                     "usada na decisão: visões, convicção e postura do PM aparecem como não "
                     "disponíveis.")
    return ThesisInputs(
        week=week, cfg=cfg, proposal=p, decision=d, ctx=ctx, weights=issuer_weights(p),
        pack=book.load_research_pack(week), pm=pm, shadow=_load_shadow(wdir),
        briefing_facts=_briefing_facts(wdir), drawdown=drawdown,
        fund_name=cfg.fund.name, notes=notes, config_drift=drift, pm_verified=pm is not None)


# ==========================================================
# Pesquisa e visões por emissor
# ==========================================================

def render_research_text(text: object, facts: Mapping[str, str]) -> str:
    """Texto de pesquisa (dado não confiável, já validado na entrada) com placeholders
    resolvidos pelos fatos do briefing; espaços normalizados."""
    from ..research.guardrails import PLACEHOLDER_RE

    s = " ".join(str(text or "").split())
    return PLACEHOLDER_RE.sub(lambda m: facts.get(m.group(1), "[fato indisponível]"), s)


def notes_by_issuer(pack: ResearchPack | None) -> dict[str, dict[str, list[ResearchNote]]]:
    """Notas de pesquisa por emissor e papel (``fundamental``, ``short_risk``…), por ``note_id``."""
    out: dict[str, dict[str, list[ResearchNote]]] = {}
    for n in (pack.notes if pack is not None else []):
        out.setdefault(n.issuer_id, {}).setdefault(n.role, []).append(n)
    for roles in out.values():
        for lst in roles.values():
            lst.sort(key=lambda n: n.note_id)
    return out


def pm_views(pm: PMDecisionOutput | None) -> dict[str, Any]:
    """Primeira visão do PM por emissor (mesma regra de ``pm_output_to_views``)."""
    out: dict[str, Any] = {}
    if pm is None or pm.abstain:
        return out
    for v in pm.views:
        out.setdefault(v.issuer_id, v)
    return out


def pm_journal(pm: PMDecisionOutput | None) -> dict[str, Any]:
    """Primeiro item do diário do PM por emissor (tese, invalidação e pré-mortem)."""
    out: dict[str, Any] = {}
    for j in (pm.position_journal if pm is not None else []):
        out.setdefault(j.issuer_id, j)
    return out


def _week_views(ti: ThesisInputs) -> list:
    """Visões usadas no ``decide``: as do pacote de pesquisa gravado + as do PM verificadas
    (código), tratadas como na tentativa que gerou a proposta aprovada (``overrides.label``):
    ``cdp-restricoes``/``reduzir-risco`` ⇒ só restrições; ``quant`` ⇒ nenhuma."""
    from ..research.pm_agent import pm_output_to_views
    from .weekly import tighten_only

    views = list(ti.pack.views) if ti.pack is not None else []
    if ti.pm is not None:
        try:
            pmv, _ov, _j = pm_output_to_views(ti.pm, ti.cfg, drawdown=ti.drawdown)
        except ValueError:
            pmv = []
        views = views + list(pmv)
    label = ti.proposal.overrides.get("label")
    if label in ("quant", "sombra-quant"):
        return []
    if label in ("cdp-restricoes", "reduzir-risco"):
        return tighten_only(views)
    return views


# ==========================================================
# Limites por emissor e dimensionamento
# ==========================================================

@dataclass
class SizingTable:
    """Limites por emissor reconstruídos (``None`` = indisponível) e a conferência das visões."""

    constraints: pd.DataFrame | None
    pre_liq: pd.DataFrame | None
    vol_target: float
    views_ok: bool | None
    n_view_mismatch: int = 0


def sizing_table(ti: ThesisInputs) -> SizingTable:
    """Tabela de limites por emissor exatamente como no ``build_proposal`` (sem otimizar)."""
    from ..alpha.views import apply_views
    from ..portfolio.optimizer import build_asset_constraints
    from .weekly import apply_liquidity_minimums, apply_specific_risk_caps

    ctx, cfg, p = ti.ctx, ti.cfg, ti.proposal
    vt = float(p.overrides.get("vol_target", cfg.risk.vol_target_annual))
    if ti.config_drift:  # limites da configuração atual não explicam a decisão
        return SizingTable(None, None, vt, None)
    try:
        spec_vol = ctx.model.specific_vol
        adjusted, vcons, _log = apply_views(ctx.alpha.alpha, _week_views(ti), spec_vol, cfg)
        stored = {t.issuer_id: _f(t.alpha_annual) for t in p.positions}
        mism = 0
        for iid, a in stored.items():
            b = _f(adjusted.get(iid))
            if (a is None) != (b is None) or (a is not None and b is not None
                                              and abs(a - b) > 1e-9):
                mism += 1
        issuers = list(ctx.model.assets)
        current = ctx.current_w.reindex(issuers).fillna(0.0) if len(ctx.current_w) else None
        c = build_asset_constraints(issuers, ctx.sides, ctx.squeeze, vcons, ctx.betas,
                                    ctx.panel.assets, cfg, ctx.nav, current=current,
                                    inception=ctx.inception)
        pre = c.copy()
        c = apply_liquidity_minimums(c, cfg, ctx.nav)
        c = apply_specific_risk_caps(c, spec_vol, cfg, vt)
        return SizingTable(c, pre, vt, mism == 0, mism)
    except Exception:  # noqa: BLE001 - dimensionamento é explicativo; nunca derruba a tese
        return SizingTable(None, None, vt, None)


def _caps(row: pd.Series, side: str, cfg: FundConfig, nav: float, spec_vol: float | None,
          vt: float) -> dict[str, float | None]:
    rk, liq = cfg.risk, cfg.liquidity
    view = _f(row.get("view_max_abs"))
    if side == "LONG":
        adtv = _f(row.get("adtv_long_usd"))
        liq_cap = (liq.participation_rate * adtv * liq.max_days_to_liquidate_long / nav
                   if adtv is not None else 0.0)
        name_cap = float(rk.max_long_weight)
        mult = 1.0
    else:
        adtv = _f(row.get("adtv_short_usd"))
        liq_cap = (liq.short_participation_rate * adtv * liq.max_days_to_liquidate_short / nav
                   if adtv is not None else 0.0)
        name_cap = float(rk.max_short_weight)
        bucket = str(row.get("squeeze_bucket") or "NA")
        mult = (float(cfg.squeeze.medium_short_cap_multiplier)
                if bucket in ("MEDIUM", "NA") else 1.0)
    spec_cap = (math.sqrt(rk.max_single_name_risk_share) * vt / spec_vol
                if spec_vol is not None and spec_vol > 0 else None)
    col = "max_long" if side == "LONG" else "max_short"
    return {"teto_nome": name_cap, "liquidez": liq_cap, "teto_visao": view,
            "squeeze_mult": mult, "teto_risco": spec_cap, "efetivo": _f(row.get(col)),
            "execucao": _f(row.get("max_trade_liq")), "atual": _f(row.get("current"))}


def sizing_driver(iid: str, weight: float, caps: Mapping[str, float | None] | None,
                  binding: Iterable[str]) -> str:
    """Restrição que define o tamanho (ver docstring do módulo)."""
    if caps is None:
        return "indeterminado"
    side = "LONG" if weight > 0 else "SHORT"
    a = abs(weight)
    eff = caps.get("efetivo")

    def at(cap: float | None) -> bool:
        return cap is not None and cap > 0 and a >= cap * (1 - SIZING_TOL) - 1e-9

    bind = set(binding)
    if at(eff):
        spec = caps.get("teto_risco")
        if spec is not None and eff is not None and spec <= eff * (1 + SIZING_TOL):
            return "teto_risco"
        comps = {k: caps.get(k) for k in ("teto_nome", "liquidez", "teto_visao")}
        valid = {k: v for k, v in comps.items() if v is not None}
        if not valid:
            return "indeterminado"
        base = min(valid.values())
        mult = caps.get("squeeze_mult") or 1.0
        if side == "SHORT" and mult < 1.0 - 1e-12:
            return "squeeze"
        for k in ("teto_visao", "liquidez", "teto_nome"):
            if k in valid and valid[k] <= base * (1 + SIZING_TOL):
                return k
        return "indeterminado"
    col = "max_long" if side == "LONG" else "max_short"
    if f"{col}:{iid}" in bind:
        return "teto_risco"
    if f"max_trade:{iid}" in bind or f"max_trade_liq:{iid}" in bind:
        return "liquidez"
    ex, cur = caps.get("execucao"), caps.get("atual") or 0.0
    if ex is not None and ex > 0 and abs(weight - cur) >= ex * (1 - SIZING_TOL) \
            and abs(weight) > abs(cur):
        return "liquidez"
    return "interior"


def position_role(weight: float, alpha: float | None, risk: float | None) -> str:
    if alpha is None or np.sign(weight) * alpha <= 0:
        return "hedge"
    return "alpha_div" if risk is not None and risk < 0 else "alpha"


# ==========================================================
# Posições
# ==========================================================

def _next_earnings(md: Any, iid: str, as_of: date) -> str | None:
    fund = getattr(md, "fundamentals", None)
    if fund is None or fund.empty or "next_earnings_date" not in fund.columns:
        return None
    lines = md.universe.lines
    tickers = [t for t in lines.index[lines["issuer_id"] == iid] if t in fund.index]
    found: list[date] = []
    for t in tickers:
        raw = fund.loc[t, "next_earnings_date"]
        try:
            d = pd.Timestamp(raw).date() if raw is not None and not pd.isna(raw) else None
        except (TypeError, ValueError):
            d = None
        if d is not None and d >= as_of:
            found.append(d)
    return min(found).isoformat() if found else None


def _tilt(alpha: float | None, alpha_quant: float | None) -> float | None:
    """Inclinação das visões (α da proposta − α quantitativo); ruído numérico ⇒ zero exato."""
    if alpha is None or alpha_quant is None:
        return None
    t = alpha - alpha_quant
    return 0.0 if abs(t) < 1e-12 else t


def _event_exposure(ctx: WeekContext, iid: str) -> float | None:
    for _name, spec in sorted(ctx.event_exposures.items()):
        v = _f((spec.get("exposures") or {}).get(iid))
        if v is not None:
            return v
    return None


def _cell(frame: pd.DataFrame | None, iid: str, col: str) -> float | None:
    if frame is None or frame.empty or col not in frame.columns or iid not in frame.index:
        return None
    return _f(frame.loc[iid, col])


def build_positions(ti: ThesisInputs, table: SizingTable) -> list[dict[str, Any]]:
    """Linhas por emissor detido (ordem |peso| decrescente) com todos os campos numéricos."""
    ctx, cfg, p = ti.ctx, ti.cfg, ti.proposal
    nav = float(p.nav_usd)
    as_of = ti.week
    binding = list(p.optimizer.binding_constraints)
    notes = notes_by_issuer(ti.pack)
    views = pm_views(ti.pm)
    by_iid: dict[str, list] = {}
    for t in p.positions:
        by_iid.setdefault(t.issuer_id, []).append(t)
    lines = ctx.md.universe.lines
    spec_vol = ctx.model.specific_vol
    out: list[dict[str, Any]] = []
    for iid, w in ti.weights.items():
        w = float(w)
        legs = by_iid.get(iid, [])
        t = max(legs, key=lambda x: abs(x.weight)) if legs else None
        side = "LONG" if w > 0 else "SHORT"
        alpha = _f(t.alpha_annual) if t else None
        risk = sum(_f(x.risk_contribution) or 0.0 for x in legs) \
            if legs and all(_f(x.risk_contribution) is not None for x in legs) else None
        # Alpha quantitativo e sinais só com a configuração da decisão (senão ``None``).
        aq = None if ti.config_drift else _f(ctx.alpha.alpha.get(iid))
        caps = None
        if table.constraints is not None and iid in table.constraints.index:
            caps = _caps(table.constraints.loc[iid], side, cfg, ctx.nav,
                         _f(spec_vol.get(iid)), table.vol_target)
        sizing = sizing_driver(iid, w, caps, binding)
        notional = sum(float(x.notional_usd) for x in legs)
        adtv = _f(t.adtv_usd) if t else None
        part = (cfg.liquidity.participation_rate if side == "LONG"
                else cfg.liquidity.short_participation_rate)
        days = abs(notional) / (part * adtv) if adtv and adtv > 0 and part > 0 else None
        fnote = (notes.get(iid, {}).get("fundamental") or [None])[0]
        snote = (notes.get(iid, {}).get("short_risk") or [None])[0]
        view = views.get(iid)
        row: dict[str, Any] = {
            "iid": iid, "name": t.name if t else iid,
            "tickers": sorted({str(x) for x in lines.index[lines["issuer_id"] == iid]}),
            "execution_ticker": t.execution_ticker if t else None,
            "country": t.country if t else None, "sector": t.sector if t else None,
            "side": side, "weight": w, "weight_usd": w * nav, "role": position_role(w, alpha, risk),
            "sizing": sizing, "caps": caps,
            "alpha": alpha, "alpha_quant": aq,
            "tilt": _tilt(alpha, aq),
            "beta": _f(t.beta) if t else None, "risk": risk,
            "alpha_contrib": _mul(w, alpha),
        }
        for sig, code, _label in SIGNALS:
            row[f"z_{code}"] = None if ti.config_drift else _cell(ctx.alpha.signal_z, iid, sig)
            row[f"c_{code}"] = (None if ti.config_drift
                                else _cell(ctx.alpha.contributions_pure, iid, sig))
        for c in ("oil", "copper", "gold"):
            row[c] = _cell(ctx.commodity_betas, iid, c)
        row.update({
            "election": _event_exposure(ctx, iid),
            "next_earnings": _next_earnings(ctx.md, iid, as_of),
            "r_stance": fnote.stance if fnote else None,
            "r_conf": fnote.confidence if fnote else None,
            "r_squeeze": snote.squeeze.verdict if snote and snote.squeeze else None,
            "pm_stance": view.stance if view is not None else None,
            "pm_conv": view.conviction if view is not None else None,
            "days_liq": days, "pct_adtv": _f(t.pct_adtv) if t else None,
            "borrow": _f(t.borrow_fee_annual) if t and side == "SHORT" else None,
            "squeeze_score": _f(t.squeeze_score) if t else None,
            "squeeze_bucket": t.squeeze_bucket if t else None,
            "alpha_z": _f(t.alpha_z) if t else None,
        })
        out.append(row)
    return out


# ==========================================================
# Números da carteira
# ==========================================================

def _close(a: float | None, b: float | None, tol: float = RISK_CHECK_TOL) -> bool:
    if a is None or b is None:
        return a is None and b is None
    return abs(a - b) <= tol * max(1.0, abs(a), abs(b)) or abs(a - b) <= 1e-12


def risk_check(ti: ThesisInputs) -> tuple[Any, dict[str, Any]]:
    """``RiskSummary`` recalculado e a conferência com o gravado (vol, beta, participação)."""
    from .weekly import risk_summary

    rs = risk_summary(ti.ctx, ti.weights)
    stored = ti.proposal.risk
    out: dict[str, Any] = {}
    for key in ("ex_ante_vol", "beta", "factor_risk_share"):
        a, b = _f(getattr(stored, key)), _f(getattr(rs, key))
        out[key] = {"gravado": a, "recalculado": b, "confere": _close(a, b)}
    out["ok"] = all(v["confere"] for v in out.values() if isinstance(v, dict))
    return rs, out


def _liquidity(positions: Sequence[Mapping[str, Any]], cfg: FundConfig,
               nav: float) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for side, key in (("LONG", "long"), ("SHORT", "short")):
        part = (cfg.liquidity.participation_rate if side == "LONG"
                else cfg.liquidity.short_participation_rate)
        rows = [r for r in positions if r["side"] == side]
        total = sum(abs(r["weight"]) for r in rows)
        res: dict[str, Any] = {"participation": part, "n": len(rows)}
        missing = any(r["days_liq"] is None for r in rows)
        for h in LIQ_HORIZONS:
            if not rows or missing or total == 0:
                res[f"d{int(h)}"] = None
                continue
            liquid = sum(min(1.0, h / r["days_liq"]) * abs(r["weight"]) if r["days_liq"] > 0
                         else abs(r["weight"]) for r in rows)
            res[f"d{int(h)}"] = liquid / total
        days = [r["days_liq"] for r in rows if r["days_liq"] is not None]
        res["max_days"] = max(days) if days else None
        res["limit_days"] = float(cfg.liquidity.max_days_to_liquidate_long if side == "LONG"
                                  else cfg.liquidity.max_days_to_liquidate_short)
        out[key] = res
    return out


def _exposure_rows(p: Proposal, group: str) -> list[Any]:
    return [e for e in p.risk.exposures if e.group == group]


VOL_BASIS: tuple[str, ...] = ("vies_postura", "postura", "vies_mandato", "mandato", "piso",
                               "outro")
"""Origem da meta de vol aplicada (mesmo teste em :func:`_vol_budget` e no texto da tese)."""


def vol_target_basis(applied: float | None, post_vol: float | None,
                     cfg: FundConfig) -> str | None:
    """Como a meta aplicada foi obtida (``effective_vol_target``, sem reotimizar).

    ``vies_postura``: meta da postura ÷ viés a priori (histórico curto); ``postura``: meta da
    postura sem ajuste (histórico suficiente); ``vies_mandato``/``mandato``: idem a partir da
    meta do mandato (postura indisponível ou carteira de contingência); ``piso``: limitada ao
    piso da banda; ``outro``: nenhuma das anteriores; ``None``: meta não registrada.
    """
    rk = cfg.risk
    if applied is None:
        return None
    candidates: list[tuple[str, float | None]] = [
        ("vies_postura", None if post_vol is None else post_vol / rk.bias_prior),
        ("postura", post_vol),
        ("vies_mandato", rk.vol_target_annual / rk.bias_prior),
        ("mandato", rk.vol_target_annual),
        ("piso", rk.vol_band_min),
    ]
    for basis, value in candidates:
        if value is not None and _close(applied, float(value), 1e-6):
            return basis
    return "outro"


def _vol_budget(ti: ThesisInputs) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    from ..portfolio.optimizer import FLOOR_MARGIN, MATCH_REL_TOL
    from ..research.pm_agent import POSTURE_PT, REGIME_PT, posture_limits

    cfg, p = ti.cfg, ti.proposal
    rk = cfg.risk
    applied = _f(p.overrides.get("vol_target"))
    achieved = _f(p.risk.ex_ante_vol)
    posture = ti.pm.risk_posture if ti.pm is not None else None
    limits = None
    if posture is not None:
        try:
            limits = posture_limits(posture, cfg, ti.drawdown)
        except ValueError:
            limits = None
    post_vol = limits.vol_target if limits is not None else None
    regime = REGIME_PT.get(ti.pm.regime, ti.pm.regime) if ti.pm is not None else None
    basis = vol_target_basis(applied, post_vol, cfg)
    meta = {"posture": limits.effective if limits else posture,
            "posture_requested": posture, "regime": ti.pm.regime if ti.pm else None,
            "bias_prior": float(rk.bias_prior), "risk_target_mode": rk.risk_target_mode,
            "vol_basis": basis, "pm_verified": bool(ti.pm_verified),
            "config_drift": bool(ti.config_drift)}
    if limits is None:
        post_note = ("Postura do PM não disponível: a decisão do PM não pôde ser reproduzida."
                     if not ti.pm_verified else "Postura não informada pela decisão do PM.")
    else:
        post_note = (f"Postura {POSTURE_PT[limits.effective]}"
                     + (f" (regime {regime})" if regime else "")
                     + ("; escada de drawdown rebaixou a postura solicitada."
                        if limits.effective != limits.requested else "."))
    app_note = {
        None: "Meta aplicada não registrada na decisão (vale a do mandato).",
        "vies_postura": (f"Meta da postura dividida pelo viés a priori de "
                         f"{_br(rk.bias_prior, 2)}: carteiras otimizadas subestimam o risco nas "
                         f"primeiras {rk.bias_prior_weeks} semanas de histórico."),
        "postura": "Meta da postura, sem ajuste de viés (histórico suficiente).",
        "vies_mandato": (f"Meta do mandato dividida pelo viés a priori de "
                         f"{_br(rk.bias_prior, 2)}: carteiras otimizadas subestimam o risco nas "
                         f"primeiras {rk.bias_prior_weeks} semanas de histórico."),
        "mandato": "Meta do mandato, sem ajuste de viés (histórico suficiente).",
        "piso": "Meta limitada ao piso da banda do mandato.",
        "outro": "Meta aplicada pelo código (postura, viés a priori e banda do mandato).",
    }[basis]
    floor_target = rk.vol_band_min * (1 + FLOOR_MARGIN)
    bind = list(p.optimizer.binding_constraints)
    neutral = [b for b in bind if not b.startswith(("max_long:", "max_short:", "max_trade"))]
    per_name = [b for b in bind if b.startswith(("max_long:", "max_short:"))]
    if achieved is None or applied is None:
        ach_note = "Vol ex-ante da carteira aprovada."
    elif achieved >= applied * (1 - MATCH_REL_TOL):
        ach_note = "Meta aplicada atingida."
    else:
        parts = []
        if rk.risk_target_mode == "match" and achieved <= floor_target * 1.01:
            parts.append("O alpha líquido de custos não sustentou a meta aplicada; o otimizador "
                         "ampliou o risco apenas até o piso da banda, com margem de segurança.")
        else:
            parts.append("O alpha líquido de custos não sustentou a meta aplicada dentro dos "
                         "limites da carteira.")
        if neutral:
            parts.append("Neutralidades ativas no ótimo: " + ", ".join(
                _binding_label(b) for b in neutral) + ".")
        if per_name:
            parts.append(f"{len(per_name)} nomes no teto individual (peso, risco, liquidez, "
                         "visão ou squeeze).")
        ach_note = "Abaixo da meta aplicada. " + " ".join(parts)
    steps = [
        {"step": "mandato", "label": "Meta do mandato", "value": float(rk.vol_target_annual),
         "note": "Meta de volatilidade ex-ante anual do mandato."},
        {"step": "postura", "label": "Meta da postura", "value": post_vol, "note": post_note},
        {"step": "aplicada", "label": "Meta aplicada", "value": applied, "note": app_note},
        {"step": "piso", "label": "Piso da banda", "value": float(rk.vol_band_min),
         "note": "Piso da banda do mandato: abaixo dele o orçamento de risco fica subutilizado."},
        {"step": "atingida", "label": "Vol ex-ante atingida", "value": achieved,
         "note": ach_note},
    ]
    return steps, meta


def _br(v: float, digits: int) -> str:
    text = f"{abs(v):,.{digits}f}"
    text = text.replace(",", "\x00").replace(".", ",").replace("\x00", ".")
    return ("-" if v < 0 and round(abs(v), digits) != 0 else "") + text


def _binding_label(b: str) -> str:
    if b in BINDING_PT:
        return BINDING_PT[b]
    kind, _, name = b.partition(":")
    if kind == "country":
        return f"país {country_label(name)}"
    if kind == "sector":
        return f"setor {sector_label(name)}"
    if kind == "style":
        return f"estilo {style_label(name).lower()}"
    return b


def _sensitivity(ti: ThesisInputs) -> tuple[list[dict[str, Any]], dict[str, Any], list[str]]:
    from ..research.factbook import level_returns
    from ..risk.analytics import historical_pnl

    ctx, p = ti.ctx, ti.proposal
    nav = float(p.nav_usd)
    beta = _f(p.risk.beta)
    rows: list[dict[str, Any]] = [{
        "code": "MERCADO", "label": "Mercado LatAm (beta do modelo)", "kind": "modelo",
        "beta": beta, "corr": None, "shock": SHOCK_MARKET, "pnl": _mul(beta, SHOCK_MARKET),
        "pnl_usd": _mul(_mul(beta, SHOCK_MARKET), nav), "n_obs": None}]
    missing: list[str] = []
    try:
        pnl, _meta = historical_pnl(ti.weights, ctx.panel, ctx.model, HIST_LOOKBACK)
        pnl = pnl.dropna()
    except Exception:  # noqa: BLE001 - histórico é complementar
        pnl = pd.Series(dtype=float)
    hist: dict[str, Any] = {"vol": None, "n_days": int(len(pnl)), "start": None, "end": None}
    if len(pnl) >= 20:
        hist.update({"vol": float(pnl.std(ddof=1) * math.sqrt(TRADING_DAYS)),
                     "start": pnl.index[0].date().isoformat(),
                     "end": pnl.index[-1].date().isoformat()})
    as_of = pd.Timestamp(ctx.md.as_of)
    for code, label, kind, col, shock in SENS_SERIES:
        frame = ctx.md.benchmarks if kind == "bench" else ctx.md.fx
        if frame is None or col not in frame.columns or pnl.empty:
            missing.append(label)
            continue
        r = level_returns(frame[col].loc[:as_of])
        df = pd.concat([pnl.rename("p"), r.rename("r")], axis=1, join="inner").dropna()
        if len(df) < MIN_SENS_OBS or not df["r"].var(ddof=1) > 0:
            missing.append(label)
            continue
        b = float(df["p"].cov(df["r"]) / df["r"].var(ddof=1))
        corr = float(df["p"].corr(df["r"]))
        rows.append({"code": code, "label": label, "kind": "historico", "beta": b, "corr": corr,
                     "shock": shock, "pnl": b * shock, "pnl_usd": b * shock * nav,
                     "n_obs": int(len(df))})
    return rows, hist, missing


def _missing_in_window(ti: ThesisInputs, d0: date, d1: date) -> list[str]:
    """Emissores sem retorno observado nem implícito na janela (motivo de "sem dados")."""
    from ..risk.analytics import model_implied_returns

    panel, model = ti.ctx.panel, ti.ctx.model
    held = [i for i in ti.weights.index if i in model.assets]
    cal = pd.DatetimeIndex(panel.returns.index)
    dates = cal[(cal > pd.Timestamp(d0)) & (cal <= pd.Timestamp(d1))]
    if len(dates) == 0 or not held:
        return []
    rets = panel.returns.reindex(index=dates, columns=held)
    px = panel.price_usd.reindex(columns=held)
    traded = px.loc[px.index <= pd.Timestamp(d0)].notna().any()
    covered = rets.notna().any() & traded
    miss = [i for i in held if not bool(covered.get(i, False))]
    if not miss:
        return []
    implied = model_implied_returns(model, miss, dates)
    return [i for i in miss if implied[i].dropna().empty]


def _historical_contrib(ti: ThesisInputs, d0: date, d1: date) -> pd.Series | None:
    """Contribuição por emissor de uma réplica histórica (mesma conta do ``stress``)."""
    from ..risk.analytics import model_implied_returns

    panel, model = ti.ctx.panel, ti.ctx.model
    w = ti.weights[[i for i in ti.weights.index if i in model.assets]]
    cal = pd.DatetimeIndex(panel.returns.index)
    dates = cal[(cal > pd.Timestamp(d0)) & (cal <= pd.Timestamp(d1))]
    if len(dates) == 0 or w.empty:
        return None
    rets = panel.returns.reindex(index=dates, columns=w.index)
    px = panel.price_usd.reindex(columns=w.index)
    traded = px.loc[px.index <= pd.Timestamp(d0)].notna().any()
    cum = pd.Series(np.nan, index=w.index)
    for iid in w.index:
        r = rets[iid].dropna()
        if len(r) and bool(traded.get(iid, False)):
            cum[iid] = float(np.prod(1.0 + r.to_numpy()) - 1.0)
    miss = list(cum.index[cum.isna()])
    if miss:
        implied = model_implied_returns(model, miss, dates)
        for iid in miss:
            r = implied[iid].dropna()
            if r.empty:
                return None
            cum[iid] = float(np.prod(1.0 + r.to_numpy()) - 1.0)
    return (w * cum).rename("pnl")


def _stress(ti: ThesisInputs, names: Mapping[str, str]) -> tuple[list[dict[str, Any]], list[str]]:
    from ..risk.stress import HISTORICAL_SCENARIOS, IDIO_TOP_N, stress_report
    from .weekly import country_gap_stress

    ctx, p = ti.ctx, ti.proposal
    nav = float(p.nav_usd)
    stored = {k: _f(v) for k, v in p.risk.stress_tests.items()}
    rep = stress_report(ti.weights, ctx.panel, ctx.model, ctx.market_w)
    gaps = country_gap_stress(ti.weights, ctx.panel.assets, ti.cfg)
    rows: list[dict[str, Any]] = []
    diverge: list[str] = []
    used: set[str] = set()

    def code_for(name: str) -> str:
        base = code_slug(name)
        code, k = base, 2
        while code in used:
            code, k = f"{base}_{k}", k + 1
        used.add(code)
        return code

    for name, r in rep.iterrows():
        rec = _f(r["pnl"])
        sto = stored.get(name)
        pnl = sto if sto is not None else rec
        if sto is not None and rec is not None and not _close(sto, rec, 1e-6):
            diverge.append(str(name))
        kind = STRESS_KIND.get(str(r["kind"]), "hipotetico")
        status = "ok" if pnl is not None else "sem dados"
        note = ""
        if kind == "historico" and name in HISTORICAL_SCENARIOS:
            d0, d1 = HISTORICAL_SCENARIOS[str(name)]
            note = f"Réplica estática de {d0.isoformat()} a {d1.isoformat()}."
            if pnl is None:
                cal = ctx.panel.returns.index
                if len(cal) == 0 or cal[0] > pd.Timestamp(d0):
                    note += " Sem dados: o histórico de preços não cobre a janela."
                else:
                    miss = _missing_in_window(ti, d0, d1)
                    who = ", ".join(names.get(i, i) for i in miss) or "algum nome"
                    note += (" Sem dados: sem retorno observado nem implícito pelo modelo para "
                             f"{who}.")
            else:
                contrib = _historical_contrib(ti, d0, d1)
                if contrib is not None and _close(float(contrib.sum()), pnl, 1e-6):
                    note += _top_contributor(contrib, pnl, names)
        elif kind == "hipotetico":
            note = "Choque fatorial com propagação condicional pela covariância do modelo."
        elif kind == "idiossincratico":
            leg = (ti.weights[ti.weights < 0].sort_values() if str(name).lower()
                   .startswith("squeeze") else
                   ti.weights[ti.weights > 0].sort_values(ascending=False)).head(IDIO_TOP_N)
            note = ("Choque específico simultâneo nos maiores nomes da ponta: "
                    + ", ".join(names.get(i, i) for i in leg.index) + ".")
        rows.append({"code": code_for(str(name)), "label": str(name), "kind": kind, "pnl": pnl,
                     "usd": _mul(pnl, nav), "status": status, "note": note})
    for name, v in gaps.items():
        sto = stored.get(name)
        pnl = sto if sto is not None else _f(v)
        country, label = gap_label(name)
        rows.append({"code": code_for(name), "label": label, "kind": "gap", "pnl": pnl,
                     "usd": _mul(pnl, nav), "status": "ok" if pnl is not None else "sem dados",
                     "country": country,
                     "note": "Gap simultâneo de todos os emissores do país (exposição líquida "
                             "× choque)."})
    rows.sort(key=lambda r: (r["pnl"] is None, r["pnl"] if r["pnl"] is not None else 0.0,
                             r["code"]))
    return rows, diverge


def _top_contributor(contrib: pd.Series, pnl: float, names: Mapping[str, str]) -> str:
    """Maior contribuição individual NA DIREÇÃO do resultado do cenário (perda ou ganho)."""
    c = contrib.dropna()
    if c.empty:
        return ""
    if pnl < 0:
        iid, word = c.idxmin(), "Maior perda individual"
    else:
        iid, word = c.idxmax(), "Maior ganho individual"
    return f" {word}: {names.get(iid, iid)} ({_br(float(c[iid]) * 100, 2)} p.p.)."


def gap_label(name: str) -> tuple[str | None, str]:
    """(código do país, rótulo) de um cenário ``country_gap_stress`` (``"Gap BR -10%"`` ⇒
    ``("BR", "Gap Brasil −10%")``); o código do cenário continua o do nome original."""
    parts = str(name).split()
    if len(parts) != 3 or parts[0] != "Gap":
        return None, str(name)
    country, move = parts[1], parts[2]
    if move.startswith("-"):
        move = "−" + move[1:]
    return country, f"Gap {country_label(country)} {move}"


def _util(value: float | None, limit: float | None) -> float | None:
    """Utilização do limite (|valor| / |limite|); limite ausente ou nulo ⇒ ``None``."""
    if value is None or limit is None or limit == 0:
        return None
    return abs(value) / abs(limit)


def _funnel(ti: ThesisInputs, table: SizingTable) -> dict[str, Any]:
    p, ctx, cfg = ti.proposal, ti.ctx, ti.cfg
    excl = [{"code": k, "label": EXCLUSION_PT.get(k.split(":")[0], k), "n": int(v)}
            for k, v in p.optimizer.n_excluded.items()]
    pre = table.pre_liq
    if pre is not None:
        has_alpha = ctx.alpha.alpha.reindex(pre.index).notna()
        liq = cfg.liquidity
        low_l = ~(pd.to_numeric(pre["adtv_long_usd"], errors="coerce") >= liq.min_adtv_long_usd)
        low_s = ~(pd.to_numeric(pre["adtv_short_usd"], errors="coerce")
                  >= liq.min_adtv_short_usd)
        n_l = int((low_l & (pre["max_long"] > 0) & has_alpha).sum())
        n_s = int((low_s & (pre["max_short"] > 0) & has_alpha).sum())
        for code, n in (("liquidez_minima_long", n_l), ("liquidez_minima_short", n_s)):
            if n:
                excl.append({"code": code, "label": EXCLUSION_PT[code], "n": n})
    excl.sort(key=lambda r: (-r["n"], r["code"]))
    return {"universe": int(len(ctx.panel.eligible)), "candidates": int(p.optimizer.n_candidates),
            "exclusions": excl, "final": int(len(ti.weights)), "long": int(p.risk.n_long),
            "short": int(p.risk.n_short)}


def _reference(ti: ThesisInputs) -> dict[str, Any] | None:
    from .reports import _overlap

    s = ti.shadow
    if s is None:
        return None
    ov = _overlap(ti.proposal, s)
    return {"alpha": _f(s.optimizer.expected_alpha_annual), "vol": _f(s.risk.ex_ante_vol),
            "names": int(ov["names_shadow"]), "common": int(ov["common_same_side"]),
            "active_share": _f(ov["active_share"]), "overlap": _f(ov["weight_overlap"]),
            "cost": _f(s.optimizer.expected_cost_annual), "beta": _f(s.risk.beta),
            "factor_share": _f(s.risk.factor_risk_share)}


def _currencies(p: Proposal) -> list[dict[str, Any]]:
    nav = float(p.nav_usd)
    rows = [{"code": h.currency, "net_usd": _f(h.exposure_usd),
             "net": _mul(_f(h.exposure_usd), 1.0 / nav)} for h in p.fx_hedges]
    rows.sort(key=lambda r: (-abs(r["net_usd"] or 0.0), r["code"]))
    return rows


def _event(ti: ThesisInputs) -> dict[str, Any] | None:
    p, ctx = ti.proposal, ti.ctx
    for name, spec in sorted(ctx.event_exposures.items()):
        check = next((c for c in p.compliance if c.check_id == f"EVENT:{name}"), None)
        if check is not None:
            value = _f(check.value)
        else:
            e = pd.Series(spec["exposures"], dtype=float).reindex(ti.weights.index)
            value = float((ti.weights[e.notna()] * e.dropna()).sum())
        country = name.split(":")[1] if name.count(":") >= 2 else ""
        limit = _f(spec.get("limit"))
        return {"code": ("eleicao_" if "elei" in str(spec.get("name", "")).lower() else "evento_")
                + code_slug(country), "name": name, "label": str(spec.get("name") or name),
                "exposure": value, "limit": limit, "utilization": _util(value, limit),
                "reaction_date": spec.get("date"), "country": country}
    return None


def build_numbers(ti: ThesisInputs, positions: Sequence[Mapping[str, Any]], table: SizingTable,
                  names: Mapping[str, str], *, decomposition_ok: bool = True
                  ) -> tuple[dict[str, Any], dict[str, Any], list[str]]:
    """Bloco ``numbers`` do contrato (frações; ausente = ``None``) + metadados e notas.

    ``decomposition_ok`` falso (participação fatorial recalculada ≠ gravada) ou configuração da
    decisão indisponível ⇒ grupos e fatores de risco sem participação (``None``).
    """
    from ..risk.analytics import risk_decomposition

    p, ctx, cfg = ti.proposal, ti.ctx, ti.cfg
    rk = p.risk
    nav = float(p.nav_usd)
    notes: list[str] = []
    dec = risk_decomposition(ti.weights, ctx.model)
    shares_ok = decomposition_ok and not ti.config_drift
    alpha = _f(p.optimizer.expected_alpha_annual)
    cost = _f(p.optimizer.expected_cost_annual)
    gross = _f(rk.gross)
    top10 = float(ti.weights.abs().head(10).sum())
    # Sem ordens (ex.: carteira mantida) o giro é ZERO, não ausente.
    turnover = sum(abs(float(t.weight_change)) for t in p.trades)
    traded = sum(abs(float(t.notional_usd)) for t in p.trades if _f(t.est_cost_bps) is not None)
    exec_bps = (sum(abs(float(t.notional_usd)) * float(t.est_cost_bps) for t in p.trades
                    if _f(t.est_cost_bps) is not None) / traded) if traded > 0 else None
    shorts = [r for r in positions if r["side"] == "SHORT" and r["borrow"] is not None]
    s_gross = sum(abs(r["weight"]) for r in shorts)
    borrow = (sum(abs(r["weight"]) * r["borrow"] for r in shorts) / s_gross) if s_gross else None
    summary = {
        "nav_usd": nav, "n_long": int(rk.n_long), "n_short": int(rk.n_short),
        "long": _f(rk.long_exposure), "short": _f(rk.short_exposure), "gross": gross,
        "net": _f(rk.net), "beta": _f(rk.beta), "beta_limit": float(cfg.risk.beta_max_abs),
        "vol": _f(rk.ex_ante_vol), "factor_vol": _f(rk.factor_vol),
        "specific_vol": _f(rk.specific_vol), "factor_share": _f(rk.factor_risk_share),
        "var_1d": _f(rk.var_1d_99), "es_1d": _f(rk.es_1d_99), "var_1w": _f(rk.var_1w_99),
        "alpha": alpha, "cost": cost,
        "alpha_net": None if alpha is None or cost is None else alpha - cost,
        "effective_n": _f(rk.effective_n), "turnover": turnover,
        "gross_min": float(cfg.risk.gross_min), "horizon_weeks": float(cfg.alpha.horizon_weeks),
        "top10_gross": top10 / gross if gross else None,
        "exec_cost_bps": exec_bps, "borrow_avg": borrow,
    }
    vol_budget, meta = _vol_budget(ti)
    vol = summary["vol"]
    sigma = [{"horizon": h, "label": lab, "pct": _mul(vol, math.sqrt(n / TRADING_DAYS)),
              "usd": _mul(_mul(vol, math.sqrt(n / TRADING_DAYS)), nav)}
             for h, lab, n in SIGMA_HORIZONS]
    risk_groups = [{"group": GROUP_CODE[g], "label": GROUP_LABEL[GROUP_CODE[g]],
                    "share": _f(dec.by_group.get(g)) if shares_ok else None}
                   for g in ("market", "country", "sector", "style", "specific")]
    factors = []
    for f, v in dec.by_factor.items():
        label, group = factor_label(str(f))
        factors.append({"factor": str(f), "label": label, "group": group,
                        "share": _f(v) if shares_ok else None})
    factors.sort(key=lambda r: (r["share"] is None, -abs(r["share"] or 0.0), r["factor"]))

    def leg_row(e: Any, label: str) -> dict[str, Any]:
        net, limit = _f(e.net), _f(e.limit)
        return {"code": e.name, "label": label, "long": _f(e.long), "short": _f(e.short),
                "net": net, "gross": _f(e.gross), "limit": limit,
                "utilization": _util(net, limit)}

    countries = [leg_row(e, country_label(e.name)) for e in _exposure_rows(p, "country")]
    countries.sort(key=lambda r: (-(r["gross"] or 0.0), r["code"]))
    sectors = [leg_row(e, sector_label(e.name)) for e in _exposure_rows(p, "sector")]
    sectors.sort(key=lambda r: (-(r["gross"] or 0.0), r["code"]))
    styles = [{"code": e.name, "label": style_label(e.name), "net": _f(e.net),
               "limit": _f(e.limit), "utilization": _util(_f(e.net), _f(e.limit))}
              for e in _exposure_rows(p, "style")]
    styles.sort(key=lambda r: (-abs(r["net"] or 0.0), r["code"]))
    commodities, themes = [], []
    for e in _exposure_rows(p, "market"):
        if e.name.startswith("commodity:"):
            c = e.name.split(":", 1)[1]
            b = _f(e.net)
            commodities.append({"code": c, "label": commodity_label(c), "beta": b,
                                "shock": SHOCK_COMMODITY, "pnl": _mul(b, SHOCK_COMMODITY),
                                "limit": _f(e.limit), "utilization": _util(b, _f(e.limit))})
        elif e.name.startswith("tema:"):
            t = e.name.split(":", 1)[1]
            themes.append({"code": t, "label": theme_label(t), "net": _f(e.net),
                           "limit": _f(e.limit), "long": _f(e.long), "short": _f(e.short),
                           "utilization": _util(_f(e.net), _f(e.limit))})
    sens, hist, missing = _sensitivity(ti)
    if missing:
        notes.append("Sensibilidade realizada não calculada (série ausente ou curta): "
                     + ", ".join(missing) + ".")
    stress, diverge = _stress(ti, names)
    if diverge:
        labels = {r["code"]: r["label"] for r in stress}
        shown = [labels.get(code_slug(d), gap_label(d)[1]) for d in diverge]
        notes.append("O recálculo dos cenários de estresse difere do registrado na decisão em: "
                     + ", ".join(shown) + "; prevalecem os valores registrados na decisão.")
    signals = [{"code": code, "label": label[:1].upper() + label[1:]}
               for _sig, code, label in SIGNALS]
    numbers = {
        "summary": summary, "vol_budget": vol_budget, "sigma": sigma, "signals": signals,
        "risk_groups": risk_groups, "factors": factors, "countries": countries,
        "sectors": sectors, "styles": styles, "commodities": commodities,
        "themes_market": themes, "event": _event(ti), "currencies": _currencies(p),
        "sensitivity": sens, "historical": hist, "stress": stress,
        "funnel": _funnel(ti, table), "liquidity": _liquidity(positions, cfg, nav),
        "reference": _reference(ti),
    }
    return numbers, meta, notes


# ==========================================================
# Calendário
# ==========================================================

def _clip(text: str, n: int = 160) -> str:
    text = " ".join(str(text).split())
    return text if len(text) <= n else text[: n - 1].rstrip() + "…"


def build_calendar(ti: ThesisInputs, positions: Sequence[Mapping[str, Any]],
                   names: Mapping[str, str]) -> list[dict[str, Any]]:
    """Datas futuras (≥ semana, até o horizonte do alpha) de resultados, catalisadores da
    pesquisa dos nomes detidos, eventos macro dos países expostos e janelas de evento."""
    start = ti.week
    end = start + timedelta(weeks=int(math.ceil(ti.cfg.alpha.horizon_weeks)))
    held = set(ti.weights.index)
    items: dict[tuple[str, str, str], dict[str, Any]] = {}

    def add(d: date | None, label: str, issuers: Iterable[str], kind: str) -> None:
        if d is None or not (start <= d <= end):
            return
        key = (d.isoformat(), kind, label)
        cur = items.setdefault(key, {"date": d.isoformat(), "label": label, "issuers": [],
                                     "kind": kind})
        cur["issuers"] = sorted(set(cur["issuers"]) | set(issuers))

    by_date: dict[str, list[str]] = {}
    for r in positions:
        if r["next_earnings"]:
            by_date.setdefault(r["next_earnings"], []).append(r["iid"])
    for d, iids in by_date.items():
        add(date.fromisoformat(d), "Divulgação de resultados: "
            + ", ".join(names.get(i, i) for i in sorted(iids, key=lambda i: names.get(i, i))),
            iids, "resultado")
    cats: dict[date, list[tuple[str, str]]] = {}
    for iid, roles in notes_by_issuer(ti.pack).items():
        if iid not in held:
            continue
        for lst in roles.values():
            for n in lst:
                for c in n.catalysts:
                    if c.expected_date is not None:
                        desc = render_research_text(c.description, ti.briefing_facts)
                        cats.setdefault(c.expected_date, []).append((iid, desc))
    for d, items_d in cats.items():
        iids = sorted({i for i, _ in items_d}, key=lambda i: names.get(i, i))
        if len(iids) >= CATALYST_GROUP_MIN:
            add(d, "Catalisadores da pesquisa: " + ", ".join(names.get(i, i) for i in iids),
                iids, "catalisador")
            continue
        for iid, desc in items_d:
            add(d, f"{names.get(iid, iid)}: {_clip(desc)}", [iid], "catalisador")
    gross = sum(abs(r["weight"]) for r in positions)
    by_country: dict[str, float] = {}
    for r in positions:
        by_country[str(r.get("country"))] = by_country.get(str(r.get("country")), 0.0) \
            + abs(r["weight"])
    countries = {c for c, g in by_country.items()
                 if gross > 0 and g / gross >= MACRO_COUNTRY_SHARE} | {"GLOBAL"}
    for m in (ti.pack.macro if ti.pack is not None else []):
        if m.scope not in countries:
            continue
        for ev in m.key_events:
            desc = render_research_text(ev.description, ti.briefing_facts)
            add(ev.expected_date, f"{country_label(m.scope)}: {_clip(desc)}", [], "macro")
    from ..risk.event_scaling import active_event_windows

    for w in active_event_windows(ti.cfg, ti.week):
        try:
            d_end = date.fromisoformat(str(w["end"]))
        except (KeyError, ValueError):
            continue
        members = [r["iid"] for r in positions if r.get("country") == w.get("country")]
        add(d_end, f"Fim da janela de evento: {w.get('name', w.get('country'))}", members,
            "evento")
    order = {"evento": 0, "macro": 1, "resultado": 2, "catalisador": 3}
    return sorted(items.values(), key=lambda x: (x["date"], order.get(x["kind"], 9),
                                                 x["label"]))


# ==========================================================
# Análise completa
# ==========================================================

def build_analysis(ti: ThesisInputs) -> dict[str, Any]:
    """``analise.json``: números da carteira, posições, calendário e notas (determinístico)."""
    from .. import SIMULATED_DATA_NOTICE

    p, ctx, cfg, d = ti.proposal, ti.ctx, ti.cfg, ti.decision
    notes = list(ti.notes)
    _rs, check = risk_check(ti)
    if check["ok"]:
        notes.append("Números recalculados com os pesos aprovados, sem reotimizar; conferem com "
                     "o risco registrado na decisão.")
    else:
        bad = [CHECK_PT.get(k, k) for k, v in check.items()
               if isinstance(v, dict) and not v["confere"]]
        notes.append("Números recalculados com os pesos aprovados, sem reotimizar; o recálculo "
                     "difere do risco registrado na decisão em " + ", ".join(bad)
                     + ": prevalecem os valores registrados na decisão.")
    if not p.trades:
        notes.append("Sem ordens na semana: o giro é zero"
                     + (" (a decisão manteve a carteira vigente; nenhuma alternativa passou em "
                        "todos os limites)." if p.overrides.get("label") == "manter" else "."))
    table = sizing_table(ti)
    if table.constraints is None and not ti.config_drift:
        notes.append("Limites por emissor não reconstruídos: o motivo do tamanho de cada "
                     "posição aparece como indeterminado.")
    elif table.views_ok is False:
        notes.append(f"As visões reconstruídas não reproduzem o alpha da decisão em "
                     f"{table.n_view_mismatch} nomes: a leitura do tamanho limitado por visão "
                     "pode estar imprecisa.")
    positions = build_positions(ti, table)
    names = {r["iid"]: r["name"] for r in positions}
    fs = check.get("factor_risk_share")
    numbers, meta, num_notes = build_numbers(
        ti, positions, table, names,
        decomposition_ok=not (isinstance(fs, dict) and not fs["confere"]))
    notes += num_notes
    windows = ctx.model.meta.get("event_windows") or []
    for w in windows:
        notes.append(f"Janela de evento ativa ({w.get('name')}): volatilidade do país "
                     f"{country_label(str(w.get('country')))} multiplicada por "
                     f"{_br(float(w.get('multiplier', 1.0)), 2)} no modelo de risco.")
    non_pit = _non_pit_signals(ctx)
    labels = {code: lab for _s, code, lab in SIGNALS}
    if non_pit:
        notes.append("Sinais com retrato atual dos dados (não point-in-time): "
                     + ", ".join(labels[c] for c in non_pit) + "; o alpha desses sinais não "
                     "tem validação histórica equivalente à dos sinais de preço.")
    covered = sum(1 for r in positions if r["r_stance"] is not None)
    notes.append(f"Cobertura de pesquisa fundamental: {covered} de {len(positions)} nomes; os "
                 "demais são mantidos pelo modelo quantitativo e pelas restrições da carteira.")
    measured = [c["code"] for c in numbers["commodities"]]
    if measured:
        notes.append("Commodities medidas: " + ", ".join(commodity_label(c).lower()
                                                         for c in measured)
                     + "; demais commodities não têm proxy no modelo.")
    else:
        notes.append("Sensibilidade a commodities não medida: sem séries de referência nos "
                     "dados da semana.")
    notes.append("Sensibilidade a juros não é modelada: o modelo de risco não tem fator de "
                 "juros (curva local ou Treasuries).")
    notes.append("Beta do modelo medido contra a carteira de mercado LatAm ponderada por valor "
                 "de mercado; betas realizados reprecificam os pesos atuais sobre o histórico "
                 "(retornos ausentes completados pelo modelo).")
    notes.append("Dias para liquidar com a participação de cada ponta no volume médio: compras "
                 f"{_br(cfg.liquidity.participation_rate * 100, 0)}%, vendas "
                 f"{_br(cfg.liquidity.short_participation_rate * 100, 0)}%.")
    prices_as_of = _prices_as_of(ctx.md)
    if prices_as_of != ctx.md.as_of:
        notes.append(f"Preços de fechamento até {prices_as_of.isoformat()}; a decisão usou também "
                     f"a barra intradiária provisória de {ctx.md.as_of.isoformat()} (cotações do "
                     "momento da análise).")
    return clean_json({
        "schema": ANALYSIS_SCHEMA, "week": ti.week, "as_of": ti.week,
        "prices_as_of": prices_as_of, "is_synthetic": bool(p.is_synthetic),
        "data_notice": (SIMULATED_DATA_NOTICE + " — mercado sintético") if p.is_synthetic
        else p.data_notice, "fund_name": ti.fund_name, "nav_usd": float(p.nav_usd),
        "proposal": {"proposal_id": p.proposal_id, "version": p.version,
                     "proposal_hash": d.proposal_hash, "snapshot_hash": p.snapshot_hash,
                     "config_hash": p.config_hash, "label": p.overrides.get("label")},
        "decision": {"approval_hash": d.approval_hash, "decided_at": d.decided_at,
                     "conviction": d.conviction, **meta},
        "check": check, "non_pit_signals": non_pit,
        "numbers": numbers, "positions": positions,
        "calendar": build_calendar(ti, positions, names), "notes": notes,
    })


def _prices_as_of(md: Any) -> date:
    """Último pregão com fechamento definitivo (exclui a barra intradiária provisória)."""
    prov = set(md.manifest.provisional_dates)
    if md.as_of not in prov:
        return md.as_of
    days = [d.date() for d in pd.DatetimeIndex(md.close.index)
            if d.date() not in prov and d.date() <= md.as_of]
    return max(days) if days else md.as_of


def _non_pit_signals(ctx: WeekContext) -> list[str]:
    """Códigos curtos dos sinais usados que vêm de retratos atuais (não point-in-time)."""
    from ..research.factbook import NON_PIT_SIGNALS

    attrs = ctx.alpha.signal_z.attrs.get("point_in_time") \
        if isinstance(ctx.alpha.signal_z.attrs, dict) else None
    out = []
    for sig, code, _lab in SIGNALS:
        if sig not in ctx.alpha.signal_z.columns or not ctx.alpha.weights_used.get(sig):
            continue
        pit = bool(attrs[sig]) if isinstance(attrs, Mapping) and sig in attrs \
            else sig not in NON_PIT_SIGNALS
        if not pit:
            out.append(code)
    return out


__all__ = [
    "ANALYSIS_SCHEMA", "COUNTRY_PT", "ROLE_PT", "SIGNALS", "SIZING_PT", "ThesisInputs",
    "approved_proposal", "build_analysis", "clean_json", "code_slug", "commodity_label",
    "country_label", "factor_label", "issuer_weights", "load_inputs", "notes_by_issuer",
    "pm_journal", "pm_views", "position_role", "render_research_text", "sector_label",
    "sizing_driver", "style_label", "theme_label",
]
