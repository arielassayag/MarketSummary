"""Exportador determinístico do painel do CDP — Cabra da Peste (artifact HTML do fundo).

O painel é um artifact republicado pelas rotinas após cada decisão semanal, fechamento diário e
monitor de risco intradiário. Este módulo só LÊ os artefatos do fundo (livro, tese publicada da
carteira, track record, relatórios, base de mercado, backtests) e monta um retrato JSON; a página
apenas formata e plota esses dados. Publicação (:func:`write_painel`):

- ``index.html``: casca pequena da página (cabeçalho, marcação, elemento de dados vazio ``null``
  e a versão da página carimbada) que referencia o estilo e o script do template em arquivos
  versionados ``painel-<versão>.css`` e ``painel-<versão>.js``. A ferramenta Artifact exige a
  página em toda publicação, e quem publica precisa ler por inteiro o que publica: a casca é
  pequena, e os arquivos versionados só vão junto quando a página muda (os já publicados ficam
  no artifact). Só é regravado quando o template muda; a página busca ``data.json`` ao lado dela.
- ``data.json``: perfil ``publicacao`` (:mod:`cdp.workflow.painel_publicacao`), JSON indentado
  que cabe na leitura integral exigida de quem publica (≤ 260 KB, linhas ≤ 1.500 caracteres),
  com a versão da página para a qual foi gerado (``meta.page_sha256``).
- ``cdp_painel_local.html``: cópia autônoma com o perfil ``completo`` embutido (abrir offline).
- ``PAGINA_PUBLICADA.sha256``: a versão da página publicada por último no artifact, gravada
  por :func:`mark_published` (``cdp painel --publicado``) depois de uma publicação bem-sucedida.
  ``page_changed`` compara a versão atual com ESTE marcador (não com o ``index.html`` local):
  fica verdadeiro até a página nova ser de fato publicada.

Regras:

- Números só em código: tudo o que é número vem dos registros/propostas gravados ou de
  agregações simples e testadas feitas aqui em Python (somas, compostos, comparações com os
  limites do mandato). A página nunca calcula nada além de formatação.
- Ausente continua ausente: ``NaN``/``inf`` viram ``null`` (``n/d`` na página), nunca zero.
- Determinístico: mesma entrada (e mesmo ``now``) ⇒ mesmo JSON (chaves ordenadas) e mesmo hash.
- Somente leitura: nada é gravado no livro, nos relatórios ou na base; antes da inception nenhuma
  pasta é criada como efeito colateral.
- Robusto: arquivo corrompido ou adulterado vira apontamento de integridade (``issues`` e
  ``status.integrity``), nunca uma exceção.
- Dados simulados carregam sempre "DADOS SIMULADOS" (``meta.is_synthetic``/``meta.data_notice``).
- Sem identificadores de modelo: campos ``model``/``models`` são descartados e nomes de modelos
  em textos livres são substituídos por ``[modelo]`` (a mente — claude-code/codex — é mantida).
- Injeção: o JSON é embutido em ``<script type="application/json">`` com ``<``, ``>`` e ``&``
  escapados como ``\\u003c``/``\\u003e``/``\\u0026`` — nenhum texto de IA, notícia ou relatório
  consegue fechar o elemento.
"""

from __future__ import annotations

import enum
import hashlib
import json
import math
import os
import re
import tempfile
from collections import Counter
from collections.abc import Callable, Iterable, Mapping, Sequence
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from pydantic import BaseModel

from .. import SIMULATED_DATA_NOTICE
from ..config import FundConfig
from ..research.pm_agent import POSTURE_PT, REGIME_PT, STAGE_PT, ladder_stage
from ..ui.fmt import PATH_PT
from .daily import REAL_DATA_SOURCES
from .memo import fmt_pct

SCHEMA_VERSION = "cdp-painel/3"
PLACEHOLDER = "__CDP_DATA__"
DATA_ELEMENT = f'<script type="application/json" id="cdp-data">{PLACEHOLDER}</script>'
EMPTY_DATA_ELEMENT = DATA_ELEMENT.replace(PLACEHOLDER, "null")
#: Carimbo da versão da página no script (``var PAGE_SHA``) e, na casca publicada, também no
#: ``<meta name="cdp-page-sha256">``.
PAGE_SHA_PLACEHOLDER = "__CDP_PAGE_SHA256__"
PAGE_SHA_RE = re.compile(r'(?:var PAGE_SHA = "|<meta name="cdp-page-sha256" content=")'
                         r'([0-9a-f]{64})"')
#: Formato da publicação (casca + estilo e script versionados). Entra na versão da página: mudar o
#: formato obriga a republicar a página mesmo com o template igual.
PAGE_LAYOUT = "cdp-painel-casca/1"
#: Arquivos versionados da página: ``painel-<16 primeiros hex da versão>.css``/``.js``.
ASSET_PREFIX = "painel-"
ASSET_RE = re.compile(r"painel-[0-9a-f]{16}\.(?:css|js)")
DEFAULT_TEMPLATE = Path(__file__).with_name("painel_template.html")
DEFAULT_OUT_DIR = Path("artifacts/painel")
INDEX_NAME = "index.html"
DATA_NAME = "data.json"
LOCAL_NAME = "cdp_painel_local.html"
URL_NAME = "ARTIFACT_URL"
MARKER_NAME = "PAGINA_PUBLICADA.sha256"
DEFAULT_MAX_DAILY_REPORTS = 60
DEFAULT_FULL_WEEKS = 8
DEFAULT_FULL_RESEARCH_WEEKS = 2
DEFAULT_AUDIT_TAIL = 40
DEFAULT_MAX_RISK_RUNS = 30
DEFAULT_RISK_FULL_RUNS = 8
MAX_RISK_FILE_BYTES = 2_000_000
MAX_BACKTEST_DEPTH = 3
EVIDENCE_NOTE_CHARS = 160
MAX_EVIDENCE_PER_NOTE = 8
#: Tolerância dos limites: a mesma dos gates de compliance (``portfolio.compliance.TOL``), para o
#: painel nunca acusar "excesso" num limite que o gate aprovou.
LIMIT_TOL = 1e-6
COMMENTARY_SECTION = "Comentário do dia"
# Fontes entre parênteses (o rodapé da página lê o primeiro parêntese como fontes de dados).
REAL_DATA_NOTICE = (f"Dados reais de mercado ({REAL_DATA_SOURCES}); paper trading com execução "
                    "hipotética no leilão de fechamento.")
EMPTY_DATA_NOTICE = "Pré-início: o fundo ainda não tem carteira."

_MODEL_KEYS = frozenset({"model", "models", "model_id", "model_name"})
_MODEL_ID_RE = re.compile(
    r"\b(?:claude-(?!code\b)[a-z0-9][\w.\-]*|gpt-[\w.\-]+|chatgpt-[\w.\-]+|"
    r"o[134]-(?:mini|preview|pro)[\w.\-]*|gemini-[\w.\-]+|text-davinci-[\w.\-]+)",
    re.IGNORECASE)
_PROVENANCE_RE = re.compile(r"^_\s*(Autoria:.*?)\s*_\s*$", re.MULTILINE)
_MIND_RE = re.compile(r"mente\s+([\w.-]+)\s*\[IA\]", re.IGNORECASE)
_WEEK_DIR_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
#: Marcador ``{{fact:id}}`` que escapou da renderização (nunca pode chegar ao painel).
_RAW_FACT_RE = re.compile(r"\{\{\s*fact\s*:")
#: Tese da carteira (``book/<semana>/tese/``): só a versão PUBLICADA (imutável, ancorada na
#: trilha pelo evento ``WEEKLY_THESIS``) é exportada; o rascunho ``tese.json`` da mente, nunca.
THESIS_DIR = "tese"
THESIS_FILE = "tese_publicada.json"
THESIS_MD = "tese.md"
THESIS_EVENT = "WEEKLY_THESIS"
#: Chaves que citam emissores (``meta.issuer_names`` cobre todas): um id ou uma lista de ids
#: (inclusive os nomes só no CDP / só na carteira quantitativa de referência, da sobreposição).
_IID_KEYS = frozenset({"issuer_id", "iid"})
_IID_LIST_KEYS = frozenset({"issuer_ids", "issuers", "only_shadow", "only_cdp"})

PHASE_PT = {
    "pre_inception": "Pré-início: carteira inaugural na data de início do mandato, ao preço de "
                     "fechamento.",
    "aguardando_decisao": "Semana em preparação: pesquisa em andamento, aguardando a decisão "
                          "do comitê.",
    "decidida_aguardando_execucao": "Carteira decidida; execução no leilão de fechamento.",
    "bloqueada": "Decisão da semana suspensa: limite rígido do mandato ou verificação de dados "
                 "não atendidos.",
    "em_operacao": "Em operação: carteira executada e marcada diariamente.",
}
WEEK_STAGE_PT = {
    "vazia": "sem carteira", "preparada": "dados da semana preparados",
    "entradas_gravadas": "pesquisa e visão do gestor registradas; aguardando a decisão",
    "decidida": "carteira decidida; execução no leilão de fechamento",
    "efetivada": "carteira executada e marcada diariamente",
}
#: Textos dos alertas de status para o leitor (sem ids de verificação nem jargão técnico).
PATH_ALERT_PT = {"cdp-restricoes": "somente as restrições da pesquisa e do gestor",
                 "quant": "somente o modelo quantitativo", "manter": "carteira anterior mantida",
                 "reduzir-risco": "somente redução de risco"}
LIMIT_ALERT_PT = {
    "GROSS_MIN": "exposição bruta mínima", "GROSS_MAX": "exposição bruta máxima",
    "VOL_MIN": "volatilidade ex-ante mínima", "VOL_MAX": "volatilidade ex-ante máxima",
    "VOL_TARGET": "distância à meta de volatilidade", "TURNOVER": "giro semanal",
    "FACTOR_RISK_SHARE": "parcela fatorial do risco",
    "SINGLE_NAME_RISK": "contribuição máxima de um nome ao risco",
    "COUNTRY_GAP_STRESS": "perda em gap de país", "DRAWDOWN_SOFT": "nível de revisão do drawdown",
    "SQUEEZE_MEDIUM_CAP": "teto do short com squeeze médio", "STYLE": "exposição ao estilo",
    "COMMODITY": "sensibilidade a commodity", "EVENT": "exposição ao choque de evento",
    "THEME_NET": "exposição líquida ao tema", "COUNTRY_NET": "exposição líquida por país",
    "SECTOR_NET": "exposição líquida por setor", "NET_EXPOSURE": "exposição líquida",
    "BETA": "beta previsto", "BORROW_FEE": "taxa de aluguel dos shorts",
    "LIQ_DAYS_LONG": "prazo de liquidação dos longs",
    "LIQ_DAYS_SHORT": "prazo de liquidação dos shorts",
}


def limit_label_pt(check_id: str) -> str:
    """Rótulo pt-BR de uma verificação do mandato pelo id (``STYLE:size`` → estilo tamanho)."""
    base, _, arg = str(check_id).partition(":")
    label = LIMIT_ALERT_PT.get(base)
    if label is None:
        return base.replace("_", " ").lower()
    if base == "STYLE":
        arg = STYLE_PT.get(arg, arg).lower()
    elif base == "COMMODITY":
        arg = COMMODITY_PT.get(arg, arg)
    elif base == "THEME_NET":
        arg = THEME_PT.get(arg, arg)
    elif base == "SECTOR_NET":
        arg = SECTOR_PT.get(arg, arg)
    elif base == "EVENT":
        arg = ""
    return f"{label} ({arg})" if arg else label
BACKTEST_SIG_DIGITS = 8
ATTRIBUTION_GROUPS = ("component", "factor_group", "factor", "country", "sector", "side",
                      "issuer")
COMPONENT_ORDER = ("equity", "factor", "specific", "costs", "borrow", "financing")
LIQUIDITY_BUCKETS = ((1.0, "≤ 1 dia"), (2.0, "1–2 dias"), (3.0, "2–3 dias"), (5.0, "3–5 dias"),
                     (math.inf, "> 5 dias"))
#: Rótulos pt-BR dos nomes de exposição usados nos textos gerados aqui (alertas e detalhes).
SECTOR_PT = {
    "Financials": "Financeiro", "Energy": "Energia", "Materials": "Materiais",
    "Utilities": "Utilidades públicas", "Industrials": "Industriais",
    "Consumer Discretionary": "Consumo discricionário", "Consumer Staples": "Consumo básico",
    "Health Care": "Saúde", "Real Estate": "Imobiliário", "Communication Services": "Comunicações",
    "Information Technology": "Tecnologia", "OTHER": "Outros"}
STYLE_PT = {"momentum": "Momentum", "value": "Valor (value)", "size": "Tamanho (size)",
            "beta": "Beta de mercado", "resvol": "Vol residual", "liquidity": "Liquidez",
            "fx_sens": "Sensibilidade cambial", "quality": "Qualidade", "growth": "Crescimento"}
COMMODITY_PT = {"oil": "petróleo", "copper": "cobre", "gold": "ouro",
                "iron_ore": "minério de ferro", "lithium": "lítio", "soy": "soja",
                "silver": "prata"}
THEME_PT = {"state_owned": "estatais"}


# ==========================================================
# Sanitização e serialização determinística
# ==========================================================

_URL_ONLY_RE = re.compile(r"^https?://\S+$")


def scrub_text(text: str) -> str:
    """Remove identificadores de modelo de um texto livre (a mente claude-code/codex fica).

    Uma URL isolada (evidência) é preservada: alterá-la quebraria a referência à fonte.
    """
    if _URL_ONLY_RE.match(text):
        return text
    return _MODEL_ID_RE.sub("[modelo]", text)


def clean(obj: Any) -> Any:
    """Estrutura JSON pura e determinística: NaN/inf ⇒ ``None``, datas ISO, enums por valor,
    conjuntos ordenados, chaves de modelo descartadas e textos sem identificadores de modelo."""
    if obj is None or isinstance(obj, bool):
        return obj
    if isinstance(obj, BaseModel):
        return clean(obj.model_dump(mode="json"))
    if isinstance(obj, enum.Enum):
        return clean(obj.value)
    if isinstance(obj, str):
        return scrub_text(obj)
    if isinstance(obj, int):
        return int(obj)
    if isinstance(obj, float):
        return float(obj) if math.isfinite(obj) else None
    if isinstance(obj, Mapping):
        return {str(k): clean(v) for k, v in obj.items() if str(k) not in _MODEL_KEYS}
    if isinstance(obj, (set, frozenset)):
        return sorted((clean(v) for v in obj), key=lambda v: json.dumps(v, sort_keys=True))
    if isinstance(obj, (list, tuple)):
        return [clean(v) for v in obj]
    if hasattr(obj, "to_pydatetime"):  # pandas.Timestamp (subclasse de datetime)
        ts = obj.to_pydatetime()
        midnight = ts.time() == datetime.min.time() and ts.tzinfo is None
        return ts.date().isoformat() if midnight else ts.isoformat()
    if isinstance(obj, (datetime, date)):
        return obj.isoformat()
    if isinstance(obj, Path):
        return obj.as_posix()
    if hasattr(obj, "item"):  # escalares numpy
        return clean(obj.item())
    return scrub_text(str(obj))


def to_json(data: Any) -> str:
    """JSON canônico (chaves ordenadas, sem espaços, UTF-8, sem NaN)."""
    return json.dumps(clean(data), ensure_ascii=False, sort_keys=True, separators=(",", ":"),
                      allow_nan=False)


def data_hash(data: Mapping[str, Any]) -> str:
    """SHA-256 do JSON canônico do painel sem ``meta.data_hash``."""
    body = dict(data)
    meta = dict(body.get("meta") or {})
    meta.pop("data_hash", None)
    body["meta"] = meta
    return hashlib.sha256(to_json(body).encode("utf-8")).hexdigest()


def embed_json(data: Any) -> str:
    """JSON seguro para ``<script type="application/json">`` (nada fecha o elemento)."""
    text = to_json(data)
    return (text.replace("&", "\\u0026").replace("<", "\\u003c").replace(">", "\\u003e")
            .replace("\u2028", "\\u2028").replace("\u2029", "\\u2029"))


# ==========================================================
# Utilidades
# ==========================================================

def _num(x: object) -> float | None:
    if x is None or isinstance(x, bool):
        return None
    try:
        v = float(x)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None
    return v if math.isfinite(v) else None


def _iso(d: date | datetime | None) -> str | None:
    return d.isoformat() if d is not None else None


def _compound(rets: Iterable[object]) -> float | None:
    """Π(1 + r) − 1; vazio ou algum dia ausente ⇒ ``None`` (nunca zero)."""
    g, n = 1.0, 0
    for r in rets:
        v = _num(r)
        if v is None:
            return None
        g *= 1.0 + v
        n += 1
    return g - 1.0 if n else None


def _sha256_file(path: Path) -> str | None:
    try:
        return hashlib.sha256(path.read_bytes()).hexdigest()
    except OSError:
        return None


def _read_text(path: Path) -> str | None:
    try:
        return path.read_text(encoding="utf-8") if path.is_file() else None
    except (OSError, UnicodeDecodeError):
        return None


def _read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


class _Issues:
    """Apontamentos de leitura (o painel nunca quebra por um artefato)."""

    def __init__(self) -> None:
        self.items: list[dict[str, str]] = []

    def add(self, scope: str, message: str) -> None:
        self.items.append({"scope": scope, "message": scrub_text(message)[:500]})

    def attempt(self, scope: str, fn: Callable[[], Any], default: Any = None) -> Any:
        try:
            return fn()
        except Exception as exc:  # noqa: BLE001 - qualquer falha vira apontamento
            self.add(scope, f"{type(exc).__name__}: {exc}")
            return default


def _local(dt: datetime | None, tz: ZoneInfo) -> str | None:
    if dt is None:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return dt.astimezone(tz).isoformat()


def _render_facts(text: Any, facts: Mapping[str, str]) -> Any:
    if not isinstance(text, str) or "{{" not in text:
        return text
    from ..ui.data import render_facts

    return render_facts(text, dict(facts))


def _safe_url(url: Any) -> str | None:
    from ..ui.data import safe_url

    return safe_url(str(url)) if url else None


# ==========================================================
# Mandato
# ==========================================================

def _mandate(cfg: FundConfig) -> dict[str, Any]:
    rs = cfg.research
    return {
        "risk": cfg.risk.model_dump(mode="json"),
        "liquidity": cfg.liquidity.model_dump(mode="json"),
        "shorting": cfg.shorting.model_dump(mode="json"),
        "squeeze": cfg.squeeze.model_dump(mode="json"),
        "drawdown": cfg.drawdown.model_dump(mode="json"),
        "costs": cfg.costs.model_dump(mode="json"),
        "alpha": cfg.alpha.model_dump(mode="json"),
        "risk_model": cfg.risk_model.model_dump(mode="json"),
        "ai_adoption": {
            "provider": rs.provider, "phase": rs.llm_phase, "view_ic": rs.llm_view_ic,
            "view_ic_by_phase": dict(rs.llm_view_ic_by_phase),
            "llm_can_only_tighten": rs.llm_can_only_tighten,
            "samples_per_judgment": rs.samples_per_judgment,
            "min_sign_agreement": rs.min_sign_agreement,
            "top_n_candidates": rs.top_n_candidates,
            "news_lookback_days": rs.news_lookback_days,
            "quant_information_coefficient": cfg.alpha.information_coefficient,
            "view_information_coefficient": cfg.alpha.view_information_coefficient,
            "max_view_tilt_z": cfg.alpha.max_view_tilt_z,
            "view_sign_coherence": cfg.alpha.view_sign_coherence,
        },
        "schedule": {
            "timezone": cfg.fund.timezone, "primary_calendar": cfg.fund.primary_calendar,
            "rebalance_rule": cfg.fund.rebalance_rule,
            "weekly_research_start_local": cfg.fund.weekly_research_start_local,
            "decision_deadline_local": cfg.fund.decision_deadline_local,
            "daily_close_run_local": cfg.fund.daily_close_run_local,
            "execution_convention": cfg.fund.execution_convention,
            "minds": list(cfg.fund.minds),
        },
        "table": _mandate_table(cfg),
    }


def _mandate_table(cfg: FundConfig) -> list[dict[str, Any]]:
    rk, lq, sh, sq, dd = cfg.risk, cfg.liquidity, cfg.shorting, cfg.squeeze, cfg.drawdown
    rows: list[tuple[str, str, str, Any, str]] = [
        ("risco", "vol_target_annual", "Vol-alvo ex-ante (a.a.)", rk.vol_target_annual, "pct"),
        ("risco", "vol_band", "Banda de vol ex-ante", [rk.vol_band_min, rk.vol_band_max], "pct"),
        ("risco", "risk_target_mode", "Modo da meta de risco", rk.risk_target_mode, "text"),
        ("risco", "bias_prior", "Viés a priori do risco ex-ante", rk.bias_prior, "x"),
        ("risco", "net_exposure_max_abs", "Net máximo (|Σw|)", rk.net_exposure_max_abs, "pct"),
        ("risco", "beta_max_abs", "Beta máximo (|β|)", rk.beta_max_abs, "x"),
        ("risco", "gross", "Gross mínimo / máximo", [rk.gross_min, rk.gross_max], "pct"),
        ("risco", "country_net_max_abs", "Net por país (|net|)", rk.country_net_max_abs, "pct"),
        ("risco", "sector_net_max_abs", "Net por setor (|net|)", rk.sector_net_max_abs, "pct"),
        ("risco", "style_exposure_max_abs", "Exposição por estilo (|z × NAV|)",
         rk.style_exposure_max_abs, "x"),
        ("risco", "theme_net_max_abs", "Net por tema", dict(rk.theme_net_max_abs), "pct"),
        ("risco", "country_gross_share_max", "Fatia máxima do gross por país",
         dict(rk.country_gross_share_max), "pct"),
        ("risco", "commodity_beta_max_abs", "Sensibilidade a commodity (|Σ w·β|)",
         rk.commodity_beta_max_abs, "pct"),
        ("risco", "max_long_weight", "Peso máximo por nome (long)", rk.max_long_weight, "pct"),
        ("risco", "max_short_weight", "Peso máximo por nome (short)", rk.max_short_weight,
         "pct"),
        ("risco", "min_position_weight", "Peso mínimo por posição", rk.min_position_weight,
         "pct"),
        ("risco", "max_single_name_risk_share", "Contribuição máxima de um nome ao risco",
         rk.max_single_name_risk_share, "pct"),
        ("risco", "max_factor_risk_share", "Fração máxima do risco vinda de fatores",
         rk.max_factor_risk_share, "pct"),
        ("risco", "var_1d_max", f"VaR 1d ({rk.var_confidence:.0%}) máximo", rk.var_1d_max,
         "pct"),
        ("risco", "es_1d_max", f"ES 1d ({rk.var_confidence:.0%}) máximo", rk.es_1d_max, "pct"),
        ("risco", "country_stress_max_loss", "Perda máxima por gap de país",
         rk.country_stress_max_loss, "pct"),
        ("risco", "event_windows", "Janelas de evento", list(rk.event_windows), "list"),
        ("liquidez", "min_adtv_usd", "ADTV mínimo (USD)", lq.min_adtv_usd, "usd"),
        ("liquidez", "min_adtv_long_usd", "ADTV mínimo long (USD)", lq.min_adtv_long_usd, "usd"),
        ("liquidez", "min_adtv_short_usd", "ADTV mínimo short (USD)", lq.min_adtv_short_usd,
         "usd"),
        ("liquidez", "participation_rate", "Participação no ADTV (long)", lq.participation_rate,
         "pct"),
        ("liquidez", "short_participation_rate", "Participação no ADTV (short)",
         lq.short_participation_rate, "pct"),
        ("liquidez", "max_days_to_liquidate_long", "Dias para liquidar (long)",
         lq.max_days_to_liquidate_long, "days"),
        ("liquidez", "max_days_to_liquidate_short", "Dias para liquidar (short)",
         lq.max_days_to_liquidate_short, "days"),
        ("liquidez", "max_weekly_turnover", "Giro semanal máximo", lq.max_weekly_turnover, "pct"),
        ("liquidez", "min_gross_liquid_3d", "Gross liquidável em 3 dias (mín.)",
         lq.min_gross_liquid_3d, "pct"),
        ("liquidez", "min_gross_liquid_5d", "Gross liquidável em 5 dias (mín.)",
         lq.min_gross_liquid_5d, "pct"),
        ("short", "max_borrow_fee", "Taxa de aluguel máxima (a.a.)", sh.max_borrow_fee, "pct"),
        ("short", "min_market_cap_short_usd", "Market cap mínimo para short (USD)",
         sh.min_market_cap_short_usd, "usd"),
        ("short", "shortable_line_types", "Linhas alugáveis", list(sh.shortable_line_types),
         "list"),
        ("squeeze", "score_buckets", "Escore de squeeze (médio / alto)",
         [sq.score_medium, sq.score_high], "score"),
        ("squeeze", "si_pct_float", "Short interest % float (médio / alto)",
         [sq.si_pct_float_medium, sq.si_pct_float_high], "pct"),
        ("squeeze", "days_to_cover", "Dias para cobrir (médio / alto)",
         [sq.days_to_cover_medium, sq.days_to_cover_high], "days"),
        ("squeeze", "borrow_fee", "Taxa de aluguel (médio / alto)",
         [sq.borrow_fee_medium, sq.borrow_fee_high], "pct"),
        ("squeeze", "medium_short_cap_multiplier", "Multiplicador do teto (squeeze médio)",
         sq.medium_short_cap_multiplier, "x"),
        ("squeeze", "stop_short_position_loss", "Stop de perda no short (corte de 50%)",
         sq.stop_short_position_loss, "pct"),
        ("squeeze", "stop_short_nav_loss", "Stop de perda do short em % do NAV",
         sq.stop_short_nav_loss, "pct"),
        ("drawdown", "soft_stop", "Stop suave (revisão; gross × multiplicador)",
         [dd.soft_stop, dd.soft_degross_multiplier], "pct"),
        ("drawdown", "hard_stop", "Stop duro (gross × multiplicador)",
         [dd.hard_stop, dd.degross_multiplier], "pct"),
        ("drawdown", "stop_out", "Stop-out (gross mínimo)", [dd.stop_out, dd.stop_out_gross],
         "pct"),
        ("ia", "llm_phase", "Fase de adoção das visões de IA", cfg.research.llm_phase, "text"),
        ("ia", "llm_view_ic", "IC efetivo das visões de IA", cfg.research.llm_view_ic, "ratio"),
        ("ia", "llm_can_only_tighten", "IA só aperta (nunca afrouxa)",
         cfg.research.llm_can_only_tighten, "bool"),
    ]
    return [{"section": s, "key": k, "label": lab, "value": v, "unit": u}
            for s, k, lab, v, u in rows]


# ==========================================================
# Track record
# ==========================================================

def _risk_scalars(risk: Any, names: Mapping[str, str] | None = None) -> dict[str, Any]:
    """Bloco de risco sem as linhas de exposição. Em ``RiskSummary`` os mapas de contribuição
    fatorial, stress e maiores contribuintes viram listas ordenadas (mesmo formato em toda parte).
    """
    d = risk.model_dump(mode="json")
    d.pop("exposures", None)
    if "factor_contributions" in d:
        d["factor_contributions"] = _sorted_map(risk.factor_contributions, by_abs=True,
                                                key_name="factor", value_name="share")
    if "stress_tests" in d:
        d["stress_tests"] = _sorted_map(risk.stress_tests, key_name="scenario",
                                        value_name="pnl")
    if "top_risk_contributors" in d:
        tops = _sorted_map(risk.top_risk_contributors, by_abs=True, key_name="issuer_id",
                           value_name="share")
        for row in tops:
            row["name"] = (names or {}).get(row["issuer_id"])
        d["top_risk_contributors"] = tops
    return d


def _record_compact(r: Any) -> dict[str, Any]:
    return {
        "date": r.date, "nav_start": r.nav_start_usd, "nav_end": r.nav_end_usd,
        "pnl": r.pnl_usd, "ret": r.ret, "pnl_components": dict(r.pnl_components),
        "risk": _risk_scalars(r.risk), "n_alerts": len(r.alerts), "alerts": list(r.alerts),
        "n_positions": len(r.positions), "live_book_week": r.live_book_week,
        "approval_hash": r.approval_hash, "record_hash": r.record_hash,
        "prev_record_hash": r.prev_record_hash, "is_synthetic": r.is_synthetic,
    }


def _load_records(tr: Any, issues: _Issues, label: str) -> tuple[list[Any], list[str]]:
    """Registros um a um: JSON ilegível vira apontamento sem esconder os demais."""
    out, bad = [], []
    for d in issues.attempt(f"{label} (datas)", tr.dates, []):
        rec = issues.attempt(f"{label} {d.isoformat()} ilegível", lambda d=d: tr.get(d))
        if rec is None:
            bad.append(d.isoformat())
        else:
            out.append(rec)
    return out, bad


def _stats(tr: Any, cfg: FundConfig, issues: _Issues, label: str) -> dict[str, Any] | None:
    raw = issues.attempt(f"{label} (estatísticas)", lambda: tr.stats(cfg))
    if not raw:
        return None
    out = dict(raw)
    for key in ("best_day", "worst_day"):
        v = out.get(key)
        out[key] = {"date": v[0], "ret": v[1]} if v else None
    band = out.get("vol_band")
    out["vol_band"] = list(band) if band else None
    return out


def _monthly(tr: Any, issues: _Issues) -> dict[str, Any] | None:
    table = issues.attempt("Track record (grade mensal)", tr.monthly_returns_table)
    if table is None:
        return None
    cols = [str(c) for c in table.columns]
    rows = [{"year": int(y), "values": [_num(v) for v in table.loc[y].tolist()]}
            for y in table.index]
    return {"columns": cols, "rows": rows}


def _attribution_sum(records: Sequence[Any]) -> dict[str, list[dict[str, Any]]]:
    acc: dict[str, dict[str, list[float]]] = {}
    for r in records:
        for a in r.attribution:
            slot = acc.setdefault(a.group, {}).setdefault(a.name, [0.0, 0.0, 0])
            slot[0] += float(a.pnl_usd)
            slot[1] += float(a.contribution)
            slot[2] += 1
    out: dict[str, list[dict[str, Any]]] = {}
    for g in [*ATTRIBUTION_GROUPS, *sorted(set(acc) - set(ATTRIBUTION_GROUPS))]:
        if g not in acc:
            continue
        rows = [{"name": k, "pnl_usd": v[0], "contribution": v[1], "days": int(v[2])}
                for k, v in acc[g].items()]
        out[g] = sorted(rows, key=lambda x: (-x["pnl_usd"], x["name"]))
    return out


def _components_sum(records: Sequence[Any]) -> list[dict[str, Any]]:
    acc: dict[str, list[float]] = {}
    for r in records:
        nav0 = float(r.nav_start_usd)
        for k, v in r.pnl_components.items():
            fv = _num(v)
            if fv is None:
                continue
            slot = acc.setdefault(k, [0.0, 0.0, 0])
            slot[0] += fv
            slot[1] += fv / nav0
            slot[2] += 1
    order = [k for k in COMPONENT_ORDER if k in acc] + sorted(set(acc) - set(COMPONENT_ORDER))
    return [{"key": k, "pnl_usd": acc[k][0], "contribution": acc[k][1], "days": int(acc[k][2])}
            for k in order]


def _period(records: Sequence[Any], label: str, start: date | None, end: date | None
            ) -> dict[str, Any]:
    sub = [r for r in records if (start is None or r.date >= start)
           and (end is None or r.date <= end)]
    return {
        "label": label, "start": sub[0].date if sub else start, "end": sub[-1].date if sub else end,
        "n_days": len(sub), "ret": _compound(r.ret for r in sub),
        "pnl_usd": sum(float(r.pnl_usd) for r in sub) if sub else None,
        "components": _components_sum(sub), "attribution": _attribution_sum(sub),
    }


def _track_section(rt: Any, cfg: FundConfig, book_exists: bool, issues: _Issues
                   ) -> tuple[dict[str, Any], list[Any], list[Any]]:
    from .track_record import SHADOW_RECORD_EVENT, TrackRecord, compare_tracks

    empty = {"exists": False, "n_days": 0, "records": [], "unreadable_dates": [],
             "stats": None, "monthly": None, "shadow": {"exists": False, "records": [],
                                                       "stats": None},
             "compare": [], "periods": {}}
    root = Path(rt.book_root)
    main_dir, shadow_dir = root / "track_record", root / "track_record_shadow"
    if not book_exists or not main_dir.is_dir():
        return empty, [], []
    main = TrackRecord(main_dir)
    records, bad = _load_records(main, issues, "Track record")
    out = dict(empty)
    out.update({"exists": True, "n_days": len(records), "unreadable_dates": bad,
                "records": [_record_compact(r) for r in records],
                "stats": _stats(main, cfg, issues, "Track record"),
                "monthly": _monthly(main, issues),
                "inception_nav": issues.attempt("Track record (NAV inicial)",
                                                main.inception_nav)})
    shadow_records: list[Any] = []
    if shadow_dir.is_dir():
        shadow = TrackRecord(shadow_dir, audit_event=SHADOW_RECORD_EVENT)
        shadow_records, sbad = _load_records(shadow, issues, "Sombra só-quant")
        out["shadow"] = {"exists": True, "n_days": len(shadow_records),
                         "unreadable_dates": sbad,
                         "records": [_record_compact(r) for r in shadow_records],
                         "stats": _stats(shadow, cfg, issues, "Sombra só-quant")}
        cmp = issues.attempt("CDP vs sombra", lambda: compare_tracks(main, shadow))
        if cmp is not None:
            out["compare"] = [{"date": idx.date(), **{c: _num(row[c]) for c in cmp.columns}}
                              for idx, row in cmp.iterrows()]
    if records:
        # Âncora da inception: NAV de abertura do primeiro registro (antes da execução no MOC),
        # para o gráfico do 1º dia ter um segmento a partir do NAV inicial.
        first_shadow = shadow_records[0] if shadow_records else None
        out["anchor"] = {
            "label": "início", "date": records[0].date, "nav_cdp": records[0].nav_start_usd,
            "nav_shadow": (first_shadow.nav_start_usd if first_shadow is not None
                           and first_shadow.date == records[0].date else None)}
        last = records[-1].date
        week_start = records[-1].live_book_week
        out["periods"] = {
            "itd": _period(records, "Desde o início", None, None),
            "ytd": _period(records, "No ano", date(last.year, 1, 1), last),
            "mtd": _period(records, "No mês", date(last.year, last.month, 1), last),
            "semana": _period(records, "Carteira da semana vigente", week_start, last)
            if week_start else None,
            "dia": _period(records, "Último pregão", last, last),
        }
    return out, records, shadow_records


# ==========================================================
# Livro semanal
# ==========================================================

def _facts_from_briefing(week_dir: Path, issues: _Issues, scope: str,
                         names: dict[str, str] | None = None) -> dict[str, str]:
    """Fatos do briefing (``{id: formatado}``). Com ``names``, acrescenta nele os nomes dos
    emissores do universo congelado no briefing (``issuers``)."""
    path = week_dir / "briefing" / "context.json"
    if not path.is_file():
        return {}
    raw = issues.attempt(f"{scope}: briefing/context.json", lambda: _read_json(path))
    if names is not None and isinstance(raw, dict) and isinstance(raw.get("issuers"), dict):
        for iid, info in raw["issuers"].items():
            if isinstance(info, dict) and isinstance(info.get("name"), str) and info["name"]:
                names[str(iid)] = info["name"]
    facts = raw.get("facts") if isinstance(raw, dict) else None
    if not isinstance(facts, dict):
        return {}
    return {str(k): str(v.get("formatted", "n/d")) for k, v in facts.items()
            if isinstance(v, dict)}


def _without_raw_facts(x: Any, path: str, dropped: list[str]) -> Any:
    """Cópia sem os textos que ainda trazem ``{{fact:...}}`` (falha da renderização em código):
    em objetos o texto vira ``None``; em listas, sai. ``dropped`` recebe os caminhos."""
    if isinstance(x, dict):
        out: dict[str, Any] = {}
        for k, v in x.items():
            if isinstance(v, str) and _RAW_FACT_RE.search(v):
                dropped.append(f"{path}.{k}")
                out[k] = None
            else:
                out[k] = _without_raw_facts(v, f"{path}.{k}", dropped)
        return out
    if isinstance(x, list):
        items = []
        for i, v in enumerate(x):
            if isinstance(v, str) and _RAW_FACT_RE.search(v):
                dropped.append(f"{path}[{i}]")
                continue
            items.append(_without_raw_facts(v, f"{path}[{i}]", dropped))
        return items
    return x


def _thesis_section(week_dir: Path, week: date, issues: _Issues) -> dict[str, Any]:
    """Tese da carteira da semana: o bloco ``rendered`` de ``tese/tese_publicada.json`` (formato
    do painel, ``{{fact:id}}`` já resolvidos pelo código) com ``available: true``. Sem tese
    publicada — inclusive com só o rascunho ``tese.json`` da mente — ``{"available": false}``.
    Texto com ``{{fact:`` remanescente sai (apontamento), nunca vai ao painel."""
    path = week_dir / THESIS_DIR / THESIS_FILE
    if not path.is_file():
        return {"available": False}
    raw = _read_json(path)
    rendered = raw.get("rendered") if isinstance(raw, dict) else None
    if not isinstance(rendered, dict):
        raise ValueError(f"{THESIS_FILE} sem o bloco 'rendered'")
    if str(rendered.get("week")) != week.isoformat():
        raise ValueError(f"{THESIS_FILE} de outra semana ({rendered.get('week')!r})")
    dropped: list[str] = []
    out = _without_raw_facts(rendered, "thesis", dropped)
    if dropped:
        issues.add("tese publicada", f"{len(dropped)} texto(s) com marcador de fato não "
                   "resolvido omitido(s): " + ", ".join(dropped[:5]))
    out["available"] = True
    return out


def referenced_issuers(obj: Any) -> set[str]:
    """Emissores citados em qualquer ponto do retrato: ``issuer_id``/``iid``, listas
    ``issuer_ids``/``issuers``/``only_shadow``/``only_cdp`` e as linhas da atribuição por emissor
    (``name`` = id)."""
    found: set[str] = set()

    def walk(x: Any) -> None:
        if isinstance(x, dict):
            for k, v in x.items():
                if k in _IID_KEYS and isinstance(v, str):
                    found.add(v)
                elif k in _IID_LIST_KEYS and isinstance(v, list):
                    found.update(s for s in v if isinstance(s, str))
                else:
                    if k == "issuer" and isinstance(v, list):
                        found.update(r["name"] for r in v
                                     if isinstance(r, dict) and isinstance(r.get("name"), str))
                    walk(v)
        elif isinstance(x, list):
            for v in x:
                walk(v)

    walk(obj)
    return found


def _row_names(obj: Any, out: dict[str, str]) -> None:
    """Nomes das linhas que trazem ``issuer_id`` e ``name`` (posições, sombra, contribuintes)."""
    if isinstance(obj, dict):
        iid, name = obj.get("issuer_id"), obj.get("name")
        if isinstance(iid, str) and isinstance(name, str) and name:
            out.setdefault(iid, name)
        for v in obj.values():
            _row_names(v, out)
    elif isinstance(obj, list):
        for v in obj:
            _row_names(v, out)


def _issuer_names(data: Mapping[str, Any], universe: Mapping[str, str]) -> dict[str, str]:
    """``{issuer_id: nome}`` de todo emissor citado no retrato (a página nunca mostra o id cru):
    nomes do universo congelado nos briefings (o mais recente prevalece) e, na falta, os das
    linhas exportadas. Emissor sem nome conhecido fica de fora."""
    known = dict(universe)
    rows: dict[str, str] = {}
    _row_names(data, rows)
    for iid, name in rows.items():
        known.setdefault(iid, name)
    return {i: known[i] for i in sorted(referenced_issuers(data)) if known.get(i)}


def _final_proposal(proposals: Sequence[Any], decisions: Mapping[int, Any], booked: Any):
    """Proposta vigente: a efetivada; senão a última APPROVE; senão a versão mais recente."""
    if booked is not None:
        for p in proposals:
            if p.proposal_id == booked.proposal_id:
                return p
    approved = [p for p in proposals if (d := decisions.get(p.version)) is not None
                and d.proposal_id == p.proposal_id and d.decision.value == "APPROVE"]
    if approved:
        return approved[-1]
    return proposals[-1] if proposals else None


def _issuer_weights(p: Any) -> dict[str, float]:
    out: dict[str, float] = {}
    for t in (p.positions if p is not None else []):
        out[t.issuer_id] = out.get(t.issuer_id, 0.0) + float(t.weight)
    return out


def _expo_label(group: str, name: str) -> str:
    """Nome pt-BR de uma linha de exposição (para os textos gerados pelo painel)."""
    s = str(name)
    if s.startswith("tema:"):
        return f"tema {THEME_PT.get(s[5:], s[5:])}"
    if s.startswith("commodity:"):
        return f"commodity {COMMODITY_PT.get(s[10:], s[10:])}"
    if s.startswith("evento:"):
        return f"evento {s[7:]}"
    if group == "sector":
        return SECTOR_PT.get(s, s)
    if group == "style":
        return STYLE_PT.get(s, s)
    return s


def _expo_severity(group: str, name: str) -> str | None:
    """Severidade do gate de compliance que cobre a linha: país, setor e tema são HARD
    (``COUNTRY_NET``/``SECTOR_NET``/``THEME_NET``); estilo, commodity e evento, SOFT."""
    s = str(name)
    if group in ("country", "sector") or s.startswith("tema:"):
        return "HARD"
    if group in ("style", "market"):
        return "SOFT"
    return None


def _exposure_rows(lines: Iterable[Any], *, daily: bool) -> list[dict[str, Any]]:
    """Linhas de exposição com uso do limite e ``status`` pela MESMA política dos limites
    (:func:`_over`): no registro diário (drift) o excesso é ``alerta``; ``excesso`` só para
    limite HARD no ex-ante da decisão. Estilo e commodity não têm ponta long/short (o produtor
    grava 0,0 como marcador): long/short/gross saem ``None`` e ``measure`` diz a unidade."""
    rows = []
    for e in lines:
        d = e.model_dump(mode="json")
        lim, net = _num(e.limit), _num(e.net)
        sev = _expo_severity(e.group, e.name)
        d["utilization"] = abs(net) / lim if lim and net is not None and lim > 0 else None
        d["breach"] = (abs(net) > lim + LIMIT_TOL) if lim is not None and net is not None else None
        d["severity"] = sev if lim is not None else None
        d["status"] = (_over(abs(net) / lim, 1.0, daily=daily, hard=sev == "HARD")
                       if lim and lim > 0 and net is not None else None)
        if e.group == "style" or str(e.name).startswith("commodity:"):
            d.update({"long": None, "short": None, "gross": None,
                      "measure": "z × NAV" if e.group == "style" else "Σ w·β"})
        rows.append(d)
    return rows


def _sorted_map(m: Mapping[str, Any], *, by_abs: bool = False, key_name: str = "name",
                value_name: str = "value") -> list[dict[str, Any]]:
    items = [(k, _num(v)) for k, v in m.items()]
    if by_abs:
        items.sort(key=lambda kv: (kv[1] is None, -abs(kv[1] or 0.0), kv[0]))
    else:
        items.sort(key=lambda kv: (kv[1] is None, kv[1] if kv[1] is not None else 0.0, kv[0]))
    return [{key_name: k, value_name: v} for k, v in items]


def _risk_summary(risk: Any, names: Mapping[str, str]) -> dict[str, Any]:
    d = _risk_scalars(risk, names)
    d["exposures"] = _exposure_rows(risk.exposures, daily=False)
    return d


def _compliance(checks: Sequence[Any]) -> dict[str, Any]:
    sev_order = {"HARD": 0, "SOFT": 1, "INFO": 2}
    rows = [c.model_dump(mode="json") for c in checks]
    rows.sort(key=lambda c: (c["passed"], sev_order.get(c["severity"], 9), c["check_id"]))
    failed = [c for c in rows if not c["passed"]]
    return {
        "n": len(rows), "n_passed": len(rows) - len(failed),
        "failed_hard": [c["check_id"] for c in failed if c["severity"] == "HARD"],
        "failed_soft": [c["check_id"] for c in failed if c["severity"] == "SOFT"],
        "failed_info": [c["check_id"] for c in failed if c["severity"] == "INFO"],
        "checks": rows,
    }


def _participation(side: str, cfg: FundConfig) -> float:
    lq = cfg.liquidity
    return float(lq.participation_rate if side == "LONG" else lq.short_participation_rate)


def _liq_days(p: Any, cfg: FundConfig) -> float | None:
    """Dias para liquidar uma posição-alvo com a participação do mandato POR PONTA (long
    ``participation_rate``, short ``short_participation_rate``): ``|nocional| / (p × ADTV)``,
    a mesma conta do gate ``LIQ_DAYS_<ponta>``. O ``days_to_liquidate`` gravado na proposta usa
    a participação dos longs também nos shorts; por isso é recalculado aqui. Sem ADTV ⇒ ``None``."""
    adtv, notional = _num(getattr(p, "adtv_usd", None)), _num(getattr(p, "notional_usd", None))
    rate = _participation(p.side.value, cfg)
    if adtv is None or adtv <= 0 or notional is None or not rate > 0:
        return None
    return abs(notional) / (rate * adtv)


def _liquid_share(positions: Sequence[Any], cfg: FundConfig, horizon: float) -> float | None:
    """Fração do gross liquidável em ``horizon`` dias: Σ min(|w|, h × p × ADTV / NAV) / Σ|w|
    (participação por ponta; cada nome limitado ao próprio tamanho). Algum nome sem ADTV ⇒
    ``None`` (ausente nunca vira zero)."""
    total, liquid = 0.0, 0.0
    for p in positions:
        w = abs(float(p.weight))
        notional, adtv = _num(p.notional_usd), _num(p.adtv_usd)
        if adtv is None or adtv <= 0 or notional is None or w == 0:
            if w:
                return None
            continue
        nav = abs(notional) / w
        total += w
        liquid += min(w, horizon * _participation(p.side.value, cfg) * adtv / nav)
    return liquid / total if total else None


def _liquidity_by_side(positions: Sequence[Any], cfg: FundConfig) -> dict[str, Any]:
    limits = {"LONG": cfg.liquidity.max_days_to_liquidate_long,
              "SHORT": cfg.liquidity.max_days_to_liquidate_short}
    out: dict[str, Any] = {}
    days = {id(p): _liq_days(p, cfg) for p in positions}
    for side, lim in limits.items():
        ps = [p for p in positions if p.side.value == side]
        vals = [v for p in ps if (v := days[id(p)]) is not None]
        mx = max(vals) if vals else None
        out[side] = {"max_days": mx, "limit": float(lim), "n": len(ps),
                     "participation": _participation(side, cfg),
                     "n_missing": len(ps) - len(vals),
                     "breach": (mx > lim + LIMIT_TOL) if mx is not None else None}
    total = sum(abs(float(p.weight)) for p in positions)
    buckets: dict[str, list[float]] = {label: [0.0, 0] for _, label in LIQUIDITY_BUCKETS}
    buckets["n/d"] = [0.0, 0]
    for p in positions:
        d = days[id(p)]
        label = "n/d" if d is None else next(lab for ub, lab in LIQUIDITY_BUCKETS if d <= ub)
        buckets[label][0] += abs(float(p.weight))
        buckets[label][1] += 1
    out["buckets"] = [{"bucket": k, "gross": v[0], "gross_share": v[0] / total if total else None,
                       "n": int(v[1])} for k, v in buckets.items()]
    n_missing = sum(1 for p in positions if days[id(p)] is None)
    out["liquid_3d"] = _liquid_share(positions, cfg, 3.0)
    out["liquid_5d"] = _liquid_share(positions, cfg, 5.0)
    out["n_missing_adtv"] = n_missing
    return out


def _squeeze_summary(positions: Sequence[Any]) -> dict[str, Any]:
    shorts = [p for p in positions if p.side.value == "SHORT"]
    counts = Counter(p.squeeze_bucket for p in shorts)
    weights: dict[str, float] = {}
    for p in shorts:
        weights[p.squeeze_bucket] = weights.get(p.squeeze_bucket, 0.0) + float(p.weight)
    return {"n_shorts": len(shorts),
            "by_bucket": [{"bucket": b, "n": int(counts.get(b, 0)), "weight": weights.get(b)}
                          for b in ("HIGH", "MEDIUM", "LOW", "NA")]}


def _proposal_summary(p: Any) -> dict[str, Any]:
    total_cost, partial = 0.0, False
    for t in p.trades:
        bps = _num(t.est_cost_bps)
        if bps is None:
            partial = True
        else:
            total_cost += abs(float(t.notional_usd)) * bps / 1e4
    return {
        "n_positions": len(p.positions), "n_long": p.risk.n_long, "n_short": p.risk.n_short,
        "gross": p.risk.gross, "net": p.risk.net, "beta": p.risk.beta,
        "ex_ante_vol": p.risk.ex_ante_vol, "var_1d_99": p.risk.var_1d_99,
        "expected_alpha_annual": p.optimizer.expected_alpha_annual,
        "expected_cost_annual": p.optimizer.expected_cost_annual,
        "n_trades": len(p.trades),
        "turnover": sum(abs(float(t.weight_change)) for t in p.trades) if p.trades else 0.0,
        "trade_cost_usd": total_cost if p.trades else 0.0,
        "trade_cost_partial": partial,
        "hard_failures": [c.check_id for c in p.hard_failures],
        "soft_failures": [c.check_id for c in p.soft_failures],
    }


def _proposal_full(p: Any, cfg: FundConfig, proposal_hash: str | None) -> dict[str, Any]:
    names = {t.issuer_id: t.name for t in p.positions}
    positions = sorted(({**t.model_dump(mode="json"), "days_to_liquidate": _liq_days(t, cfg),
                         "days_to_liquidate_recorded": t.days_to_liquidate,
                         "liq_participation": _participation(t.side.value, cfg)}
                        for t in p.positions),
                       key=lambda t: (-abs(t["weight"]), t["issuer_id"]))
    trades = sorted((t.model_dump(mode="json") for t in p.trades),
                    key=lambda t: (-abs(t["notional_usd"]), t["issuer_id"]))
    return {
        "proposal_id": p.proposal_id, "week": p.week, "version": p.version,
        "created_at": p.created_at, "created_by": p.created_by, "nav_usd": p.nav_usd,
        "snapshot_id": p.snapshot_id, "snapshot_hash": p.snapshot_hash,
        "config_hash": p.config_hash, "research_hash": p.research_hash,
        "proposal_hash": proposal_hash, "overrides": dict(p.overrides),
        "is_synthetic": p.is_synthetic, "data_notice": p.data_notice,
        "summary": _proposal_summary(p), "positions": positions, "trades": trades,
        "fx_hedges": [h.model_dump(mode="json") for h in p.fx_hedges],
        "risk": _risk_summary(p.risk, names), "compliance": _compliance(p.compliance),
        "optimizer": p.optimizer.model_dump(mode="json"),
        "liquidity_by_side": _liquidity_by_side(p.positions, cfg),
        "squeeze": _squeeze_summary(p.positions),
    }


def _proposal_compact(p: Any, proposal_hash: str | None) -> dict[str, Any]:
    return {
        "proposal_id": p.proposal_id, "week": p.week, "version": p.version,
        "created_at": p.created_at, "proposal_hash": proposal_hash,
        "is_synthetic": p.is_synthetic, "summary": _proposal_summary(p),
        "risk": _risk_scalars(p.risk, {t.issuer_id: t.name for t in p.positions}),
        "compliance": {
            k: v for k, v in _compliance(p.compliance).items() if k != "checks"},
        "positions": [{"issuer_id": t.issuer_id, "name": t.name, "side": t.side.value,
                       "weight": t.weight, "country": t.country, "sector": t.sector}
                      for t in sorted(p.positions, key=lambda t: (-abs(t.weight), t.issuer_id))],
    }


def _changes(new: Any, old: Any, threshold: float = 0.0025) -> list[dict[str, Any]]:
    """Entradas, saídas, inversões e redimensionamentos (|Δw| ≥ ``threshold``)."""
    if old is None:
        return []
    a, b = _issuer_weights(old), _issuer_weights(new)
    names = {t.issuer_id: t.name for t in [*old.positions, *new.positions]}
    rows = []
    for iid in sorted(set(a) | set(b)):
        wa, wb = a.get(iid), b.get(iid)
        delta = (wb or 0.0) - (wa or 0.0)
        if wa is None:
            kind = "entrada"
        elif wb is None:
            kind = "saida"
        elif wa * wb < 0:
            kind = "inversao"
        elif abs(delta) >= threshold:
            kind = "aumento" if abs(wb) > abs(wa) else "reducao"
        else:
            continue
        rows.append({"issuer_id": iid, "name": names.get(iid, iid), "change": kind,
                     "w_old": wa, "w_new": wb, "delta": delta})
    order = {"entrada": 0, "saida": 1, "inversao": 2, "aumento": 3, "reducao": 4}
    return sorted(rows, key=lambda r: (order[r["change"]], -abs(r["delta"]), r["issuer_id"]))


def _shadow_section(cdp: Any, shadow: Any, cfg: FundConfig) -> dict[str, Any]:
    from .reports import _overlap

    ra, rb = cdp.risk, shadow.risk
    oa, ob = cdp.optimizer, shadow.optimizer

    def row(key: str, label: str, a: Any, b: Any, unit: str) -> dict[str, Any]:
        x, y = _num(a), _num(b)
        return {"key": key, "label": label, "cdp": x, "shadow": y, "unit": unit,
                "diff": (x - y) if x is not None and y is not None else None}

    metrics = [
        row("expected_alpha_annual", "Alpha esperado (a.a.)", oa.expected_alpha_annual,
            ob.expected_alpha_annual, "pct"),
        row("expected_cost_annual", "Custo esperado (a.a.)", oa.expected_cost_annual,
            ob.expected_cost_annual, "pct"),
        row("ex_ante_vol", "Vol ex-ante", ra.ex_ante_vol, rb.ex_ante_vol, "pct"),
        row("factor_vol", "Vol fatorial", ra.factor_vol, rb.factor_vol, "pct"),
        row("specific_vol", "Vol específica", ra.specific_vol, rb.specific_vol, "pct"),
        row("factor_risk_share", "Fração de risco fatorial", ra.factor_risk_share,
            rb.factor_risk_share, "pct"),
        row("beta", "Beta", ra.beta, rb.beta, "x"),
        row("gross", "Gross", ra.gross, rb.gross, "pct"),
        row("net", "Net", ra.net, rb.net, "pct"),
        row("n_long", "Longs", ra.n_long, rb.n_long, "count"),
        row("n_short", "Shorts", ra.n_short, rb.n_short, "count"),
        row("effective_n", "N efetivo", ra.effective_n, rb.effective_n, "x"),
        row("var_1d_99", "VaR 1d (99%)", ra.var_1d_99, rb.var_1d_99, "pct"),
        row("es_1d_99", "ES 1d (99%)", ra.es_1d_99, rb.es_1d_99, "pct"),
        row("max_days_to_liquidate", "Máx. dias para liquidar (participação por ponta)",
            _max_liq_days(cdp, cfg), _max_liq_days(shadow, cfg), "days"),
    ]
    ov = _overlap(cdp, shadow)
    wa, wb = _issuer_weights(cdp), _issuer_weights(shadow)
    diffs = sorted(({"issuer_id": i, "w_cdp": wa.get(i), "w_shadow": wb.get(i),
                     "diff": wa.get(i, 0.0) - wb.get(i, 0.0)} for i in set(wa) | set(wb)),
                   key=lambda r: (-abs(r["diff"]), r["issuer_id"]))
    abs_sum = sum(abs(r["diff"]) for r in diffs)
    return {
        "proposal_id": shadow.proposal_id, "summary": _proposal_summary(shadow),
        "risk": _risk_scalars(shadow.risk, {t.issuer_id: t.name for t in shadow.positions}),
        "compliance": {k: v for k, v in _compliance(shadow.compliance).items() if k != "checks"},
        "positions": [{"issuer_id": t.issuer_id, "name": t.name, "side": t.side.value,
                       "weight": t.weight, "country": t.country, "sector": t.sector,
                       "alpha_z": t.alpha_z}
                      for t in sorted(shadow.positions,
                                      key=lambda t: (-abs(t.weight), t.issuer_id))],
        "comparison": {"metrics": metrics, "overlap": ov, "weight_diffs": diffs[:40],
                       "active_weight_sum": 0.5 * abs_sum, "active_weight_abs_sum": abs_sum},
    }


def _max_liq_days(p: Any, cfg: FundConfig) -> float | None:
    vals = [v for t in p.positions if (v := _liq_days(t, cfg)) is not None]
    return max(vals) if vals else None


def _pm_section(path: Path, facts: Mapping[str, str], issues: _Issues, scope: str
                ) -> dict[str, Any] | None:
    if not path.is_file():
        return None
    from ..research.pm_agent import PMDecisionOutput

    out = issues.attempt(f"{scope}: decisão do PM fora do schema",
                         lambda: PMDecisionOutput.model_validate(_read_json(path)))
    if out is None:
        return {"valid": False, "file_sha256": _sha256_file(path)}
    d = out.model_dump(mode="json")
    for key in ("market_view", "what_changed", "evaluation_last_week"):
        d[key] = _render_facts(d.get(key), facts)
    for v in d.get("views", []):
        v["rationale"] = _render_facts(v.get("rationale"), facts)
        v["evidence"] = [{"id": e, "url": _safe_url(e) if str(e).startswith("http") else None}
                         for e in v.pop("evidence_ids", [])]
    for x in d.get("exclusions", []):
        x["reason"] = _render_facts(x.get("reason"), facts)
    for j in d.get("position_journal", []):
        for k in ("thesis", "invalidation_criteria", "premortem"):
            j[k] = _render_facts(j.get(k), facts)
    d["views"] = sorted(d.get("views", []), key=lambda v: (-v["stance"], -v["conviction"],
                                                           v["issuer_id"]))
    d.update({"valid": True, "file_sha256": _sha256_file(path),
              "regime_label": REGIME_PT.get(str(d.get("regime")), d.get("regime")),
              "posture_label": POSTURE_PT.get(str(d.get("risk_posture")),
                                              d.get("risk_posture"))})
    return d


def _evidence(refs: Sequence[Any]) -> list[dict[str, Any]]:
    out = []
    for e in list(refs)[:MAX_EVIDENCE_PER_NOTE]:
        kind = str(getattr(e.kind, "value", e.kind))
        ref = e.ref_id
        url = _safe_url(ref) if kind == "source" or str(ref).startswith("http") else None
        out.append({"kind": kind, "ref_id": ref, "url": url,
                    "note": (e.note or "")[:EVIDENCE_NOTE_CHARS]})
    return out


def _research_section(pack: Any, facts: Mapping[str, str], *, full: bool,
                      source: str = "livro", notes_detail: bool = True) -> dict[str, Any]:
    """Pesquisa da semana: ``source="livro"`` (pacote gravado com hash) ou ``"entradas"``
    (arquivo da mente em ``inputs/``, ainda não validado pela decisão)."""
    notes = list(pack.notes)
    roles = Counter(n.role for n in notes)
    news = list(getattr(pack, "news", []) or [])
    rh = getattr(pack, "research_hash", None)
    out: dict[str, Any] = {
        "source": source, "provider": getattr(pack, "provider", None), "mind": pack.mind,
        "snapshot_id": getattr(pack, "snapshot_id", None),
        "research_hash": rh() if callable(rh) else None,
        "is_synthetic": bool(getattr(pack, "is_synthetic", False)),
        "counts": {"notes": len(notes), "by_role": dict(sorted(roles.items())),
                   "issuers": len({n.issuer_id for n in notes}), "macro": len(pack.macro),
                   "views": len(pack.views), "news": len(news),
                   "squeeze_veto": sum(1 for n in notes if n.squeeze
                                       and n.squeeze.verdict == "veto"),
                   "squeeze_caution": sum(1 for n in notes if n.squeeze
                                          and n.squeeze.verdict == "caution")},
        "macro": [{
            "note_id": m.note_id, "scope": m.scope, "stance": m.stance, "regime": m.regime,
            "summary": _render_facts(m.summary, facts),
            "key_events": [c.model_dump(mode="json") for c in m.key_events],
            "risks": [_render_facts(r, facts) for r in m.risks],
            "portfolio_implications": [_render_facts(r, facts)
                                       for r in m.portfolio_implications],
            "evidence": _evidence(m.evidence), "n_evidence": len(m.evidence),
            "provider": m.provider, "created_at": m.created_at,
        } for m in sorted(pack.macro, key=lambda m: m.scope)],
    }
    if not full:
        return out
    out["notes_detail"] = notes_detail
    out["notes"] = [] if not notes_detail else [{
        "note_id": n.note_id, "issuer_id": n.issuer_id, "role": n.role, "stance": n.stance,
        "confidence": n.confidence, "horizon_weeks": n.horizon_weeks,
        "thesis": _render_facts(n.thesis, facts),
        "bull_points": [_render_facts(x, facts) for x in n.bull_points],
        "bear_points": [_render_facts(x, facts) for x in n.bear_points],
        "key_risks": [_render_facts(x, facts) for x in n.key_risks],
        "catalysts": [c.model_dump(mode="json") for c in n.catalysts],
        "squeeze": n.squeeze.model_dump(mode="json") if n.squeeze else None,
        "evidence": _evidence(n.evidence), "n_evidence": len(n.evidence),
        "provider": n.provider, "created_at": n.created_at,
    } for n in sorted(notes, key=lambda n: (n.issuer_id, n.role, n.note_id))]
    out["views"] = [{
        "issuer_id": v.issuer_id, "source": str(getattr(v.source, "value", v.source)),
        "score": v.score,
        "confidence": v.confidence, "no_short": v.no_short, "no_long": v.no_long,
        "max_abs_weight": v.max_abs_weight, "rationale": _render_facts(v.rationale, facts),
        "author": v.author, "note_ids": list(v.note_ids),
    } for v in sorted(pack.views, key=lambda v: (v.issuer_id,
                                                 str(getattr(v.source, "value", v.source))))]
    out["news"] = [{
        "news_id": x.news_id, "title": x.title, "source": x.source, "url": _safe_url(x.url),
        "published_at": x.published_at, "issuer_ids": list(x.issuer_ids),
        "is_synthetic": x.is_synthetic,
    } for x in sorted(news, key=lambda x: (x.published_at, x.news_id), reverse=True)]
    return out


def _ai_calls(week_dir: Path, issues: _Issues, scope: str) -> dict[str, Any] | None:
    from ..contracts import LLMCallRecord

    calls = []
    for path in sorted(week_dir.rglob("llm_calls.jsonl")):
        if "raw" in path.relative_to(week_dir).parts[:-1]:
            continue
        for line in (_read_text(path) or "").splitlines():
            if line.strip():
                rec = issues.attempt(f"{scope}: ledger de IA ({path.name})",
                                     lambda line=line: LLMCallRecord.model_validate_json(line))
                if rec is not None:
                    calls.append(rec)
    if not calls:
        return None
    tin = [c.input_tokens for c in calls if c.input_tokens is not None]
    tout = [c.output_tokens for c in calls if c.output_tokens is not None]
    cost = [v for c in calls if (v := _num(c.cost_usd)) is not None]
    return {"n_calls": len(calls), "parse_ok": sum(1 for c in calls if c.parse_ok),
            "failed": sum(1 for c in calls if not c.parse_ok),
            "with_issues": sum(1 for c in calls if c.validation_issues),
            "by_task": dict(sorted(Counter(c.task for c in calls).items())),
            "prompt_versions": sorted({c.prompt_version for c in calls}),
            "input_tokens": sum(tin) if tin else None,
            "output_tokens": sum(tout) if tout else None,
            "cost_usd": sum(cost) if cost else None}


def _decision_dict(d: Any, cfg: FundConfig, facts: Mapping[str, str], *,
                   journal: bool = True) -> dict[str, Any]:
    tz = ZoneInfo(cfg.fund.timezone)
    h, m = (int(x) for x in cfg.fund.decision_deadline_local.split(":"))
    deadline = datetime(d.week.year, d.week.month, d.week.day, h, m, tzinfo=tz)
    out = d.model_dump(mode="json")
    out["rationale"] = _render_facts(out.get("rationale"), facts)
    out["journal_omitted"] = not journal and out.get("journal") is not None
    if not journal:
        out["journal"] = None
    j = out.get("journal")
    if isinstance(j, dict):
        for k in ("situation", "alternatives_considered", "sizing_rationale",
                  "ai_vs_quant_vs_pm", "premortem", "mental_state"):
            j[k] = _render_facts(j.get(k), facts)
        for jp in j.get("positions", []):
            for k in ("thesis", "variant_perception", "invalidation_criteria", "premortem",
                      "ai_vs_pm_divergence"):
                jp[k] = _render_facts(jp.get(k), facts)
    out["decided_at_local"] = _local(d.decided_at, tz)
    out["deadline_local"] = deadline.isoformat()
    out["on_time"] = d.decided_at <= deadline
    return out


def _week_performance(week: date, records: Sequence[Any], shadow: Sequence[Any]
                      ) -> dict[str, Any] | None:
    sub = [r for r in records if r.live_book_week == week]
    if not sub:
        return None
    dates = {r.date for r in sub}
    sh = [r for r in shadow if r.date in dates]
    ret, sret = _compound(r.ret for r in sub), _compound(r.ret for r in sh)
    return {"n_days": len(sub), "first_date": sub[0].date, "last_date": sub[-1].date,
            "ret": ret, "pnl_usd": sum(float(r.pnl_usd) for r in sub),
            "shadow_n_days": len(sh), "shadow_ret": sret,
            "value_added": ((1 + ret) / (1 + sret) - 1)
            if ret is not None and sret is not None and len(sh) == len(sub) else None}


def _week_entry(rt: Any, cfg: FundConfig, book: Any, week: date, full: bool,
                prev_final: Any, records: Sequence[Any], shadow_records: Sequence[Any],
                issues: _Issues, notes_detail: bool = True,
                names: dict[str, str] | None = None) -> tuple[dict[str, Any], Any]:
    """Uma semana do livro (``full`` ⇒ detalhe completo, com a tese publicada; senão resumo).
    ``names`` recebe os nomes dos emissores do briefing das semanas completas."""
    from ..contracts import Proposal
    from ..hashing import sha256_obj

    reports_root = Path(rt.reports_root)
    scope = f"Semana {week.isoformat()}"
    wdir = Path(rt.book_root) / week.isoformat()
    local = _Issues()
    proposals = []
    for v in local.attempt("versões de proposta", lambda: book.proposal_versions(week), []):
        p = local.attempt(f"proposta v{v}", lambda v=v: book.load_proposal(week, v))
        if p is not None:
            proposals.append(p)
    states = local.attempt("estados das propostas", lambda: book.week_states(week), {})
    decisions = local.attempt("decisões", lambda: book.list_decisions(week), {})
    booked = local.attempt("efetivação (booked.json não confere com a trilha)",
                           lambda: book.load_booked(week))
    booked_raw = booked
    if booked is None and (wdir / "booked.json").is_file():
        booked_raw = local.attempt("efetivação (leitura crua)",
                                   lambda: book._read_booked(week))
    research = local.attempt("pacote de pesquisa", lambda: book.load_research_pack(week))
    final = _final_proposal(proposals, decisions, booked)
    decision = decisions.get(final.version) if final is not None else None
    if decision is not None and decision.proposal_id != final.proposal_id:
        decision = None
    needs_facts = full or (decision is not None and "{{" in decision.rationale)
    facts = (_facts_from_briefing(wdir, local, "briefing", names if full else None)
             if needs_facts else {})
    attempts = None
    if (wdir / "attempts.json").is_file():
        attempts = local.attempt("attempts.json", lambda: _read_json(wdir / "attempts.json"))
    manifest = None
    mpath = wdir / "briefing" / "prepare_manifest.json"
    if mpath.is_file():
        manifest = local.attempt("prepare_manifest.json", lambda: _read_json(mpath))
    shadow = None
    spath = wdir / "shadow_quant.json"
    if spath.is_file():
        shadow = local.attempt("shadow_quant.json",
                               lambda: Proposal.model_validate(_read_json(spath)))
    state = (states.get(final.version) if final is not None else None)
    entry: dict[str, Any] = {
        "week": week, "detail": "completo" if full else "resumo",
        "state": state.value if state is not None else None,
        "proposals": [{"version": p.version, "proposal_id": p.proposal_id,
                       "created_at": p.created_at,
                       "state": (states.get(p.version).value
                                 if states.get(p.version) is not None else None),
                       "n_positions": len(p.positions)} for p in proposals],
        "decisions": [{"version": v, "decision": d.decision.value, "mode": d.mode.value,
                       "decided_at": d.decided_at, "approval_hash": d.approval_hash,
                       "proposal_id": d.proposal_id}
                      for v, d in sorted(decisions.items())],
        "decision": (_decision_dict(decision, cfg, facts, journal=full)
                     if decision is not None else None),
        "path_taken": (attempts or {}).get("path") if isinstance(attempts, dict) else None,
        "attempts": (attempts or {}).get("attempts", []) if isinstance(attempts, dict) else [],
        "input_issues": ((attempts or {}).get("input_issues", [])
                         if isinstance(attempts, dict) else []),
        "executed": booked is not None,
        "booked": ({"booked_at": booked_raw.booked_at, "proposal_id": booked_raw.proposal_id,
                    "approval_hash": booked_raw.approval_hash, "nav_usd": booked_raw.nav_usd,
                    "n_positions": len(booked_raw.positions),
                    "pricing_note": booked_raw.pricing_note,
                    "verified": booked is not None}
                   if booked_raw is not None else None),
        "briefing": ({k: manifest.get(k) for k in (
            "prepared_at", "captured_at", "previous_session", "live", "snapshot_hash",
            "store_content_hash", "config_hash", "n_quotes", "slow_failures")}
            if isinstance(manifest, dict) else None),
        "performance": _week_performance(week, records, shadow_records),
    }
    entry["path_label"] = PATH_PT.get(str(entry["path_taken"]), entry["path_taken"])
    inputs = {"briefing": (wdir / "briefing" / "prepare_manifest.json").is_file(),
              "research_pack": (wdir / "inputs" / "research_pack.json").is_file(),
              "pm_decision": (wdir / "inputs" / "pm_decision.json").is_file()}
    entry["inputs"] = inputs
    stage = ("efetivada" if booked is not None else "decidida" if decisions
             else "entradas_gravadas" if inputs["pm_decision"] or inputs["research_pack"]
             else "preparada" if inputs["briefing"] else "vazia")
    entry["stage"] = stage
    entry["stage_label"] = WEEK_STAGE_PT[stage]
    if final is not None:
        ph = local.attempt("hash da proposta", lambda: sha256_obj(final))
        entry["proposal"] = (_proposal_full(final, cfg, ph) if full
                             else _proposal_compact(final, ph))
        entry["changes_vs_previous"] = _changes(final, prev_final)
        entry["previous_week"] = prev_final.week if prev_final is not None else None
    else:
        entry["proposal"] = None
        entry["changes_vs_previous"] = []
        entry["previous_week"] = None
    if shadow is not None and final is not None:
        entry["shadow"] = local.attempt("comparação CDP × sombra",
                                        lambda: _shadow_section(final, shadow, cfg))
    else:
        entry["shadow"] = None
    entry["pm_decision"] = (_pm_section(wdir / "inputs" / "pm_decision.json", facts, local,
                                        "inputs") if full else None)
    entry["research"] = (local.attempt("resumo da pesquisa",
                                       lambda: _research_section(research, facts, full=full,
                                                                 notes_detail=notes_detail))
                         if research is not None else None)
    rp_input = wdir / "inputs" / "research_pack.json"
    if research is None and full and rp_input.is_file():
        from ..research.pm_agent import ResearchPackFile

        rp = local.attempt("inputs/research_pack.json fora do schema",
                           lambda: ResearchPackFile.model_validate(_read_json(rp_input)))
        if rp is not None:
            entry["research"] = local.attempt(
                "resumo da pesquisa (entradas)",
                lambda: _research_section(rp, facts, full=True, source="entradas",
                                          notes_detail=notes_detail))
    entry["ai_calls"] = _ai_calls(wdir, local, "ledger") if wdir.is_dir() else None
    rdir = reports_root / "weekly" / week.isoformat()
    md_path = rdir / "relatorio.md"
    md = _read_text(md_path)
    entry["report"] = ({"available": True, "has_html": (rdir / "relatorio.html").is_file(),
                        "sha256": _sha256_file(md_path),
                        "markdown": md if full else None, "chars": len(md)}
                       if md is not None else {"available": False})
    if md is None and full and final is not None and final.memo_markdown:
        entry["memo_markdown"] = final.memo_markdown
    if full:
        entry["thesis"] = local.attempt("tese publicada (tese/tese_publicada.json)",
                                        lambda: _thesis_section(wdir, week, local),
                                        {"available": False})
    entry["issues"] = local.items
    for it in local.items:
        issues.add(f"{scope}: {it['scope']}", it["message"])
    return entry, final


def _weeks_section(rt: Any, cfg: FundConfig, book: Any, records: Sequence[Any],
                   shadow_records: Sequence[Any], issues: _Issues, full_weeks: int,
                   full_research_weeks: int = DEFAULT_FULL_RESEARCH_WEEKS,
                   names: dict[str, str] | None = None
                   ) -> tuple[list[dict[str, Any]], dict[date, Any]]:
    weeks = issues.attempt("Semanas do livro", book.list_weeks, []) if book is not None else []
    full_set = set(weeks[-full_weeks:]) if full_weeks > 0 else set()
    notes_set = set(weeks[-full_research_weeks:]) if full_research_weeks > 0 else set()
    out: list[dict[str, Any]] = []
    finals: dict[date, Any] = {}
    prev_final = None
    for week in weeks:
        entry, final = _week_entry(rt, cfg, book, week, week in full_set, prev_final, records,
                                   shadow_records, issues, notes_detail=week in notes_set,
                                   names=names)
        finals[week] = final
        if final is not None:
            prev_final = final
        out.append(entry)
    return out, finals


# ==========================================================
# Dia mais recente e risco consolidado
# ==========================================================

def _latest_day(records: Sequence[Any], shadow_records: Sequence[Any],
                finals: Mapping[date, Any], cfg: FundConfig) -> dict[str, Any] | None:
    if not records:
        return None
    from ..research.commentary import period_returns

    rec = records[-1]
    history = list(records[:-1])
    live = finals.get(rec.live_book_week) if rec.live_book_week else None
    targets = {t.issuer_id: t for t in (live.positions if live is not None else [])}
    positions = []
    for p in sorted(rec.positions, key=lambda x: (-abs(x.weight), x.issuer_id)):
        d = p.model_dump(mode="json")
        t = targets.get(p.issuer_id)
        d.update({
            "name": t.name if t else None, "country": t.country if t else None,
            "sector": t.sector if t else None,
            "line_type": t.line_type.value if t else None,
            "target_weight": t.weight if t else None,
            "drift": (p.weight - t.weight) if t else None,
            "squeeze_bucket": t.squeeze_bucket if t else None,
            "squeeze_score": t.squeeze_score if t else None,
            "borrow_fee_annual": t.borrow_fee_annual if t else None,
            "days_to_liquidate": _liq_days(t, cfg) if t else None,
            "pct_adtv": t.pct_adtv if t else None, "adtv_usd": t.adtv_usd if t else None,
            "beta": t.beta if t else None, "alpha_z": t.alpha_z if t else None,
            "view_score": t.view_score if t else None,
            "risk_contribution_ex_ante": t.risk_contribution if t else None,
        })
        positions.append(d)
    attribution: dict[str, list[dict[str, Any]]] = {}
    for a in rec.attribution:
        attribution.setdefault(a.group, []).append(
            {"name": a.name, "pnl_usd": a.pnl_usd, "contribution": a.contribution})
    for g in attribution:
        attribution[g].sort(key=lambda x: (-x["pnl_usd"], x["name"]))
    risk = rec.risk.model_dump(mode="json")
    risk["exposures"] = _exposure_rows(rec.risk.exposures, daily=True)
    shadow_same = next((s for s in shadow_records if s.date == rec.date), None)
    return {
        "date": rec.date, "fund_name": rec.fund_name, "nav_start": rec.nav_start_usd,
        "nav_end": rec.nav_end_usd, "pnl": rec.pnl_usd, "ret": rec.ret,
        "pnl_components": dict(rec.pnl_components),
        "period": period_returns(rec, history),
        "risk": risk, "ladder_stage": ladder_stage(rec.risk.drawdown, cfg),
        "positions": positions, "attribution": attribution, "alerts": list(rec.alerts),
        "live_book_week": rec.live_book_week, "approval_hash": rec.approval_hash,
        "record_hash": rec.record_hash, "prev_record_hash": rec.prev_record_hash,
        "input_hashes": dict(rec.input_hashes), "is_synthetic": rec.is_synthetic,
        "data_notice": rec.data_notice, "track_record_type": rec.track_record_type,
        "shadow": _record_compact(shadow_same) if shadow_same is not None else None,
    }


#: Gate de compliance que cobre cada verificação do painel (``None``: limite do mandato sem gate
#: próprio, acompanhado só aqui). Só define a severidade exibida; o status segue :func:`_over`.
CHECK_GATES: dict[str, tuple[str | None, str | None]] = {
    "vol_ex_ante": ("VOL_MAX / VOL_MIN", "HARD"), "net": ("NET_EXPOSURE", "HARD"),
    "beta": ("BETA", "HARD"), "gross_max": ("GROSS_MAX", "HARD"),
    "gross_min": ("GROSS_MIN", "SOFT"), "country_net": ("COUNTRY_NET", "HARD"),
    "sector_net": ("SECTOR_NET", "HARD"), "style": ("STYLE", "SOFT"),
    "theme_net": ("THEME_NET", "HARD"), "commodity_beta": ("COMMODITY", "SOFT"),
    "name_long_max": ("NAME_LONG_MAX", "HARD"), "name_short_max": ("NAME_SHORT_MAX", "HARD"),
    "name_short_medium_max": ("SQUEEZE_MEDIUM_CAP", "HARD"),
    "squeeze_high": ("SQUEEZE_HIGH", "HARD"), "liq_days_long": ("LIQ_DAYS_LONG", "HARD"),
    "liq_days_short": ("LIQ_DAYS_SHORT", "HARD"),
    "factor_risk_share": ("FACTOR_RISK_SHARE", "SOFT"),
    "single_name_risk": ("SINGLE_NAME_RISK", "SOFT"),
    "country_gap_stress": ("COUNTRY_GAP_STRESS", "SOFT"), "borrow_fee": ("BORROW_FEE", "HARD"),
}
#: Verificações de PISO (o valor precisa ficar acima do limite): sem "uso do limite".
FLOOR_CHECKS = frozenset({"gross_min", "liquidez_3d", "liquidez_5d"})


def _check(cid: str, label: str, basis: str, value: Any, limit: Any, unit: str, status: str,
           detail: str = "", utilization: float | None = None, *,
           subject: Mapping[str, Any] | None = None) -> dict[str, Any]:
    """Uma verificação de limite. Teto: ``utilization`` = |valor| / |limite|. Piso
    (:data:`FLOOR_CHECKS`): ``utilization`` é ``None`` e ``floor``/``shortfall`` (quanto falta
    para o piso, ≥ 0) e ``headroom`` (valor − piso) descrevem a distância ao limite."""
    floor = cid in FLOOR_CHECKS
    v, lim = _num(value), _num(limit)
    if floor:
        utilization = None
    elif utilization is None and not isinstance(limit, list):
        if v is not None and lim not in (None, 0.0):
            utilization = abs(v) / abs(lim)
    gate, severity = CHECK_GATES.get(cid, (None, None))
    out = {"id": cid, "label": label, "basis": basis, "value": value, "limit": limit,
           "unit": unit, "status": status, "detail": detail, "utilization": utilization,
           "floor": floor, "gate": gate, "severity": severity,
           "subject": dict(subject) if subject else None}
    if floor:
        ok = v is not None and lim is not None
        out["shortfall"] = max(0.0, lim - v) if ok else None
        out["headroom"] = v - lim if ok else None
    return out


def _over(value: float | None, limit: float | None, *, daily: bool, hard: bool) -> str:
    """Status de um teto: ``excesso`` só para limite HARD na decisão (ex-ante); no registro
    diário (carteira com drift) o excesso é ``alerta`` — o código reequilibra no próximo
    rebalanceamento, como os gatilhos SOFT do monitor de risco."""
    if value is None or limit is None:
        return "n/d"
    if value > limit + LIMIT_TOL:
        return "excesso" if hard and not daily else "alerta"
    return "ok"


def _under(value: float | None, floor: float | None, *, daily: bool) -> str:
    """Status de um piso SOFT/sem gate: abaixo do piso é ``alerta`` (``info`` no diário)."""
    if value is None or floor is None:
        return "n/d"
    if value < floor - LIMIT_TOL:
        return "info" if daily else "alerta"
    return "ok"


def _worst_exposure(lines: Sequence[Any], group: str, prefix: str | None = None
                    ) -> tuple[Any | None, float | None]:
    worst, util = None, None
    for e in lines:
        if e.group != group or _num(e.limit) in (None, 0.0) or _num(e.net) is None:
            continue
        if prefix is not None and not str(e.name).startswith(prefix):
            continue
        u = abs(float(e.net)) / float(e.limit)
        if util is None or u > util:
            worst, util = e, u
    return worst, util


def _util_txt(util: float) -> str:
    """Uso do limite em texto: 2 casas acima de 100% (para "100,02%" não virar "100,0%")."""
    return fmt_pct(util, 2 if util > 1.0 + LIMIT_TOL else 1)


EXPOSURE_CHECKS = (
    ("country", None, "country_net", "Net por país (pior)", True),
    ("sector", None, "sector_net", "Net por setor (pior)", True),
    ("style", None, "style", "Exposição a estilo (pior)", False),
    ("market", "tema:", "theme_net", "Net por tema (pior)", True),
    ("market", "commodity:", "commodity_beta", "Sensibilidade a commodity (pior, Σ w·β)", False),
)


def _limit_checks(cfg: FundConfig, rec: Any | None, proposal: Any | None) -> list[dict]:
    """Risco vigente × mandato, em código.

    Base: o último registro diário (carteira com drift) quando existe; senão o ex-ante da
    decisão. Liquidez, stress, contribuições ao risco e aluguel vêm sempre do ex-ante da decisão
    vigente. Status: ``ok`` | ``info`` | ``alerta`` | ``excesso`` | ``n/d``.
    """
    rk, lq = cfg.risk, cfg.liquidity
    checks: list[dict[str, Any]] = []
    dr = rec.risk if rec is not None else None
    pr = proposal.risk if proposal is not None else None
    d_basis = f"diário de {rec.date:%d/%m/%Y}" if rec is not None else ""
    p_basis = (f"ex-ante na decisão de {proposal.week:%d/%m/%Y}"
               if proposal is not None else "")
    daily = dr is not None
    basis = d_basis if daily else p_basis
    src = dr if daily else pr
    if src is None:
        return checks

    def pick(name: str) -> float | None:
        return _num(getattr(src, name, None))

    band = [rk.vol_band_min, rk.vol_band_max]
    vol = pick("ex_ante_vol")
    if vol is None:
        st = "n/d"
    elif vol > rk.vol_band_max + LIMIT_TOL:
        st = "alerta" if daily else "excesso"
    elif vol < rk.vol_band_min - LIMIT_TOL:
        st = "info" if daily else "alerta"
    else:
        st = "ok"
    checks.append(_check("vol_ex_ante", "Vol ex-ante vs. banda do mandato", basis, vol, band,
                         "pct", st, f"meta {fmt_pct(rk.vol_target_annual)}",
                         vol / rk.vol_band_max if vol is not None else None))
    if daily:
        rv = _num(dr.realized_vol_21d)
        st = ("n/d" if rv is None else "alerta" if rv > rk.vol_band_max + LIMIT_TOL
              else "info" if rv < rk.vol_band_min - LIMIT_TOL else "ok")
        checks.append(_check("vol_realizada_21d", "Vol realizada 21d vs. banda", d_basis, rv,
                             band, "pct", st, "histórico insuficiente" if rv is None else "",
                             rv / rk.vol_band_max if rv is not None else None))
    net = pick("net")
    checks.append(_check("net", "Exposição líquida (|net|)", basis, net,
                         rk.net_exposure_max_abs, "pct",
                         _over(abs(net) if net is not None else None, rk.net_exposure_max_abs,
                               daily=daily, hard=True)))
    beta = pick("beta")
    checks.append(_check("beta", "Beta previsto (|β|)", basis, beta, rk.beta_max_abs, "x",
                         _over(abs(beta) if beta is not None else None, rk.beta_max_abs,
                               daily=daily, hard=True)))
    gross = pick("gross")
    checks.append(_check("gross_max", "Gross máximo", basis, gross, rk.gross_max, "pct",
                         _over(gross, rk.gross_max, daily=daily, hard=True)))
    checks.append(_check("gross_min", "Gross mínimo (piso)", basis, gross, rk.gross_min, "pct",
                         _under(gross, rk.gross_min, daily=daily),
                         "pode refletir a escada de drawdown"))
    var = pick("var_1d_99")
    checks.append(_check("var_1d", f"VaR 1d ({fmt_pct(rk.var_confidence, 0)})", basis, var,
                         rk.var_1d_max, "pct", _over(var, rk.var_1d_max, daily=daily,
                                                     hard=False)))
    es = pick("es_1d_99")
    checks.append(_check("es_1d", f"ES 1d ({fmt_pct(rk.var_confidence, 0)})", basis, es,
                         rk.es_1d_max, "pct", _over(es, rk.es_1d_max, daily=daily, hard=False)))
    if daily:
        dd = _num(dr.drawdown)
        stage = ladder_stage(dd, cfg)
        st = {"normal": "ok", "soft_stop": "alerta", "hard_stop": "excesso",
              "stop_out": "excesso"}.get(stage, "n/d")
        checks.append(_check("drawdown", "Drawdown vs. escada do mandato", d_basis, dd,
                             [cfg.drawdown.soft_stop, cfg.drawdown.hard_stop,
                              cfg.drawdown.stop_out], "pct", st, STAGE_PT.get(stage, stage),
                             dd / cfg.drawdown.soft_stop if dd is not None else None))
    lines = list(src.exposures)
    p_lines = list(pr.exposures) if pr is not None else []
    for group, prefix, cid, label, hard in EXPOSURE_CHECKS:
        worst, util = _worst_exposure(lines, group, prefix)
        g_daily = daily
        if worst is None and p_lines and daily:
            # O registro diário não traz tema/commodity: usa o ex-ante da decisão.
            worst, util = _worst_exposure(p_lines, group, prefix)
            g_daily = False
        if worst is None or util is None:
            continue
        st = _over(util, 1.0, daily=g_daily, hard=hard)
        checks.append(_check(cid, label, d_basis if g_daily else p_basis, worst.net, worst.limit,
                             "x" if group == "style" else "pct", st,
                             f"{_expo_label(group, worst.name)}: {_util_txt(util)} do limite",
                             util, subject={"group": group, "name": worst.name}))
    shares = rk.country_gross_share_max
    if shares and gross:
        worst_name, worst_ratio, worst_val = None, None, None
        for e in lines:
            lim = shares.get(e.name)
            if e.group != "country" or lim is None or lim <= 0:
                continue
            share = float(e.gross) / gross
            ratio = share / lim
            if worst_ratio is None or ratio > worst_ratio:
                worst_name, worst_ratio, worst_val = e.name, ratio, share
        if worst_name is not None:
            # Sem gate de compliance (só restrição do otimizador): nunca "excesso".
            checks.append(_check("country_gross_share", "Fatia do gross por país (pior)", basis,
                                 worst_val, shares[worst_name], "pct",
                                 _over(worst_ratio, 1.0, daily=daily, hard=False),
                                 f"{worst_name}: {_util_txt(worst_ratio)} do limite",
                                 worst_ratio, subject={"group": "country", "name": worst_name}))
    med_cap = rk.max_short_weight * cfg.squeeze.medium_short_cap_multiplier
    buckets = ({t.issuer_id: t.squeeze_bucket for t in proposal.positions
                if t.side.value == "SHORT"} if proposal is not None else {})
    if daily and rec.positions:
        longs = [p.weight for p in rec.positions if p.weight > 0]
        shorts = [-p.weight for p in rec.positions if p.weight < 0]
        if longs:
            checks.append(_check("name_long_max", "Maior posição long", d_basis, max(longs),
                                 rk.max_long_weight, "pct",
                                 _over(max(longs), rk.max_long_weight, daily=True, hard=True)))
        if shorts:
            checks.append(_check("name_short_max", "Maior posição short (|w|)", d_basis,
                                 max(shorts), rk.max_short_weight, "pct",
                                 _over(max(shorts), rk.max_short_weight, daily=True,
                                       hard=True)))
        med = [-p.weight for p in rec.positions
               if p.weight < 0 and buckets.get(p.issuer_id, "NA") in ("MEDIUM", "NA")]
        if med:
            checks.append(_check("name_short_medium_max",
                                 "Maior short com squeeze MÉDIO/sem dado (|w|)", d_basis,
                                 max(med), med_cap, "pct",
                                 _over(max(med), med_cap, daily=True, hard=True),
                                 f"teto por nome × {cfg.squeeze.medium_short_cap_multiplier:g}"
                                 .replace(".", ",") + " (faixa da decisão)"))
        n_high = int(rec.risk.squeeze_high_shorts)
        checks.append(_check("squeeze_high", "Shorts com squeeze ALTO", d_basis, n_high, 0,
                             "count", "alerta" if n_high > 0 else "ok",
                             "reavaliar/reduzir no próximo rebalanceamento" if n_high else ""))
        liq = _num(rec.risk.pct_gross_liquid_1d)
        checks.append(_check("liquidez_1d", "Gross liquidável em 1 dia", d_basis, liq, None,
                             "pct", "info" if liq is not None else "n/d",
                             "registro diário (participação dos longs no ADTV agregado do "
                             "emissor); pisos de 3 e 5 dias abaixo"))
        mdl = _num(rec.risk.max_days_to_liquidate)
        checks.append(_check("liq_days_daily", "Dias para liquidar, pior nome (carteira com "
                             "drift)", d_basis, mdl, None, "days",
                             "info" if mdl is not None else "n/d",
                             f"registro diário: todas as posições a "
                             f"{fmt_pct(lq.participation_rate, 0)} do ADTV agregado do emissor;"
                             " os limites por ponta usam o ex-ante da decisão"))
    elif proposal is not None and proposal.positions:
        longs = [t.weight for t in proposal.positions if t.weight > 0]
        shorts = [-t.weight for t in proposal.positions if t.weight < 0]
        if longs:
            checks.append(_check("name_long_max", "Maior posição long", p_basis, max(longs),
                                 rk.max_long_weight, "pct",
                                 _over(max(longs), rk.max_long_weight, daily=False, hard=True)))
        if shorts:
            checks.append(_check("name_short_max", "Maior posição short (|w|)", p_basis,
                                 max(shorts), rk.max_short_weight, "pct",
                                 _over(max(shorts), rk.max_short_weight, daily=False,
                                       hard=True)))
        med = [-t.weight for t in proposal.positions
               if t.side.value == "SHORT" and t.squeeze_bucket in ("MEDIUM", "NA")]
        if med:
            checks.append(_check("name_short_medium_max",
                                 "Maior short com squeeze MÉDIO/sem dado (|w|)", p_basis,
                                 max(med), med_cap, "pct",
                                 _over(max(med), med_cap, daily=False, hard=True),
                                 f"teto por nome × {cfg.squeeze.medium_short_cap_multiplier:g}"
                                 .replace(".", ",")))
        n_high = sum(1 for t in proposal.positions
                     if t.side.value == "SHORT" and t.squeeze_bucket == "HIGH")
        checks.append(_check("squeeze_high", "Shorts com squeeze ALTO", p_basis, n_high, 0,
                             "count", "excesso" if n_high > 0 else "ok"))
    if proposal is not None:
        liq = _liquidity_by_side(proposal.positions, cfg)
        gates = {c.check_id: c for c in proposal.compliance}
        for side, cid, label in (("LONG", "liq_days_long", "Dias para liquidar (long)"),
                                 ("SHORT", "liq_days_short", "Dias para liquidar (short)")):
            s = liq[side]
            if not s["n"]:
                continue
            part = f"a {fmt_pct(s['participation'], 0)} do ADTV"
            gate = gates.get(f"LIQ_DAYS_{side}")
            gv = _num(gate.value) if gate is not None else None
            if gate is not None and gv is not None:
                # O gate de compliance é a fonte: mesma conta, mesma participação por ponta.
                checks.append(_check(cid, label, p_basis, gv, s["limit"], "days",
                                     "ok" if gate.passed else "excesso",
                                     f"{part} (gate {gate.check_id})"))
            else:
                checks.append(_check(cid, label, p_basis, s["max_days"], s["limit"], "days",
                                     _over(s["max_days"], s["limit"], daily=False, hard=True),
                                     part + (f"; {s['n_missing']} posição(ões) sem ADTV"
                                             if s["n_missing"] else "")))
        for h, cid, floor in ((3, "liquidez_3d", lq.min_gross_liquid_3d),
                              (5, "liquidez_5d", lq.min_gross_liquid_5d)):
            v = liq[f"liquid_{h}d"]
            checks.append(_check(cid, f"Gross liquidável em {h} dias (piso)", p_basis, v, floor,
                                 "pct", _under(v, floor, daily=False),
                                 "participação do mandato por ponta"
                                 + (f"; {liq['n_missing_adtv']} posição(ões) sem ADTV ⇒ n/d"
                                    if v is None and liq["n_missing_adtv"] else "")))
        frs = _num(pr.factor_risk_share)
        checks.append(_check("factor_risk_share", "Fração do risco vinda de fatores", p_basis,
                             frs, rk.max_factor_risk_share, "pct",
                             _over(frs, rk.max_factor_risk_share, daily=False, hard=False)))
        tops = [v for v in (_num(x) for x in pr.top_risk_contributors.values()) if v is not None]
        tops += [v for v in (_num(t.risk_contribution) for t in proposal.positions)
                 if v is not None]
        if tops:
            checks.append(_check("single_name_risk", "Maior contribuição de um nome ao risco",
                                 p_basis, max(tops), rk.max_single_name_risk_share, "pct",
                                 _over(max(tops), rk.max_single_name_risk_share, daily=False,
                                       hard=False)))
        gaps = [(k, v) for k, v in pr.stress_tests.items()
                if k.startswith("Gap ") and _num(v) is not None]
        if gaps:
            k, v = min(gaps, key=lambda kv: kv[1])
            loss = max(0.0, -float(v))
            checks.append(_check("country_gap_stress", "Pior gap de país (cenário)", p_basis,
                                 v, -rk.country_stress_max_loss, "pct",
                                 _over(loss, rk.country_stress_max_loss, daily=False,
                                       hard=False),
                                 k, loss / rk.country_stress_max_loss
                                 if rk.country_stress_max_loss else None))
        fees = [v for t in proposal.positions if t.side.value == "SHORT"
                and (v := _num(t.borrow_fee_annual)) is not None]
        if fees:
            checks.append(_check("borrow_fee", "Maior taxa de aluguel (shorts)", p_basis,
                                 max(fees), cfg.shorting.max_borrow_fee, "pct",
                                 _over(max(fees), cfg.shorting.max_borrow_fee, daily=False,
                                       hard=True)))
    return checks


def _risk_section(cfg: FundConfig, latest_rec: Any | None, live: Any | None,
                  live_week: date | None, executed: bool) -> dict[str, Any]:
    if latest_rec is not None:
        note = (f"Carteira efetivada (semana de {live_week:%d/%m/%Y}) marcada em "
                f"{latest_rec.date:%d/%m/%Y}: risco diário com drift; liquidez, stress e "
                "contribuições ex-ante da decisão." if live_week else
                f"Registro diário de {latest_rec.date:%d/%m/%Y}.")
    elif live is not None:
        note = (f"Carteira decidida em {live.week:%d/%m/%Y}"
                + ("" if executed else ", ainda sem registro diário (execução no fechamento)")
                + ": risco ex-ante da decisão.")
    else:
        note = "Sem carteira decidida: nada a medir."
    checks = _limit_checks(cfg, latest_rec, live)
    counts = Counter(c["status"] for c in checks)
    names = {t.issuer_id: t.name for t in (live.positions if live is not None else [])}
    out: dict[str, Any] = {
        "basis_note": note, "as_of_date": latest_rec.date if latest_rec is not None else None,
        "live_week": live_week, "executed": executed,
        "limit_checks": checks,
        "summary": {k: int(counts.get(k, 0)) for k in ("ok", "alerta", "excesso", "n/d",
                                                       "info")},
        "daily": None, "ex_ante": None, "liquidity_by_side": None, "squeeze_shorts": [],
        "concentration": None,
    }
    if latest_rec is not None:
        d = latest_rec.risk.model_dump(mode="json")
        d["exposures"] = _exposure_rows(latest_rec.risk.exposures, daily=True)
        out["daily"] = d
    if live is not None:
        out["ex_ante"] = _risk_summary(live.risk, names)
        out["liquidity_by_side"] = _liquidity_by_side(live.positions, cfg)
        targets = {t.issuer_id: t for t in live.positions}
        if latest_rec is not None:
            shorts = [(p.issuer_id, p.ticker, p.weight) for p in latest_rec.positions
                      if p.side.value == "SHORT"]
        else:
            shorts = [(t.issuer_id, t.execution_ticker, t.weight) for t in live.positions
                      if t.side.value == "SHORT"]
        order = {"HIGH": 0, "MEDIUM": 1, "LOW": 2, "NA": 3}
        rows = []
        for iid, ticker, w in shorts:
            t = targets.get(iid)
            rows.append({"issuer_id": iid, "name": t.name if t else None, "ticker": ticker,
                         "weight": w, "bucket": t.squeeze_bucket if t else "NA",
                         "score": t.squeeze_score if t else None,
                         "borrow_fee_annual": t.borrow_fee_annual if t else None,
                         "days_to_liquidate": _liq_days(t, cfg) if t else None,
                         "pct_adtv": t.pct_adtv if t else None})
        out["squeeze_shorts"] = sorted(rows, key=lambda r: (
            order.get(r["bucket"], 4), -(_num(r["score"]) or -1.0), r["issuer_id"]))
    weights = ([(p.issuer_id, p.weight) for p in latest_rec.positions]
               if latest_rec is not None and latest_rec.positions else
               [(t.issuer_id, t.weight) for t in (live.positions if live is not None else [])])
    if weights:
        longs = sorted((w for w in weights if w[1] > 0), key=lambda x: (-x[1], x[0]))
        shorts_w = sorted((w for w in weights if w[1] < 0), key=lambda x: (x[1], x[0]))
        gross = sum(abs(w) for _, w in weights)
        out["concentration"] = {
            "basis": "diário" if latest_rec is not None and latest_rec.positions else "ex-ante",
            "n_long": len(longs), "n_short": len(shorts_w), "gross": gross,
            "top5_long": sum(w for _, w in longs[:5]) if longs else None,
            "top5_short": sum(w for _, w in shorts_w[:5]) if shorts_w else None,
            "top10_gross_share": (sum(abs(w) for _, w in sorted(
                weights, key=lambda x: (-abs(x[1]), x[0]))[:10]) / gross) if gross else None,
            "largest_long": ({"issuer_id": longs[0][0], "name": names.get(longs[0][0]),
                              "weight": longs[0][1]} if longs else None),
            "largest_short": ({"issuer_id": shorts_w[0][0], "name": names.get(shorts_w[0][0]),
                               "weight": shorts_w[0][1]} if shorts_w else None),
            "effective_n_ex_ante": live.risk.effective_n if live is not None else None,
        }
    return out


# ==========================================================
# Relatórios diários, monitor de risco, backtests e auditoria
# ==========================================================

def _commentary(md: str | None, folder: Path, rec: Any | None, history: Sequence[Any],
                cfg: FundConfig, issues: _Issues) -> dict[str, Any] | None:
    from ..ui.data import extract_section

    section = extract_section(md, COMMENTARY_SECTION) if md else None
    source = "relatório diário publicado"
    found_issues: list[str] = []
    if not section and rec is not None and (folder / "comentario.json").is_file():
        from ..ui.data import commentary_for

        c = issues.attempt(f"Comentário {folder.name}",
                           lambda: commentary_for(folder.parent.parent, rec, history, cfg))
        if c is None or not c.markdown:
            return None
        section, source, found_issues = c.markdown, c.source, list(c.issues)
    if not section:
        return None
    prov = _PROVENANCE_RE.findall(section)
    provenance = prov[-1] if prov else None
    minds = _MIND_RE.findall(provenance or "")
    return {"markdown": section, "source": source, "provenance": provenance,
            "ai": bool(provenance and "[IA]" in provenance),
            "mind": minds[-1] if minds else None, "issues": found_issues}


def _daily_reports(rt: Any, cfg: FundConfig, records: Sequence[Any], issues: _Issues,
                   limit: int) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    from ..ui.data import list_reports

    root = Path(rt.reports_root)
    reports = issues.attempt("Relatórios publicados", lambda: list_reports(root), [])
    index = [{"kind": r.kind, "date": r.key, "has_md": r.md is not None,
              "has_html": r.html is not None,
              "md_sha256": _sha256_file(r.md) if r.md is not None else None}
             for r in reports]
    by_date = {r.date: r for r in records}
    daily = [r for r in reports if r.kind == "daily"]
    report_dates = {r.key for r in daily}
    # Registros com comentário validado ainda não publicado também aparecem.
    pending = [r for r in records if r.date not in report_dates
               and (root / "daily" / r.date.isoformat() / "comentario.json").is_file()]
    items: list[tuple[date, Path, Path | None, Path | None]] = [
        (r.key, r.folder, r.md, r.html) for r in daily]
    items += [(r.date, root / "daily" / r.date.isoformat(), None, None) for r in pending]
    items.sort(key=lambda x: x[0], reverse=True)
    out = []
    for d, folder, md_path, html_path in items[:max(limit, 0)]:
        md = _read_text(md_path) if md_path is not None else None
        rec = by_date.get(d)
        history = [r for r in records if r.date < d]
        out.append({
            "date": d, "published": md is not None, "has_html": html_path is not None,
            "report_markdown": md, "report_sha256": _sha256_file(md_path) if md_path else None,
            "commentary": _commentary(md, folder, rec, history, cfg, issues),
            "record_hash": rec.record_hash if rec is not None else None,
            "nav_end": rec.nav_end_usd if rec is not None else None,
            "ret": rec.ret if rec is not None else None,
        })
    return out, index


def _risk_run_summary(raw: Any) -> dict[str, Any] | None:
    """Resumo de uma execução do monitor (``risco_<HHMM>.json``): valores copiados do JSON
    gravado pelo código; só a contagem de gatilhos por nível é feita aqui."""
    if not isinstance(raw, dict):
        return None

    def sub(key: str) -> dict[str, Any]:
        v = raw.get(key)
        return v if isinstance(v, dict) else {}

    nav, dd, live, ks = sub("nav"), sub("drawdown"), sub("intradiario"), sub("kill_switch")
    gat = [g for g in (raw.get("gatilhos") or []) if isinstance(g, dict)]
    levels = Counter(str(g.get("nivel")) for g in gat)
    return {
        "gerado_em": raw.get("gerado_em"), "data": raw.get("data"), "modo": raw.get("modo"),
        "status": raw.get("status"), "intradiario": bool(live),
        "nav_fechamento_usd": nav.get("fechamento_usd"), "retorno_dia": nav.get("retorno_dia"),
        "drawdown_fechamento": dd.get("fechamento"), "estagio": dd.get("estagio"),
        "nav_estimado_usd": live.get("nav_estimado_usd"),
        "pnl_pct_nav": live.get("pnl_pct_nav"),
        "drawdown_estimado": live.get("drawdown_estimado"),
        "estagio_estimado": live.get("estagio_estimado"),
        "cobertura_gross": live.get("cobertura_gross"),
        "n_gatilhos": {lv: int(levels.get(lv, 0)) for lv in ("HARD", "SOFT", "INFO")},
        "gatilhos": [str(g.get("codigo")) for g in gat],
        "kill_switch_ativo": ks.get("ativo"),
        "motivo_kill_switch": raw.get("motivo_kill_switch"),
    }


def _risk_monitor(rt: Any, issues: _Issues, limit: int, full_runs: int) -> dict[str, Any]:
    """Saídas do monitor de risco (``reports/risk/<data>/risco_<HHMM>.{json,md}``).

    Uma execução = um par ``.json``/``.md`` com o mesmo nome-base. As ``full_runs`` execuções
    mais recentes vêm completas (JSON e Markdown); as anteriores só com o resumo (``timeline``),
    para o painel não crescer sem limite com o monitor intradiário.
    """
    root = Path(rt.reports_root) / "risk"
    if not root.is_dir():
        return {"available": False, "latest": None, "runs": [], "timeline": []}
    groups: dict[str, list[Path]] = {}
    for path in sorted(root.rglob("*")):
        if not path.is_file() or path.suffix.lower() not in (".json", ".md"):
            continue
        rel = path.relative_to(root)
        key = rel.parts[0] if len(rel.parts) > 1 else ""
        groups.setdefault(key, []).append(path)
    runs: list[dict[str, Any]] = []
    timeline: list[dict[str, Any]] = []
    latest: dict[str, Any] | None = None
    n_full = 0
    for key in sorted(groups, reverse=True)[:max(limit, 0)]:
        base = root / key if key else root
        stems: dict[str, list[Path]] = {}
        for path in groups[key]:
            rel = path.relative_to(base).as_posix()
            stems.setdefault(rel[: -len(path.suffix)], []).append(path)
        files = []
        for stem in sorted(stems, reverse=True):
            full = n_full < max(full_runs, 0)
            n_full += 1
            md_rel = next((p.relative_to(base).as_posix() for p in stems[stem]
                           if p.suffix.lower() == ".md"), None)
            for path in sorted(stems[stem], key=lambda p: (p.suffix.lower() != ".json", p.name)):
                rel = path.relative_to(base).as_posix()
                entry: dict[str, Any] = {"name": rel, "kind": path.suffix.lower().lstrip("."),
                                         "sha256": _sha256_file(path), "full": full}
                try:
                    size: int | None = path.stat().st_size
                except OSError:
                    size = None
                entry["bytes"] = size
                if size is not None and size > MAX_RISK_FILE_BYTES:
                    entry["omitted"] = "arquivo grande demais para o painel"
                elif entry["kind"] == "json":
                    raw = issues.attempt(f"Monitor de risco {key}/{rel}",
                                         lambda path=path: _read_json(path))
                    summary = _risk_run_summary(raw)
                    entry["summary"] = summary
                    if full:
                        entry["data"] = raw
                    else:
                        entry["omitted"] = "execução antiga: só o resumo (limite do painel)"
                    if summary is not None:
                        timeline.append({"run_key": key or "(raiz)", "file": rel,
                                         "md_file": md_rel, **summary})
                    if latest is None and raw is not None:
                        latest = {"run_key": key or "(raiz)", "file": rel, "md_file": md_rel}
                elif full:
                    entry["text"] = _read_text(path)
                else:
                    entry["omitted"] = "execução antiga: só o resumo (limite do painel)"
                files.append(entry)
        runs.append({"key": key or "(raiz)", "date": key if _WEEK_DIR_RE.match(key) else None,
                     "files": files})
    return {"available": bool(runs), "latest": latest, "runs": runs, "timeline": timeline}


def _round(v: Any) -> float | None:
    """Séries de backtest com ``BACKTEST_SIG_DIGITS`` algarismos significativos (tamanho)."""
    x = _num(v)
    return float(f"{x:.{BACKTEST_SIG_DIGITS}g}") if x is not None else None


def _cell(v: Any) -> Any:
    if v is None or isinstance(v, (str, bool)):
        return v
    return _round(v)


def _columns(df: Any) -> dict[str, list[Any]]:
    return {str(c): [_cell(v) for v in df[c].tolist()] for c in df.columns}


def _read_dated_csv(path: Path, issues: _Issues, scope: str) -> Any:
    """CSV com coluna ``date``: datas inválidas viram NaT e a linha é descartada (com
    apontamento); arquivo ilegível ou sem ``date`` levanta (o chamador transforma em apontamento).
    """
    import pandas as pd

    df = pd.read_csv(path)
    if "date" not in df.columns:
        raise ValueError("coluna 'date' ausente")
    dates = pd.to_datetime(df["date"], errors="coerce")
    bad = int(dates.isna().sum())
    if bad:
        issues.add(scope, f"{bad} linha(s) com data inválida ignorada(s) (arquivo ainda sendo "
                          "gravado ou corrompido).")
    df = df.assign(date=dates).dropna(subset=["date"]).set_index("date").sort_index()
    return df


def _backtest_nav_weekly(d: Any) -> dict[str, list[Any]]:
    """Séries semanais (sexta) do backtest. Custos e aluguel saem com sinal de P&L
    (``cum_cost_pnl``/``cum_borrow_pnl`` ≤ 0): no ``daily.csv`` são magnitudes positivas
    (``ret_net = ret_gross − cost − borrow + financing``). Valor não numérico levanta."""
    import pandas as pd

    nav = d["nav"].astype(float)
    dd = nav / nav.cummax() - 1.0
    ret = d["ret_net"].astype(float) if "ret_net" in d.columns else nav.pct_change()
    rv63 = ret.rolling(63).std(ddof=1) * math.sqrt(252)
    frame = pd.DataFrame({"nav": nav, "drawdown": dd, "realized_vol_63d": rv63})
    for col, key, sign in (("factor_pnl", "cum_factor_pnl", 1.0),
                           ("specific_pnl", "cum_specific_pnl", 1.0),
                           ("financing", "cum_financing", 1.0),
                           ("cost", "cum_cost_pnl", -1.0), ("borrow", "cum_borrow_pnl", -1.0)):
        if col in d.columns:
            frame[key] = sign * d[col].astype(float).cumsum()
    for col in ("gross", "net"):
        if col in d.columns:
            frame[col] = d[col].astype(float)
    wk = frame.resample("W-FRI").last().dropna(how="all")
    series = {"date": [ix.date().isoformat() for ix in wk.index]}
    series.update({c: [_round(v) for v in wk[c].tolist()] for c in wk.columns})
    return series


def _backtest_ic(ic: Any) -> dict[str, Any]:
    import pandas as pd

    summary = {}
    for c in ic.columns:
        s = pd.to_numeric(ic[c], errors="coerce").dropna()
        n = int(len(s))
        sd = float(s.std(ddof=1)) if n > 1 else None
        mean = float(s.mean()) if n else None
        summary[str(c)] = {
            "n": n, "mean": mean, "std": sd,
            "t_stat": (mean / (sd / math.sqrt(n))) if mean is not None and sd else None,
            "pct_positive": float((s > 0).mean()) if n else None}
    cum = ic.apply(pd.to_numeric, errors="coerce").cumsum()
    return {"summary": summary, "cumulative": {
        "date": [ix.date().isoformat() for ix in cum.index],
        **{str(c): [_round(v) for v in cum[c].tolist()] for c in cum.columns}}}


def _backtest_run(run_dir: Path, base: Path, issues: _Issues) -> dict[str, Any] | None:
    import pandas as pd

    scope = f"Backtest {run_dir.name}"
    raw = issues.attempt(f"{scope}: metrics.json", lambda: _read_json(run_dir / "metrics.json"))
    if raw is None:
        return None
    if not isinstance(raw, dict):
        issues.add(f"{scope}: metrics.json",
                   f"conteúdo não é um objeto JSON ({type(raw).__name__}); execução ignorada.")
        return None
    prov = raw.get("provenance") if isinstance(raw.get("provenance"), dict) else {}
    variant = raw.get("variant")
    desc = []
    overrides = raw.get("overrides") if isinstance(raw.get("overrides"), dict) else {}
    for sec, vals in sorted(overrides.items()):
        for k, v in sorted((vals if isinstance(vals, dict) else {}).items()):
            desc.append(f"{sec}.{k} = {v}")
    sw = raw.get("signal_weights") if isinstance(raw.get("signal_weights"), dict) else None
    if sw:
        desc.append("sinais: " + ", ".join(f"{k} {v}" for k, v in sorted(sw.items())))
    rel = run_dir.relative_to(base).as_posix() if run_dir != base else run_dir.name
    notice = str(prov.get("data_notice") or "")
    run: dict[str, Any] = {
        "id": rel,
        "label": (run_dir.name if not variant else f"Variante {variant}"
                  if run_dir.name.lower() in (str(variant).lower(), f"bt_{variant}".lower())
                  else f"Variante {variant} — {run_dir.name}"),
        "variant": variant, "description": "; ".join(desc) or "configuração do mandato",
        "overrides": overrides or None, "signal_weights": sw,
        "metrics": raw.get("metrics") if isinstance(raw.get("metrics"), dict) else {},
        "notes": [str(x) for x in (raw.get("notes") or [])] if isinstance(
            raw.get("notes"), list) else [],
        "provenance": prov, "is_synthetic": SIMULATED_DATA_NOTICE in notice.upper(),
        "files": {n: _sha256_file(run_dir / n) for n in ("metrics.json", "weekly.csv",
                                                         "daily.csv", "ic.csv")
                  if (run_dir / n).is_file()},
        "weekly": None, "nav_weekly": None, "ic": None,
    }
    wpath, dpath, ipath = run_dir / "weekly.csv", run_dir / "daily.csv", run_dir / "ic.csv"
    if wpath.is_file():
        w = issues.attempt(f"{scope}: weekly.csv", lambda: pd.read_csv(wpath))
        if w is not None:
            run["weekly"] = _columns(w.astype(object).where(w.notna(), None))
    if dpath.is_file():
        d = issues.attempt(f"{scope}: daily.csv",
                           lambda: _read_dated_csv(dpath, issues, f"{scope}: daily.csv"))
        if d is not None and "nav" in d.columns:
            run["nav_weekly"] = issues.attempt(f"{scope}: daily.csv (séries semanais)",
                                               lambda: _backtest_nav_weekly(d))
            run["n_daily_obs"] = int(len(d))
    if ipath.is_file():
        ic = issues.attempt(f"{scope}: ic.csv",
                            lambda: _read_dated_csv(ipath, issues, f"{scope}: ic.csv"))
        if ic is not None:
            run["ic"] = issues.attempt(f"{scope}: ic.csv (resumo)", lambda: _backtest_ic(ic))
    return run


def _backtest_documents(base: Path) -> list[dict[str, Any]]:
    """Notas em Markdown da árvore de backtests (ex.: ``CALIBRACAO.md``), até 3 níveis."""
    docs = []
    for path in sorted(base.rglob("*.md")):
        rel = path.relative_to(base)
        if len(rel.parts) > MAX_BACKTEST_DEPTH or not path.is_file():
            continue
        try:
            if path.stat().st_size > MAX_RISK_FILE_BYTES:
                continue
        except OSError:
            continue
        text = _read_text(path)
        if text is not None:
            docs.append({"path": rel.as_posix(), "sha256": _sha256_file(path), "markdown": text})
    return docs


def _backtests(root: Path | None, pattern: str, issues: _Issues) -> dict[str, Any]:
    if root is None or not Path(root).is_dir():
        return {"available": False, "runs": [], "documents": []}
    base = Path(root)
    found: list[Path] = []
    if (base / "metrics.json").is_file():
        found.append(base)
    else:
        for depth in range(1, MAX_BACKTEST_DEPTH + 1):
            glob = "/".join(["*"] * (depth - 1) + [pattern]) if depth > 1 else pattern
            for p in sorted(base.glob(glob)):
                if p.is_dir() and (p / "metrics.json").is_file() and p not in found:
                    found.append(p)
            if found:
                break
    runs = [r for p in found if (r := _backtest_run(p, base, issues)) is not None]
    docs = _backtest_documents(base) if pattern == "*" else []
    return {"available": bool(runs), "runs": sorted(runs, key=lambda r: r["id"]),
            "documents": docs}


def _audit_events(book_root: Path) -> list[Any]:
    """Eventos da trilha (lista vazia se ilegível: :func:`_audit` já aponta o problema)."""
    from ..audit import AuditLog

    try:
        return AuditLog(Path(book_root) / "audit_log.jsonl").events()
    except Exception:  # noqa: BLE001
        return []


def _audit(book_root: Path, book_exists: bool, cfg: FundConfig, tail: int,
           issues: _Issues) -> dict[str, Any]:
    from ..audit import AuditLog

    path = Path(book_root) / "audit_log.jsonl"
    if not book_exists or not path.is_file():
        return {"exists": False, "chain_ok": None, "chain_message": "Trilha ainda não existe.",
                "n_events": 0, "head_hash": None, "by_type": {}, "events": []}
    log = AuditLog(path)
    try:
        events = log.events()
    except Exception as exc:  # noqa: BLE001 - linha corrompida
        issues.add("Trilha de auditoria", f"{type(exc).__name__}: {exc}")
        return {"exists": True, "chain_ok": False, "chain_message": "Trilha ilegível.",
                "n_events": None, "head_hash": None, "by_type": {}, "events": []}
    ok, msg = log.verify_chain()
    tz = ZoneInfo(cfg.fund.timezone)
    return {
        "exists": True, "chain_ok": ok, "chain_message": msg, "n_events": len(events),
        "head_hash": events[-1].event_hash if events else None,
        "first_ts": events[0].ts if events else None,
        "last_ts": events[-1].ts if events else None,
        "by_type": dict(sorted(Counter(e.event_type for e in events).items())),
        "events": [{"seq": e.seq, "ts": e.ts, "ts_local": _local(e.ts, tz),
                    "event_type": e.event_type, "actor": e.actor, "summary": e.summary,
                    "week": e.week, "payload_hash": e.payload_hash, "event_hash": e.event_hash,
                    "prev_hash": e.prev_hash}
                   for e in reversed(events[-tail:] if tail > 0 else [])],
    }


# ==========================================================
# Integridade, status e meta
# ==========================================================

def _integrity(rt: Any, book: Any, book_exists: bool, audit: Mapping[str, Any]
               ) -> dict[str, Any]:
    from .track_record import DAILY_RECORD_EVENT, SHADOW_RECORD_EVENT, TrackRecord

    checks: list[dict[str, Any]] = []

    def add(cid: str, label: str, fn: Callable[[], tuple[bool, list[str]]], ok_msg: str) -> None:
        try:
            ok, msgs = fn()
        except Exception as exc:  # noqa: BLE001
            ok, msgs = False, [f"{type(exc).__name__}: {exc}"]
        checks.append({"id": cid, "label": label, "ok": bool(ok),
                       "messages": [scrub_text(str(m)) for m in (msgs or [ok_msg])]})

    root = Path(rt.book_root)
    if not book_exists:
        checks.append({"id": "livro", "label": "Livro × trilha", "ok": None,
                       "messages": ["Livro ainda não existe (antes da inception)."]})
    else:
        checks.append({"id": "auditoria", "label": "Cadeia da trilha de auditoria",
                       "ok": audit.get("chain_ok"),
                       "messages": [str(audit.get("chain_message") or "")]})
        add("livro", "Livro × trilha (pesquisa, propostas, decisões, efetivações, ledger)",
            book.verify_integrity, "Todos os artefatos conferem com a trilha.")
        for cid, label, sub, event in (
                ("track_record", "Track record do CDP", "track_record", DAILY_RECORD_EVENT),
                ("sombra", "Track record da sombra só-quant", "track_record_shadow",
                 SHADOW_RECORD_EVENT)):
            # Pasta ausente sem eventos na trilha: nada a verificar. Pasta ausente COM eventos
            # (registros removidos) é verificada e acusa o problema.
            if not (root / sub).is_dir() and not (audit.get("by_type") or {}).get(event):
                checks.append({"id": cid, "label": label, "ok": None,
                               "messages": ["Sem registros diários ainda."]})
                continue

            def run(sub=sub, event=event) -> tuple[bool, list[str]]:
                return TrackRecord(root / sub, audit_event=event).verify()

            add(cid, label, run, "Registros íntegros.")
    store = getattr(rt, "store_override", None)
    if store is not None:
        add("dados", "Base de mercado", store.verify_chain, "Base íntegra.")
    elif (Path(rt.market_root) / "base").is_dir():
        add("dados", "Base de mercado (base + incrementos)", lambda: rt.store.verify_chain(),
            "Base e incrementos íntegros.")
    else:
        checks.append({"id": "dados", "label": "Base de mercado", "ok": None,
                       "messages": ["Base de mercado ausente neste ambiente."]})
    return {"ok": _integrity_ok(checks), "checks": checks}


def _integrity_ok(checks: Sequence[Mapping[str, Any]]) -> bool | None:
    """``False`` se alguma verificação falhou; ``True`` só se ao menos uma passou; senão
    ``None`` (nada a verificar ainda — nunca um "OK" sem verificação)."""
    oks = [c.get("ok") for c in checks]
    if any(o is False for o in oks):
        return False
    return True if any(o is True for o in oks) else None


def _path_forms(path: Path) -> list[str]:
    """Grafias possíveis de um caminho gravado num payload da trilha: como dado, absoluto,
    resolvido e cada sufixo relativo (rotina rodando de qualquer pasta ancestral)."""
    forms: list[str] = []
    for p in (path, path.absolute(), path.resolve()):
        forms.append(p.as_posix())
        parts = p.parts
        for i in range(1, len(parts)):
            forms.append(Path(*parts[i:]).as_posix())
    seen: set[str] = set()
    return [f for f in forms if not (f in seen or seen.add(f))]


def _report_payload_ok(folder: Path, hashes: set[str], extra: Mapping[str, Any] | None = None
                       ) -> bool | None:
    """Relatório (``relatorio.md``/``.html``) × payload do evento ``*_REPORT`` da trilha."""
    from ..hashing import sha256_obj

    md, html = folder / "relatorio.md", folder / "relatorio.html"
    if not hashes:
        return None
    if not md.is_file() or not html.is_file():
        return False
    md_sha, html_sha = _sha256_file(md), _sha256_file(html)
    for md_s, html_s in zip(_path_forms(md), _path_forms(html), strict=False):
        payload = {"md": md_s, "html": html_s, "md_sha256": md_sha, "html_sha256": html_sha,
                   **(extra or {})}
        if sha256_obj(payload) in hashes:
            return True
    return False


def _thesis_payload_ok(folder: Path, hashes: set[str], decision: Mapping[str, Any] | None
                       ) -> bool:
    """Tese publicada (``tese_publicada.json`` + ``tese.md``) × payload do evento
    ``WEEKLY_THESIS``: ``{"tese_publicada": sha256, "tese_md": sha256, "proposal_hash",
    "approval_hash", "autoria"}``. Os hashes de vínculo vêm do próprio arquivo (``hashes``:
    ``proposal``/``approval``) ou da decisão exportada. Arquivo publicado sem evento na trilha
    não confere."""
    from ..hashing import sha256_obj

    if not hashes:
        return False
    try:
        raw = _read_json(folder / THESIS_FILE)
    except (OSError, ValueError):
        return False
    if not isinstance(raw, dict):
        return False
    base = {"tese_publicada": _sha256_file(folder / THESIS_FILE),
            "tese_md": _sha256_file(folder / THESIS_MD), "autoria": raw.get("autoria")}
    own = raw.get("hashes") if isinstance(raw.get("hashes"), dict) else {}
    dec = decision or {}
    for ph, ah in ((own.get("proposal"), own.get("approval")),
                   (own.get("proposal_hash"), own.get("approval_hash")),
                   (dec.get("proposal_hash"), dec.get("approval_hash"))):
        if sha256_obj({**base, "proposal_hash": ph, "approval_hash": ah}) in hashes:
            return True
    return False


def _aux_integrity(rt: Any, events: Sequence[Any], weeks: Sequence[dict[str, Any]],
                   daily_reports: Sequence[dict[str, Any]]) -> dict[str, Any]:
    """Artefatos exibidos pelo painel que ``Book.verify_integrity`` não cobre × a trilha:
    ``shadow_quant.json`` (evento ``SHADOW_QUANT``), ``inputs/*.json`` (``WEEKLY_INPUTS``),
    tese publicada (``WEEKLY_THESIS``, ``thesis_verified``), relatório semanal
    (``WEEKLY_REPORT``) e diário (``DAILY_REPORT``). Marca cada seção com ``verified``
    (``True``/``False``/``None`` = sem âncora para conferir)."""
    from ..hashing import sha256_obj

    by: dict[tuple[str, Any], set[str]] = {}
    for ev in events:
        by.setdefault((ev.event_type, ev.week), set()).add(ev.payload_hash)
    root, reports = Path(rt.book_root), Path(rt.reports_root)
    bad: list[str] = []
    n_ok = 0

    def note(ok: bool | None, what: str) -> bool | None:
        nonlocal n_ok
        if ok is True:
            n_ok += 1
        elif ok is False:
            bad.append(what)
        return ok

    for w in weeks:
        week = w["week"]
        wdir = root / week.isoformat()
        spath = wdir / "shadow_quant.json"
        if spath.is_file():
            ok = sha256_obj({"sha256": _sha256_file(spath)}) in by.get(("SHADOW_QUANT", week),
                                                                       set())
            w["shadow_verified"] = note(ok, f"{week.isoformat()}: shadow_quant.json")
            if isinstance(w.get("shadow"), dict):
                w["shadow"]["verified"] = ok
        files = sorted((wdir / "inputs").glob("*.json")) if (wdir / "inputs").is_dir() else []
        anchors = by.get(("WEEKLY_INPUTS", week), set())
        ok_in: bool | None = None
        if files and anchors:
            ok_in = sha256_obj({f.name: _sha256_file(f) for f in files}) in anchors
            note(ok_in, f"{week.isoformat()}: inputs/*.json")
        w["inputs_verified"] = ok_in
        if isinstance(w.get("pm_decision"), dict):
            w["pm_decision"]["verified"] = ok_in
        if isinstance(w.get("research"), dict) and w["research"].get("source") == "entradas":
            w["research"]["verified"] = ok_in
        tdir = wdir / THESIS_DIR
        if (tdir / THESIS_FILE).is_file():
            ok_t = _thesis_payload_ok(tdir, by.get((THESIS_EVENT, week), set()),
                                      w.get("decision") if isinstance(w.get("decision"), dict)
                                      else None)
            w["thesis_verified"] = note(ok_t, f"{week.isoformat()}: tese publicada")
        rep = w.get("report")
        if isinstance(rep, dict) and rep.get("available"):
            ok_r = _report_payload_ok(reports / "weekly" / week.isoformat(),
                                      by.get(("WEEKLY_REPORT", week), set()))
            rep["verified"] = note(ok_r, f"{week.isoformat()}: relatório semanal")
    daily_hashes = by.get(("DAILY_REPORT", None), set())
    n_unknown = 0
    for r in daily_reports:
        if not r.get("published"):
            r["verified"] = None
            continue
        ok_d = _report_payload_ok(reports / "daily" / r["date"].isoformat(), daily_hashes,
                                  {"record": r.get("record_hash"), "commentary_issues": []})
        if ok_d is False:
            # O evento grava também os apontamentos do comentário (desconhecidos aqui):
            # sem casar com a lista vazia, o relatório fica "não verificado", não "falho".
            ok_d = None
            n_unknown += 1
        r["verified"] = note(ok_d, f"{r['date'].isoformat()}: relatório diário")
    msgs = ([f"Não conferem com a trilha: {', '.join(bad)}."] if bad else
            [f"{n_ok} artefato(s) conferem com a trilha."] if n_ok else
            ["Nada a conferir ainda."])
    if n_unknown:
        msgs.append(f"{n_unknown} relatório(s) diário(s) sem conferência possível (evento com "
                    "apontamentos do comentário ou pasta movida).")
    return {"id": "auxiliares",
            "label": "Artefatos auxiliares × trilha (sombra, entradas da mente, tese, "
                     "relatórios)",
            "ok": False if bad else True if n_ok else None, "messages": msgs}


def _market_info(rt: Any, issues: _Issues) -> dict[str, Any]:
    store = getattr(rt, "store_override", None)
    if store is None and not (Path(rt.market_root) / "base").is_dir():
        return {"available": False, "last_date": None, "is_synthetic": False}
    last = issues.attempt("Base de mercado (último pregão)",
                          lambda: (store or rt.store).last_date())
    synthetic = False
    md = getattr(store, "md", None)
    if md is not None:
        synthetic = bool(getattr(md, "is_synthetic", False))
    else:
        from ..ui.data import market_is_synthetic

        synthetic = bool(issues.attempt("Base de mercado (manifesto)",
                                        lambda: market_is_synthetic(Path(rt.market_root)),
                                        False))
    return {"available": True, "last_date": last, "is_synthetic": synthetic}


_AGENDA_DROP = frozenset({"fuso_do_pc", "pc_menos_brasilia_horas", "reinicio"})


def _agenda(rt: Any, now: datetime, book_exists: bool, issues: _Issues) -> dict[str, Any] | None:
    """``cdp agenda`` (o que a rotina deve fazer agora), sem os campos da máquina local."""
    if not book_exists:
        return None
    from .agenda import agenda

    raw = issues.attempt("Agenda operacional", lambda: agenda(rt, now=now))
    if not isinstance(raw, dict):
        return None
    return {k: v for k, v in raw.items() if k not in _AGENDA_DROP}


def _status(rt: Any, cfg: FundConfig, now: datetime, weeks: Sequence[dict[str, Any]],
            records: Sequence[Any], kill: Any, integrity: Mapping[str, Any],
            market: Mapping[str, Any], risk: Mapping[str, Any]) -> dict[str, Any]:
    from ..calendar import dia_de_montagem, is_session, open_markets, week_id
    from ..ui.data import next_events

    tz = ZoneInfo(cfg.fund.timezone)
    local = now.astimezone(tz)
    today = local.date()
    current = week_id(today, cfg)
    by_week = {w["week"]: w for w in weeks}
    cw = by_week.get(current)
    decided = {w["week"] for w in weeks if w["decisions"]}
    last = records[-1] if records else None
    latest_decided = max(decided) if decided else None
    executed_weeks = [w["week"] for w in weeks if w["executed"]]
    lw = by_week.get(latest_decided) if latest_decided else None
    if lw is None:
        phase = ("em_operacao" if records else "aguardando_decisao" if weeks
                 else "pre_inception")
    elif lw.get("state") == "BLOCKED":
        phase = "bloqueada"
    elif not lw["executed"]:
        phase = "decidida_aguardando_execucao"
    else:
        phase = "em_operacao"
    inicio = cfg.fund.inception_date
    events = next_events(now, cfg, decided)
    inaugural: dict[str, Any] | None = None
    phase_label = PHASE_PT[phase]
    if phase == "pre_inception":
        # Data da carteira inaugural: a data de início ou, se ela passou sem decisão, a próxima
        # data de montagem (nunca uma data passada).
        nxt = [e.when.astimezone(tz).date() for e in events
               if not e.overdue and e.label.startswith("Decisão semanal")]
        quando = inicio if today < inicio else (nxt[0] if nxt else None)
        inaugural = {"date": quando, "convention": "ao preço de fechamento"}
        phase_label = (f"Pré-início: carteira inaugural em {quando:%d/%m/%Y}, ao preço de "
                       "fechamento." if quando is not None else
                       "Pré-início: carteira inaugural na próxima data de montagem, ao preço de "
                       "fechamento.")
    dd = float(last.risk.drawdown) if last is not None else None
    stage = ladder_stage(dd, cfg) if last is not None else "desconhecido"
    alerts: list[dict[str, str]] = []
    if kill.active:
        alerts.append({"severity": "error",
                       "text": "Modo somente redução de risco ativo: "
                               f"{kill.reason or 'motivo não informado'}"})
    if integrity.get("ok") is False:
        bad = [c["label"] for c in integrity.get("checks", []) if c["ok"] is False]
        # Só do perfil completo (operação): o perfil publicado não mostra a verificação.
        alerts.append({"severity": "error", "source": "integridade",
                       "text": "Verificação de integridade dos registros com falha: "
                               + ", ".join(bad)})
    for ev in events:
        if ev.overdue:
            alerts.append({"severity": "error",
                           "text": f"{ev.label.replace(' ATRASADA', '')} em atraso (prevista "
                                   f"para {ev.when.astimezone(tz).strftime('%d/%m/%Y %H:%M')})."})
    if lw is not None:
        path = lw.get("path_taken")
        if path and path != "cdp":
            alerts.append({"severity": "warning",
                           "text": f"Semana de {latest_decided.strftime('%d/%m/%Y')} decidida "
                                   "por processo reduzido: "
                                   f"{PATH_ALERT_PT.get(path, PATH_PT.get(path, path))}."})
        for issue in (lw.get("input_issues") or [])[:10]:
            alerts.append({"severity": "warning",
                           "text": f"Pendência nos dados da decisão: {issue}"})
        soft = ((lw.get("proposal") or {}).get("summary") or {}).get("soft_failures") or []
        if soft:
            labels = "; ".join(limit_label_pt(x) for x in soft)
            alerts.append({"severity": "warning",
                           "text": ("Limites de alerta reconhecidos na decisão: " if len(soft) > 1
                                    else "Limite de alerta reconhecido na decisão: ") + labels})
    for c in risk.get("limit_checks", []):
        if c["status"] in ("excesso", "alerta"):
            alerts.append({"severity": "error" if c["status"] == "excesso" else "warning",
                           "text": f"{c['label']}: "
                                   + ("acima do limite" if c["status"] == "excesso"
                                      else "em alerta")
                                   + (f" ({c['detail']})" if c.get("detail") else "")})
    if last is not None:
        # Alertas gravados pelo fechamento diário (liquidez por ponta, squeeze desde a decisão,
        # stops do short, ADTV ausente, limitações de dados): o texto do código, um a um.
        for a in last.alerts:
            alerts.append({"severity": "info" if str(a).startswith("Limitação de dados")
                           else "warning", "source": "fechamento",
                           "text": f"Fechamento de {last.date.strftime('%d/%m/%Y')}: {a}"})
    nav = float(last.nav_end_usd) if last is not None else float(cfg.fund.inception_nav_usd)
    return {
        "now_utc": now.astimezone(UTC).isoformat(), "now_local": local.isoformat(),
        "today": today, "timezone": cfg.fund.timezone,
        "is_session_today": is_session(today, "BVMF"),
        "open_markets_today": open_markets(today),
        "is_rebalance_day": (dia_de_montagem(today, cfg)
                             and not (phase == "pre_inception" and today < inicio)),
        "current_week": current,
        "current_week_status": {
            "exists": cw is not None, "decided": bool(cw and cw["decisions"]),
            "executed": bool(cw and cw["executed"]),
            "decision_mode": ((cw or {}).get("decision") or {}).get("mode"),
            "path_taken": (cw or {}).get("path_taken"),
            "state": (cw or {}).get("state")},
        "phase": phase, "phase_label": phase_label,
        "inaugural": inaugural,
        "kill_switch": {"active": kill.active, "reason": kill.reason, "by": kill.by,
                        "created_at": kill.created_at, "error": kill.error},
        "last_record_date": last.date if last is not None else None,
        "nav_usd": nav,
        "nav_source": "fechamento diário" if last is not None else "PL inicial do mandato",
        "day_ret": last.ret if last is not None else None,
        "drawdown": dd, "realized_vol_21d": last.risk.realized_vol_21d if last else None,
        "ladder_stage": stage, "ladder_stage_label": STAGE_PT.get(stage, stage),
        "latest_decision_week": latest_decided,
        "live_book_week": max(executed_weeks) if executed_weeks else None,
        "market_last_date": market.get("last_date"),
        "integrity": integrity,
        "next_events": [{"label": e.label, "when_utc": e.when.astimezone(UTC).isoformat(),
                         "when_local": e.when.astimezone(tz).isoformat(), "note": e.note,
                         "overdue": e.overdue} for e in events],
        "alerts": alerts,
    }


def _synthetic(records: Sequence[Any], shadow: Sequence[Any], weeks: Sequence[dict[str, Any]],
               market: Mapping[str, Any]) -> tuple[bool, list[str], str | None]:
    found: list[str] = []
    notice = None
    if any(r.is_synthetic for r in records):
        found.append("track record")
        notice = next(r.data_notice for r in records if r.is_synthetic)
    if any(r.is_synthetic for r in shadow):
        found.append("sombra só-quant")
    for w in weeks:
        p = w.get("proposal") or {}
        if p.get("is_synthetic"):
            found.append(f"proposta de {w['week']:%d/%m/%Y}")
            notice = notice or p.get("data_notice")
        if (w.get("research") or {}).get("is_synthetic"):
            found.append(f"pesquisa de {w['week']:%d/%m/%Y}")
        if (w.get("thesis") or {}).get("is_synthetic"):
            found.append(f"tese de {w['week']:%d/%m/%Y}")
    if market.get("is_synthetic"):
        found.append("base de mercado")
    return bool(found), found, notice


def _data_notice(is_synth: bool, notice: str | None, records: Sequence[Any],
                 weeks: Sequence[dict[str, Any]], market: Mapping[str, Any] | None = None
                 ) -> str:
    if is_synth:
        text = notice or "mercado sintético gerado por código."
        if SIMULATED_DATA_NOTICE not in text.upper():
            text = f"{SIMULATED_DATA_NOTICE} — {text}"
        return text
    if records:
        return records[-1].data_notice or REAL_DATA_NOTICE
    for w in reversed(weeks):
        p = w.get("proposal") or {}
        if p.get("data_notice"):
            return str(p["data_notice"])
    real_market = bool(market and market.get("available") and not market.get("is_synthetic"))
    return REAL_DATA_NOTICE if weeks or real_market else EMPTY_DATA_NOTICE


# ==========================================================
# API pública
# ==========================================================

def painel_data(rt: Any, *, now: datetime | None = None, profile: str = "completo",
                max_daily_reports: int = DEFAULT_MAX_DAILY_REPORTS,
                backtest_root: Path | str | None = None, backtest_pattern: str = "*",
                full_weeks: int = DEFAULT_FULL_WEEKS,
                full_research_weeks: int = DEFAULT_FULL_RESEARCH_WEEKS,
                audit_tail: int = DEFAULT_AUDIT_TAIL,
                max_risk_runs: int = DEFAULT_MAX_RISK_RUNS,
                max_risk_full_runs: int = DEFAULT_RISK_FULL_RUNS) -> dict[str, Any]:
    """Retrato JSON determinístico da operação do CDP (somente leitura).

    ``profile="completo"`` (padrão): o retrato inteiro (cópia local e app). ``"publicacao"``:
    o retrato compacto do artifact (``data.json``), derivado do completo por
    :func:`cdp.workflow.painel_publicacao.publicacao` — mesmos números, menos itens e textos.
    ``now`` (com fuso; sem fuso ⇒ UTC) fixa o relógio do painel (padrão: ``rt.now()``).
    ``backtest_root`` (padrão: ``<reports>/backtest``) pode conter um ``metrics.json`` ou
    subpastas de execuções até 3 níveis (``backtest_pattern`` filtra os nomes, ex.:
    ``"bt_*"``; com o padrão ``"*"`` as notas ``*.md`` da árvore também entram).
    Semanas mais antigas que as ``full_weeks`` mais recentes vêm resumidas; as notas por
    emissor da pesquisa só vêm nas ``full_research_weeks`` mais recentes. O monitor de risco
    traz as pastas das ``max_risk_runs`` datas mais recentes, com JSON/Markdown completos só
    nas ``max_risk_full_runs`` execuções mais recentes (as demais, resumidas). Cada semana
    completa traz a tese publicada da carteira (``weeks[].thesis``) e ``meta.issuer_names`` dá
    o nome de todo emissor citado.
    """
    from ..ui.data import CDP_INVARIANTS, kill_switch_state
    from .painel_publicacao import PROFILES, publicacao
    from .reports import PAPER_TRADING_TEXT

    if profile not in PROFILES:
        raise ValueError(f"perfil desconhecido: {profile!r} (use {', '.join(PROFILES)})")
    cfg: FundConfig = rt.cfg
    if now is None:
        now = rt.now()
    if now.tzinfo is None:
        now = now.replace(tzinfo=UTC)
    issues = _Issues()
    book_root = Path(rt.book_root)
    book_exists = book_root.is_dir()
    book = None
    if book_exists:
        from .book import Book

        book = issues.attempt("Livro", lambda: Book(book_root, config=cfg))
    track, records, shadow_records = _track_section(rt, cfg, book_exists, issues)
    universe_names: dict[str, str] = {}
    weeks, finals = _weeks_section(rt, cfg, book, records, shadow_records, issues,
                                   full_weeks, full_research_weeks,
                                   names=universe_names) if book is not None else ([], {})
    latest = _latest_day(records, shadow_records, finals, cfg)
    # Carteira vigente: a da semana do último registro; sem registro, a última decidida.
    live_week = records[-1].live_book_week if records else None
    if live_week is None:
        decided = [w["week"] for w in weeks if w["decision"] is not None
                   and w["decision"].get("decision") == "APPROVE"]
        live_week = decided[-1] if decided else None
    live = finals.get(live_week) if live_week is not None else None
    executed = any(w["week"] == live_week and w["executed"] for w in weeks)
    risk = _risk_section(cfg, records[-1] if records else None, live, live_week, executed)
    daily_reports, reports_index = _daily_reports(rt, cfg, records, issues, max_daily_reports)
    bt_root = Path(backtest_root) if backtest_root is not None else (
        Path(rt.reports_root) / "backtest")
    backtests = _backtests(bt_root, backtest_pattern, issues)
    audit = _audit(book_root, book_exists, cfg, audit_tail, issues)
    integrity = _integrity(rt, book, book_exists, audit)
    if book_exists and audit.get("exists"):
        events = _audit_events(book_root)
        integrity["checks"].append(_aux_integrity(rt, events, weeks, daily_reports))
        integrity["ok"] = _integrity_ok(integrity["checks"])
    market = _market_info(rt, issues)
    kill = kill_switch_state(book_root)
    status = _status(rt, cfg, now, weeks, records, kill, integrity, market, risk)
    status["agenda"] = _agenda(rt, now, book_exists, issues)
    is_synth, sources, notice = _synthetic(records, shadow_records, weeks, market)
    synth_bt = [r["id"] for r in backtests["runs"] if r.get("is_synthetic")]
    if synth_bt:
        sources += [f"backtest {i}" for i in synth_bt]
        is_synth = True
    tz = ZoneInfo(cfg.fund.timezone)
    meta = {
        "schema_version": SCHEMA_VERSION, "profile": "completo", "fund_name": cfg.fund.name,
        "generated_at": now.astimezone(UTC).isoformat(),
        "generated_at_local": now.astimezone(tz).isoformat(), "timezone": cfg.fund.timezone,
        "is_synthetic": is_synth, "synthetic_sources": sources,
        "data_notice": _data_notice(is_synth, notice, records, weeks, market),
        "simulated_label": SIMULATED_DATA_NOTICE if is_synth else None,
        "paper_trading_label": cfg.fund.track_record_type,
        "paper_trading_text": PAPER_TRADING_TEXT,
        "base_currency": cfg.fund.base_currency, "inception_date": cfg.fund.inception_date,
        "inception_nav_usd": cfg.fund.inception_nav_usd, "manager": cfg.fund.manager_name,
        "config_hash": cfg.config_hash(), "mandate": _mandate(cfg),
        "invariants": list(CDP_INVARIANTS),
        "market": market,
        "counts": {"weeks": len(weeks), "daily_records": len(records),
                   "shadow_records": len(shadow_records),
                   "daily_reports": sum(1 for r in reports_index if r["kind"] == "daily"),
                   "weekly_reports": sum(1 for r in reports_index if r["kind"] == "weekly"),
                   "audit_events": audit.get("n_events"),
                   "backtests": len(backtests["runs"])},
        "export_limits": {"max_daily_reports": max_daily_reports, "full_weeks": full_weeks,
                          "full_research_weeks": full_research_weeks,
                          "audit_tail": audit_tail, "max_risk_runs": max_risk_runs,
                          "max_risk_full_runs": max_risk_full_runs},
    }
    data = {
        "meta": meta, "status": status, "track_record": track, "latest_day": latest,
        "risk": risk, "weeks": weeks, "daily_reports": daily_reports,
        "reports_index": reports_index,
        "risk_monitor": _risk_monitor(rt, issues, max_risk_runs, max_risk_full_runs),
        "backtests": backtests, "audit": audit, "issues": issues.items,
    }
    data = clean(data)
    data["meta"]["issuer_names"] = clean(_issuer_names(data, universe_names))
    data["meta"]["data_hash"] = data_hash(data)
    if profile == "publicacao":
        return publicacao(data, reports_dir=_reports_label(rt), page_sha256=page_sha256())
    return data


def _reports_label(rt: Any) -> str:
    """Pasta dos relatórios como aparece nos caminhos publicados (relativa; senão só o nome)."""
    p = Path(rt.reports_root)
    return p.as_posix() if not p.is_absolute() else p.name


def _template(template_path: Path | str | None) -> str:
    path = Path(template_path) if template_path is not None else DEFAULT_TEMPLATE
    template = path.read_text(encoding="utf-8")
    n = template.count(DATA_ELEMENT)
    if n != 1:
        raise ValueError(f"O template precisa conter exatamente um {DATA_ELEMENT!r} "
                         f"(encontrado(s): {n}).")
    return template


def _version(template: str) -> str:
    return hashlib.sha256(f"{PAGE_LAYOUT}\n{template}".encode()).hexdigest()


def page_sha256(template_path: Path | str | None = None) -> str:
    """Versão da página: SHA-256 do formato de publicação (``PAGE_LAYOUT``) e do template — muda
    só quando um dos dois muda. Vai carimbada no ``index.html``, no script versionado, na cópia
    local e em ``data.json`` (``meta.page_sha256``)."""
    return _version(_template(template_path))


def _split_template(template_path: Path | str | None) -> tuple[str, str]:
    template = _template(template_path)
    sha = _version(template)
    head, tail = template.split(DATA_ELEMENT)
    return head.replace(PAGE_SHA_PLACEHOLDER, sha), tail.replace(PAGE_SHA_PLACEHOLDER, sha)


def render_painel(data: Mapping[str, Any], template_path: Path | str | None = None) -> str:
    """Injeta o JSON do painel no template (no elemento ``<script id="cdp-data">``)."""
    head, tail = _split_template(template_path)
    element = DATA_ELEMENT.replace(PLACEHOLDER, embed_json(data))
    return head + element + tail


def asset_names(version: str) -> tuple[str, str]:
    """Nomes do estilo e do script versionados de uma versão da página."""
    stem = f"{ASSET_PREFIX}{version[:16]}"
    return f"{stem}.css", f"{stem}.js"


def _page_parts(template_path: Path | str | None) -> dict[str, str]:
    """Separa o template (já com a versão carimbada) em cabeçalho, estilo, marcação, scripts de
    CDN e script da página. Exige exatamente um ``<style>`` e um ``<script>`` sem atributos
    depois do elemento de dados."""
    head, tail = _split_template(template_path)
    if head.count("<style>") != 1 or head.count("</style>") != 1:
        raise ValueError("O template precisa de exatamente um <style> antes do elemento de dados.")
    top, rest = head.split("<style>")
    css, body = rest.split("</style>")
    if tail.count("<script>") != 1:
        raise ValueError("O template precisa de exatamente um <script> sem atributos depois do "
                         "elemento de dados.")
    cdn, rest = tail.split("<script>")
    js, sep, after = rest.rpartition("</script>")
    if not sep:
        raise ValueError("O <script> da página não fecha.")
    return {"top": top, "css": css.strip("\n") + "\n", "body": body, "cdn": cdn,
            "js": js.strip("\n") + "\n", "after": after}


def page_assets(template_path: Path | str | None = None) -> dict[str, str]:
    """Estilo e script da página, versionados (``painel-<versão>.css``/``.js``)."""
    parts = _page_parts(template_path)
    css_name, js_name = asset_names(page_sha256(template_path))
    return {css_name: parts["css"], js_name: parts["js"]}


def render_page(template_path: Path | str | None = None) -> str:
    """``index.html`` publicado: a casca da página com o elemento de dados vazio (``null``), a
    versão carimbada e as referências ao estilo e ao script versionados — a página busca
    ``data.json`` ao lado dela. Não depende dos dados: só muda quando o template muda."""
    parts = _page_parts(template_path)
    version = page_sha256(template_path)
    css_name, js_name = asset_names(version)
    return (parts["top"] + f'<meta name="cdp-page-sha256" content="{version}">\n'
            + f'<link rel="stylesheet" href="{css_name}">' + parts["body"] + EMPTY_DATA_ELEMENT
            + parts["cdn"] + f'<script src="{js_name}"></script>' + parts["after"])


def page_version(page_text: str) -> str | None:
    """A versão carimbada num ``index.html`` (``None`` se não houver carimbo)."""
    m = PAGE_SHA_RE.search(page_text)
    return m.group(1) if m else None


def published_page_sha(out_dir: Path | str = DEFAULT_OUT_DIR) -> str | None:
    """Versão da página publicada por último no artifact (``PAGINA_PUBLICADA.sha256``)."""
    try:
        text = (Path(out_dir) / MARKER_NAME).read_text(encoding="utf-8").strip()
    except OSError:
        return None
    return text if re.fullmatch(r"[0-9a-f]{64}", text) else None


def mark_published(out_dir: Path | str = DEFAULT_OUT_DIR) -> dict[str, Any]:
    """Registra que o ``index.html`` atual foi publicado no artifact: grava a versão carimbada
    nele em ``PAGINA_PUBLICADA.sha256``. Chamado (``cdp painel --publicado``) só depois de uma
    publicação bem-sucedida que incluiu a página; até lá ``page_changed`` continua verdadeiro."""
    out = Path(out_dir)
    index = out / INDEX_NAME
    try:
        sha = page_version(index.read_text(encoding="utf-8"))
    except OSError as exc:
        raise ValueError(f"{index.as_posix()} ilegível ({exc.__class__.__name__}): rode "
                         "`cdp painel` antes") from exc
    if sha is None:
        raise ValueError(f"{index.as_posix()} sem a versão da página (var PAGE_SHA): rode "
                         "`cdp painel` de novo")
    before = published_page_sha(out)
    marker = out / MARKER_NAME
    if before != sha:
        _write_atomic(marker, sha + "\n")
    return {"marcador": marker.as_posix(), "page_sha256": sha, "anterior": before,
            "mudou": before != sha}


STANDALONE_HEAD = ('<!doctype html><html lang="pt-BR"><head><meta charset="utf-8">'
                   '<meta name="viewport" content="width=device-width,initial-scale=1,'
                   'viewport-fit=cover"></head><body>')
STANDALONE_TAIL = "</body></html>"


def _write_atomic(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=".tmp_", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as f:
            f.write(text)
        os.chmod(tmp, 0o644)  # mkstemp cria 0600; os arquivos do painel são públicos no clone
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)


def _file_info(path: Path, text: str) -> dict[str, Any]:
    raw = text.encode("utf-8")
    return {"path": path.as_posix(), "bytes": len(raw), "sha256": hashlib.sha256(raw).hexdigest(),
            "max_line": max_line(text), "lines": text.count("\n") + (not text.endswith("\n"))}


def write_painel(rt: Any, out_dir: Path | str = DEFAULT_OUT_DIR, *, standalone: bool = True,
                 now: datetime | None = None, template_path: Path | str | None = None,
                 **kw: Any) -> dict[str, Any]:
    """Grava o painel para o artifact em ``out_dir``:

    - ``index.html`` (casca com ``#cdp-data`` = ``null`` e a versão da página carimbada),
      regravado só quando o conteúdo muda (``index_written``);
    - ``painel-<versão>.css``/``.js`` (estilo e script do template), regravados só quando mudam;
      versões antigas desses arquivos saem da pasta (``assets_removed``);
    - ``data.json``: perfil ``publicacao`` (indentado, chaves ordenadas) — sempre;
    - ``cdp_painel_local.html`` (``standalone``): cópia autônoma com o perfil ``completo``
      embutido e esqueleto ``<!doctype>``, para abrir offline.

    ``page_changed``: a versão da página (SHA-256 do template) difere da última PUBLICADA no
    artifact (``PAGINA_PUBLICADA.sha256``, ver :func:`mark_published`) ou ainda não há registro
    de publicação — continua verdadeiro em todas as execuções até a página ser publicada, mesmo
    que o ``index.html`` local já tenha sido regravado (e commitado) antes.

    Monta o retrato completo uma vez e deriva dele a publicação (mesmos números). Devolve
    caminhos, tamanhos, SHA-256, maior linha, ``data_hash``, ``page_changed`` e
    ``index_written``."""
    from .painel_publicacao import dump_publicacao, publicacao

    full = painel_data(rt, now=now, profile="completo", **kw)
    version = page_sha256(template_path)
    pub = publicacao(full, reports_dir=_reports_label(rt), page_sha256=version)
    out = Path(out_dir)
    page = render_page(template_path)
    index = out / INDEX_NAME
    index_written = _sha256_file(index) != hashlib.sha256(page.encode("utf-8")).hexdigest()
    if index_written:
        _write_atomic(index, page)
    assets = page_assets(template_path)
    asset_info = []
    for name, text in assets.items():
        path = out / name
        if _sha256_file(path) != hashlib.sha256(text.encode("utf-8")).hexdigest():
            _write_atomic(path, text)
        asset_info.append(_file_info(path, text))
    removed = []
    for old_asset in sorted(out.glob(f"{ASSET_PREFIX}*")):
        if ASSET_RE.fullmatch(old_asset.name) and old_asset.name not in assets:
            old_asset.unlink()
            removed.append(old_asset.name)
    published = published_page_sha(out)
    page_changed = published != version
    text = dump_publicacao(pub)
    _write_atomic(out / DATA_NAME, text)
    index_info, data_info = _file_info(index, page), _file_info(out / DATA_NAME, text)
    pmeta = pub["meta"]
    result: dict[str, Any] = {
        "out_dir": out.as_posix(), "page_changed": page_changed, "index_written": index_written,
        "page_sha256": version, "published_page_sha256": published,
        "index_path": index_info["path"], "index_bytes": index_info["bytes"],
        "index_sha256": index_info["sha256"], "index_max_line": index_info["max_line"],
        "assets": [{"path": a["path"], "bytes": a["bytes"], "sha256": a["sha256"],
                    "max_line": a["max_line"]} for a in asset_info],
        "assets_removed": removed,
        "data_path": data_info["path"], "data_bytes": data_info["bytes"],
        "data_sha256": data_info["sha256"], "data_max_line": data_info["max_line"],
        "data_lines": data_info["lines"], "data_hash": pmeta["data_hash"],
        "data_hash_completo": full["meta"]["data_hash"], "profile": pmeta.get("profile"),
        "nivel_publicacao": (pmeta.get("publication") or {}).get("nivel"),
        "cortes": len(expandir(pmeta.get("truncations") or [])),
        "generated_at": pmeta["generated_at"], "is_synthetic": pmeta["is_synthetic"],
        "local_path": None, "local_bytes": None, "local_sha256": None,
    }
    if standalone:
        local = STANDALONE_HEAD + render_painel(full, template_path) + STANDALONE_TAIL
        lp = out / LOCAL_NAME
        _write_atomic(lp, local)
        info = _file_info(lp, local)
        result.update({"local_path": info["path"], "local_bytes": info["bytes"],
                       "local_sha256": info["sha256"]})
    return result


def max_line(text: str) -> int:
    from .painel_publicacao import max_line as ml

    return ml(text)


def expandir(x: Any) -> Any:
    from .painel_publicacao import expandir as ex

    return ex(x)


__all__ = ["ASSET_PREFIX", "ASSET_RE", "DATA_ELEMENT", "DATA_NAME", "DEFAULT_OUT_DIR",
           "DEFAULT_TEMPLATE", "EMPTY_DATA_ELEMENT", "INDEX_NAME", "LOCAL_NAME", "MARKER_NAME",
           "PAGE_LAYOUT", "PAGE_SHA_PLACEHOLDER", "PLACEHOLDER", "SCHEMA_VERSION", "URL_NAME",
           "asset_names", "clean", "data_hash", "embed_json", "expandir", "mark_published",
           "page_assets", "page_sha256", "page_version", "painel_data", "published_page_sha",
           "referenced_issuers", "render_page", "render_painel", "scrub_text", "to_json",
           "write_painel"]
