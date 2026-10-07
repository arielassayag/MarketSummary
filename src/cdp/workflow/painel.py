"""Exportador determinístico do painel do CDP — Cabra da Peste (portal do fundo).

O portal principal é o site público (:mod:`cdp.site`, perfil ``site``); o artifact do claude.ai
é um espelho privado opcional (perfil ``publicacao``). Este módulo só LÊ os registros do fundo
(livro, tese publicada da carteira, track record, relatórios, base de mercado, backtests) e monta
um retrato de dados; a página apenas formata e plota esses dados. O modelo aberto da carteira
(``modelo``: metodologia vigente, formulação resolvida da decisão, risco idiossincrático,
dimensionamento e execução por posição, auditoria e reprodução) chega já em texto pt-BR montado
aqui. Publicação (:func:`write_painel`):

- ``index.html``: casca pequena da página (cabeçalho, marcação, elemento de dados vazio ``null``
  e a versão da página carimbada) que referencia o estilo e o script do template em arquivos
  versionados ``painel-<versão>.css`` e ``painel-<versão>.js``; os módulos carregados sob demanda
  (``painel-<versão>-modelo.js``, ``painel-<versão>-cobertura.js``) vão ao lado. Quem publica no
  artifact precisa ler por inteiro o que publica: a casca é pequena, e os arquivos versionados só
  vão junto quando a página muda (os já publicados ficam). Só é regravado quando o template muda;
  a página busca ``data.json`` ao lado dela.
- ``cobertura*.json``: dados da aba "Cobertura de ativos" (:mod:`cdp.workflow.painel_cobertura`),
  republicados no artifact só quando mudam e só quando cabem inteiros no orçamento de leitura da
  publicação (:func:`cdp.workflow.painel_artifact.plano_cobertura`; ``COBERTURA_PUBLICADA.json``).
  Falha no registro da cobertura nunca derruba o painel: a aba fica "em verificação".
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
from ..noticias import neutralizar_citacao
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
#: Formato da publicação (casca + estilo, script e módulos versionados). Entra na versão da
#: página: mudar o formato obriga a republicar a página mesmo com o template igual.
PAGE_LAYOUT = "cdp-painel-casca/2"
#: Arquivos versionados da página: ``painel-<16 primeiros hex da versão>.css``/``.js`` e os
#: módulos carregados sob demanda ``painel-<16 hex>-<nome>.js``.
ASSET_PREFIX = "painel-"
ASSET_RE = re.compile(r"painel-[0-9a-f]{16}(?:-(?:cobertura|modelo))?\.(?:css|js)")
#: Módulos da página carregados sob demanda (nome → fonte ao lado deste arquivo): a aba
#: "Cobertura de ativos" e o modelo aberto da carteira (Mandato, Risco, Carteira, Comitê). A
#: página cria o elemento de script na primeira abertura da aba; a cópia local os embute. Módulo
#: ausente no código fica fora da versão e da publicação (a aba mostra o aviso de indisponível).
MODULOS = {"cobertura": "painel_cobertura.js", "modelo": "painel_modelo.js"}
MODULOS_DIR = Path(__file__).parent
#: Arquivos de dados da aba de cobertura (gerados por :mod:`cdp.workflow.painel_cobertura`),
#: soltos ao lado de ``index.html``, e o marcador local da última publicação deles no artifact.
COBERTURA_RE = re.compile(r"cobertura(?:-[a-z0-9-]+)?\.json")
COBERTURA_MARKER = "COBERTURA_PUBLICADA.json"
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
MIN_PREGOES_ANUALIZAR = 63
"""Pregões mínimos para o portal mostrar retorno e vol anualizados e Sharpe."""
MIN_PREGOES_MELHOR_DIA = 5
"""Pregões mínimos para o portal destacar melhor e pior dia."""
COMMENTARY_SECTION = "Comentário do dia"
# Fontes entre parênteses (o rodapé da página lê o primeiro parêntese como fontes de dados).
REAL_DATA_NOTICE = (f"Dados reais de mercado ({REAL_DATA_SOURCES}); carteira simulada com execução "
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
        # Sem a metodologia ativada, o cronograma recorrente e a convenção de execução da
        # configuração anterior não são publicados (só a data da carteira inaugural).
        "schedule": {
            "timezone": cfg.fund.timezone, "primary_calendar": cfg.fund.primary_calendar,
            "weekly_research_start_local": cfg.fund.weekly_research_start_local,
            "daily_close_run_local": cfg.fund.daily_close_run_local,
            "minds": list(cfg.fund.minds),
            **({"rebalance_rule": cfg.fund.rebalance_rule,
                "rebalance_weekday": cfg.fund.rebalance_weekday,
                "decision_deadline_local": cfg.fund.decision_deadline_local,
                "execution_convention": cfg.fund.execution_convention}
               if metodologia_ativada(cfg) else {}),
        },
        "execution": (cfg.execution.model_dump(mode="json") if cfg.execution is not None
                      else None),
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
        ("risco", "country_gross_share_max", "Fatia máxima da exposição bruta por país",
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
        ("liquidez", "min_gross_liquid_3d", "Exposição bruta liquidável em 3 dias (mín.)",
         lq.min_gross_liquid_3d, "pct"),
        ("liquidez", "min_gross_liquid_5d", "Exposição bruta liquidável em 5 dias (mín.)",
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
        ("drawdown", "soft_stop", "Stop suave (revisão; exposição bruta × multiplicador)",
         [dd.soft_stop, dd.soft_degross_multiplier], "pct"),
        ("drawdown", "hard_stop", "Stop duro (exposição bruta × multiplicador)",
         [dd.hard_stop, dd.degross_multiplier], "pct"),
        ("drawdown", "stop_out", "Stop-out (exposição bruta mínima)", [dd.stop_out, dd.stop_out_gross],
         "pct"),
        ("ia", "llm_phase", "Fase de adoção das visões de IA", cfg.research.llm_phase, "text"),
        ("ia", "llm_view_ic", "Coeficiente de informação (IC) efetivo das visões de IA",
         cfg.research.llm_view_ic, "ratio"),
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
    n = int(out.get("n_days") or 0)
    if n < MIN_PREGOES_ANUALIZAR:
        # Anualizar poucos pregões não informa (ex.: um dia de custos vira −25% a.a.).
        out.update({"annualized_return": None, "annualized_vol": None, "sharpe": None,
                    "annualization_note": (f"Retorno e volatilidade anualizados e Sharpe a partir "
                                           f"de {MIN_PREGOES_ANUALIZAR} pregões (hoje: {n}).")})
    if n < MIN_PREGOES_MELHOR_DIA:
        out.update({"best_day": None, "worst_day": None})
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
    reported_cost = total_cost if p.trades else 0.0
    if partial and not any(_num(t.est_cost_bps) is not None for t in p.trades):
        from .contrato_custos import STAMP, descriptor

        if descriptor(p) == STAMP:
            reported_cost = None
    return {
        "n_positions": len(p.positions), "n_long": p.risk.n_long, "n_short": p.risk.n_short,
        "gross": p.risk.gross, "net": p.risk.net, "beta": p.risk.beta,
        "ex_ante_vol": p.risk.ex_ante_vol, "var_1d_99": p.risk.var_1d_99,
        "expected_alpha_annual": p.optimizer.expected_alpha_annual,
        "expected_cost_annual": p.optimizer.expected_cost_annual,
        "n_trades": len(p.trades),
        "turnover": sum(abs(float(t.weight_change)) for t in p.trades) if p.trades else 0.0,
        "trade_cost_usd": reported_cost,
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
        "news_id": x.news_id, "title": neutralizar_citacao(x.title),
        "source": neutralizar_citacao(x.source), "url": _safe_url(x.url),
        "citacao_neutralizada": (neutralizar_citacao(x.title) != x.title
                                or neutralizar_citacao(x.source) != x.source),
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
    from . import rotulos as R

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
        "data_notice": R.aviso(rec.data_notice), "track_record_type": R.aviso(rec.track_record_type),
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
            checks.append(_check("country_gross_share", "Fatia da exposição bruta por país (pior)", basis,
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
        checks.append(_check("liquidez_1d", "Exposição bruta liquidável em 1 dia", d_basis, liq, None,
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
            checks.append(_check(cid, f"Exposição bruta liquidável em {h} dias (piso)", p_basis, v, floor,
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
        # stops do short, ADTV ausente): o texto do código, um a um. As limitações técnicas de
        # dados viram uma frase só (o detalhe fica no registro diário, nos dados abertos).
        from .daily import data_limitations_summary, split_data_limitations

        investor_alerts, tech = split_data_limitations(last.alerts)
        for a in investor_alerts:
            alerts.append({"severity": "warning", "source": "fechamento",
                           "text": f"Fechamento de {last.date.strftime('%d/%m/%Y')}: {a}"})
        resumo = data_limitations_summary(len(tech))
        if resumo:
            alerts.append({"severity": "info", "source": "fechamento",
                           "text": f"Fechamento de {last.date.strftime('%d/%m/%Y')}: {resumo}"})
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
    from . import rotulos as R

    if is_synth:
        text = notice or "mercado sintético gerado por código."
        if SIMULATED_DATA_NOTICE not in text.upper():
            text = f"{SIMULATED_DATA_NOTICE} — {text}"
        return R.aviso(text)
    if records:
        return R.aviso(records[-1].data_notice or REAL_DATA_NOTICE)
    for w in reversed(weeks):
        p = w.get("proposal") or {}
        if p.get("data_notice"):
            return R.aviso(p["data_notice"])
    real_market = bool(market and market.get("available") and not market.get("is_synthetic"))
    return REAL_DATA_NOTICE if weeks or real_market else EMPTY_DATA_NOTICE


# ==========================================================
# Modelo aberto da carteira (metodologia, risco, formulação, dimensionamento, auditoria)
# ==========================================================

#: Repositório público (código, metodologia, configuração e registros) e portal principal.
#: ``configs/cdp/site.yaml`` traz os mesmos endereços (teste confere).
REPO = "arielassayag/MarketSummary"
REPO_URL = f"https://github.com/{REPO}"
PORTAL_URL = "https://arielassayag.github.io/MarketSummary/"
#: Documentos e módulos citados em "Auditoria e reprodução" (caminho no repositório, rótulo,
#: o que contém): no portal, links fixados na versão do código que gerou a publicação; no espelho
#: privado (sem versão conhecida), no ramo principal.
DOCS_AUDITORIA = (
    ("docs/cdp/REPRODUZIR.md", "Auditoria e reprodução",
     "conferir os registros, recalcular modelos e decisões e refazer os passos da IA com "
     "qualquer assistente"),
    ("docs/cdp/METODOLOGIA.md", "Metodologia de gestão",
     "alpha, modelo de risco, construção, limites e controle de perdas"),
    ("docs/cdp/COBERTURA.md", "Metodologia de avaliação",
     "modelos abertos de valuation, preço-alvo de 12 meses, rating e placar"),
    ("docs/cdp/EXECUCAO.md", "Cronograma e execução",
     "dia de montagem, prazo da decisão, leilão de fechamento e capacidade"),
    ("docs/cdp/REPLICAR.md", "Replicar a operação", "operar uma cópia própria do processo"),
    ("docs/cdp/SITE.md", "Portal e dados abertos", "o que é publicado e como conferir"),
)
CONFIG_AUDITORIA = (
    ("configs/cdp/fund.yaml", "Mandato do fundo", "limites, custos, calendário e execução"),
    ("configs/cdp/valuation.yaml", "Parâmetros de valuation",
     "taxa livre de risco, prêmios de risco e parâmetros dos modelos de cobertura"),
)
CODIGO_AUDITORIA = (
    ("src/cdp/alpha", "Sinais de alpha", "fatores padronizados e combinação"),
    ("src/cdp/risk/model.py", "Modelo de risco", "fatores, meias-vidas e risco específico"),
    ("src/cdp/risk/idio.py", "Risco idiossincrático", "decomposição e inflação de 2ª ordem κF"),
    ("src/cdp/portfolio/optimizer.py", "Otimizador", "objetivo, restrições e custo de cada "
     "restrição"),
    ("src/cdp/portfolio/compliance.py", "Verificações de conformidade",
     "limites rígidos e de alerta da carteira"),
    ("src/cdp/portfolio/execucao.py", "Execução no fechamento",
     "capacidade do leilão e mercados fechados"),
    ("src/cdp/risk/limites.py", "Vetos e stops", "vetos de short e stops por nome"),
    ("src/cdp/cobertura", "Modelos de cobertura", "valuation, preço-alvo e rating"),
    ("src/cdp/audit.py", "Trilha de auditoria", "eventos encadeados e verificação"),
)
#: Fontes públicas de dados (nome, endereço, uso, nome curto do rodapé): as mesmas do catálogo de
#: dados abertos do portal (``cdp.site.FONTES_PUBLICAS`` deriva desta lista).
FONTES_PUBLICAS_PT = (
    ("CVM — dados abertos (DFP, ITR, FRE, IPE)", "https://dados.cvm.gov.br",
     "demonstrações financeiras, formulários e fatos relevantes de emissores brasileiros", "CVM"),
    ("SEC EDGAR (documentos protocolados e XBRL)", "https://www.sec.gov/edgar",
     "demonstrações de emissores com registro nos EUA (20-F, 40-F, 10-K)", "SEC EDGAR"),
    ("B3 — dados públicos", "https://www.b3.com.br", "calendário, aluguel de ações e negociação",
     "B3"),
    ("Banco Central do Brasil (SGS)", "https://www.bcb.gov.br", "juros, inflação e câmbio",
     "Banco Central do Brasil"),
    ("Banxico e INEGI", "https://www.banxico.org.mx", "juros, inflação e câmbio do México",
     "Banxico e INEGI"),
    ("FRED (Federal Reserve Bank of St. Louis)", "https://fred.stlouisfed.org",
     "juros dos Treasuries e séries macroeconômicas dos EUA", "FRED"),
    ("Damodaran Online (NYU Stern)", "https://pages.stern.nyu.edu/~adamodar/",
     "prêmio de risco de mercado, risco-país e betas setoriais", "Damodaran"),
    ("Yahoo Finance (cotações e consenso público)", "https://finance.yahoo.com",
     "preços, volumes, câmbio, composição de ETFs e consenso público de analistas",
     "Yahoo Finance"),
    ("FINRA — posições vendidas consolidadas (short interest)", "https://api.finra.org",
     "posições vendidas de ações negociadas nos EUA, usadas no escore de squeeze e nos vetos "
     "de short", "FINRA"),
)
#: Rodapé do portal: as mesmas fontes, pelo nome curto.
FONTES_RODAPE = ", ".join(f[3] for f in FONTES_PUBLICAS_PT)
PAIS_PT = {"AR": "Argentina", "BR": "Brasil", "CL": "Chile", "CO": "Colômbia", "MX": "México",
           "PE": "Peru", "UY": "Uruguai", "PA": "Panamá", "US": "Estados Unidos",
           "LATAM": "regional (América Latina)", "*": "demais países"}
GRUPO_IDIO_PT = {"mercado": "Mercado", "pais": "Países", "setor": "Setores", "estilo": "Estilos",
                 "macro": "Commodities e dólar", "especifico": "Específico (idiossincrático)"}
MODELO_RISCO_PT = {"decisao": "modelo de decisão", "base": "modelo base"}
#: Origem do teto que limita cada posição (tokens de ``weekly.construction_constraints`` e
#: ``optimizer._per_name_bounds``), como locução nominal: a página mostra "no teto" ao lado.
ORIGEM_TETO_PT = {
    "mandato": "peso máximo do mandato", "risco_por_nome": "risco por nome",
    "risco_especifico": "risco específico", "capacidade_fechamento":
    "capacidade do leilão de fechamento", "liquidez": "liquidez", "visao": "visão da pesquisa",
    "squeeze": "risco de squeeze", "congelado": "mercado local sem pregão",
    "adtv_minimo": "volume médio diário mínimo", "veto_short": "veto de short",
    "stop_squeeze": "stop de squeeze", "elegibilidade": "elegibilidade (linha, aluguel ou porte)",
    "sem_alpha": "sem alpha", "excluido_gestor": "exclusão pelo gestor",
    "so_reducao": "modo somente redução de risco", "negociacao": "capacidade de negociação"}
ORIGEM_OUTRA = "outro limite"
GRUPO_RESTRICAO = (
    ("net_exposure", "total", "Exposição e risco da carteira"),
    ("beta", "total", None), ("vol_target", "total", None), ("gross", "total", None),
    ("op_country:", "pais_op", "Países — limite operacional"),
    ("country_share:", "pais_fatia", "Concentração da exposição bruta por país"),
    ("country:", "pais", "Países — limite do mandato"),
    ("sector:", "setor", "Setores"), ("style:", "estilo", "Estilos (fatores)"),
    ("theme:", "tema", "Temas, commodities e eventos"),
    ("factor_risk:", "fatorial", "Risco fatorial"),
    ("linked_", "controle", "Grupos de controle"),
)
_FORMULA_UNIDADE_X = ("beta", "style:")


def _grupo_restricao(chave: str) -> tuple[str, str]:
    titulos = {g: t for _, g, t in GRUPO_RESTRICAO if t}
    for prefixo, grupo, _t in GRUPO_RESTRICAO:
        if chave == prefixo or chave.startswith(prefixo):
            return grupo, titulos[grupo]
    return "outras", "Outras restrições"


def _fx(x: Any, chave: str) -> str:
    """Limite/valor de uma restrição no formato da sua unidade (texto pt-BR)."""
    from ..cobertura import formato as fm

    if any(chave == p or chave.startswith(p) for p in _FORMULA_UNIDADE_X):
        return fm.num(x, 3)
    return fm.pct(x, 2)


def _lista_pt(itens: Sequence[str]) -> str:
    itens = [str(i) for i in itens if i]
    if len(itens) <= 1:
        return "".join(itens)
    return ", ".join(itens[:-1]) + " e " + itens[-1]


DIAS_PT = ("segunda-feira", "terça-feira", "quarta-feira", "quinta-feira", "sexta-feira",
           "sábado", "domingo")
#: Sinais do alpha quantitativo (chaves de ``alpha.signal_weights``).
SINAL_PT = {"residual_momentum": "momentum residual", "short_term_reversal":
            "reversão de curto prazo", "value": "valor", "quality": "qualidade",
            "low_risk": "baixo risco", "analyst_revision": "revisões de analistas",
            "valuation_gap": "valuation da cobertura", "valuation": "valuation da cobertura"}
SOLVER_PT = {"CLARABEL": "Clarabel", "SCS": "SCS", "ECOS": "ECOS", "OSQP": "OSQP"}


def metodologia_ativada(cfg: FundConfig) -> bool:
    """A configuração já traz a metodologia da carteira inaugural: dia de montagem no último
    pregão da semana na NYSE, execução no leilão de fechamento (bloco ``execution``) e data de
    início num dia de montagem dessa regra. Antes disso (configuração anterior à ativação), o
    portal não publica o cronograma recorrente, a convenção de execução nem a fração fatorial
    da configuração anterior — só a data da carteira inaugural."""
    from ..calendar import is_rebalance_day, regra

    if cfg.execution is None or regra(cfg) != "LAST_US_SESSION":
        return False
    try:
        return bool(is_rebalance_day(cfg.fund.inception_date, cfg))
    except Exception:  # noqa: BLE001 - calendário indisponível: não afirma o cronograma
        return False


def _pais_pt(c: Any) -> str:
    return PAIS_PT.get(str(c), str(c))


def _controle_perdas(cfg: FundConfig) -> tuple[list[dict[str, str]], str]:
    """Escada de controle de perdas (nível, tom, gatilho e ação) e a referência da escada, da
    configuração e de :mod:`cdp.risk.drawdown` (o mesmo texto no Mandato e na aba Risco)."""
    from ..cobertura import formato as fm
    from ..risk.drawdown import d_max, stage_multiplier

    dd = cfg.drawdown
    linhas = [{"nivel": "Normal", "tom": "ok", "gatilho": f"acima de {fm.pct(dd.soft_stop, 1)}",
               "acao": "gestão normal"}]
    if dd.risk_reference == "normal_book_vol":
        m1, m2, m3 = (stage_multiplier(s, cfg) for s in ("soft_stop", "hard_stop", "stop_out"))
        reta = d_max(cfg)
        linhas += [
            {"nivel": "Nível 1 · revisão", "tom": "warn", "gatilho": fm.pct(dd.soft_stop, 1),
             "acao": f"revisão da carteira; volatilidade ex-ante limitada a {fm.num(m1, 2)} × a "
                     "da carteira resolvida no estágio normal"},
            {"nivel": "Nível 2 · redução", "tom": "crit", "gatilho": fm.pct(dd.hard_stop, 1),
             "acao": f"volatilidade ex-ante limitada a {fm.num(m2, 2)} × a do estágio normal"},
            {"nivel": "Nível 3 · stop-out", "tom": "crit", "gatilho": fm.pct(dd.stop_out, 1),
             "acao": f"volatilidade ex-ante limitada a {fm.num(m3, 2)} × a do estágio normal"
                     + (f" (reta que zera o risco em {fm.pct(-reta, 1)})"
                        if math.isfinite(reta) else "") + " e revisão completa do processo"},
        ]
        ref = ("a escada limita a volatilidade ex-ante a um múltiplo da volatilidade da mesma "
               "carteira resolvida no estágio normal; o risco volta sozinho quando o drawdown "
               "se recupera")
    else:
        linhas += [
            {"nivel": "Nível 1 · revisão", "tom": "warn", "gatilho": fm.pct(dd.soft_stop, 1),
             "acao": "revisão da carteira; exposição bruta × "
                     f"{fm.num(dd.soft_degross_multiplier, 2)}"},
            {"nivel": "Nível 2 · redução", "tom": "crit", "gatilho": fm.pct(dd.hard_stop, 1),
             "acao": f"exposição bruta × {fm.num(dd.degross_multiplier, 2)}"},
            {"nivel": "Nível 3 · stop-out", "tom": "crit", "gatilho": fm.pct(dd.stop_out, 1),
             "acao": f"exposição bruta reduzida a {fm.pct(dd.stop_out_gross, 0)} do PL e "
                     "revisão completa do processo"},
        ]
        ref = "a escada reduz a exposição bruta do mandato"
    return linhas, ref


def _metodologia(cfg: FundConfig, hoje: date, inaugural: Mapping[str, Any] | None = None
                 ) -> dict[str, Any]:
    """Metodologia vigente em texto pt-BR (cronograma, construção, gestão de risco, processo,
    fontes e adoção de IA), montada só da configuração, do calendário e do código: nunca cita
    mudanças. ``inaugural`` (``status.inaugural``): data da carteira inaugural no pré-início.
    Sem a metodologia ativada (:func:`metodologia_ativada`), o cronograma recorrente sai e fica
    só a data da carteira inaugural."""
    from ..calendar import resumo_cronograma
    from ..cobertura import formato as fm
    from ..research.pm_agent import POSTURE_MAP
    from ..risk import gatilhos as gt

    rk, lq, sq, ex = cfg.risk, cfg.liquidity, cfg.squeeze, cfg.execution
    op = rk.operational
    tz = ZoneInfo(cfg.fund.timezone)
    ativa = metodologia_ativada(cfg)
    cron: dict[str, Any] = {}
    if ativa:
        try:
            cron = resumo_cronograma(cfg, hoje)
        except Exception:  # noqa: BLE001 - calendário indisponível: só os textos da configuração
            cron = {}
    datas = [d for d in cron.get("proximas_datas") or [] if isinstance(d, date)]
    cronograma: list[dict[str, str]] = []
    if ativa:
        cronograma.append({"rotulo": "Dia de montagem", "texto": cfg.fund.rebalance_rule[:1].upper()
                           + cfg.fund.rebalance_rule[1:] + "."})
    cronograma.append({"rotulo": "Pesquisa e decisão", "texto": (
        f"Início às {cfg.fund.weekly_research_start_local} (Brasília) do dia de montagem"
        + (", com todos os dados disponíveis até o momento da análise"
           if cfg.fund.use_all_available_data else "") + ".")})
    if ativa and ex is not None:
        cronograma.append({"rotulo": "Prazo da decisão", "texto": (
            f"{ex.decision_deadline_cap_local} (Brasília) ou {ex.decision_buffer_minutes} minutos "
            "antes do fechamento mais cedo entre NYSE, B3 e BMV, o que vier primeiro; depois do "
            "prazo, a decisão não é gravada e a carteira vigente é mantida.")})
        cronograma.append({"rotulo": "Execução", "texto": (
            "Ordens em quantidade de ações, executadas ao preço oficial de fechamento de cada "
            "linha, limitadas à capacidade do leilão de fechamento e da janela anterior a ele.")})
        cp = ex.capacity
        estat = {"p25": "o percentil 25", "p50": "a mediana", "mean": "a média"}[cp.adv_statistic]
        cronograma.append({"rotulo": "Capacidade no fechamento", "texto": (
            f"Por linha, até {fm.pct(cp.auction_participation, 0)} do volume esperado do leilão "
            f"de fechamento e {fm.pct(cp.preclose_participation, 0)} da janela pré-fechamento "
            f"({fm.pct(cp.preclose_volume_share, 0)} do volume do dia), sobre {estat} do "
            f"volume diário de {cp.adv_window_days} pregões; shorts com "
            f"{fm.pct(cp.short_multiplier, 0)} dessa capacidade e dias de fechamento antecipado "
            f"com {fm.pct(cp.early_close_multiplier, 0)}. Volume desconhecido não negocia.")})
        politica = ("a linha local não negocia e o emissor negocia pelo ADR elegível; sem ADR "
                    "elegível, mantém a posição"
                    if ex.local_closed_policy == "adr_if_eligible_else_freeze"
                    else "a linha local não negocia e o emissor mantém a posição")
        cronograma.append({"rotulo": "Mercado local fechado",
                           "texto": f"Sem pregão no mercado local no dia de montagem, {politica} "
                                    "até o próximo fechamento negociável."})
        cronograma.append({"rotulo": "Ordens mínimas", "texto": (
            f"Ajustes abaixo de {fm.pct(ex.min_trade_weight, 2)} do PL não são enviados "
            "(banda de não negociação).")})
    cronograma.append({"rotulo": "Fechamento diário", "texto": (
        f"Marcação a mercado, risco, atribuição e relatório às {cfg.fund.daily_close_run_local} "
        "(Brasília), em todo pregão.")})
    proximas = [f"{d:%d/%m/%Y} ({DIAS_PT[d.weekday()]})" for d in datas]
    fechamentos = []
    for mic, quando in sorted((cron.get("fechamentos") or {}).items(),
                              key=lambda kv: (kv[1], kv[0])):
        from ..portfolio.execucao import MIC_NOME

        fechamentos.append({"mercado": MIC_NOME.get(mic, mic),
                            "texto": quando.astimezone(tz).strftime("%H:%M")})
    prazo = cron.get("prazo_decisao")
    cron_out = {
        "itens": cronograma, "proximas_datas": proximas,
        "proxima": (f"{datas[0]:%d/%m/%Y}" if datas else None),
        "prazo_proxima": (prazo.astimezone(tz).strftime("%H:%M") if isinstance(prazo, datetime)
                          else None),
        "fechamentos": fechamentos,
        "mercados_fechados": [str(m) for m in cron.get("mercados_fechados") or []],
        "nota": None if ativa else ("O cronograma semanal das montagens é publicado com a "
                                    "carteira inaugural."),
    }
    # --- carteira inaugural (pré-início): data, prazo e execução no leilão do dia
    inaug: list[dict[str, str]] = []
    d_ina = (inaugural or {}).get("date")
    if isinstance(d_ina, str):
        try:
            d_ina = date.fromisoformat(d_ina[:10])
        except ValueError:
            d_ina = None
    if isinstance(d_ina, date):
        inaug.append({"rotulo": "Carteira inaugural", "texto": (
            f"{d_ina:%d/%m/%Y} ({DIAS_PT[d_ina.weekday()]}), executada no leilão de fechamento "
            "do dia.")})
        if ativa:
            try:
                from ..portfolio.execucao import prazo_efetivo

                pz = prazo_efetivo(d_ina, cfg).astimezone(tz)
                inaug.append({"rotulo": "Prazo da decisão", "texto": (
                    f"{pz:%H:%M} (Brasília) em {d_ina:%d/%m/%Y}: o menor entre "
                    f"{ex.decision_deadline_cap_local} e {ex.decision_buffer_minutes} minutos "
                    "antes do fechamento mais cedo entre NYSE, B3 e BMV.")})
            except Exception:  # noqa: BLE001 - calendário indisponível: sem o prazo
                pass

    # --- construção
    def lim(mand: float | None, oper: float | None, fmt) -> str:
        if oper is not None and mand is not None and oper < mand:
            return f"{fmt(oper)} (operacional; mandato {fmt(mand)})"
        return fmt(mand)

    def p2(v: Any) -> str:
        return fm.pct(v, 1)

    def x3(v: Any) -> str:
        return fm.num(v, 2)

    camadas = [
        {"rotulo": "Mercado", "texto": f"Exposição líquida até {fm.pct(rk.net_exposure_max_abs, 1)} "
         f"do PL e beta previsto contra o mercado latino-americano até "
         f"{lim(rk.beta_max_abs, op.beta if op else None, x3)}."},
        {"rotulo": "Países", "texto": "Exposição líquida por país até " + (
            _lista_pt([f"{fm.pct(v, 1)} ({_pais_pt(k)})"
                       for k, v in sorted(op.country_net.items(), key=lambda kv: kv[0] == '*')])
            + f" no limite operacional; mandato {fm.pct(rk.country_net_max_abs, 1)}"
            if op else fm.pct(rk.country_net_max_abs, 1)) + "."},
        {"rotulo": "Setores", "texto": "Exposição líquida por setor até "
         f"{lim(rk.sector_net_max_abs, op.sector_net if op else None, p2)}."},
        {"rotulo": "Estilos", "texto": "Beta, tamanho, momentum, volatilidade residual, valor, "
         "liquidez e sensibilidade cambial, cada um até "
         f"{lim(rk.style_exposure_max_abs, op.style if op else None, x3)} desvio-padrão × PL."},
        {"rotulo": "Temas e commodities", "texto": (
            ("Estatais até " + _lista_pt([fm.pct(v, 1) for v in rk.theme_net_max_abs.values()])
             + "; " if rk.theme_net_max_abs else "")
            + "sensibilidade a cada commodity (Σ peso × beta) até "
            + lim(rk.commodity_beta_max_abs, op.commodity_beta if op else None, p2) + ".")},
    ]
    if cfg.risk_model.macro_factors:
        camadas.append({"rotulo": "Commodities e dólar no modelo de risco", "texto": (
            "Petróleo, cobre, ouro e o índice do dólar entram como fatores do modelo de risco "
            f"(betas com meia-vida de {cfg.risk_model.macro_beta_halflife} pregões).")})
    for w in rk.event_windows or []:
        if w.get("reaction_exposure_max_abs") is not None:
            camadas.append({"rotulo": "Janela de evento", "texto": (
                f"{w.get('name')}: volatilidade do país × {fm.num(w.get('vol_multiplier'), 1)} "
                "e exposição à reação residual do evento até "
                f"{fm.pct(w.get('reaction_exposure_max_abs'), 2)} do PL.")})
    if cfg.risk.country_gross_share_max:
        camadas.append({"rotulo": "Concentração por país", "texto": (
            "Fatia máxima da exposição bruta: " + _lista_pt(
                [f"{_pais_pt(k)} {fm.pct(v, 0)}"
                 for k, v in cfg.risk.country_gross_share_max.items()]) + ".")})
    meta, piso = rk.idio_share_goal, rk.idio_share_floor
    kappa = rk.second_order_inflation
    modelos = [{"decisao": "de decisão", "base": "base"}.get(m, m) for m in rk.idio_gate_models]
    idio_txt = (
        f"Meta de pelo menos {fm.pct(meta, 0)} da variância ex-ante vinda do risco específico de "
        f"cada empresa, com piso de {fm.pct(piso, 0)} que nunca é relaxado, medido "
        + ("nos modelos " if len(modelos) > 1 else "no modelo ") + _lista_pt(modelos)
        + f", com a covariância fatorial inflada por κF = {fm.num(kappa, 2)}."
        if meta is not None and piso is not None else None)
    kappa_txt = (
        f"κF = {fm.num(kappa, 2)}: multiplica a covariância dos fatores na medida "
        "idiossincrática e no teto de risco fatorial, para compensar o erro de estimação dos "
        "fatores que o otimizador tende a explorar"
        + (" (fórmula (1 − K/T)⁻² limitada a "
           f"{fm.num(rk.second_order_inflation_bounds[0], 2)}–"
           f"{fm.num(rk.second_order_inflation_bounds[1], 2)})"
           if rk.second_order_inflation_mode == "analytic" else " (valor do mandato)") + ".")
    lam_f = rk.factor_risk_aversion_multiplier
    objetivo = ("max αᵀw − (52/H)·custo(w − w⁰) − taxaᵀw⁻ − λ·wᵀΣw"
                + (" − λF·κF·wᵀBFBᵀw" if lam_f > 0 else ""))
    posturas = [(k, v) for k, v in POSTURE_MAP.items()]
    postura_txt = "; ".join(
        f"{POSTURE_PT.get(k, k)}: {fm.pct(v[0], 1) if v[0] is not None else 'meta do mandato'}"
        f" com até {fm.pct(v[1], 0)} da exposição bruta do mandato" for k, v in posturas)
    construcao = [
        {"rotulo": "Objetivo", "texto": (
            f"{objetivo}: alpha esperado líquido do custo de negociação amortizado em "
            f"H = {fm.num(cfg.costs.amortization_weeks, 0)} semanas, do aluguel dos shorts e da "
            "aversão a risco" + (f", com penalidade extra no risco fatorial (λF = "
                                 f"{fm.num(lam_f, 0)} × λ)" if lam_f > 0 else "") + ".")},
        {"rotulo": "Volatilidade", "texto": (
            f"Meta ex-ante de {fm.pct(rk.vol_target_annual, 1)} a.a. dentro da banda "
            f"{fm.pct(rk.vol_band_min, 0)}–{fm.pct(rk.vol_band_max, 0)}; o alpha nunca é "
            "ampliado para alcançar a banda." if not rk.vol_floor_alpha_scaling else
            f"Meta ex-ante de {fm.pct(rk.vol_target_annual, 1)} a.a. dentro da banda "
            f"{fm.pct(rk.vol_band_min, 0)}–{fm.pct(rk.vol_band_max, 0)}.")},
        {"rotulo": "Meta de risco da semana", "texto": (
            "Parte da meta do mandato e da postura do gestor (" + postura_txt + "); nas "
            f"primeiras {rk.bias_prior_weeks} semanas é dividida pelo viés a priori de "
            f"{fm.num(rk.bias_prior, 2)} do risco ex-ante de carteiras otimizadas; fica sempre "
            "dentro da banda. A conta da semana vigente está na formulação da decisão.")},
    ]
    if idio_txt:  # meta e piso de risco específico (com a inflação κF que os mede)
        construcao += [{"rotulo": "Risco idiossincrático", "texto": idio_txt},
                       {"rotulo": "Inflação de 2ª ordem", "texto": kappa_txt}]
    construcao += [
        {"rotulo": "Dimensionamento", "texto": (
            "O peso de cada nome sai do ótimo do objetivo: cresce com o alpha e cai com a "
            "variância residual (aproximadamente o alpha dividido pela variância residual) e com "
            "o custo, limitado pelo menor "
            f"teto — peso do mandato ({fm.pct(rk.max_long_weight, 1)} long, "
            f"{fm.pct(rk.max_short_weight, 1)} short), contribuição de um nome ao risco "
            f"(até {fm.pct(rk.max_single_name_risk_share, 0)} da variância), capacidade do "
            "fechamento, squeeze e visões da pesquisa; posições abaixo de "
            f"{fm.pct(rk.min_position_weight, 1)} do PL não entram.")},
    ]
    if op is not None:
        construcao.append({"rotulo": "Limites operacionais e mandato", "texto": (
            "O otimizador usa o menor entre o limite operacional e o do mandato. Se a carteira "
            "não for viável, os limites operacionais afrouxam até os do mandato (giro até o "
            "dobro); persistindo, a exposição bruta cai à metade e depois a um quarto. O piso "
            "idiossincrático nunca é relaxado.")})
    tabela_limites = []
    if op is not None:
        tabela_limites = [
            {"limite": "Beta previsto", "operacional": fm.num(op.beta, 2),
             "mandato": fm.num(rk.beta_max_abs, 2)},
            {"limite": "Estilo (desvio-padrão × PL)", "operacional": fm.num(op.style, 2),
             "mandato": fm.num(rk.style_exposure_max_abs, 2)},
            {"limite": "Líquido por setor", "operacional": fm.pct(op.sector_net, 1),
             "mandato": fm.pct(rk.sector_net_max_abs, 1)},
            {"limite": "Commodity (Σ peso × beta)", "operacional": fm.pct(op.commodity_beta, 1),
             "mandato": fm.pct(rk.commodity_beta_max_abs, 1)},
        ] + [{"limite": f"Líquido por país ({_pais_pt(k)})",
              "operacional": fm.pct(v, 1), "mandato": fm.pct(rk.country_net_max_abs, 1)}
             for k, v in sorted(op.country_net.items(), key=lambda kv: kv[0] == "*")]

    # --- gestão de risco
    perdas, ref = _controle_perdas(cfg)
    stop_txt = (
        f"Short com perda de {fm.pct(sq.stop_short_position_loss, 0)} desde a entrada ou de "
        f"{fm.pct(sq.stop_short_nav_loss, 1)} do PL é cortado à metade no rebalanceamento "
        "seguinte e o emissor não pode ficar comprado até revisão; "
        f"{sq.stop_escalation_count} shorts distintos em stop em {sq.stop_escalation_sessions} "
        "pregões acionam o modo somente redução de risco."
        if sq.stop_scope == "name" else
        f"Short com perda de {fm.pct(sq.stop_short_position_loss, 0)} desde a entrada ou de "
        f"{fm.pct(sq.stop_short_nav_loss, 1)} do PL aciona o modo somente redução de risco.")
    vetos = [f"aluguel acima de {fm.pct(cfg.shorting.max_borrow_fee, 0)} a.a.",
             f"valor de mercado abaixo de {fm.total(cfg.shorting.min_market_cap_short_usd, 'USD')}",
             "escore de squeeze alto (squeeze médio ou sem dado: teto do nome × "
             f"{fm.num(sq.medium_short_cap_multiplier, 2)})"]
    if sq.enforce_entry_blocks:
        vetos += [f"divulgação de resultado em até {sq.catalyst_block_sessions} pregões",
                  f"free float abaixo de {fm.pct(sq.free_float_min_pct, 0)} (desconhecido em "
                  f"empresa abaixo de {fm.total(sq.free_float_mcap_low_usd, 'USD')}: vetado)"]
    gatilhos = (
        f"Perda do dia abaixo de −{fm.num(gt.SOFT_1D_SIGMAS, 0)}σ diário (alerta) ou de "
        f"−{fm.num(gt.HARD_1D_SIGMAS, 0)}σ / {fm.pct(gt.ABS_HARD_1D, 1)} do PL (redução de "
        f"risco); perda de {gt.WINDOW_5D} pregões abaixo de −{fm.num(gt.SOFT_5D_SIGMAS, 0)}σ ou "
        f"de {fm.pct(gt.ABS_SOFT_5D, 1)} (alerta); σ diário sobre o risco efetivamente tomado, "
        f"entre {fm.pct(gt.SIGMA_FLOOR, 0)} e {fm.pct(gt.SIGMA_CAP, 0)} a.a.")
    gestao = [
        {"rotulo": "Controle de perdas", "texto": "Drawdown a partir do pico — "
         + "; ".join(f"{x['gatilho']}: {x['acao']}" for x in perdas[1:]) + f". Referência: {ref}."},
        {"rotulo": "Stops de squeeze", "texto": stop_txt},
        {"rotulo": "Modo somente redução de risco", "texto": (
            "Acionado por perda extrema, stops ou decisão do gestor: nenhum nome cresce, a vol "
            "ex-ante e a exposição bruta ficam no máximo na metade das da carteira atual, e o "
            "piso idiossincrático vale para a carteira reduzida.")},
        {"rotulo": "Gatilhos diários", "texto": gatilhos},
        {"rotulo": "Estresse e cauda", "texto": (
            f"VaR e ES de 1 dia (99%) até {fm.pct(rk.var_1d_max, 2)} e "
            f"{fm.pct(rk.es_1d_max, 2)} do PL; perda em gap de país até "
            f"{fm.pct(rk.country_stress_max_loss, 1)} do PL (cenários: "
            + _lista_pt([f"{_pais_pt(k)} " + " / ".join(fm.pct(v, 0, True) for v in vs)
                         for k, vs in rk.country_gap_scenarios.items()]) + ").")},
        {"rotulo": "Liquidez", "texto": (
            f"Long até {fm.num(lq.max_days_to_liquidate_long, 0)} e short até "
            f"{fm.num(lq.max_days_to_liquidate_short, 0)} pregões para zerar a "
            f"{fm.pct(lq.participation_rate, 0)} e {fm.pct(lq.short_participation_rate, 0)} do "
            f"volume médio; pelo menos {fm.pct(lq.min_gross_liquid_3d, 0)} da exposição bruta "
            "liquidável em 3 pregões; giro semanal até "
            f"{fm.pct(lq.max_weekly_turnover, 0)} do PL.")},
        {"rotulo": "Vetos de short", "texto": "Sem short novo com " + _lista_pt(vetos) + "."},
    ]
    # --- processo de investimento
    al, rm = cfg.alpha, cfg.risk_model
    pesos = {k: float(v) for k, v in al.signal_weights.items() if v and float(v) > 0}
    soma = sum(pesos.values())
    sinais = [f"{SINAL_PT.get(k, k.replace('_', ' '))} {fm.pct(v / soma, 0)}"
              for k, v in sorted(pesos.items(), key=lambda kv: (-kv[1], kv[0]))] if soma else []
    peso_val = float(al.signal_weights.get("valuation_gap") or al.signal_weights.get("valuation")
                     or 0.0)
    processo = [
        {"rotulo": "Alpha quantitativo", "texto": (
            "Sinais padronizados por emissor"
            + (" — " + _lista_pt(sinais) + " (pesos relativos arredondados, cuja soma pode "
               "diferir de 100%; renormalizados em cada emissor entre os sinais disponíveis) —"
               if sinais else "")
            + " ortogonalizados aos fatores de risco, com horizonte de "
            f"{fm.num(al.horizon_weeks, 0)} semanas.")},
        {"rotulo": "Pesquisa", "texto": (
            "Pesquisa fundamental por emissor, análise de risco de short (squeeze e aluguel) e "
            "leitura macro por país, com fontes públicas. Visões da pesquisa e do gestor só "
            f"inclinam o alpha dentro de um teto de {fm.num(al.max_view_tilt_z, 1)} "
            "desvio-padrão e só restringem risco; nunca ampliam limites do mandato.")},
        {"rotulo": "Cobertura e rating", "texto": (
            "O rating de 12 meses da cobertura é uma opinião de valuation e não dimensiona "
            "posições: a carteira é construída pelo alpha quantitativo neutro. O sinal de "
            "valuation só passa a compor o alpha depois de validado pelo poder de previsão "
            f"realizado (peso atual: {fm.pct(peso_val / soma if soma else 0.0, 0)}).")},
        {"rotulo": "Modelo de risco", "texto": (
            "Modelo fatorial com mercado, países, setores, estilos"
            + (", commodities e dólar" if rm.macro_factors else "")
            + f", estimado com {fm.inteiro(rm.history_days)} pregões de histórico e o ETF "
            f"{rm.market_proxy} como referência de mercado. Mede volatilidade ex-ante, VaR, ES, "
            "contribuições ao risco e cenários de estresse. Parâmetros: meias-vidas de "
            f"{fm.inteiro(rm.halflife_factor_vol)} pregões (volatilidade dos fatores), "
            f"{fm.inteiro(rm.halflife_factor_corr)} (correlações) e "
            f"{fm.inteiro(rm.halflife_specific)} (risco específico); Newey–West com "
            f"{fm.inteiro(rm.newey_west_lags)} defasagens; encolhimento do risco específico de "
            f"{fm.num(rm.specific_shrinkage, 1)}; setor com menos de "
            f"{fm.inteiro(rm.min_names_per_sector)} nomes agrupado; "
            + (f"{len(rm.linked_groups)} grupos de holding e controlada tratados como a mesma "
               "aposta; " if rm.linked_groups else "")
            + ("a escala do alpha (κ) é calibrada a cada semana para a carteira atingir a meta de "
               "volatilidade da semana, com a aversão a risco (λ) do mandato; "
               if cfg.risk.risk_target_mode == "match" else
               "a meta de volatilidade é um teto, com a aversão a risco (λ) do mandato; ")
            + f"fatores com penalidade adicional de {fm.num(cfg.risk.factor_risk_aversion_multiplier, 1)} × λ.")},
        {"rotulo": "Execução e custos", "texto": (
            "Ordens no leilão de fechamento de cada mercado; custos estimados com corretagem por "
            "mercado, meio spread por faixa de liquidez e impacto de mercado.")},
    ]
    rs = cfg.research
    fase = {"S0": "registradas sem efeito na carteira", "S1": "peso pequeno no alpha",
            "S2": "peso intermediário no alpha", "S3": "peso pleno no alpha"}.get(rs.llm_phase, "")
    ia = {"fase": rs.llm_phase, "texto": (
        f"Fase {rs.llm_phase} de adoção das visões da IA ({fase}): coeficiente de informação "
        f"(IC, a correlação entre a visão e o retorno seguinte) efetivo de "
        f"{fm.num(rs.llm_view_ic, 2)}, contra {fm.num(cfg.alpha.information_coefficient, 2)} do "
        f"alpha quantitativo; inclinação máxima de {fm.num(cfg.alpha.max_view_tilt_z, 1)} "
        "desvio-padrão; cada juízo exige "
        f"{rs.samples_per_judgment} amostras com {fm.pct(rs.min_sign_agreement, 0)} de "
        "concordância de sinal" + ("; a IA só restringe risco, nunca amplia limites"
                                   if rs.llm_can_only_tighten else "") + "."),
        "fases": [{"fase": k, "texto": fm.num(v, 2)}
                  for k, v in sorted(rs.llm_view_ic_by_phase.items())]}
    processo.append({"rotulo": "Adoção de IA", "texto": ia["texto"]})
    return {
        "ativa": ativa, "cronograma": cron_out, "inaugural": inaug,
        "neutralizacao": camadas, "construcao": construcao,
        "limites": tabela_limites, "gestao_risco": gestao, "controle_perdas": perdas,
        "processo": processo, "ia": ia,
        "fontes": [{"nome": n, "url": u, "uso": d} for n, u, d, _c in FONTES_PUBLICAS_PT],
    }


def _txt_bp(x: Any) -> str:
    from ..cobertura import formato as fm

    return f"{fm.num(x, 2)} bp" if x is not None else NA_TXT


NA_TXT = "n/d"


def _risco_modelo(prop: Any, records: Sequence[Any], md: Any, cfg: FundConfig,
                  issues: _Issues, *, diagnostics: Mapping[date, dict] | None = None
                  ) -> dict[str, Any] | None:
    """Risco idiossincrático da decisão vigente (decomposição por grupo nos modelos de decisão e
    base, κF, meta e piso), parâmetros do modelo de risco e a série diária monitorada."""
    from ..cobertura import formato as fm

    ov = dict(prop.overrides) if prop is not None and isinstance(prop.overrides, dict) else {}
    rs = ov.get("risco") if isinstance(ov.get("risco"), dict) else None
    form = ov.get("formulacao") if isinstance(ov.get("formulacao"), dict) else {}
    mr = form.get("modelo_risco") if isinstance(form.get("modelo_risco"), dict) else None
    serie = None
    if records:
        try:
            from ..risk.idio import serie_idio

            s = serie_idio(records, md, cfg, diagnostics=diagnostics)
            if s.get("datas"):
                serie = {"datas": s["datas"], "ex_ante": s["ex_ante"],
                         "realizada_63d": s["realizada_63d"], "sem_modelo_63d": s["sem_modelo_63d"],
                         "janela": s.get("janela")}
        except Exception as exc:  # noqa: BLE001 - série é complementar
            issues.add("Série idiossincrática", f"{type(exc).__name__}: {exc}")
    if rs is None and mr is None and serie is None:
        return None
    out: dict[str, Any] = {"disponivel": rs is not None, "serie": serie}
    if rs is not None:
        grupos = []
        pg, pb = rs.get("por_grupo") or {}, rs.get("por_grupo_base") or {}
        fatores = [abs(v) for g in GRUPO_IDIO_PT if g != "especifico"
                   for v in (_num(pg.get(g)), _num(pb.get(g))) if v is not None]
        escala = max(fatores) if fatores and max(fatores) > 0 else None

        def barra(v: Any, g: str) -> str | None:
            # Largura da barra (texto CSS): fatores comuns na escala do maior grupo fatorial;
            # o específico, sem barra (a parte restante da variância).
            x = _num(v)
            if g == "especifico" or x is None or escala is None:
                return None
            return f"{min(abs(x) / escala, 1.0) * 100:.2f}%"

        for g in ("mercado", "pais", "setor", "estilo", "macro", "especifico"):
            if g not in pg and g not in pb:
                continue
            grupos.append({"grupo": g, "rotulo": GRUPO_IDIO_PT[g],
                           "decisao": _num(pg.get(g)), "decisao_texto": fm.pct(pg.get(g), 1),
                           "base": _num(pb.get(g)), "base_texto": fm.pct(pb.get(g), 1),
                           "barra_decisao": barra(pg.get(g), g), "barra_base": barra(pb.get(g), g)})
        kap = rs.get("kappa_f") if isinstance(rs.get("kappa_f"), dict) else {"valor": rs.get("kappa_f")}
        vinc = rs.get("modelo_vinculante")
        out.update({
            "grupos": grupos,
            "idio_decisao_texto": fm.pct(rs.get("idio_decisao"), 1),
            "idio_base_texto": fm.pct(rs.get("idio_base"), 1),
            "meta_texto": fm.pct(rs.get("meta_idio"), 0), "piso_texto": fm.pct(rs.get("piso_idio"), 0),
            "meta": _num(rs.get("meta_idio")), "piso": _num(rs.get("piso_idio")),
            "kappa_texto": fm.num(kap.get("valor"), 2),
            "kappa_fonte": {"config": "valor do mandato", "analitico": "fórmula analítica",
                            "analytic": "fórmula analítica"}.get(str(kap.get("fonte")),
                                                                  kap.get("fonte")),
            "vinculante_texto": MODELO_RISCO_PT.get(str(vinc)) if vinc else None,
            "vol_texto": fm.pct(rs.get("vol_ex_ante"), 2),
            "vol_fatorial_texto": fm.pct(rs.get("vol_fatorial"), 2),
            "vol_especifica_texto": fm.pct(rs.get("vol_especifica"), 2),
            "custo_neutralidade_texto": (f"{fm.num(rs.get('custo_neutralidade_bp'), 1)} bp a.a."
                                         if rs.get("custo_neutralidade_bp") is not None else NA_TXT),
        })
    if mr is not None:
        fpg = mr.get("fatores_por_grupo") or {}
        rot = {"mercado": "Mercado", "pais": "Países", "setor": "Setores", "estilo": "Estilos",
               "macro": "Commodities e dólar"}
        out["fatores"] = [{"grupo": rot.get(g, g), "n": len(fs),
                           "texto": ", ".join(_fator_pt(f) for f in fs)}
                          for g, fs in fpg.items() if isinstance(fs, list)]
        janelas = [f"{j.get('nome')} (× {fm.num(j.get('multiplicador'), 1)})"
                   for j in mr.get("janelas_evento") or [] if isinstance(j, dict)]
        out["parametros"] = [
            {"rotulo": "Data do modelo", "texto": _fdate_pt(mr.get("data"))},
            {"rotulo": "Emissores e fatores", "texto": f"{fm.inteiro(mr.get('n_emissores'))} "
             f"emissores, {fm.inteiro(mr.get('n_fatores'))} fatores"},
            {"rotulo": "Histórico", "texto": f"{fm.inteiro(mr.get('historico_pregoes'))} pregões"},
            {"rotulo": "Meia-vida da volatilidade dos fatores",
             "texto": f"{fm.inteiro(mr.get('meia_vida_vol_fatores'))} pregões"},
            {"rotulo": "Meia-vida das correlações",
             "texto": f"{fm.inteiro(mr.get('meia_vida_correlacao'))} pregões"},
            {"rotulo": "Meia-vida do risco específico",
             "texto": f"{fm.inteiro(mr.get('meia_vida_especifico'))} pregões"},
            {"rotulo": "Correção de autocorrelação (Newey-West)",
             "texto": f"{fm.inteiro(mr.get('newey_west'))} defasagens"},
            {"rotulo": "Encolhimento do risco específico",
             "texto": fm.pct(mr.get("encolhimento_especifico"), 0)},
            {"rotulo": "Referência de mercado", "texto": str(mr.get("proxy_mercado") or NA_TXT)},
        ]
        if mr.get("meia_vida_betas_macro") is not None:
            out["parametros"].append({"rotulo": "Meia-vida dos betas de commodities e dólar",
                                      "texto": f"{fm.inteiro(mr.get('meia_vida_betas_macro'))} "
                                               "pregões"})
        if janelas:
            out["parametros"].append({"rotulo": "Janelas de evento",
                                      "texto": "; ".join(janelas)})
    return out


_FATOR_PT = {"market": "Mercado", "beta": "Beta", "size": "Tamanho", "momentum": "Momentum",
             "resvol": "Vol residual", "value": "Valor", "liquidity": "Liquidez",
             "fx_sens": "Sensibilidade cambial", "BZ=F": "Petróleo Brent", "HG=F": "Cobre",
             "GC=F": "Ouro", "DX-Y.NYB": "Índice do dólar"}


def _fator_pt(f: str) -> str:
    grp, _, nome = str(f).partition(":")
    if not nome:
        return _FATOR_PT.get(grp, grp)
    if grp == "country":
        return {"AR": "Argentina", "BR": "Brasil", "CL": "Chile", "CO": "Colômbia",
                "MX": "México", "PE": "Peru", "LATAM": "Regional (América Latina)"}.get(nome, nome)
    if grp == "sector":
        return SECTOR_PT.get(nome, nome)
    return _FATOR_PT.get(nome, nome)


def _fdate_pt(s: Any) -> str:
    m = re.match(r"^(\d{4})-(\d{2})-(\d{2})", str(s or ""))
    return f"{m.group(3)}/{m.group(2)}/{m.group(1)}" if m else NA_TXT


_ESTILO_EXPR = {"beta": "beta", "size": "tamanho", "momentum": "momentum", "resvol": "vol residual",
                "value": "valor", "liquidity": "liquidez", "fx_sens": "câmbio"}


def _expr_pt(t: Any) -> Any:
    """Nomes e expressões das restrições em pt-BR (setores e estilos pelo rótulo do portal; PL
    no lugar de NAV)."""
    if not isinstance(t, str):
        return t
    t = re.sub(r"(∈ )([A-Za-z][A-Za-z ]+?)(\))", lambda m: m.group(1) + SECTOR_PT.get(m.group(2),
                                                                                  m.group(2))
               + m.group(3), t)
    t = re.sub(r"(xᵢ,)([a-z_]+)", lambda m: m.group(1) + _ESTILO_EXPR.get(m.group(2), m.group(2)), t)
    # países pelo nome; grupos de controle pela palavra "grupo" (a chave interna não aparece)
    t = re.sub(r"(∈ )(AR|BR|CL|CO|MX|PE|UY|PA|US|LATAM)(\))", lambda m: m.group(1)
               + _pais_pt(m.group(2)) + m.group(3), t)
    t = re.sub(r"(∈ )([a-z][a-z0-9_]*)(\))", r"\1grupo\3", t)
    t = re.sub(r" \((?:value|size|momentum|beta)\)", "", t)
    return (t.replace(" vs. mercado LatAm", " contra o mercado latino-americano")
            .replace("Fatia do gross", "Fatia da exposição bruta")
            .replace("× gross", "× exposição bruta").replace("do gross", "da exposição bruta")
            .replace("× NAV", "× PL").replace("NAV", "PL"))


def _custo_txt(custo: Any) -> str:
    """Custo da restrição em bp a.a. do PL (por 1% de folga no limite); abaixo de 0,01 bp
    aparece como "< 0,01 bp a.a." (vincula, mas quase não custa)."""
    from ..cobertura import formato as fm

    x = _num(custo)
    if x is None:
        return NA_TXT
    if 0 < abs(x) < 0.005:
        return "< 0,01 bp a.a."
    return f"{fm.num(x, 2)} bp a.a."


def _formulacao(prop: Any) -> dict[str, Any] | None:
    """Formulação resolvida da decisão vigente: objetivo (termos com coeficiente e valor) e cada
    restrição com limite, valor atingido, folga, se vincula e o custo da restrição (preço-sombra
    em bp a.a. do PL por 1% de folga no limite), em texto pt-BR."""
    from ..cobertura import formato as fm

    ov = dict(prop.overrides) if prop is not None and isinstance(prop.overrides, dict) else {}
    f = ov.get("formulacao")
    if not isinstance(f, dict):
        return None
    obj = f.get("objetivo") or {}
    termos = [{"nome": t.get("nome"), "expressao": t.get("expressao"),
               "coeficiente_texto": fm.num(t.get("coeficiente"), 4),
               "valor_texto": fm.pct(t.get("valor"), 3)}
              for t in obj.get("termos") or [] if isinstance(t, dict)]
    grupos: dict[str, dict[str, Any]] = {}
    n_vinc = 0
    for r in f.get("restricoes") or []:
        if not isinstance(r, dict):
            continue
        chave = str(r.get("chave") or "")
        g, titulo = _grupo_restricao(chave)
        vinc = bool(r.get("vinculante"))
        n_vinc += vinc
        custo = r.get("custo_bp_1pct")
        grupos.setdefault(g, {"grupo": g, "titulo": titulo, "restricoes": []})["restricoes"].append({
            "chave": chave, "nome": _expr_pt(r.get("nome")), "expressao": _expr_pt(r.get("expressao")),
            "limite_texto": _fx(r.get("limite"), chave), "valor_texto": _fx(r.get("valor"), chave),
            "folga_texto": _fx(r.get("folga"), chave), "vinculante": vinc,
            "custo_texto": _custo_txt(custo) if vinc else "—",
            "uso": _num(abs(float(r["valor"])) / abs(float(r["limite"])))
            if _num(r.get("valor")) is not None and _num(r.get("limite")) else None})
    ordem = [g for _, g, _ in GRUPO_RESTRICAO] + ["outras"]
    lista = [grupos[g] for g in dict.fromkeys(ordem) if g in grupos]
    for g in lista:
        g["n"] = len(g["restricoes"])
        g["n_vinculantes"] = sum(1 for r in g["restricoes"] if r["vinculante"])
    par = f.get("parametros") or {}
    solver = str(par.get("solver") or "")
    resolv = (f"otimizador {SOLVER_PT.get(solver.upper(), solver)} (versões fixadas no "
              "repositório)" if solver else NA_TXT)
    vabp = par.get("vol_abaixo_do_piso") if isinstance(par.get("vol_abaixo_do_piso"), dict) else None
    parametros = [
        {"rotulo": "Aversão a risco (λ)", "texto": (
            f"{fm.num(par.get('lambda_efetivo'), 4)} na resolução (mandato "
            f"{fm.num(par.get('lambda_mandato'), 2)} ÷ {fm.num(par.get('divisor_aversao'), 0)} "
            "para alcançar a meta de volatilidade)")
         if par.get("divisor_aversao") not in (None, 1, 1.0) else fm.num(par.get("lambda_mandato"), 2)},
        {"rotulo": "Penalidade de risco fatorial (λF)", "texto": fm.num(par.get("lambda_f"), 2)},
        {"rotulo": "Inflação de 2ª ordem (κF)", "texto": fm.num(par.get("kappa_f"), 2)},
        {"rotulo": "Amortização do custo (H)", "texto": f"{fm.num(par.get('amortizacao_semanas'), 0)} semanas"},
        {"rotulo": "Meta de volatilidade", "texto": fm.pct(par.get("meta_vol"), 2)
         + ("" if par.get("meta_vol_atingida") is not False else " (não atingida)")},
        {"rotulo": "Resolução numérica", "texto": resolv},
    ]
    if isinstance(par.get("idio"), dict):
        parametros.insert(3, {"rotulo": "Fatia idiossincrática atingida", "texto": "; ".join(
            f"{MODELO_RISCO_PT.get(k, k)} {fm.pct(v, 1)}" for k, v in par["idio"].items())})
    if par.get("degraus_escada"):
        parametros.append({"rotulo": "Degraus de viabilidade usados",
                           "texto": ", ".join(str(x) for x in par["degraus_escada"])})
    nota_vol = None
    if vabp:
        motivo = {"custo_alpha": "o custo de negociação consome parte relevante do alpha esperado",
                  "capacidade": "a capacidade do leilão de fechamento limita as posições"}.get(
            str(vabp.get("motivo")), str(vabp.get("motivo") or ""))
        nota_vol = (f"Volatilidade abaixo do piso da banda: {motivo} (custo/alpha "
                    f"{fm.pct(vabp.get('custo_sobre_alpha'), 0)}; {fm.inteiro(vabp.get('no_teto_nome'))} "
                    f"de {fm.inteiro(vabp.get('posicoes'))} posições no teto do nome e "
                    f"{fm.inteiro(vabp.get('no_teto_negociacao'))} no teto de negociação).")
    pn = f.get("por_nome") if isinstance(f.get("por_nome"), dict) else {}
    return {
        "expressao": obj.get("expressao"), "termos": termos, "grupos": lista,
        "n_restricoes": sum(g["n"] for g in lista), "n_vinculantes": n_vinc,
        "parametros": parametros, "nota_vol": nota_vol,
        "contagens": [{"rotulo": r, "texto": fm.inteiro(pn.get(k))} for r, k in (
            ("Posições long", "n_long"), ("Posições short", "n_short"),
            ("Long no teto", "n_no_teto_long"), ("Short no teto", "n_no_teto_short"),
            ("No teto de negociação", "n_no_teto_negociacao"),
            ("Vetados para long", "n_vetados_long"), ("Vetados para short", "n_vetados_short"))
            if pn.get(k) is not None],
    }


def _carteira_modelo(prop: Any, names: Mapping[str, str]) -> dict[str, Any] | None:
    """Dimensionamento e execução por posição da decisão vigente: alpha, tetos (long, short,
    negociação) e a origem do teto que vincula, contribuição ao risco, uso da capacidade do
    leilão de fechamento, fechamentos necessários e emissores congelados."""
    from ..cobertura import formato as fm

    if prop is None:
        return None
    ov = dict(prop.overrides) if isinstance(prop.overrides, dict) else {}
    form = ov.get("formulacao") if isinstance(ov.get("formulacao"), dict) else {}
    cons = ov.get("construcao") if isinstance(ov.get("construcao"), dict) else {}
    lpn = form.get("limites_por_nome") if isinstance(form.get("limites_por_nome"), dict) else {}
    trades = {t.issuer_id: t for t in prop.trades}
    cap = cons.get("capacidade_fechamento") if isinstance(cons.get("capacidade_fechamento"), dict) else {}
    congelados = cap.get("congelados") if isinstance(cap.get("congelados"), dict) else {}
    linhas = []
    for p in sorted(prop.positions, key=lambda t: (-abs(t.weight), t.issuer_id)):
        lim = lpn.get(p.issuer_id) if isinstance(lpn.get(p.issuer_id), dict) else {}
        tr = trades.get(p.issuer_id)
        lado = "long" if p.weight > 0 else "short"
        vinc = lim.get("vinculante")
        negociacao = vinc == "negociacao"
        teto = _num(lim.get("teto_negociacao" if negociacao else f"teto_{lado}"))
        org = lim.get("origem")
        origem = ORIGEM_TETO_PT.get(str(org), ORIGEM_OUTRA) if org else None
        if negociacao:
            dim = (f"No teto de negociação ({origem or 'capacidade do fechamento'}): ordem de até "
                   f"{fm.pct(teto, 2)} do PL nesta montagem.")
        elif vinc:
            dim = f"No teto ({origem or ORIGEM_OUTRA}): {fm.pct(teto, 2)} do PL."
        elif teto is not None:
            dim = (f"Ótimo abaixo do teto: {fm.pct(abs(p.weight), 2)} de {fm.pct(teto, 2)} "
                   f"({origem or ORIGEM_OUTRA}).")
        else:
            dim = "Ótimo do objetivo (sem teto registrado)."
        # Com a execução no fechamento, ``est_days`` da ordem é o número de FECHAMENTOS que ela
        # consome (fração da capacidade de um leilão); sem capacidade, fica ausente.
        fech = _num(tr.est_days) if tr is not None else None
        linhas.append({
            "issuer_id": p.issuer_id, "nome": names.get(p.issuer_id) or p.name, "lado": lado,
            "peso_texto": fm.pct(p.weight, 2, True), "alpha_texto": fm.pct(p.alpha_annual, 2, True),
            "z_texto": fm.num(p.alpha_z, 2, True),
            "risco_texto": fm.pct(p.risk_contribution, 1),
            "teto_texto": fm.pct(teto, 2), "origem_texto": origem or NA_TXT,
            "vinculante": bool(vinc), "teto_negociacao": negociacao, "dimensionamento": dim,
            "ordem_texto": fm.pct(tr.weight_change, 2, True) if tr is not None else "—",
            "uso_capacidade_texto": fm.pct(fech, 1) if fech is not None else "—",
            "fechamentos_texto": (fm.inteiro(max(1, math.ceil(fech - 1e-9))) if fech else
                                  "—"),
            "participacao_texto": fm.pct(tr.pct_adtv, 2) if tr is not None else "—",
            "congelado": congelados.get(p.issuer_id)})
    vetos = cons.get("vetos_short") if isinstance(cons.get("vetos_short"), dict) else {}
    vet_pt = {"bloqueio_free_float": "free float abaixo do mínimo",
              "bloqueio_resultado": "divulgação de resultado próxima",
              "bloqueio_catalisador": "divulgação de resultado próxima"}
    sess = cap.get("sessao")
    return {
        "posicoes": linhas, "n_posicoes": len(linhas),
        "sessao_texto": _fdate_pt(sess) if sess else None,
        "congelados": [{"issuer_id": k, "nome": names.get(k) or k, "motivo": v}
                       for k, v in sorted(congelados.items())],
        "fechamento_antecipado": bool(cap.get("fechamento_antecipado")),
        "vetos_short": [{"issuer_id": k, "nome": names.get(k) or k,
                         "motivo": vet_pt.get(str(v), str(v).replace("_", " "))}
                        for k, v in sorted(vetos.items())],
        "vetos_sem_dado": cons.get("vetos_short_dados_ausentes"),
        "stops": [{"issuer_id": k, "nome": names.get(k) or k} for k in
                  sorted((cons.get("stops_squeeze") or {}) if isinstance(cons.get("stops_squeeze"), dict) else {})],
    }


_VERSAO_RE = re.compile(r"[0-9a-f]{7,40}")


def _auditoria(audit: Mapping[str, Any], integrity: Mapping[str, Any],
               versao: str | None = None) -> dict[str, Any]:
    """Seção "Auditoria e reprodução": resultado da verificação em linguagem de investidor, o que
    é publicado, como conferir, links para o repositório público e o roteiro de reprodução com
    qualquer assistente de IA. ``versao`` (versão do código que gerou a publicação, só no
    portal): os links ficam fixados nela; sem ela (espelho privado), apontam para o ramo
    principal."""
    n = audit.get("n_events")
    ok = bool(audit.get("exists")) and audit.get("chain_ok") is True and integrity.get("ok") is not False
    if ok:
        res = (f"Registro íntegro — {n} evento{'s' if n != 1 else ''} conferido{'s' if n != 1 else ''}"
               if n else "Registro íntegro")
    elif audit.get("exists") and (audit.get("chain_ok") is False or integrity.get("ok") is False):
        res = "Divergência na conferência do registro"
    else:
        res = "Registro ainda não aberto"
    ref = versao if isinstance(versao, str) and _VERSAO_RE.fullmatch(versao) else None
    blob = f"{REPO_URL}/blob/{ref or 'main'}/"
    tree = f"{REPO_URL}/tree/{ref or 'main'}/"

    def link(caminho: str, rotulo: str, desc: str) -> dict[str, str]:
        base = blob if "." in caminho.rsplit("/", 1)[-1] else tree
        return {"rotulo": rotulo, "url": base + caminho, "texto": desc}

    versao_txt = (f"Obtenha a versão {ref[:12]} do código — a que gerou esta publicação — e as "
                  "mesmas versões das bibliotecas usadas nas decisões; a versão de cada decisão "
                  "também fica registrada no livro." if ref else
                  "Obtenha a mesma versão do código e das bibliotecas usadas nas decisões; a "
                  "versão de cada decisão fica registrada no livro.")
    return {
        "resultado": res, "integro": ok, "n_eventos": n,
        "versao": ref[:12] if ref else None,
        "publicado": [
            "Carteira, ordens e decisões de cada semana, com a formulação resolvida do otimizador.",
            "Registro diário encadeado: valor da cota, retorno, risco e atribuição.",
            "Tese de investimento, relatórios e notas de pesquisa, com os fatos calculados pelo "
            "código.",
            "Modelos abertos de cobertura: insumos públicos com fonte e data, fórmulas com os "
            "valores substituídos e preços-alvo de 12 meses.",
            "Mandato, parâmetros dos modelos e a trilha de auditoria encadeada.",
        ],
        "passos": [
            {"titulo": "Obtenha a mesma versão", "texto": versao_txt},
            {"titulo": "Confira os registros", "texto": (
                "A verificação refaz a cadeia de eventos da trilha, os registros diários e os "
                "códigos de verificação de cada arquivo publicado.")},
            {"titulo": "Recalcule modelos e decisões", "texto": (
                "Os modelos de cobertura são recalculados a partir dos insumos públicos arquivados "
                "(diferença relativa de até 0,001%); a decisão de cada semana é refeita sobre a "
                "versão do código da decisão (diferença de até 1 ponto-base por posição).")},
            {"titulo": "Refaça os passos da IA", "texto": (
                "Cada etapa da IA é exportada como um pacote autossuficiente (fatos, esquema e "
                "regras) que pode ser usado em qualquer assistente de IA por assinatura; a "
                "resposta é validada pelos mesmos validadores do processo.")},
        ],
        "documentos": [link(*d) for d in DOCS_AUDITORIA],
        "configuracao": [link(*d) for d in CONFIG_AUDITORIA],
        "codigo": [link(*d) for d in CODIGO_AUDITORIA],
        "repositorio": REPO_URL + (f"/tree/{ref}" if ref else ""), "portal": PORTAL_URL,
        "dados_abertos": PORTAL_URL + "dados/",
    }


def _cadeia_meta(cfg: FundConfig, prop: Any, posture: str | None, drawdown: float | None
                 ) -> list[dict[str, str]]:
    """Como a meta de volatilidade e a exposição bruta máxima da decisão vigente foram obtidas
    (mandato → postura → viés a priori), com as mesmas funções da decisão
    (:func:`cdp.research.pm_agent.posture_limits`,
    :func:`cdp.workflow.tese_analise.vol_target_basis`)."""
    from ..cobertura import formato as fm
    from ..research.pm_agent import POSTURE_MAP, posture_limits
    from .tese_analise import vol_target_basis

    ov = dict(prop.overrides) if prop is not None and isinstance(prop.overrides, dict) else {}
    applied, gross = _num(ov.get("vol_target")), _num(ov.get("gross_max"))
    if applied is None:
        return []
    rk = cfg.risk
    lim = None
    if posture in POSTURE_MAP:
        try:
            lim = posture_limits(str(posture), cfg, drawdown)
        except ValueError:
            lim = None
    post_vol = lim.vol_target if lim is not None else None
    basis = vol_target_basis(applied, post_vol, cfg)
    passos = [f"mandato {fm.pct(rk.vol_target_annual, 2)}"]
    if lim is not None:
        passos.append(f"postura {POSTURE_PT.get(lim.effective, lim.effective)} "
                      f"{fm.pct(lim.vol_target, 2)}")
    if basis in ("vies_postura", "vies_mandato"):
        passos.append(f"÷ {fm.num(rk.bias_prior, 2)} (viés a priori nas primeiras "
                      f"{rk.bias_prior_weeks} semanas)")
    txt = " → ".join(passos) + f" = {fm.pct(applied, 2)}"
    if basis == "piso":
        txt = f"{fm.pct(applied, 2)}: piso da banda do mandato"
    elif basis == "outro":
        txt += " (ajustada pelos controles de risco da semana)"
    out = [{"rotulo": "Meta de volatilidade da semana", "texto": txt}]
    if gross is not None:
        share = POSTURE_MAP.get(lim.effective, (None, None))[1] if lim is not None else None
        out.append({"rotulo": "Exposição bruta máxima da semana", "texto": (
            f"{fm.pct(gross, 0)} do PL"
            + (f" (postura {POSTURE_PT.get(lim.effective, lim.effective)}: {fm.num(share, 2)} × "
               f"{fm.pct(rk.gross_max, 0)} do mandato)"
               if share is not None and abs(share * rk.gross_max - gross) < 1e-6 else ""))})
    return out


def _modelo_aberto(rt: Any, cfg: FundConfig, live: Any, records: Sequence[Any],
                   audit: Mapping[str, Any], integrity: Mapping[str, Any], now: datetime,
                   names: Mapping[str, str], issues: _Issues, *,
                   weeks: Sequence[Mapping[str, Any]] = (),
                   inaugural: Mapping[str, Any] | None = None,
                   versao: str | None = None) -> dict[str, Any]:
    """Modelo aberto da carteira (aba Mandato e metodologia, Risco, Carteira e Comitê): textos e
    números em pt-BR montados aqui; a página só exibe."""
    tz = ZoneInfo(cfg.fund.timezone)
    hoje = now.astimezone(tz).date()
    md = None
    if records:
        try:
            md = rt.store.load(as_of=records[-1].date)
        except Exception:  # noqa: BLE001 - base indisponível: a série "sem modelo" fica n/d
            md = None
    out: dict[str, Any] = {
        "metodologia": _metodologia(cfg, hoje, inaugural),
        "auditoria": _auditoria(audit, integrity, versao),
        "risco": None, "formulacao": None, "carteira": None,
        "semana": getattr(live, "week", None),
    }
    if live is not None:
        from .risco_diario import read_measures

        try:
            diagnostics = read_measures(rt.track(), market_loader=rt.store.load,
                                        market_root=getattr(rt.store, "root", None))
        except (ValueError, OSError, KeyError) as exc:
            diagnostics = {}
            issues.add("Risco diário base/evento", str(exc))
        out["risco"] = _risco_modelo(live, records, md, cfg, issues,
                                    diagnostics=diagnostics)
        out["formulacao"] = _formulacao(live)
        out["carteira"] = _carteira_modelo(live, names)
        if out["formulacao"] is not None:
            semana = next((w for w in weeks if w.get("week") == live.week), None) or {}
            pm = semana.get("pm_decision") if isinstance(semana.get("pm_decision"), dict) else {}
            antes = [r for r in records if r.date < live.week]
            dd = _num(antes[-1].risk.drawdown) if antes else None
            try:
                cadeia = _cadeia_meta(cfg, live, pm.get("risk_posture"), dd)
            except Exception as exc:  # noqa: BLE001 - a conta da meta é complementar
                issues.add("Meta de risco da semana", f"{type(exc).__name__}: {exc}")
                cadeia = []
            out["formulacao"]["parametros"] = cadeia + out["formulacao"]["parametros"]
    return out


def _rotulos(data: Mapping[str, Any]) -> dict[str, dict[str, str]]:
    """Rótulos pt-BR dos códigos de fator e de restrição citados no retrato (a página mostra o
    rótulo; o código nunca aparece): ``fatores`` (``factor``) e ``restricoes`` (restrições que
    vinculam na solução de cada semana)."""
    fatores: set[str] = set()
    restricoes: set[str] = set()

    def walk(x: Any) -> None:
        if isinstance(x, dict):
            for k, v in x.items():
                if k == "factor" and isinstance(v, str):
                    fatores.add(v)
                elif k == "binding_constraints" and isinstance(v, list):
                    restricoes.update(str(c) for c in v)
                else:
                    walk(v)
        elif isinstance(x, list):
            for v in x:
                walk(v)

    walk({k: v for k, v in data.items() if k != "meta"})
    form = (data.get("modelo") or {}).get("formulacao") or {}
    nomes = {str(r.get("chave")): str(r.get("nome")) for g in form.get("grupos") or []
             for r in g.get("restricoes") or [] if r.get("chave") and r.get("nome")}
    return {"fatores": {f: _fator_rotulo(f) for f in sorted(fatores)},
            "restricoes": {c: nomes.get(c) or _restricao_pt(c, data) for c in sorted(restricoes)}}


def _fator_rotulo(f: str) -> str:
    """Rótulo de um fator do modelo de risco ou da atribuição (``country:BR`` ⇒ "Brasil",
    ``macro:BZ=F`` ⇒ "Petróleo Brent", ``commodity:oil`` ⇒ "Commodity: petróleo")."""
    grp, _, nome = str(f).partition(":")
    if nome and grp == "commodity":
        return f"Commodity: {COMMODITY_PT.get(nome, nome.replace('_', ' '))}"
    if nome and grp in ("theme", "tema"):
        return f"Tema: {THEME_PT.get(nome, nome.replace('_', ' '))}"
    if nome and grp == "country":
        return "Regional (América Latina)" if nome == "LATAM" else _pais_pt(nome)
    return _fator_pt(f)


def _restricao_pt(c: str, data: Mapping[str, Any]) -> str:
    """Nome pt-BR de uma restrição do otimizador pela chave (``country_share:BR``,
    ``op_country:CL``, ``max_long:<emissor>``, ``theme:evento:BR:2026-10-05``...)."""
    nomes = (data.get("meta") or {}).get("issuer_names") or {}
    simples = {"net_exposure": "exposição líquida do mandato", "gross": "exposição bruta máxima",
               "gross_min": "exposição bruta mínima", "beta": "beta previsto",
               "turnover": "giro semanal", "vol": "meta de volatilidade",
               "vol_target": "meta de volatilidade", "factor_risk": "teto de risco fatorial",
               "idio": "piso de risco específico"}
    k, _, v = str(c).partition(":")
    if not v:
        return simples.get(k, k.replace("_", " "))
    if k in ("max_long", "max_short", "max_trade", "max_trade_liq"):
        lado = {"max_long": "teto do long", "max_short": "teto do short",
                "max_trade": "teto de negociação", "max_trade_liq": "teto de negociação"}[k]
        return f"{lado} — {nomes.get(v) or v}"
    if k == "country":
        return f"líquido de {_pais_pt(v)} (mandato)"
    if k == "op_country":
        return f"líquido de {_pais_pt(v)} (limite operacional)"
    if k == "country_share":
        return f"fatia da exposição bruta — {_pais_pt(v)}"
    if k == "sector":
        return f"líquido do setor {SECTOR_PT.get(v, v)}"
    if k == "style":
        return f"estilo {STYLE_PT.get(v, v).lower()}"
    if k in ("theme", "tema"):
        g2, _, r2 = v.partition(":")
        if g2 == "commodity":
            return f"commodity {COMMODITY_PT.get(r2, r2)}"
        if g2 == "evento":
            pais, _, dia = r2.partition(":")
            return f"evento em {_pais_pt(pais)}" + (f" ({_fdate_pt(dia)})" if dia else "")
        return f"tema {THEME_PT.get(v, v.replace('_', ' '))}"
    if k == "commodity":
        return f"commodity {COMMODITY_PT.get(v, v)}"
    if k.startswith("factor_risk") or k.startswith("factor_hold"):
        return f"risco fatorial — {_fator_rotulo(v)}"
    if k.startswith("linked"):
        return f"grupo de controle — {v.replace('_', ' ')}"
    return f"{k.replace('_', ' ')} — {v.replace('_', ' ')}"


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
                max_risk_full_runs: int = DEFAULT_RISK_FULL_RUNS,
                versao: str | None = None) -> dict[str, Any]:
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
    o nome de todo emissor citado. ``versao``: versão do código que gera a publicação do portal
    (os links de "Auditoria e reprodução" ficam fixados nela; sem ela, no ramo principal).
    """
    from ..ui.data import CDP_INVARIANTS, kill_switch_state
    from . import rotulos as R
    from .painel_publicacao import PROFILES, publicacao, site
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
        "paper_trading_label": R.aviso(cfg.fund.track_record_type),
        "paper_trading_text": PAPER_TRADING_TEXT,
        "base_currency": cfg.fund.base_currency, "inception_date": cfg.fund.inception_date,
        "inception_nav_usd": cfg.fund.inception_nav_usd, "manager": cfg.fund.manager_name,
        "config_hash": cfg.config_hash(), "mandate": _mandate(cfg),
        "data_sources": None if is_synth else FONTES_RODAPE,
        "coverage": _coverage_meta(rt, issues),
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
    modelo = _modelo_aberto(rt, cfg, live, records, audit, integrity, now,
                            universe_names, issues, weeks=weeks,
                            inaugural=status.get("inaugural"), versao=versao)
    data = {
        "meta": meta, "status": status, "track_record": track, "latest_day": latest,
        "risk": risk, "weeks": weeks, "daily_reports": daily_reports,
        "reports_index": reports_index,
        "risk_monitor": _risk_monitor(rt, issues, max_risk_runs, max_risk_full_runs),
        "backtests": backtests, "audit": audit, "modelo": modelo, "issues": issues.items,
    }
    data = clean(data)
    data["meta"]["issuer_names"] = clean(_issuer_names(data, universe_names))
    data["meta"]["rotulos"] = clean(_rotulos(data))
    data["meta"]["data_hash"] = data_hash(data)
    if profile == "publicacao":
        return publicacao(data, reports_dir=_reports_label(rt), page_sha256=page_sha256())
    if profile == "site":
        return site(data, page_sha256=page_sha256())
    return data


# ==========================================================
# Cobertura de ativos (dados da aba, gerados por painel_cobertura)
# ==========================================================

def _painel_cobertura() -> Any:
    """O módulo dos dados da aba "Cobertura de ativos" (:mod:`cdp.workflow.painel_cobertura`),
    ou ``None`` se ainda não existir no código."""
    try:
        from . import painel_cobertura
    except ImportError:
        return None
    return painel_cobertura


def _coverage_meta(rt: Any, issues: _Issues) -> dict[str, Any] | None:
    """Resumo da cobertura para ``meta.coverage`` (≤ 300 B): a página só mostra a aba com dados
    e os botões "Ficha do ativo" quando ``disponivel``. Vem de ``painel_cobertura.resumo(rt)``;
    sem ele, da existência de um retrato em ``<livro>/cobertura/<data>/``. O registro da
    cobertura é conferido (cadeia e selo, como na leitura dos modelos): com divergência, a aba
    fica indisponível (``estado = "em_verificacao"``) e o resto do portal segue publicado."""
    pc = _painel_cobertura()
    if pc is None:
        return None
    fn = getattr(pc, "resumo", None)
    if callable(fn):
        try:
            r = fn(rt)
        except Exception as exc:  # noqa: BLE001 - cobertura é complementar ao painel
            issues.add("Cobertura", f"{type(exc).__name__}: {exc}")
            return {"disponivel": False, "estado": "em_verificacao"}
        if not isinstance(r, dict):
            return None
        out = dict(r, disponivel=bool(r.get("disponivel", True)))
    else:
        base = Path(rt.book_root) / "cobertura"
        datas = (sorted(p.name for p in base.iterdir() if p.is_dir() and _WEEK_DIR_RE.match(p.name))
                 if base.is_dir() else [])
        if not datas:
            return None
        out = {"disponivel": True, "as_of": datas[-1]}
    if out.get("disponivel"):
        problema = _registro_cobertura_divergente(Path(rt.book_root))
        if problema:
            issues.add("Cobertura", problema)
            out = {"disponivel": False, "estado": "em_verificacao", "as_of": out.get("as_of")}
    return clean(out)


def _registro_cobertura_divergente(book: Path) -> str | None:
    """Problema na cadeia ou no selo do registro da cobertura (``None`` se íntegro) — a mesma
    conferência de ``cobertura.livro.ultimo_snapshot``, sem ler os modelos."""
    try:
        from ..cobertura import livro as L

        ok, probs = L.verificar_livro(book)
        if not ok:
            return "; ".join(probs)
        ok_s, msg = L.selado(book)
        return None if ok_s else msg
    except Exception as exc:  # noqa: BLE001 - registro ilegível
        return f"{type(exc).__name__}: {exc}"


def _cobertura_em_verificacao(pc: Any) -> dict[str, str]:
    """``cobertura.json`` institucional (sem modelos) quando o registro da cobertura não pôde
    ser lido ou conferido: estado ``"em_verificacao"``."""
    from .painel_publicacao import dump_publicacao

    base = pc.exportar(None)
    try:
        nome = getattr(pc, "ARQUIVO", "cobertura.json")
        obj = json.loads(base[nome])
        obj["meta"]["estado"] = "em_verificacao"
        obj["meta"].pop("data_hash", None)
        obj["meta"]["data_hash"] = data_hash(obj)
        return {nome: dump_publicacao(obj)}
    except Exception:  # noqa: BLE001 - forma inesperada: o aviso "sem cobertura" do módulo
        return dict(base)


def arquivos_cobertura(rt: Any, *, perfil: str = "publicacao",
                       painel: Mapping[str, Any] | None = None,
                       erros: list[str] | None = None) -> dict[str, str]:
    """Arquivos de dados da aba "Cobertura de ativos" (``{nome: texto}``; nomes
    ``cobertura*.json``), exportados por :mod:`cdp.workflow.painel_cobertura` a partir do livro da
    cobertura, dos fechamentos da base de mercado e da carteira vigente (``painel``: retrato do
    painel). ``perfil="publicacao"``: cada arquivo ≤ 260 KB e linhas ≤ 1.500 (cortes
    progressivos de ``cobertura.json``); ``"site"``: sem cortes. Sem o módulo, vazio; sem retrato
    de cobertura, só ``cobertura.json`` com o aviso institucional. Falha na leitura ou na
    conferência do registro da cobertura nunca derruba o portal: sai só ``cobertura.json`` com o
    estado ``"em_verificacao"`` e a mensagem vai para ``erros``."""
    pc = _painel_cobertura()
    if pc is None:
        return {}
    md = None
    try:
        last = rt.store_last_date()
        md = rt.store.load(as_of=last) if last is not None else None
    except Exception:  # noqa: BLE001 - sem base: preços dos próprios retratos
        md = None
    try:
        ent = pc.carregar(Path(rt.book_root), md=md, carteira=pc.carteira_do_painel(painel),
                          repositorio=REPO, page_sha256=page_sha256())
        if perfil == "site":
            sem = 10**9
            out = pc.exportar(ent, niveis=(pc.Limites(revisoes=sem, etf_top=sem, ic_semanas=sem),))
        else:
            out = pc.exportar(ent)
    except Exception as exc:  # noqa: BLE001 - cobertura é complementar ao portal
        if erros is not None:
            erros.append(f"{type(exc).__name__}: {exc}")
        out = _cobertura_em_verificacao(pc)
    bad = sorted(k for k in out if not COBERTURA_RE.fullmatch(str(k)))
    if bad:
        raise ValueError("arquivos de cobertura com nome fora do padrão cobertura*.json: "
                         + ", ".join(bad))
    return {str(k): str(v) for k, v in sorted(out.items())}


def cobertura_publicada(out_dir: Path | str = DEFAULT_OUT_DIR) -> dict[str, str]:
    """``{arquivo: sha256}`` dos dados da cobertura publicados por último no artifact
    (``COBERTURA_PUBLICADA.json``; vazio se ainda não houve publicação)."""
    try:
        raw = json.loads((Path(out_dir) / COBERTURA_MARKER).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    arqs = raw.get("arquivos") if isinstance(raw, dict) else None
    return {str(k): str(v) for k, v in (arqs or {}).items()
            if COBERTURA_RE.fullmatch(str(k)) and re.fullmatch(r"[0-9a-f]{64}", str(v))}


def cobertura_local(out_dir: Path | str = DEFAULT_OUT_DIR) -> dict[str, str]:
    """``{arquivo: sha256}`` dos dados da cobertura gravados agora na pasta do painel."""
    out = Path(out_dir)
    if not out.is_dir():
        return {}
    return {p.name: _sha256_file(p) or "" for p in sorted(out.glob("cobertura*.json"))
            if COBERTURA_RE.fullmatch(p.name)}


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


def modulos() -> dict[str, str]:
    """Fontes dos módulos da página presentes no código (``{nome: texto}``, ordem fixa). Um
    módulo nunca contém o fechamento literal do elemento de script (vai embutido na cópia
    local)."""
    out = {}
    for nome, arq in MODULOS.items():
        path = MODULOS_DIR / arq
        if not path.is_file():
            continue
        texto = path.read_text(encoding="utf-8")
        if "</script" in texto.lower():
            raise ValueError(f"{arq}: o módulo não pode conter o fechamento do elemento de script")
        out[nome] = texto.strip("\n") + "\n"
    return out


def _version(template: str, mods: Mapping[str, str] | None = None) -> str:
    mods = modulos() if mods is None else mods
    corpo = "".join(f"\n{nome}\n{texto}" for nome, texto in sorted(mods.items()))
    return hashlib.sha256(f"{PAGE_LAYOUT}\n{template}{corpo}".encode()).hexdigest()


def page_sha256(template_path: Path | str | None = None) -> str:
    """Versão da página: SHA-256 do formato de publicação (``PAGE_LAYOUT``), do template e dos
    módulos (:func:`modulos`) — muda só quando um deles muda. Vai carimbada no ``index.html``, no
    script versionado, na cópia local e em ``data.json`` (``meta.page_sha256``)."""
    return _version(_template(template_path))


def _split_template(template_path: Path | str | None) -> tuple[str, str]:
    template = _template(template_path)
    sha = _version(template)
    head, tail = template.split(DATA_ELEMENT)
    return head.replace(PAGE_SHA_PLACEHOLDER, sha), tail.replace(PAGE_SHA_PLACEHOLDER, sha)


def render_painel(data: Mapping[str, Any], template_path: Path | str | None = None,
                  arquivos: Mapping[str, Any] | None = None) -> str:
    """Injeta o JSON do painel no template (no elemento ``<script id="cdp-data">``), com os
    módulos da página embutidos antes dele e, opcionalmente, os ``arquivos`` de dados da
    cobertura (``{nome: texto JSON}``) num elemento
    ``<script type="application/json" id="cdp-cobertura-dados">`` com ``{arquivo: dados}`` (o
    mesmo de ``painel_cobertura.embutir``) — a cópia local abre offline, sem buscar nada."""
    head, tail = _split_template(template_path)
    mods = "".join(f"<script>\n{texto}</script>\n" for _n, texto in sorted(modulos().items()))
    extras = ""
    if arquivos:
        dados = {n: json.loads(t) if isinstance(t, str) else t for n, t in sorted(arquivos.items())}
        extras = (f'<script type="application/json" id="cdp-cobertura-dados">{embed_json(dados)}'
                  "</script>\n")
    element = DATA_ELEMENT.replace(PLACEHOLDER, embed_json(data))
    return head + mods + extras + element + tail


def asset_names(version: str) -> tuple[str, str]:
    """Nomes do estilo e do script versionados de uma versão da página."""
    stem = f"{ASSET_PREFIX}{version[:16]}"
    return f"{stem}.css", f"{stem}.js"


def module_names(version: str) -> dict[str, str]:
    """Nome versionado de cada módulo presente (``painel-<16 hex>-<nome>.js``)."""
    return {nome: f"{ASSET_PREFIX}{version[:16]}-{nome}.js" for nome in modulos()}


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
    """Estilo, script e módulos da página, versionados (``painel-<versão>.css``/``.js`` e
    ``painel-<versão>-<nome>.js``)."""
    parts = _page_parts(template_path)
    version = page_sha256(template_path)
    css_name, js_name = asset_names(version)
    out = {css_name: parts["css"], js_name: parts["js"]}
    mods = modulos()
    out.update({module_names(version)[nome]: texto for nome, texto in mods.items()})
    return out


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
    publicação bem-sucedida que incluiu a página; até lá ``page_changed`` continua verdadeiro.
    Os dados da cobertura só são registrados (``COBERTURA_PUBLICADA.json``) quando a checagem
    os incluiu na publicação (:func:`cdp.workflow.painel_artifact.plano_cobertura`, refeito
    aqui com a mesma pasta); senão o marcador fica como estava."""
    from .painel_artifact import plano_cobertura

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
    plano = plano_cobertura(out, page_changed=before != sha)
    marker = out / MARKER_NAME
    if before != sha:
        _write_atomic(marker, sha + "\n")
    # Dados da cobertura: só o que a checagem incluiu na publicação (o conjunto inteiro da pasta).
    cob_antes = cobertura_publicada(out)
    cob = cobertura_local(out) if plano["incluida"] else cob_antes
    cob_marker = out / COBERTURA_MARKER
    if plano["incluida"] and (cob != cob_antes or (cob and not cob_marker.is_file())):
        _write_atomic(cob_marker, json.dumps({"arquivos": cob}, ensure_ascii=False, indent=1,
                                             sort_keys=True) + "\n")
    return {"marcador": marker.as_posix(), "page_sha256": sha, "anterior": before,
            "mudou": before != sha, "marcador_cobertura": cob_marker.as_posix(),
            "cobertura_incluida": plano["incluida"], "cobertura_motivo": plano["motivo"],
            "cobertura_mudou": cob != cob_antes, "cobertura_arquivos": sorted(cob)}


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
    erros_cob: list[str] = []
    cob = arquivos_cobertura(rt, perfil="publicacao", painel=full, erros=erros_cob)
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
    cob_info, cob_removed = [], []
    for name, texto in cob.items():
        path = out / name
        if _sha256_file(path) != hashlib.sha256(texto.encode("utf-8")).hexdigest():
            _write_atomic(path, texto)
        cob_info.append(_file_info(path, texto))
    for old in sorted(out.glob("cobertura*.json")):
        if COBERTURA_RE.fullmatch(old.name) and old.name not in cob:
            old.unlink()
            cob_removed.append(old.name)
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
        "cobertura": [{"path": a["path"], "bytes": a["bytes"], "sha256": a["sha256"],
                       "max_line": a["max_line"]} for a in cob_info],
        "cobertura_removidos": cob_removed, "cobertura_erro": "; ".join(erros_cob) or None,
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
        local = STANDALONE_HEAD + render_painel(full, template_path, cob) + STANDALONE_TAIL
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
           "COBERTURA_MARKER", "COBERTURA_RE", "MODULOS", "arquivos_cobertura", "asset_names",
           "clean", "cobertura_local", "cobertura_publicada", "data_hash", "embed_json",
           "expandir", "mark_published", "module_names", "modulos", "page_assets", "page_sha256",
           "page_version", "painel_data", "published_page_sha", "referenced_issuers",
           "render_page", "render_painel", "scrub_text", "to_json", "write_painel"]
