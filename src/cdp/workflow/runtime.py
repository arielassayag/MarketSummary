"""Orquestração operacional do CDP (usada pela CLI, pelas rotinas agendadas e pelo app).

Mantém a reprodutibilidade: a etapa ``weekly prepare`` grava, com hash, tudo o que foi coletado
no momento da análise (barra intradiária e dados lentos); ``weekly decide`` reconstrói exatamente
o mesmo ``MarketData`` a partir desses arquivos e falha se qualquer hash divergir.
"""

from __future__ import annotations

import json
import os
import shutil
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd
import yaml

from ..audit import AuditLog
from ..calendar import (
    chave_valida,
    is_rebalance_day,
    is_session,
    previous_data_session,
    previous_session,
)
from ..config import FundConfig, load_config
from ..contracts import ResearchPack
from ..hashing import sha256_file, sha256_obj
from ..market import MarketData
from .book import Book

PREPARE_MANIFEST = "prepare_manifest.json"
KILL_SWITCH_FILE = "KILL_SWITCH"
#: Pedido de kill switch (arquivo novo, mesclável): ``reports/risk/<data>/kill_switch_<HHMM>.yaml``
#: (conteúdo JSON, que também é YAML válido; a extensão o mantém fora da lista de execuções do
#: monitor, que são ``risco_<HHMM>.json``/``.md``). Quem liga o kill switch sem a trava exclusiva
#: (rotina de risco num clone separado) deixa o pedido publicado; a próxima execução exclusiva
#: (semanal ou diária) o aplica no livro.
KILL_SWITCH_REQUEST_PREFIX = "kill_switch_"
KILL_SWITCH_REQUEST_SUFFIX = ".yaml"
KILL_SWITCH_REQUEST_EVENT = "KILL_SWITCH_PEDIDO"
RISK_REPORTS_DIR = "risk"
DECISION_CONFIG = "config_decisao.json"
"""Configuração do mandato vigente no ``decide`` (``book/<semana>/``), autenticada pelo
``config_hash`` da proposta: reconstruções posteriores (tese) usam a configuração da decisão."""
DEFAULT_TESES_ROOT = Path("docs/cdp/teses")
"""Pasta versionada das teses escritas pela mente fora do clone da rotina
(``<AAAA-MM-DD>.json``, mesmo schema de ``book/<semana>/tese/tese.json``)."""
BENCH_INTRADAY = ["ILF", "EWZ", "EWW", "ECH", "ARGT", "SPY"]
_BRT = ZoneInfo("America/Sao_Paulo")


class RecusaEstruturada(ValueError):
    """Recusa prevista de uma etapa (ex.: prazo vencido): a CLI a devolve como JSON
    (``status``/``motivo``), nunca como erro cru."""

    def __init__(self, status: str, motivo: str, **extra) -> None:
        super().__init__(motivo)
        self.status = status
        self.motivo = motivo
        self.extra = extra

    def as_dict(self) -> dict:
        return {"status": self.status, "motivo": self.motivo, **self.extra}


def briefing_completo(briefing_dir: Path) -> bool:
    """Briefing promovido por inteiro: manifesto, ``briefing.md`` e ``context.json``."""
    return all((Path(briefing_dir) / n).exists()
               for n in (PREPARE_MANIFEST, "briefing.md", "context.json"))


def _afastar_briefing_incompleto(briefing_dir: Path) -> Path | None:
    """Afasta (renomeia, nunca apaga) um briefing parcial deixado por uma versão antiga.

    Versões anteriores gravavam o manifesto antes de terminar; uma falha no meio deixava a
    pasta parcial e travava a semana. A pasta vai para ``.briefing.incompleto-<carimbo>``
    (ignorada pelo git) e o ``prepare`` recomeça do zero.
    """
    briefing_dir = Path(briefing_dir)
    if not briefing_dir.exists() or briefing_completo(briefing_dir):
        return None
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%S")
    dest = briefing_dir.parent / f".briefing.incompleto-{stamp}"
    os.replace(briefing_dir, dest)
    return dest


def _ultimo_pregao_completo(md: MarketData) -> date | None:
    """Pregão completo anterior quando ``md.as_of`` é barra provisória (senão ``None``)."""
    if md.as_of not in set(md.manifest.provisional_dates or []):
        return None
    anteriores = [d.date() for d in md.close.index if d.date() < md.as_of]
    return max(anteriores) if anteriores else None


def aviso_coleta(falhas: list[str], pregao_base: object = None) -> str | None:
    """Aviso legível do ``weekly prepare`` quando a coleta ao vivo falhou (rede ou fonte fora):
    a análise segue com o último dado gravado de cada fonte que falhou (nunca com dado vazio)."""
    if not falhas:
        return None
    base = str(pregao_base)[:10] if pregao_base else None
    try:
        base_txt = f" (base gravada até {date.fromisoformat(base):%d/%m/%Y})" if base else ""
    except ValueError:
        base_txt = ""
    return (f"Coleta ao vivo incompleta: {len(falhas)} fonte(s) sem resposta. A análise usa os "
            f"últimos dados gravados dessas fontes{base_txt}; nada gravado foi apagado. Com a "
            "rede fora, `weekly prepare --offline` monta o briefing só com a base gravada.")


def _write_json(path: Path, obj) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2, sort_keys=True, default=str),
                    encoding="utf-8")


@dataclass
class Runtime:
    cfg: FundConfig
    book_root: Path
    market_root: Path
    reports_root: Path
    store_override: object | None = None
    clock: Callable[[], datetime] | None = field(default=None, repr=False)
    teses_root: Path | None = DEFAULT_TESES_ROOT
    """Rascunhos de tese entregues fora do clone da rotina (``None`` desliga a adoção)."""
    expected_mind: str | None = None
    """Mente desta execução (``--mind`` ou ``CDP_HARNESS``): os validadores recusam arquivos da
    mente com outro ``mind`` (``None`` = sem conferência, ex.: demonstração)."""

    def now(self) -> datetime:
        """Relógio da rotina (UTC); a demonstração usa um relógio lógico determinístico."""
        return (self.clock() if self.clock is not None else datetime.now(UTC)).astimezone(UTC)

    # ------------------------------------------------------------------ fábrica
    @classmethod
    def from_args(cls, args) -> Runtime:
        from ..contracts import mente_do_ambiente

        cfg = load_config(getattr(args, "config", None))
        return cls(cfg=cfg, book_root=Path(args.book), market_root=Path(args.market),
                   reports_root=Path(args.reports),
                   teses_root=Path(getattr(args, "teses", None) or DEFAULT_TESES_ROOT),
                   expected_mind=getattr(args, "mind", None) or mente_do_ambiente())

    def mente_esperada(self, arquivo: Path | None = None,
                       rascunho: Path | None = None) -> str | None:
        """Mente que o arquivo da mente deve declarar nesta execução. Rascunho entregue por
        outra sessão (copiado byte a byte para ``arquivo``) mantém a mente de quem o escreveu."""
        if self.expected_mind is None:
            return None
        try:
            if (rascunho is not None and arquivo is not None and Path(rascunho).is_file()
                    and Path(arquivo).is_file()
                    and Path(rascunho).read_bytes() == Path(arquivo).read_bytes()):
                return None
        except OSError:
            pass
        return self.expected_mind

    @property
    def book(self) -> Book:
        return Book(self.book_root, config=self.cfg)

    @property
    def store(self):
        if self.store_override is not None:
            return self.store_override
        from ..data.store import MarketStore

        return MarketStore(self.market_root, cfg=self.cfg)

    def track(self, shadow: bool = False):
        from .track_record import TrackRecord

        name = "track_record_shadow" if shadow else "track_record"
        return TrackRecord(self.book_root / name)

    # ------------------------------------------------------------------ estado
    def kill_switch_active(self) -> bool:
        return (self.book_root / KILL_SWITCH_FILE).exists()

    def set_kill_switch(self, on: bool, reason: str, by: str) -> None:
        path = self.book_root / KILL_SWITCH_FILE
        audit = AuditLog(self.book_root / "audit_log.jsonl")
        at = self.now().isoformat()
        payload = {"on": on, "reason": reason, "by": by, "at": at, "created_at": at}
        if on:
            _write_json(path, payload)
        elif path.exists():
            path.unlink()
        audit.append("KILL_SWITCH_ON" if on else "KILL_SWITCH_OFF", by, payload,
                     summary=f"Kill switch {'ligado' if on else 'desligado'}: {reason}")

    # ------------------------------------------------------------------ pedidos de kill switch
    def request_kill_switch(self, reason: str, by: str) -> dict:
        """Grava o pedido de kill switch (arquivo novo, nunca sobrescrito) em
        ``reports/risk/<data de Brasília>/kill_switch_<HHMM>.yaml`` e devolve
        ``{"arquivo", "sha256", "pedido"}``. Arquivo novo é mesclável: sai na publicação da
        rotina compartilhada mesmo quando o livro (``book/KILL_SWITCH`` e a trilha) fica retido
        por falta da trava exclusiva."""
        local = self.now().astimezone(_BRT)
        folder = self.reports_root / RISK_REPORTS_DIR / local.date().isoformat()
        folder.mkdir(parents=True, exist_ok=True)
        pedido = {"tipo": "ligar", "reason": reason, "by": by,
                  "at": self.now().isoformat(), "versao": 1}
        stem = f"{KILL_SWITCH_REQUEST_PREFIX}{local:%H%M}"
        k = 1
        while (folder / f"{stem}{KILL_SWITCH_REQUEST_SUFFIX}").exists():
            k += 1
            stem = f"{KILL_SWITCH_REQUEST_PREFIX}{local:%H%M}_{k}"
        path = folder / f"{stem}{KILL_SWITCH_REQUEST_SUFFIX}"
        text = json.dumps(pedido, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
        with path.open("x", encoding="utf-8", newline="\n") as f:
            f.write(text)
        return {"arquivo": path.as_posix(), "sha256": sha256_file(path), "pedido": pedido}

    def mark_kill_switch_request(self, sha: str, efeito: str, by: str) -> None:
        """Registra na trilha que o pedido ``sha`` foi tratado (``efeito``: aplicado, já ligado ou
        superado por desligamento humano). O payload é só o hash do pedido, então qualquer clone
        reconhece o pedido como tratado pela trilha encadeada."""
        AuditLog(self.book_root / "audit_log.jsonl").append(
            KILL_SWITCH_REQUEST_EVENT, by, {"pedido_sha256": sha},
            summary=f"Pedido de kill switch {sha[:12]}: {efeito}.")

    def kill_switch_requests(self) -> list[dict]:
        """Pedidos de kill switch ainda não tratados no livro (do mais antigo ao mais recente):
        ``{"arquivo", "sha256", "pedido", "superado"}``. ``superado``: um humano desligou o kill
        switch depois do pedido (a decisão humana prevalece; o pedido só é registrado)."""
        root = self.reports_root / RISK_REPORTS_DIR
        if not root.is_dir():
            return []
        events = AuditLog(self.book_root / "audit_log.jsonl").events() \
            if (self.book_root / "audit_log.jsonl").is_file() else []
        handled = {e.payload_hash for e in events if e.event_type == KILL_SWITCH_REQUEST_EVENT}
        offs = [e.ts for e in events if e.event_type == "KILL_SWITCH_OFF"]
        last_off = max(offs) if offs else None
        out: list[dict] = []
        for path in sorted(root.glob(f"*/{KILL_SWITCH_REQUEST_PREFIX}*{KILL_SWITCH_REQUEST_SUFFIX}")):
            sha = sha256_file(path)
            if sha256_obj({"pedido_sha256": sha}) in handled:
                continue
            try:
                pedido = yaml.safe_load(path.read_text(encoding="utf-8"))
                at = datetime.fromisoformat(str(pedido["at"]))
                reason = str(pedido["reason"])
            except (OSError, ValueError, KeyError, TypeError, yaml.YAMLError):
                continue  # ilegível: nunca liga nada por arquivo inválido
            if pedido.get("tipo") != "ligar" or at.tzinfo is None:
                continue
            out.append({"arquivo": path.as_posix(), "sha256": sha, "pedido": pedido,
                        "motivo": reason, "em": at,
                        "superado": bool(last_off is not None and last_off >= at)})
        return sorted(out, key=lambda r: r["em"])

    def apply_kill_switch_requests(self) -> list[dict]:
        """Aplica no livro os pedidos de kill switch pendentes (só em execução exclusiva: semanal,
        diária). Pedido posterior ao último desligamento humano liga o kill switch (se ainda
        desligado) com o motivo do pedido; todo pedido tratado fica registrado na trilha."""
        done: list[dict] = []
        for r in self.kill_switch_requests():
            by = str(r["pedido"].get("by") or "CDP — pedido de kill switch")
            if r["superado"]:
                efeito = "superado por desligamento humano posterior"
            elif self.kill_switch_active():
                efeito = "kill switch já ligado"
            else:
                self.set_kill_switch(True, f"{r['motivo']} (pedido {Path(r['arquivo']).name})", by)
                efeito = "aplicado"
            self.mark_kill_switch_request(r["sha256"], efeito, by)
            done.append({"arquivo": r["arquivo"], "efeito": efeito})
        return done

    def last_record_date(self) -> date | None:
        try:
            last = self.track().last()
        except Exception:  # noqa: BLE001 - módulo/arquivo ausente antes da inception
            return None
        return last.date if last else None

    def current_nav(self) -> float:
        try:
            last = self.track().last()
        except Exception:  # noqa: BLE001
            last = None
        return float(last.nav_end_usd) if last else float(self.cfg.fund.inception_nav_usd)

    def store_last_date(self) -> date | None:
        try:
            return self.store.last_date()
        except Exception:  # noqa: BLE001
            return None

    def pre_inicio(self, d: date) -> bool:
        """``d`` antecede a data de início do mandato e o livro ainda não tem semana nem registro
        diário (fundo sem carteira: sem marcação, relatório diário nem monitor de risco; nenhum
        dia de montagem antes da data de início). Depende do livro, não só do calendário: a
        demonstração e os testes rodam livros históricos com a configuração real."""
        if d >= self.cfg.fund.inception_date:
            return False
        from .reinicio import chaves_vivas

        try:
            return not chaves_vivas(self)
        except OSError:  # pragma: no cover - disco
            return False

    def live_weeks(self) -> int:
        b = self.book
        return sum(1 for w in b.list_weeks() if b.load_booked(w) is not None)

    def drawdown_and_vol(self) -> tuple[float, float | None]:
        try:
            last = self.track().last()
        except Exception:  # noqa: BLE001
            last = None
        if not last:
            return 0.0, None
        return float(last.risk.drawdown), last.risk.realized_vol_21d

    def current_drifted_weights(self) -> dict[str, float] | None:
        try:
            last = self.track().last()
        except Exception:  # noqa: BLE001
            last = None
        if not last or not last.positions:
            return None
        w: dict[str, float] = {}
        for p in last.positions:
            w[p.issuer_id] = w.get(p.issuer_id, 0.0) + float(p.weight)
        return w

    def previous_booked(self, week: date):
        """Carteira efetivada mais recente ANTERIOR a ``week`` (a vigente na decisão da semana)."""
        return self.book._previous_booked(week)

    def decision_state(self, week: date):
        """Estado do livro no momento da decisão de ``week`` (para reconstruções posteriores).

        Devolve ``(booking anterior, pesos marcados, drawdown)`` como a decisão os via: o
        booking mais recente anterior à semana e os pesos e o drawdown do último registro
        diário anterior à semana (sem registro: ``None``, como o contexto do PM). Nunca usa o
        estado vivo posterior à decisão.
        """
        records = [r for r in self._records() if r.date < week]
        last = records[-1] if records else None
        drifted: dict[str, float] | None = None
        if last is not None and last.positions:
            drifted = {}
            for p in last.positions:
                drifted[p.issuer_id] = drifted.get(p.issuer_id, 0.0) + float(p.weight)
        drawdown = float(last.risk.drawdown) if last is not None else None
        return self.previous_booked(week), drifted, drawdown

    # ------------------------------------------------------------------ dados
    def market_for_week(self, week: date, *, live: bool, briefing_dir: Path,
                        record: bool) -> tuple[MarketData, dict]:
        """MarketData com TODO dado disponível até agora (pregão anterior + intradiário + lentos).

        ``record=True`` coleta ao vivo e grava os arquivos com hash; ``record=False`` reconstrói a
        partir do manifesto salvo (etapa ``decide``), verificando cada hash.
        """
        from ..data.intraday import (
            fetch_intraday_quotes,
            intraday_collection_failure,
            load_quotes,
            overlay_intraday,
            save_quotes,
        )
        from ..data.live_refresh import (
            fetch_slow_refresh,
            load_slow_refresh,
            overlay_slow_refresh,
            save_slow_refresh,
        )

        store = self.store
        manifest_path = briefing_dir / PREPARE_MANIFEST
        prev = self.information_session(week)
        if not record and manifest_path.exists():
            # A reconstrução usa o pregão de dados gravado no prepare (nunca recalcula).
            try:
                raw_prev = json.loads(manifest_path.read_text(encoding="utf-8")).get(
                    "previous_session")
                if raw_prev:
                    prev = date.fromisoformat(str(raw_prev)[:10])
            except (OSError, ValueError):
                pass
        if record:
            if live:
                self._anchor_increments(store.catch_up(prev))
            md = store.load(as_of=prev)
            info: dict = {"week": week, "previous_session": prev,
                          "store_content_hash": md.manifest.content_hash(), "live": live,
                          "config_hash": self.cfg.config_hash(),
                          "prepared_at": self.now()}
            if live:
                captured = self.now()
                lines = list(md.universe.lines.index)
                quotes = fetch_intraday_quotes(lines, md.universe.currencies, BENCH_INTRADAY)
                qpath = briefing_dir / "intraday_quotes.parquet"
                qsha = save_quotes(quotes, qpath, captured)
                falha_intradia = intraday_collection_failure(quotes, week, md.universe.currencies)
                if falha_intradia is None:
                    md = overlay_intraday(md, week, quotes, captured,
                                          "briefing/intraday_quotes.parquet", qsha)
                slow = fetch_slow_refresh(md, week, lookback_days=self.cfg.research.news_lookback_days)
                shashes = save_slow_refresh(slow, briefing_dir / "live")
                md = overlay_slow_refresh(md, slow, shashes, captured, "briefing/live")
                failures = list(slow.failures)
                if falha_intradia is not None:
                    # Falha de coleta (rede ou fonte fora): a análise usa o fechamento do pregão
                    # anterior, sem barra provisória — nunca uma barra vazia que derrube o risco.
                    failures.insert(0, falha_intradia)
                info.update({"captured_at": captured, "intraday_sha256": qsha,
                             "intraday": falha_intradia is None,
                             "slow_hashes": shashes, "slow_failures": failures,
                             "n_quotes": int(quotes["price"].notna().sum())})
            info["snapshot_hash"] = md.manifest.content_hash()
            _write_json(manifest_path, info)
            return md, info
        info = json.loads(manifest_path.read_text(encoding="utf-8"))
        md = store.load(as_of=prev)
        if md.manifest.content_hash() != info["store_content_hash"]:
            raise ValueError("O histórico de mercado mudou desde o prepare (hash divergente).")
        if info.get("live"):
            captured = datetime.fromisoformat(str(info["captured_at"]))
            quotes, _ = load_quotes(briefing_dir / "intraday_quotes.parquet",
                                    info["intraday_sha256"])
            if info.get("intraday", True):
                md = overlay_intraday(md, week, quotes, captured,
                                      "briefing/intraday_quotes.parquet", info["intraday_sha256"])
            slow = load_slow_refresh(briefing_dir / "live", info["slow_hashes"])
            md = overlay_slow_refresh(md, slow, info["slow_hashes"], captured, "briefing/live")
        if md.manifest.content_hash() != info["snapshot_hash"]:
            raise ValueError("Snapshot reconstruído difere do usado no briefing.")
        return md, info

    def information_session(self, week: date) -> date:
        """Pregão de dados anterior ao dia de montagem: com a seção ``execution``, o da união
        B3 | NYSE | BMV (ex.: um feriado só na B3 continua sendo pregão de dados); legado: o
        pregão anterior da B3."""
        if self.cfg.execution is not None:
            return previous_data_session(week)
        return previous_session(week)

    def decision_deadline(self, week: date) -> datetime:
        """Prazo efetivo da decisão no dia de montagem ``week`` (Brasília)."""
        from ..portfolio.execucao import prazo_efetivo

        return prazo_efetivo(week, self.cfg)

    def _context(self, md: MarketData, week: date, *, conhecimento_ate: datetime | None = None,
                 permitir_cobertura: bool = True, vinculo_cobertura=...):
        from .weekly import prepare_week

        b = self.book
        dd, _vol = self.drawdown_and_vol()
        ctx = prepare_week(md, self.cfg, week, nav=self.current_nav(),
                           current_entry=b.latest_booked(),
                           current_drifted_w=self.current_drifted_weights(), drawdown=dd,
                           squeeze_stops=self.squeeze_stops(week))
        snap, corte = self._snapshot_cobertura(md, conhecimento_ate, permitir=permitir_cobertura,
                                               vinculo=vinculo_cobertura)
        if corte is not None:
            from ..alpha.signals import valuation_gap_sombra
            ctx.cobertura_snapshot = snap
            ctx.cobertura_conhecimento_ate = corte
            ctx.valuation_gap_sombra = valuation_gap_sombra(
                snap, list(ctx.panel.assets.index), conhecimento_ate=corte)
        return ctx

    def squeeze_stops(self, week: date) -> dict[str, dict]:
        """Stop de squeeze por nome a aplicar na montagem de ``week`` (:func:`cdp.risk.limites.
        acoes_de_squeeze`): episódios de stop em TODOS os registros diários anteriores ao dia de
        montagem (a mesma regra do monitor de risco), com o corte à metade ainda pendente e o
        veto de compra dos emissores sem revisão humana. Só registros encadeados e revisões
        anteriores à preparação da semana: a reconstrução da decisão não muda depois. Regra do
        livro inteiro (legado) ou sem registro: nenhum."""
        if self.cfg.squeeze.stop_scope != "name":
            return {}
        recs = [r for r in self._records() if r.date < week]
        if not recs:
            return {}
        from ..risk.limites import acoes_de_squeeze, episodios_de_squeeze

        eps = episodios_de_squeeze(recs, self.cfg)
        return acoes_de_squeeze(eps, self.squeeze_reviews(week)) if eps else {}

    def squeeze_reviews(self, week: date | None = None) -> dict[str, date]:
        """Revisões humanas de stop de squeeze na trilha (emissor → registro-base revisado). Com
        ``week``: só as gravadas antes da preparação dessa semana (``WEEKLY_PREPARED``)."""
        from ..risk.limites import revisoes_de_squeeze

        path = self.book_root / "audit_log.jsonl"
        if not path.is_file():
            return {}
        try:
            events = AuditLog(path).events()
        except (OSError, ValueError):
            return {}
        if week is not None:
            cut = next((i for i, e in enumerate(events)
                        if e.event_type == "WEEKLY_PREPARED" and e.week == week), len(events))
            events = events[:cut]
        dates = {sha256_obj(r.record_hash): r.date for r in self._records()}
        return revisoes_de_squeeze(events, dates)

    def review_squeeze(self, issuer: str, reason: str, by: str) -> dict:
        """Revisão humana do stop de squeeze por nome de ``issuer``: libera o veto de compra dos
        episódios de stop até o último registro diário (um stop posterior reabre o veto). Grava
        o evento :data:`cdp.risk.limites.SQUEEZE_REVIEW_EVENT` na trilha; o corte à metade
        pendente continua (é regra do código, não da revisão)."""
        from ..risk.limites import (
            SQUEEZE_REVIEW_EVENT,
            SQUEEZE_REVIEW_SUMMARY,
            episodios_de_squeeze,
            revisado,
        )

        if self.cfg.squeeze.stop_scope != "name":
            raise ValueError("Revisão de stop de squeeze só existe com a regra por nome "
                             "(squeeze.stop_scope = name).")
        recs = self._records()
        revs = self.squeeze_reviews()
        pend = [e for e in episodios_de_squeeze(recs, self.cfg)
                if e.emissor == issuer and not revisado(e, revs)]
        if not pend:
            raise ValueError(f"{issuer} não tem stop de squeeze aguardando revisão humana.")
        payload = {"emissor": issuer, "motivo": reason, "por": by, "em": self.now().isoformat(),
                   "registro_base": recs[-1].date.isoformat(),
                   "episodios": [{"ticker": e.ticker, "data_stop": e.data_stop.isoformat(),
                                  "preco_medio_entrada": e.preco_medio_entrada}
                                 for e in pend]}
        self.book.audit.append(
            SQUEEZE_REVIEW_EVENT, by, payload,
            summary=SQUEEZE_REVIEW_SUMMARY.format(emissor=issuer, motivo=" ".join(reason.split())))
        return payload

    def _candidates(self, ctx, n: int) -> tuple[list[str], list[str]]:
        a = ctx.alpha.alpha.dropna()
        cons = ctx.sides
        can_short = cons["can_short"].reindex(a.index).fillna(False).astype(bool)
        longs = list(a.sort_values(ascending=False).head(n).index)
        shorts = list(a[can_short].sort_values().head(n).index)
        held = [i for i, w in ctx.current_w.items() if w != 0]
        return sorted(set(longs) | set(held)), sorted(set(shorts) | set(held))

    def _snapshot_cobertura(self, md: MarketData, conhecimento_ate: datetime | None,
                            *, permitir: bool = True, vinculo=...):
        from ..cobertura.parametros import carregar_parametros
        from ..cobertura.temporal import ativo
        if not permitir or (vinculo is ... and not ativo(carregar_parametros())):
            return None, None
        if vinculo is not ... and conhecimento_ate is None:
            raise ValueError("Prepare de cobertura sem instante arquivado.")
        from ..cobertura.livro import conferir_corte, snapshot, ultimo_snapshot
        from ..data.publico_arquivo import data_local
        from ..data.publico_resultados import instante
        corte = instante(conhecimento_ate if conhecimento_ate is not None else self.now())
        if vinculo is None:
            return None, corte
        if vinculo is not ...:
            if not isinstance(vinculo, dict) or set(vinculo) != {"as_of", "manifest_sha256", "corte_temporal"}:
                raise ValueError("Vínculo de cobertura incompleto no prepare.")
            snap = snapshot(self.book_root, date.fromisoformat(vinculo["as_of"]))
            conferir_corte(snap, corte)
            if (snap.manifest_sha256 != vinculo["manifest_sha256"]
                    or snap.manifest.get("corte_temporal") != vinculo["corte_temporal"]):
                raise ValueError("Snapshot de cobertura diverge do usado no prepare.")
            from dataclasses import replace
            snap = replace(snap, conhecimento_ate=corte)
        else:
            snap = ultimo_snapshot(self.book_root, data_local(corte), conhecimento_ate=corte)
        if snap is not None and date.fromisoformat(snap.manifest["prices_as_of"]) > md.as_of:
            raise ValueError("Base de cobertura posterior à base da etapa semanal.")
        return snap, corte

    def _factbook(self, ctx, issuers: list[str], *, conhecimento_ate: datetime | None = None,
                  permitir_cobertura: bool = True, vinculo_cobertura=...):
        from ..research.factbook import build_factbook, com_fatos_valuation
        fb = build_factbook(ctx.panel, ctx.md, issuers, alpha_z=ctx.alpha.composite_z,
                            signal_z=ctx.alpha.signal_z, squeeze=ctx.squeeze, betas=ctx.betas,
                            specific_vol=ctx.model.specific_vol, snapshot_id=ctx.snapshot_id)
        corte = conhecimento_ate or getattr(ctx, "cobertura_conhecimento_ate", None)
        if vinculo_cobertura is ... and hasattr(ctx, "cobertura_conhecimento_ate"):
            vinculo_cobertura = self._vinculo_cobertura(ctx)
        snap, corte = self._snapshot_cobertura(ctx.md, corte, permitir=permitir_cobertura,
                                               vinculo=vinculo_cobertura)
        return com_fatos_valuation(fb, snap, issuers, conhecimento_ate=corte) if corte is not None else fb

    @staticmethod
    def _cobertura_registrada(info):
        from ..cobertura.temporal import METODO
        if "cobertura_metodo" not in info and "cobertura" not in info:
            return False
        if info.get("cobertura_metodo") != METODO or "cobertura" not in info:
            raise ValueError("Política/vínculo de cobertura incompleto no prepare.")
        return True

    @staticmethod
    def _vinculo_cobertura(ctx):
        snap = getattr(ctx, "cobertura_snapshot", None)
        return None if snap is None else {"as_of": snap.as_of.isoformat(),
                                         "manifest_sha256": snap.manifest_sha256,
                                         "corte_temporal": snap.manifest.get("corte_temporal")}


    # ------------------------------------------------------------------ semanal
    def week_dir(self, week: date) -> Path:
        return self.book_root / week.isoformat()

    def _previous_week(self, week: date) -> date | None:
        weeks = [w for w in self.book.list_weeks() if w < week]
        return weeks[-1] if weeks else None

    def _previous_views(self, week: date):
        """Visões e decisão estruturada da semana anterior (para a avaliação da semana)."""
        from ..research.pm_agent import PM_INPUT, PMDecisionOutput

        prev = self._previous_week(week)
        if prev is None:
            return [], None, None
        pack = self.book.load_research_pack(prev)
        out = None
        path = self.week_dir(prev) / "inputs" / PM_INPUT
        if path.exists():
            try:
                out = PMDecisionOutput.model_validate_json(path.read_text(encoding="utf-8"))
            except ValueError:
                out = None
        views = list(pack.views) if pack else []
        if out is not None and not out.abstain:
            from ..research.pm_agent import pm_output_to_views

            views = list(pm_output_to_views(out, self.cfg)[0]) + views
        return views, out, prev

    @staticmethod
    def _realized_residual(ctx, since: date | None, week: date) -> pd.Series | None:
        """Σ resíduos diários do modelo de risco entre a efetivação anterior e a semana atual."""
        if since is None:
            return None
        sr = ctx.model.specific_returns
        idx = pd.to_datetime(sr.index)
        mask = (idx > pd.Timestamp(since)) & (idx < pd.Timestamp(week))
        if not mask.any():
            return None
        return sr.loc[mask].sum(min_count=1)

    def _pm_context(self, md: MarketData, ctx, week: date, fb, analysis_ts: datetime | None,
                    *, state: tuple[float | None, float | None] | None = None,
                    kill_switch: bool | None = None):
        """Contexto do PM; ``state``/``kill_switch`` substituem o estado vivo do livro
        (``(drawdown, vol realizada)`` e kill switch), para reconstruções da decisão."""
        from ..research.pm_agent import PMContext

        longs, shorts = self._candidates(ctx, self.cfg.research.top_n_candidates)
        prev_views, prev_out, prev_week = self._previous_views(week)
        if state is None:
            dd_live, vol = self.drawdown_and_vol()
            dd = dd_live if self.last_record_date() else None
        else:
            dd, vol = state
        return PMContext(
            week=week, as_of=md.as_of, fund_name=self.cfg.fund.name, factbook=fb,
            universe_issuers=ctx.panel.assets[["issuer_name", "country", "sector"]],
            quant_alpha_z=ctx.alpha.composite_z, quant_candidates_long=longs,
            quant_candidates_short=shorts, current_book=ctx.current_positions,
            previous_views=prev_views, previous_pm_output=prev_out, research_notes=[],
            macro_notes=[], drawdown=dd, realized_vol_21d=vol, track_record_facts={},
            kill_switch=self.kill_switch_active() if kill_switch is None else kill_switch,
            cfg=self.cfg, news=list(md.news),
            realized_residual_returns=self._realized_residual(ctx, prev_week, week),
            analysis_ts=analysis_ts, last_complete_session=_ultimo_pregao_completo(md))

    def decision_pm_output(self, week: date, md: MarketData, ctx, info: dict, decision):
        """Decisão do PM VERIFICADA exatamente como o ``decide`` a usou, ou ``None``.

        ``ctx`` é o contexto da semana no estado do livro na hora da decisão (ver
        :meth:`decision_state`). Reconstrói o contexto do PM nesse estado (candidatos sobre a
        carteira vigente, drawdown e vol realizada do último registro diário anterior à semana)
        e reaplica a verificação do ``decide`` (``load_week_inputs``: evidências, guardrails de
        texto, abstenção e kill switch). Só aceita a saída cujo ``pm_output_hash`` confere com o
        ``pm_decision_hash`` gravado na decisão — o kill switch da hora da decisão não é
        gravado, então as duas hipóteses são testadas. Sem conferência ⇒ ``None`` (o chamador
        publica visões e postura do PM como ausentes; nunca a decisão bruta da mente).
        """
        from ..research.pm_agent import load_week_inputs, pm_factbook, pm_output_hash

        target = getattr(decision, "pm_decision_hash", None)
        if not target:
            return None
        records = [r for r in self._records() if r.date < week]
        last = records[-1] if records else None
        state = ((float(last.risk.drawdown), last.risk.realized_vol_21d) if last is not None
                 else (None, None))
        try:
            longs, shorts = self._candidates(ctx, self.cfg.research.top_n_candidates)
            fb = self._factbook(ctx, sorted(set(longs) | set(shorts)),
                                conhecimento_ate=self._analysis_ts(info),
                                permitir_cobertura=self._cobertura_registrada(info),
                                vinculo_cobertura=info.get("cobertura"))
            for ks in (False, True):
                pmctx = self._pm_context(md, ctx, week, fb, self._analysis_ts(info),
                                         state=state, kill_switch=ks)
                _pack, out, _issues, pm_ctx = load_week_inputs(self.week_dir(week), pmctx,
                                                               now=decision.decided_at)
                if pm_output_hash(out, pm_factbook(pm_ctx)) == target:
                    return out
        except Exception:  # noqa: BLE001 - reconstrução explicativa; sem conferência ⇒ None
            return None
        return None

    @staticmethod
    def _analysis_ts(info: dict) -> datetime | None:
        raw = info.get("captured_at") or info.get("prepared_at")
        return datetime.fromisoformat(str(raw)) if raw else None

    def _week_state(self, week: date):
        """Reconstrói (com verificação de hash) o estado exato do ``prepare`` da semana."""
        briefing = self.week_dir(week) / "briefing"
        md, info = self.market_for_week(week, live=False, briefing_dir=briefing, record=False)
        registrada = self._cobertura_registrada(info)
        ctx = self._context(md, week, conhecimento_ate=self._analysis_ts(info),
                            permitir_cobertura=registrada, vinculo_cobertura=info.get("cobertura"))
        longs, shorts = self._candidates(ctx, self.cfg.research.top_n_candidates)
        fb = self._factbook(ctx, sorted(set(longs) | set(shorts)),
                            conhecimento_ate=self._analysis_ts(info),
                            permitir_cobertura=registrada, vinculo_cobertura=info.get("cobertura"))
        if "cobertura" in info and info["cobertura"] != self._vinculo_cobertura(ctx):
            raise ValueError("Snapshot de cobertura diverge do usado no prepare.")
        pmctx = self._pm_context(md, ctx, week, fb, self._analysis_ts(info))
        return md, info, ctx, fb, pmctx

    def weekly_prepare(self, week: date, *, mind: str, live: bool = True) -> dict:
        from ..research.pm_agent import write_briefing_bundle

        if not chave_valida(week, self.cfg):
            from ..calendar import regra

            rule = ("o último pregão da semana na NYSE" if regra(self.cfg) == "LAST_US_SESSION"
                    else "o primeiro pregão da semana na B3")
            raise ValueError(f"{week} não é {rule} nem a data de início do mandato.")
        self.book.check_key(week)  # livro aberto na data de início: nada anterior a ela
        briefing = self.week_dir(week) / "briefing"
        if briefing_completo(briefing):
            raise FileExistsError(f"Briefing da semana {week} já existe (imutável): {briefing}")
        if self.book.list_decisions(week):
            raise FileExistsError(f"A semana {week} já tem decisão gravada.")
        retomado = _afastar_briefing_incompleto(briefing)
        pedidos = self.apply_kill_switch_requests()
        # O briefing é montado numa área temporária e promovido de uma vez só no fim: uma falha
        # no meio (rede, fonte, modelo) não deixa briefing parcial que trave a semana.
        staging = briefing.parent / f".briefing.staging-{os.getpid()}"
        if staging.exists():
            shutil.rmtree(staging)
        try:
            md, info = self.market_for_week(week, live=live, briefing_dir=staging, record=True)
            ctx = self._context(md, week, conhecimento_ate=self._analysis_ts(info))
            longs, shorts = self._candidates(ctx, self.cfg.research.top_n_candidates)
            fb = self._factbook(ctx, sorted(set(longs) | set(shorts)),
                                conhecimento_ate=self._analysis_ts(info))
            if hasattr(ctx, "cobertura_conhecimento_ate"):
                from ..cobertura.temporal import METODO
                info["cobertura_metodo"] = METODO
                info["cobertura"] = self._vinculo_cobertura(ctx)
                _write_json(staging / PREPARE_MANIFEST, info)
            pmctx = self._pm_context(md, ctx, week, fb, self._analysis_ts(info))
            staged = write_briefing_bundle(pmctx, staging, mind_hint=mind, final_dir=briefing)
            os.replace(staging, briefing)
        except BaseException:
            shutil.rmtree(staging, ignore_errors=True)
            raise
        paths = {k: briefing / v.name for k, v in staged.items()}
        (self.week_dir(week) / "inputs").mkdir(parents=True, exist_ok=True)
        self.book.audit.append("WEEKLY_PREPARED", mind, info,
                               summary=f"Briefing da semana {week} preparado pela mente {mind}.",
                               week=week)
        falhas = list(info.get("slow_failures", []))
        aviso = aviso_coleta(falhas, info.get("previous_session"))
        return {"semana": week, "briefing": str(briefing),
                "arquivos": {k: str(v) for k, v in paths.items()},
                "entradas": str(self.week_dir(week) / "inputs"),
                "candidatos_long": len(longs), "candidatos_short": len(shorts),
                "emissores_elegiveis": int(ctx.panel.assets["eligible"].sum()),
                "barra_provisoria": bool(info.get("live")) and bool(info.get("intraday", True)),
                "snapshot_hash": info["snapshot_hash"], "falhas_coleta": falhas,
                **({"aviso_coleta": aviso} if aviso else {}),
                **({"briefing_incompleto_afastado": str(retomado)} if retomado else {}),
                **({"kill_switch_pedidos": pedidos} if pedidos else {})}

    def validate_inputs(self, week: date, *, mind: str | None = None,
                        so_pesquisa: bool = False) -> tuple[bool, list[str]]:
        from ..research.pm_agent import validate_inputs

        _md, _info, _ctx, _fb, pmctx = self._week_state(week)
        return validate_inputs(self.week_dir(week), pmctx, expected_mind=mind, now=self.now(),
                               only_research=so_pesquisa)

    def weekly_decide(self, week: date, *, mind: str) -> dict:
        from ..research.pm_agent import load_week_inputs, pm_factbook, to_bundle
        from .autonomy import make_autonomous_decision
        from .avaliacao import BINDING_FILE, FOLDER, bind, preregister
        from .reports import render_weekly_report, write_report_files
        from .weekly import run_weekly_decision

        b = self.book
        if self.expected_mind is not None and self.expected_mind != mind:
            raise RecusaEstruturada("mind_divergente", "mente solicitada difere do harness", semana=week)
        if b.list_decisions(week):
            # Reconciliar anexos depois de uma queda não produz outra decisão/ordem.
            decision = b.load_decision(week)
            binding_path = self.week_dir(week) / FOLDER / BINDING_FILE
            previous_path = (json.loads(binding_path.read_text(encoding="utf-8"))["path_taken"]
                             if binding_path.exists() else "recuperado")
            bind(b, decision, path_taken=previous_path, now=self.now())
            return {"semana": week, "status": "já decidido", "decisao": decision.approval_hash,
                    "mente": decision.mind,
                    "acao": "avaliação reconciliada; nenhuma nova decisão ou execução"}
        # Um único instante para a decisão inteira: o prazo é conferido nele e ele é o
        # ``decided_at``/``created_at`` da proposta e da decisão. A decisão é função só dos
        # insumos disponíveis neste instante (dados da preparação e arquivos da mente); o cálculo
        # posterior não usa informação nova, e o carimbo nunca passa do prazo conferido.
        t_dec = self.now()
        if self.cfg.execution is not None:
            deadline = self.decision_deadline(week)
            if t_dec > deadline:
                inaugural = b.latest_booked() is None
                mantida = ("o fundo segue sem carteira (carteira inaugural não montada) até a "
                           "próxima data de montagem" if inaugural
                           else "a carteira vigente é mantida até o próximo dia de montagem")
                raise RecusaEstruturada(
                    "prazo_vencido",
                    f"Prazo efetivo da decisão de {week} vencido "
                    f"({deadline.astimezone(_BRT):%H:%M} de Brasília): a decisão não é gravada "
                    f"depois do prazo (o fechamento seria conhecido); {mantida}.",
                    semana=week, decisao_perdida=True, carteira_inaugural=inaugural,
                    acao="nenhuma: não decidir; registrar o motivo no resumo da rotina")
        # Pedidos de kill switch publicados por rotinas sem a trava (ex.: risco na nuvem) valem
        # antes da decisão: kill switch ligado ⇒ só redução de risco.
        pedidos = self.apply_kill_switch_requests()
        _md, info, ctx, _fb, pmctx = self._week_state(week)
        pack, out, issues, pm_ctx = load_week_inputs(self.week_dir(week), pmctx, now=t_dec)
        from .avaliacao import input_authorship

        try:
            input_authorship(self.week_dir(week), mind)
        except ValueError as exc:
            raise RecusaEstruturada("mind_divergente", str(exc), semana=week) from exc
        if out.abstain and out.mind != mind:
            # A saída gerada pelo código em falha de IA tem a mente do executor; entradas
            # originais permanecem intactas e sua identidade é arquivada no pré-registro.
            from ..research.pm_agent import fallback_pm_output

            out = fallback_pm_output(mind)
        elif out.mind != mind:
            raise RecusaEstruturada("mind_divergente", "mente da decisão não confere", semana=week)
        pack = pack.model_copy(update={"mind": pack.mind or mind})
        pfb = pm_factbook(pm_ctx)
        bundle = to_bundle(out, self.cfg, pm_ctx.drawdown, factbook=pfb)
        cohort = preregister(b, ctx, pack, bundle, mind=mind, cutoff=t_dec, now=self.now(),
                             deadline=self.decision_deadline(week), clock=self.now)
        outcome = run_weekly_decision(ctx, pack, bundle, version=b.next_version(week),
                                      live_weeks=self.live_weeks(),
                                      kill_switch=self.kill_switch_active(),
                                      audit_head_hash=b.audit_head(),
                                      decided_at=t_dec, created_at=t_dec, factbook=pfb)
        inputs_dir = self.week_dir(week) / "inputs"
        b.audit.append("WEEKLY_INPUTS", pack.mind or mind,
                       {p.name: sha256_file(p) for p in sorted(inputs_dir.glob("*.json"))},
                       summary=f"Arquivos brutos da mente para {week} (hash).", week=week)
        b.save_research_pack(pack, actor=pack.mind or mind)
        b.save_proposal(outcome.final)
        shadow_path = self.week_dir(week) / "shadow_quant.json"
        _write_json(shadow_path, outcome.shadow_quant.model_dump(mode="json"))
        # Configuração da decisão (autenticada pelo config_hash da proposta): a tese da
        # carteira reconstrói a semana com ela mesmo após uma recalibração do mandato. Sem
        # ``sort_keys``: a ordem dos dicionários (ex.: pesos dos sinais) define a ordem das
        # somas, e a reconstrução precisa ser idêntica bit a bit.
        (self.week_dir(week) / DECISION_CONFIG).write_text(
            json.dumps(self.cfg.model_dump(mode="json"), ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8")
        b.audit.append("SHADOW_QUANT", "CDP", {"sha256": sha256_file(shadow_path)},
                       summary="Carteira-sombra só-quant gravada.", week=week)
        # A decisão é ancorada na trilha DEPOIS da proposta gravada (nunca retroativa).
        d0 = outcome.decision
        decision = make_autonomous_decision(
            outcome.final, research_hash=outcome.research_hash,
            pm_decision_hash=d0.pm_decision_hash or bundle.pm_output_hash,
            rationale=d0.rationale, journal=d0.journal, conviction=d0.conviction,
            decided_at=t_dec, audit_head_hash=b.audit_head(),
        ).model_copy(update={"mind": pack.mind})
        b.save_decision(decision)
        bind(b, decision, path_taken=outcome.path_taken, now=self.now())
        _write_json(self.week_dir(week) / "attempts.json",
                    {"path": outcome.path_taken, "attempts": outcome.attempts,
                     "input_issues": issues})
        prev_week = self._previous_week(week)
        prev_prop = b.load_proposal(prev_week) if prev_week else None
        prev_views = list(pm_ctx.previous_views)
        week_records = [r for r in self._records() if prev_week and prev_week <= r.date < week]
        rr = pm_ctx.realized_residual_returns
        md_txt, html = render_weekly_report(
            week, outcome.final, decision, out, prev_prop, prev_views,
            list(bundle.views) + list(pack.views),
            week_records, outcome.shadow_quant, self.cfg.fund.name, factbook=pfb, cfg=self.cfg,
            attempts=outcome.attempts, path_taken=outcome.path_taken,
            realized_residual=(None if rr is None else
                               {k: float(v) for k, v in rr.dropna().items()}))
        report = write_report_files(self.reports_root / "weekly" / week.isoformat(), md_txt, html)
        b.audit.append("WEEKLY_REPORT", "CDP", report,
                       summary=f"Relatório semanal {week} publicado.", week=week)
        p = outcome.final
        return {"semana": week, "mente": pack.mind, "caminho": outcome.path_taken,
                "postura": bundle.posture, "abstencao": bundle.abstain,
                "decisao": decision.approval_hash, "vol_ex_ante": p.risk.ex_ante_vol,
                "gross": p.risk.gross, "net": p.risk.net, "beta": p.risk.beta,
                "n_long": p.risk.n_long, "n_short": p.risk.n_short,
                "falhas_soft": [c.check_id for c in p.soft_failures],
                "apontamentos_entrada": issues, "relatorio": report,
                "analise": info.get("captured_at") or info.get("prepared_at"),
                "execucao": f"fechamento de {week} (MOC) pela rotina diária",
                "avaliacao": {"coorte": sha256_obj(cohort), "fim": cohort.end,
                              "prospectiva": cohort.prospective,
                              "autoria_observada": cohort.original_minds},
                **({"kill_switch_pedidos": pedidos} if pedidos else {})}

    def weekly_preview(self, week: date, *, mind: str) -> dict:
        """Prévia do livro da semana SEM gravar nada (revisão pré-trade da mente).

        Roda exatamente o pipeline do ``decide`` (pesquisa + decisão do PM + otimizador + gates)
        sobre os arquivos de ``inputs/`` e devolve as posições com a visão de cada nome e os
        conflitos (posição contrária à visão da pesquisa/PM). A mente ajusta só juízos ordinais
        (visões e exclusões) — números continuam vindo do código.
        """
        from ..research.pm_agent import load_week_inputs, pm_factbook, to_bundle
        from .weekly import run_weekly_decision

        _md, _info, ctx, _fb, pmctx = self._week_state(week)
        pack, out, issues, pm_ctx = load_week_inputs(self.week_dir(week), pmctx, now=self.now())
        pfb = pm_factbook(pm_ctx)
        bundle = to_bundle(out, self.cfg, pm_ctx.drawdown, factbook=pfb)
        outcome = run_weekly_decision(ctx, pack, bundle, version=self.book.next_version(week),
                                      live_weeks=self.live_weeks(),
                                      kill_switch=self.kill_switch_active(),
                                      decided_at=self.now(), created_at=self.now(),
                                      factbook=pfb)
        stance: dict[str, int] = {}
        for v in list(pack.views) + list(bundle.views):
            if v.score != 0:
                stance[v.issuer_id] = v.score  # a visão do PM (última) prevalece
        p = outcome.final
        rows, conflicts = [], []
        for pos in sorted(p.positions, key=lambda x: -abs(x.weight)):
            st = stance.get(pos.issuer_id)
            row = {"emissor": pos.issuer_id, "peso": round(pos.weight, 5), "pais": pos.country,
                   "setor": pos.sector, "alpha_z": pos.alpha_z, "visao": st,
                   "risco": pos.risk_contribution}
            rows.append(row)
            if st is not None and st * pos.weight < 0:
                conflicts.append(row)
        shadow = {x.issuer_id: x.weight for x in outcome.shadow_quant.positions}
        return {"semana": week, "caminho": outcome.path_taken, "postura": bundle.posture,
                "vol_ex_ante": p.risk.ex_ante_vol, "gross": p.risk.gross, "net": p.risk.net,
                "beta": p.risk.beta, "n_long": p.risk.n_long, "n_short": p.risk.n_short,
                "falhas_hard": [c.check_id for c in p.hard_failures],
                "falhas_soft": [c.check_id for c in p.soft_failures],
                "apontamentos_entrada": issues, "conflitos_visao_posicao": conflicts,
                "posicoes": rows, "sombra_quant": shadow,
                "tentativas": outcome.attempts}

    # ------------------------------------------------------------------ diário
    def _records(self, shadow: bool = False) -> list:
        try:
            return self.track(shadow).records()
        except Exception:  # noqa: BLE001 - sem série antes da primeira efetivação
            return []

    def _runner(self, store=None):
        from .daily import DailyRunner
        from .track_record import SHADOW_RECORD_EVENT, TrackRecord

        shadow = TrackRecord(self.book_root / "track_record_shadow",
                             audit_event=SHADOW_RECORD_EVENT)
        return DailyRunner(self.cfg, store or self.store, self.book, self.track(),
                           shadow_track=shadow)

    def _daily_factbook(self, session: date, record, store=None):
        from ..research.commentary import build_daily_factbook, build_market_day_facts

        history = [r for r in self._records() if r.date < session]
        md = (store or self.store).load(as_of=session)
        mkt = build_market_day_facts(md.benchmarks, md.fx, session)
        return build_daily_factbook(record, history, mkt, cfg=self.cfg), history

    def _anchor_increments(self, increments) -> None:
        """Ancora cada incremento diário de dados na trilha (detecta truncamento da cauda)."""
        for inc in increments or []:
            self.book.audit.append(
                "MARKET_INCREMENT", "CDP — rotina diária",
                {"session_date": inc.session_date, "manifest_hash": inc.manifest_hash},
                summary=f"Incremento de mercado de {inc.session_date} gravado.")

    def daily_dir(self, session: date) -> Path:
        return self.reports_root / "daily" / session.isoformat()

    def daily_close(self, session: date, *, live: bool = True, mind: str | None = None) -> dict:
        """Fechamento oficial: efetiva a decisão da semana (MOC), marca, mede risco e atribui.

        Grava o registro diário encadeado e os insumos do comentário da mente
        (``reports/daily/<data>/facts.md``); a publicação vem depois (``daily publish``).
        """
        from ..research.commentary import factbook_json, write_daily_commentary_inputs
        from .avaliacao import resolve
        from .daily import NoBookError, NoSessionError

        if not any(is_session(session, ex) for ex in ("BVMF", "XNYS", "XMEX")):
            return {"data": session, "status": "sem pregão"}
        pedidos = self.apply_kill_switch_requests()
        if self.pre_inicio(session):
            out = self._daily_pre_inicio(session, live=live)
            return {**out, "kill_switch_pedidos": pedidos} if pedidos else out
        store = self.store
        if live:
            from ..data.store import DataNotReadyError, StoreLockedError

            try:
                increments = store.catch_up(session)
            except (DataNotReadyError, StoreLockedError) as exc:
                return {"data": session, "status": "dados não prontos",
                        "motivo": str(exc), "acao": "tente de novo em alguns minutos"}
            self._anchor_increments(increments)
        runner = self._runner(store)
        feito = runner.track.get(session)
        if feito is not None:
            from .risco_diario import recover

            recover(runner.track, feito)
            if runner.shadow is not None:
                sombra = runner.shadow.track.get(session)
                if sombra is not None:
                    recover(runner.shadow.track, sombra)
            # Pregão já registrado (inclusive com efetivação recusada): nada a refazer — nunca
            # uma segunda passagem que efetive depois uma decisão caducada.
            out = {"data": session, "status": "já registrado", "registro": feito.record_hash,
                   "acao": "nada a fazer: siga para o próximo fechamento pendente"}
            lapso = self._lapso_do_dia(session)
            if lapso:
                out["efetivacao_recusada"] = lapso
            out["avaliacao_encerrada"] = resolve(self.book, runner.track, store.load,
                                                  session=session, now=self.now())
            return {**out, "kill_switch_pedidos": pedidos} if pedidos else out
        try:
            res = runner.run_session(session)
        except NoSessionError as exc:
            return {"data": session, "status": "sem pregão", "motivo": str(exc)}
        except NoBookError as exc:
            out = {"data": session, "status": "sem carteira efetivada", "motivo": str(exc)}
            if self.kill_switch_active():
                # Kill switch ligado antes da primeira efetivação: só reduções são permitidas e
                # não há posição a reduzir — a montagem fica bloqueada (fundo zerado).
                out.update({"status": "efetivação bloqueada pelo kill switch",
                            "kill_switch": True,
                            "acao": ("nada a negociar: o fundo segue sem carteira até um humano "
                                     "revisar e desligar o kill switch (docs/cdp/EXECUCAO.md)")})
            return {**out, "kill_switch_pedidos": pedidos} if pedidos else out
        rec = res.record
        evaluation_closed = resolve(self.book, runner.track, store.load,
                                    session=session, now=self.now())
        fb, _history = self._daily_factbook(session, rec, store)
        out_dir = self.daily_dir(session)
        out_dir.mkdir(parents=True, exist_ok=True)
        (out_dir / "factbook.json").write_text(factbook_json(fb), encoding="utf-8")
        paths = write_daily_commentary_inputs(out_dir, rec, fb, mind_hint=mind, overwrite=True)
        recusa = ({"efetivacao_recusada": {
            "semana": res.lapsed.get("semana"), "sessao": res.lapsed.get("sessao"),
            "motivo": res.lapsed.get("motivo"), "decisao_caducada": True,
            "regra": res.lapsed.get("regra")}} if res.lapsed else {})
        return {"data": session, "status": "registrado", "registro": rec.record_hash,
                "avaliacao_encerrada": evaluation_closed,
                "nav_usd": rec.nav_end_usd, "retorno_dia": rec.ret,
                "efetivacao": (res.booked.proposal_id if res.booked is not None else None),
                **recusa,
                "alertas": list(rec.alerts), "fatos": {k: str(v) for k, v in paths.items()},
                "proximo_passo": (f"escreva {out_dir / 'comentario.json'} e rode "
                                  f"`cdp daily publish --date {session}`"),
                **({"kill_switch_pedidos": pedidos} if pedidos else {})}

    def _lapso_do_dia(self, session: date) -> dict | None:
        """Registro de efetivação recusada (decisão caducada) no fechamento de ``session``."""
        for w in self.book.list_weeks():
            try:
                lapso = self.book.efetivacao_recusada(w)
            except ValueError:
                continue
            if lapso and lapso.get("sessao") == session.isoformat():
                return {"semana": lapso.get("semana"), "sessao": lapso.get("sessao"),
                        "decisao_caducada": True}
        return None

    def _daily_pre_inicio(self, session: date, *, live: bool) -> dict:
        """Antes da data de início (fundo sem carteira): sem marcação, registro nem relatório;
        só o incremento da base de mercado (dados públicos) até ``session``, ancorado na trilha,
        para a carteira inaugural partir de dados em dia."""
        inicio = self.cfg.fund.inception_date
        out: dict = {"data": session, "status": "pré-início",
                     "motivo": (f"carteira inaugural em {inicio:%d/%m/%Y}, ao preço de "
                                "fechamento; sem marcação nem relatório antes do início")}
        if not live:
            return out
        from ..data.store import DataNotReadyError, StoreLockedError

        store = self.store
        try:
            increments = store.catch_up(session)
        except (DataNotReadyError, StoreLockedError) as exc:
            out["dados_de_mercado"] = {"status": "não prontos", "motivo": str(exc),
                                       "acao": "tente de novo em alguns minutos"}
            return out
        self._anchor_increments(increments)
        novos = [inc.session_date for inc in increments or []]
        ultimo = store.last_date()
        out["dados_de_mercado"] = {
            "status": "atualizados" if novos else "sem pregões novos",
            "incrementos": novos, "ultimo_pregao": ultimo}
        if not novos and ultimo is not None and ultimo < session:
            out["dados_de_mercado"]["motivo"] = (
                f"a base termina em {ultimo}: o fechamento de {session} ainda não foi gravado "
                "(corte do fechamento oficial não alcançado ou fonte sem o pregão); a próxima "
                "rotina diária tenta de novo")
        return out

    def daily_publish(self, session: date) -> dict:
        """Valida o comentário da mente e publica o relatório diário (imutável)."""
        from ..research.commentary import COMMENTARY_JSON, load_commentary_file
        from .reports import render_daily_report, write_report_files

        rec = self.track().get(session)
        if rec is None:
            raise ValueError(f"Sem registro diário em {session}: rode `cdp daily close` antes.")
        fb, history = self._daily_factbook(session, rec)
        out_dir = self.daily_dir(session)
        comment_md, issues = load_commentary_file(out_dir / COMMENTARY_JSON, fb, record=rec,
                                                  expected_mind=self.mente_esperada())
        from .risk_monitor import idio_monitor

        idio, _t = idio_monitor(self, [*history, rec], [])
        md_txt, html = render_daily_report(rec, history, comment_md, self.cfg.fund.name,
                                           cfg=self.cfg, idio=idio)
        report = write_report_files(out_dir, md_txt, html)
        self.book.audit.append("DAILY_REPORT", "CDP", {**report, "record": rec.record_hash,
                                                       "commentary_issues": issues},
                               summary=f"Relatório diário {session} publicado.")
        return {"data": session, "relatorio": report, "apontamentos_comentario": issues,
                "comentario_da_mente": not issues}

    # ------------------------------------------------------------------ tese da carteira
    def thesis_prepare(self, week: date) -> dict:
        """Fatos, análise e briefing da tese da carteira decidida (``book/<semana>/tese/``)."""
        from .tese import prepare_thesis

        return prepare_thesis(self, week)

    def validate_thesis(self, week: date) -> dict:
        """Valida ``tese.json`` da mente SEM publicar (``ok``, ``problemas``, ``cobertura``)."""
        from .tese import validate_thesis

        return validate_thesis(self, week)

    def thesis_publish(self, week: date) -> dict:
        """Publica a tese (mente ou automática), imutável, com evento ``WEEKLY_THESIS``."""
        from .tese import publish_thesis

        return publish_thesis(self, week)

    # ------------------------------------------------------------------ integridade
    def verify_all(self) -> tuple[bool, list[str]]:
        msgs: list[str] = []
        ok = True
        b = self.book
        r_ok, r_msgs = b.verify_integrity()
        ok &= r_ok
        msgs += [f"livro: {m}" for m in (r_msgs or ["íntegro"])]
        for shadow in (False, True):
            try:
                t_ok, t_msgs = self.track(shadow).verify()
            except Exception as exc:  # noqa: BLE001
                t_ok, t_msgs = True, [f"sem track record ({exc.__class__.__name__})"]
            ok &= t_ok
            label = "sombra" if shadow else "track record"
            msgs += [f"{label}: {m}" for m in (t_msgs or ["íntegro"])]
        from .risco_diario import verify as verify_daily_risk

        for shadow in (False, True):
            try:
                daily_problems = verify_daily_risk(self.track(shadow),
                    market_loader=self.store.load, market_root=getattr(self.store, "root", None))
            except (OSError, ValueError, KeyError, TypeError) as exc:
                daily_problems = [str(exc)]
            ok &= not daily_problems
            msgs += [f"risco diário {'sombra' if shadow else 'efetivo'}: {m}"
                     for m in (daily_problems or ["íntegro (contrato v1; legado sem obrigação)"])]
        try:
            s_ok, s_msgs = self.store.verify_chain()
            ok &= s_ok
            msgs += [f"dados: {m}" for m in (s_msgs or ["íntegros"])]
        except Exception as exc:  # noqa: BLE001
            msgs.append(f"dados: sem base de mercado ({exc.__class__.__name__})")
        e_ok, e_msgs = self.verify_execucao(b)
        ok &= e_ok
        msgs += [f"execução: {m}" for m in e_msgs]
        from .notas import published_notes, verify_notes

        n_msgs = verify_notes(self)
        ok &= not n_msgs
        if n_msgs or published_notes(self.book_root):
            msgs += [f"notas: {m}" for m in (n_msgs or ["íntegras"])]
        from ..cobertura.revisao import listar_revisoes, verificar_revisoes

        rev_msgs = verificar_revisoes(self.book_root)
        ok &= not rev_msgs
        if rev_msgs or listar_revisoes(self.book_root):
            msgs += [f"revisões mensais: {m}" for m in (rev_msgs or ["íntegras"])]
        from .avaliacao import ENABLE_FILE, status, verify

        if (self.book_root / ENABLE_FILE).exists():
            evaluation_problems = verify(b, self.track(), self.market_root)
            ok &= not evaluation_problems
            msgs += [f"avaliação das mentes: {m}" for m in (evaluation_problems or ["íntegra"])]
            if not evaluation_problems:
                msgs += [f"avaliação das mentes: {r['semana']} — {r['estado']} (fim {r['fim']})"
                         for r in status(b, self.track(), now=self.now()) if r["estado"] != "resolvida"]
        return bool(ok), msgs

    def evaluation_status(self) -> list[dict]:
        """Pendências somente leitura; recusa livro sem integridade antes de informar status."""
        from .avaliacao import status

        valid, errors = self.book.verify_integrity()
        if not valid:
            raise ValueError("avaliação não autenticada: " + "; ".join(errors))
        return status(self.book, self.track(), now=self.now())

    def evaluation_history(self, *, mind: str, channel: str = "mente_final",
                           include_synthetic: bool = False) -> pd.DataFrame:
        """Leitura por mente/canal, sem escrita ou mudança de fase/mandato."""
        from ..research.evaluation import AuthenticatedViewTracker

        return AuthenticatedViewTracker(self.book_root, mind=mind, channel=channel,
                                        include_synthetic=include_synthetic, track=self.track(),
                                        market_root=self.market_root).ic_history()

    def _config_da_decisao(self, week: date, proposal) -> FundConfig | None:
        """Mandato que governou a decisão (e a efetivação) da semana: o atual se o hash confere;
        senão o arquivado na semana (``config_decisao.json``) ou no histórico de mandatos,
        autenticados pelo ``config_hash`` da proposta. ``None`` se indisponível."""
        from ..config import archived_config, book_historico_dir, load_archived_config

        if proposal.config_hash == self.cfg.config_hash():
            return self.cfg
        arq = load_archived_config(self.week_dir(week) / DECISION_CONFIG, proposal.config_hash)
        if arq is None:
            arq = archived_config(proposal.config_hash, book_historico_dir(self.book_root))
        return arq.cfg if arq is not None else None

    def verify_execucao(self, b: Book | None = None) -> tuple[bool, list[str]]:
        """Confere cada efetivação com execução no fechamento contra a regra determinística
        recalculada com os dados do pregão (:func:`cdp.portfolio.execucao.conferir_efetivacao`):
        nenhuma linha acima da capacidade pelo volume realizado, nem em mercado sem fechamento
        elegível, emissor congelado, depois do corte MOC ou abaixo da banda. Semanas sem a seção
        ``execution`` no mandato da decisão ficam fora (regra anterior)."""
        from ..portfolio.execucao import conferir_efetivacao

        b = b or self.book
        n = 0
        problems: list[str] = []
        for w in b.list_weeks():
            if not (self.week_dir(w) / "booked.json").exists():
                continue
            try:
                entry = b.load_booked(w)
            except ValueError:
                continue  # integridade do arquivo já acusada pelo livro
            if entry is None:
                continue
            prop = next((p for p in b.list_proposals(w)
                         if p.proposal_id == entry.proposal_id), None)
            if prop is None:
                continue
            cfg_w = self._config_da_decisao(w, prop)
            if cfg_w is None:
                problems.append(f"{w}: mandato autenticado da decisão indisponível para "
                                "conferir a efetivação")
                continue
            if cfg_w.execution is None:
                continue
            dec = b.load_decision(w, prop.version)
            session = entry.booked_at.astimezone(ZoneInfo(cfg_w.fund.timezone)).date()
            try:
                # Universo/moeda/linha pertencem ao vintage do próprio pregão, além de preços.
                md = self.store.load(as_of=session)
                if session in set(md.manifest.provisional_dates):
                    problems.append(f"{w}: efetivação no pregão {session} sem fechamento "
                                    "oficial (barra intradiária provisória)")
                    continue
                found = conferir_efetivacao(entry, prop, dec.decided_at if dec else None,
                                            b.holdings_before(w), md, cfg_w)
            except Exception as exc:  # noqa: BLE001 - fonte/contexto indisponível não é conforme
                problems.append(f"{w}: sem base de mercado para conferir a efetivação "
                                f"no próprio pregão {session} ({exc.__class__.__name__})")
                continue
            problems += [f"{w}: {m}" for m in found]
            n += 1
        if problems:
            return False, problems
        if n:
            return True, [("1 efetivação conferida" if n == 1 else
                           f"{n} efetivações conferidas")
                          + " contra a execução esperada no fechamento"]
        return True, []

    def run_backtest(self, start: date, end: date | None, out: Path) -> dict:
        from ..backtest.engine import BacktestConfig, run_backtest

        md = self.store.load()
        res = run_backtest(md, self.cfg, BacktestConfig(start=start, end=end,
                                                        nav=self.cfg.fund.inception_nav_usd))
        out.mkdir(parents=True, exist_ok=True)
        res.daily.to_csv(out / "daily.csv")
        res.weekly.to_csv(out / "weekly.csv")
        res.ic.to_csv(out / "ic.csv")
        _write_json(out / "metrics.json", {"metrics": res.metrics, "notes": res.notes})
        return {"saida": str(out), "metricas": res.metrics}


def research_pack_hash(pack: ResearchPack) -> str:
    return pack.research_hash()


def is_decision_day(d: date) -> bool:
    return is_rebalance_day(d)


def frame_hash(df: pd.DataFrame) -> str:
    return sha256_obj(df.to_dict("split"))
