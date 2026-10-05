"""Estado de uma execução do app: leitores com ``st.cache_data`` chaveados por impressão digital.

A chave de cada cache inclui a impressão digital (caminho, tamanho e mtime) dos arquivos lidos —
nunca o relógio. Um novo registro diário, decisão ou relatório invalida automaticamente o cache
correspondente; nada fica velho e nada é relido sem necessidade.
"""

from __future__ import annotations

from datetime import UTC, datetime
from functools import cached_property
from pathlib import Path

import streamlit as st

from ..config import FundConfig
from ..contracts import DailyRecord
from . import data
from .settings import AppPaths


@st.cache_data(show_spinner=False, max_entries=8)
def _config(path: str, fp: str) -> data.ConfigInfo:
    return data.load_config_info(Path(path))


@st.cache_data(show_spinner="Carregando o track record…", max_entries=4)
def _track(book: str, fp: str, cfg_hash: str, _cfg: FundConfig) -> data.TrackData:
    return data.load_track(Path(book), _cfg)


@st.cache_data(show_spinner="Carregando o livro…", max_entries=4)
def _book(book: str, fp: str) -> data.BookData:
    return data.load_book(Path(book))


@st.cache_data(show_spinner=False, max_entries=4)
def _audit(book: str, fp: str) -> data.AuditData:
    return data.load_audit(Path(book))


@st.cache_data(show_spinner=False, max_entries=4)
def _reports(root: str, fp: str) -> list[data.ReportInfo]:
    return data.list_reports(Path(root))


@st.cache_data(show_spinner="Lendo a base de mercado…", max_entries=2)
def _market(root: str, fp: str) -> data.MarketContext:
    return data.load_market_context(Path(root))


@st.cache_data(show_spinner=False, max_entries=16)
def _commentary(reports: str, fp: str, track_fp: str, day: str, cfg_hash: str,
                _record: DailyRecord, _history: list[DailyRecord],
                _cfg: FundConfig) -> data.Commentary | None:
    return data.commentary_for(Path(reports), _record, _history, _cfg)


class AppState:
    """Acesso preguiçoso (e cacheado) aos artefatos durante uma execução do script."""

    def __init__(self, paths: AppPaths | None = None) -> None:
        self.paths = paths or AppPaths.from_env()

    # ------------------------------------------------------------------ impressões digitais
    @cached_property
    def track_fp(self) -> str:
        b = self.paths.book
        return data.fingerprint(b / data.TRACK_DIR, b / data.SHADOW_DIR)

    @cached_property
    def reports_fp(self) -> str:
        return data.fingerprint(self.paths.reports)

    # ------------------------------------------------------------------ artefatos
    @cached_property
    def config(self) -> data.ConfigInfo:
        return _config(str(self.paths.config), data.fingerprint(self.paths.config))

    @property
    def cfg(self) -> FundConfig:
        return self.config.cfg

    @cached_property
    def track(self) -> data.TrackData:
        return _track(str(self.paths.book), self.track_fp, self.config.config_hash, self.cfg)

    @cached_property
    def book(self) -> data.BookData:
        return _book(str(self.paths.book), data.fingerprint(self.paths.book))

    @cached_property
    def audit(self) -> data.AuditData:
        return _audit(str(self.paths.book),
                      data.fingerprint(self.paths.book / data.AUDIT_FILE))

    @cached_property
    def reports(self) -> list[data.ReportInfo]:
        return _reports(str(self.paths.reports), self.reports_fp)

    @cached_property
    def market(self) -> data.MarketContext:
        m = self.paths.market
        return _market(str(m), data.fingerprint(m / "base", m / "daily"))

    @property
    def kill_switch(self) -> data.KillSwitchState:
        # Sempre lido do disco: é o estado mais crítico do app.
        return data.kill_switch_state(self.paths.book)

    @cached_property
    def synthetic(self) -> list[str]:
        found = data.synthetic_artifacts(self.track, self.book)
        if data.market_is_synthetic(self.paths.market):
            found.append("base de mercado")
        return found

    def commentary(self, record: DailyRecord) -> data.Commentary | None:
        history = self.track.history_until(record)
        return _commentary(str(self.paths.reports), self.reports_fp, self.track_fp,
                           record.date.isoformat(), self.config.config_hash, record, history,
                           self.cfg)

    @staticmethod
    def now() -> datetime:
        return datetime.now(UTC)


def clear_caches() -> None:
    """Força a releitura de todos os artefatos (botão "Atualizar dados")."""
    st.cache_data.clear()
