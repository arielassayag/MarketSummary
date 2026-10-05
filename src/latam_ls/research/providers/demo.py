"""Provedor DEMO: regras determinísticas, offline, sem aleatoriedade (rótulo explícito).

Trabalha somente com o ``context`` estruturado de cada tarefa (não interpreta o prompt) e
produz saídas que respeitam os mesmos schemas e guardrails de um LLM real: textos sem
algarismos, números apenas via ``{{fact:<id>}}`` de fatos existentes e cada afirmação citando
os ids de evidência usados. Serve para testes, demonstração e como linha de base auditável.
"""

from __future__ import annotations

import math
import re
import unicodedata
from typing import Any

from pydantic import BaseModel

from ..guardrails import detect_injection, is_injection_flagged
from ..schemas import (
    AnalystOutput,
    DebateOutput,
    Driver,
    JudgeOutput,
    MacroOutput,
    NewsAssessment,
    NewsOutput,
    ShortRiskOutput,
)
from .base import LLMProvider, LLMResult, error_result

DEMO_NAME = "demo"
DEMO_MODEL_LABEL = "demo (regras determinísticas)"

STANCE_THRESHOLDS = ((1.5, 2), (0.5, 1), (-0.5, 0), (-1.5, -1))
"""alpha_z >= 1,5 ⇒ +2; >= 0,5 ⇒ +1; > −0,5 ⇒ 0; > −1,5 ⇒ −1; senão −2."""

_STANCE_LABEL = {2: "fortemente comprador", 1: "comprador", 0: "neutro", -1: "vendedor",
                 -2: "fortemente vendedor"}
_BUCKET_LABEL = {"HIGH": "alta", "MEDIUM": "média", "LOW": "baixa", "NA": "indeterminada"}
_COUNTRY_BENCH = {"BR": "EWZ", "MX": "EWW", "CL": "ECH", "CO": "GXG", "PE": "EPU", "AR": "ARGT"}
_COUNTRY_RATE = {"BR": "SELIC"}

_POSITIVE = (
    "acima do consenso", "acima das expectativas", "supera", "superou", "recorde", "lucro sobe",
    "lucro cresce", "eleva guidance", "eleva projecao", "aumenta dividendo", "recompra",
    "eleva recomendacao", "upgrade", "beats", "beat estimates", "raises guidance",
    "record profit", "por encima", "supera estimaciones", "utilidad sube", "ganancia record",
)
_NEGATIVE = (
    "abaixo do consenso", "abaixo das expectativas", "prejuizo", "investigacao", "multa",
    "fraude", "processo", "rebaixa", "downgrade", "lucro cai", "queda do lucro",
    "recuperacao judicial", "calote", "default", "renuncia", "misses", "probe",
    "investigation", "lawsuit", "por debajo", "perdida", "investigacion", "demanda", "quiebra",
)
_EVENT_RULES: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("m&a", ("aquisicao", "fusao", "incorporacao", "adquire", "merger", "acquisition",
             "acquire", "adquisicion", "fusion", "opa")),
    ("regulatory", ("regulat", "regulador", "cvm", "anvisa", "aneel", "anatel", "cade",
                    "antitruste", "antitrust", "cnbv", "cmf")),
    ("legal", ("processo", "justica", "tribunal", "acao judicial", "lawsuit", "court", "demanda",
               "litigio", "fraude")),
    ("earnings", ("lucro", "resultado", "balanco", "receita", "ebitda", "earnings", "utilidad",
                  "ganancia", "trimestre", "consenso")),
    ("guidance", ("guidance", "projecao", "projecoes", "perspectiva", "outlook")),
    ("capital", ("emissao", "follow-on", "ipo", "recompra", "dividendo", "debenture",
                 "buyback", "dividend", "aumento de capital")),
    ("governance", ("governanca", "conselho", "controlador", "assembleia", "governance",
                    "board", "auditoria")),
    ("management", ("ceo", "presidente", "diretor", "cfo", "management", "nomeia")),
    ("macro", ("juros", "selic", "inflacao", "cambio", "pib", "banxico", "copom", "tarifa",
               "fiscal")),
)


def _norm(text: str) -> str:
    decomposed = unicodedata.normalize("NFKD", text or "")
    return "".join(c for c in decomposed if not unicodedata.combining(c)).lower()


def _has(text: str, words: tuple[str, ...]) -> int:
    return sum(1 for w in words if re.search(rf"(?<![a-z]){re.escape(w)}", text))


def _finite(x: Any) -> float | None:
    if x is None or isinstance(x, bool):
        return None
    try:
        v = float(x)
    except (TypeError, ValueError):
        return None
    return v if math.isfinite(v) else None


def stance_from_alpha(alpha_z: float) -> int:
    for threshold, stance in STANCE_THRESHOLDS:
        if alpha_z >= threshold:
            return stance
    return -2


def _ph(fact_id: str) -> str:
    return "{{fact:" + fact_id + "}}"


class DemoResearchProvider(LLMProvider):
    """Provedor determinístico de demonstração (sem rede, sem chave, sem aleatoriedade)."""

    name = DEMO_NAME
    model = DEMO_MODEL_LABEL
    deterministic = True

    def complete_json(self, system: str, user: str, schema: type[BaseModel], *, task: str,
                      temperature: float = 0.0, sample: int = 0,
                      context: dict | None = None) -> LLMResult:
        ctx = context or {}
        handlers = {
            "analyst": self._analyst, "news": self._news, "short_risk": self._short_risk,
            "macro": self._macro, "debate_bull": self._debate, "debate_bear": self._debate,
            "judge": self._judge,
        }
        handler = handlers.get(task)
        if handler is None:
            return error_result(self.name, self.model, f"Tarefa desconhecida no modo demo: {task}",
                                deterministic=True)
        try:
            out = handler(ctx, task)
        except (KeyError, TypeError, ValueError) as exc:
            return error_result(self.name, self.model,
                                f"Contexto insuficiente para a tarefa {task} no modo demo: {exc}",
                                deterministic=True)
        if not isinstance(out, schema):
            return error_result(self.name, self.model,
                                f"Schema pedido ({schema.__name__}) incompatível com a tarefa "
                                f"{task}.", deterministic=True)
        return LLMResult(parsed=out, raw_text=out.model_dump_json(), provider=self.name,
                         model=self.model, latency_ms=0.0, usage=None, cost_usd=0.0, error=None,
                         deterministic=True, stop_reason="end_turn")

    # ------------------------------------------------------------------ R3 analista
    def _analyst(self, ctx: dict, task: str) -> AnalystOutput:
        iid = str(ctx["issuer_id"])
        facts: dict[str, Any] = dict(ctx.get("facts") or {})
        alpha_id = f"{iid}.alpha_z"
        az = _finite(ctx.get("alpha_z"))
        if az is None:
            return AnalystOutput(
                thesis="Abstenção: alpha composto indisponível para o emissor; sem base "
                       "quantitativa verificável (modo demo).",
                data_gaps=["alpha composto ausente"], abstain=True, stance=0,
                p_outperform=0.5, confidence=0.0)
        stance = stance_from_alpha(az)
        sig_ids = sorted(f for f in facts if f.startswith(f"{iid}.sig_") and f.endswith("_z"))
        scored = [alpha_id] + sig_ids if alpha_id in facts else sig_ids
        available = [f for f in scored if _finite(facts.get(f)) is not None]
        coverage = len(available) / len(scored) if scored else 0.0
        confidence = round(0.3 + 0.5 * coverage, 4)

        drivers: list[Driver] = []
        risks: list[Driver] = []
        if alpha_id in facts:
            text = ("Alpha composto em " + _ph(alpha_id) +
                    (" próximo da neutralidade" if stance == 0 else
                     f" indica viés {_STANCE_LABEL[stance]}"))
            drivers.append(Driver(text=text, evidence_ids=[alpha_id]))
        sign = 1 if stance >= 0 else -1
        sigs = [(f, _finite(facts.get(f))) for f in sig_ids]
        sigs = [(f, v) for f, v in sigs if v is not None]
        aligned = sorted([(f, v) for f, v in sigs if v * sign > 0], key=lambda t: (-abs(t[1]), t[0]))
        opposed = sorted([(f, v) for f, v in sigs if v * sign < 0], key=lambda t: (-abs(t[1]), t[0]))
        for fid, _ in aligned[:2]:
            name = fid[len(iid) + 5:-2]
            drivers.append(Driver(text=f"Sinal {name} alinhado em " + _ph(fid), evidence_ids=[fid]))
        for fid, _ in opposed[:1]:
            name = fid[len(iid) + 5:-2]
            risks.append(Driver(text=f"Sinal {name} contrário em " + _ph(fid), evidence_ids=[fid]))
        up_id = f"{iid}.target_upside"
        upside = _finite(facts.get(up_id))
        if upside is not None:
            target = drivers if (upside > 0) == (stance >= 0) else risks
            target.append(Driver(text="Upside ao preço-alvo do consenso em " + _ph(up_id),
                                 evidence_ids=[up_id]))
        for metric, label in (("vol_3m", "Volatilidade trimestral em "),
                              ("squeeze_score", "Escore de risco de squeeze em ")):
            fid = f"{iid}.{metric}"
            if _finite(facts.get(fid)) is not None:
                risks.append(Driver(text=label + _ph(fid), evidence_ids=[fid]))
        for item in ctx.get("news") or []:
            sentiment = item.get("sentiment")
            nid = str(item["news_id"])
            if sentiment == "negative":
                risks.append(Driver(text="Notícia recente com tom negativo "
                                         f"(materialidade {item.get('materiality', 'n/d')})",
                                    evidence_ids=[nid]))
            elif sentiment == "positive" and stance >= 0:
                drivers.append(Driver(text="Notícia recente com tom positivo "
                                           f"(materialidade {item.get('materiality', 'n/d')})",
                                      evidence_ids=[nid]))
        gaps = []
        if not ctx.get("local_language"):
            gaps.append("Sem documentos em idioma local no pacote da semana (modo demo)")
        for metric in ("pe_trailing", "target_upside", "ret_1m_usd"):
            fid = f"{iid}.{metric}"
            if fid in facts and _finite(facts.get(fid)) is None:
                gaps.append(f"{metric} indisponível")
        coverage_label = "ampla" if coverage >= 0.8 else "parcial" if coverage >= 0.4 else "baixa"
        thesis = (f"Viés {_STANCE_LABEL[stance]} no horizonte da tese: alpha composto em "
                  + _ph(alpha_id) + f" com cobertura {coverage_label} de sinais; volatilidade, "
                  "liquidez e risco de squeeze monitorados (modo demo, regras determinísticas).")
        if alpha_id not in facts:
            thesis = (f"Viés {_STANCE_LABEL[stance]} pelo alpha composto (fato não publicado); "
                      "modo demo, regras determinísticas.")
        return AnalystOutput(
            thesis=thesis, drivers=drivers[:8], risks=risks[:8], catalysts=[],
            kill_criteria=["Reversão do alpha composto para o sinal oposto",
                           "Evento de governança ou regulatório material"],
            data_gaps=gaps, abstain=False, stance=stance,
            p_outperform=round(0.5 + 0.1 * stance, 4), confidence=confidence)

    # ------------------------------------------------------------------ R2 notícias
    def _news(self, ctx: dict, task: str) -> NewsOutput:
        iid = str(ctx["issuer_id"])
        items = []
        for item in sorted(ctx.get("items") or [], key=lambda x: str(x["news_id"])):
            title = _norm(str(item.get("title", "")))
            score = _has(title, _POSITIVE) - _has(title, _NEGATIVE)
            sentiment = "positive" if score > 0 else "negative" if score < 0 else "neutral"
            event = next((name for name, words in _EVENT_RULES if _has(title, words)), "other")
            if event in ("m&a", "regulatory", "legal") or (event == "earnings"
                                                            and sentiment != "neutral"):
                materiality = "high"
            elif event in ("earnings", "guidance", "capital", "governance", "management"):
                materiality = "medium"
            else:
                materiality = "low"
            injection = is_injection_flagged(item.get("flags") or []) or bool(
                detect_injection(str(item.get("title", ""))))
            items.append(NewsAssessment(news_id=str(item["news_id"]), issuer_id=iid,
                                        sentiment=sentiment, materiality=materiality,
                                        event_type=event, injection_suspected=injection))
        return NewsOutput(items=items)

    # ------------------------------------------------------------------ R6 sentinela
    def _short_risk(self, ctx: dict, task: str) -> ShortRiskOutput:
        iid = str(ctx["issuer_id"])
        facts: dict[str, Any] = dict(ctx.get("facts") or {})
        bucket = ctx.get("bucket") or "NA"
        fee = _finite(ctx.get("borrow_fee"))
        max_fee = _finite(ctx.get("max_borrow_fee"))
        flags = []
        if bucket == "HIGH":
            verdict = "veto"
            flags.append("squeeze_alto")
        elif fee is None:
            verdict = "veto"
            flags.append("taxa_de_aluguel_ausente")
        elif max_fee is not None and fee > max_fee:
            verdict = "veto"
            flags.append("aluguel_acima_do_mandato")
        elif bucket in ("MEDIUM", "NA"):
            verdict = "caution"
            flags.append("squeeze_medio_ou_indeterminado")
        else:
            verdict = "ok"
        used = [f"{iid}.{m}" for m in ("squeeze_score", "si_pct_float", "days_to_cover",
                                       "borrow_fee") if f"{iid}.{m}" in facts]
        labels = {"squeeze_score": "escore", "si_pct_float": "short interest",
                  "days_to_cover": "dias para cobrir", "borrow_fee": "aluguel"}
        parts = [f"{labels[f.split('.', 1)[1]]} {_ph(f)}" for f in used]
        rationale = (f"Faixa de risco de squeeze {_BUCKET_LABEL.get(bucket, 'indeterminada')}"
                     + (": " + ", ".join(parts) if parts else "") + " (modo demo).")
        return ShortRiskOutput(rationale=rationale, flags=flags, evidence_ids=used,
                               verdict=verdict)

    # ------------------------------------------------------------------ R5 macro
    def _macro(self, ctx: dict, task: str) -> MacroOutput:
        scope = str(ctx["scope"])
        facts: dict[str, Any] = dict(ctx.get("facts") or {})
        ccy = ctx.get("currency")
        parts, used = [], []
        fx_id = f"fx.{ccy}.ret_1m"
        if ccy and fx_id in facts:
            parts.append("câmbio local em " + _ph(fx_id) + " no mês")
            used.append(fx_id)
        bench = _COUNTRY_BENCH.get(scope)
        for sym in [s for s in (bench, "ILF") if s]:
            for suffix, label in (("ret_1m", "no mês"), ("ret_ytd", "no ano")):
                fid = f"bench.{sym}.{suffix}"
                if fid in facts:
                    parts.append(f"{sym} em " + _ph(fid) + f" {label}")
                    used.append(fid)
        rate = _COUNTRY_RATE.get(scope)
        for fid in [f"rate.{rate}" if rate else "", "rate.USD_3M"]:
            if fid and fid in facts:
                parts.append("juro " + fid.split(".", 1)[1] + " em " + _ph(fid))
                used.append(fid)
        summary = ("Leitura neutra (modo demo): " + "; ".join(parts) + "." if parts
                   else "Leitura neutra (modo demo): sem fatos macro disponíveis.")
        return MacroOutput(
            scope=scope, regime="neutro (modo demo, sem leitura qualitativa de regime)",
            summary=summary, key_events=[],
            risks=["Volatilidade cambial e de juros locais", "Eventos políticos e fiscais"],
            implications=["Manter neutralidade de país e de câmbio via otimizador"],
            evidence_ids=used, stance=0)

    # ------------------------------------------------------------------ R4 debate/juiz
    def _debate(self, ctx: dict, task: str) -> DebateOutput:
        iid = str(ctx["issuer_id"])
        side = "bull" if task == "debate_bull" else "bear"
        facts: dict[str, Any] = dict(ctx.get("facts") or {})
        z_ids = sorted(f for f in facts if f.startswith(f"{iid}.") and
                       (f.endswith(".alpha_z") or (".sig_" in f and f.endswith("_z"))))
        vals = [(f, _finite(facts.get(f))) for f in z_ids]
        vals = [(f, v) for f, v in vals if v is not None]
        args: list[Driver] = []
        if side == "bull":
            for fid, _ in sorted([t for t in vals if t[1] > 0], key=lambda t: (-t[1], t[0]))[:2]:
                args.append(Driver(text="Indicador favorável em " + _ph(fid), evidence_ids=[fid]))
            up = f"{iid}.target_upside"
            if (_finite(facts.get(up)) or 0.0) > 0:
                args.append(Driver(text="Upside ao preço-alvo em " + _ph(up), evidence_ids=[up]))
        else:
            for fid, _ in sorted([t for t in vals if t[1] < 0], key=lambda t: (t[1], t[0]))[:2]:
                args.append(Driver(text="Indicador desfavorável em " + _ph(fid), evidence_ids=[fid]))
            for metric, label in (("vol_3m", "Volatilidade trimestral em "),
                                  ("squeeze_score", "Risco de squeeze em ")):
                fid = f"{iid}.{metric}"
                if _finite(facts.get(fid)) is not None:
                    args.append(Driver(text=label + _ph(fid), evidence_ids=[fid]))
        return DebateOutput(side=side, arguments=args)

    def _judge(self, ctx: dict, task: str) -> JudgeOutput:
        return JudgeOutput(
            rationale="Argumentos dos dois lados apoiados em fatos já considerados pelo analista; "
                      "sem evidência nova verificável (modo demo).",
            new_evidence_ids=[], stance_change=0)
