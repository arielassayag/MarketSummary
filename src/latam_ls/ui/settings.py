"""Caminhos do app (somente leitura), configuráveis por variáveis de ambiente.

- ``CDP_BOOK_DIR``: livro (padrão ``book``) — semanas, trilha de auditoria e track records.
- ``CDP_REPORTS_DIR``: relatórios (padrão ``reports``) — ``daily/<data>`` e ``weekly/<semana>``.
- ``CDP_CONFIG``: mandato (padrão ``configs/latam_ls/fund.yaml``).
- ``CDP_MARKET_DIR``: base de mercado ``MarketStore`` (padrão ``data/market``).
- ``CDP_AGENTS_MD``: ``AGENTS.md`` com as invariantes (padrão: raiz do repositório).

Caminhos relativos são resolvidos a partir do diretório de trabalho (a raiz do repositório
quando o app roda com ``uv run streamlit run cdp_app.py``).
"""

from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

ENV_BOOK = "CDP_BOOK_DIR"
ENV_REPORTS = "CDP_REPORTS_DIR"
ENV_CONFIG = "CDP_CONFIG"
ENV_MARKET = "CDP_MARKET_DIR"
ENV_AGENTS = "CDP_AGENTS_MD"

DEFAULT_BOOK = Path("book")
DEFAULT_REPORTS = Path("reports")
DEFAULT_CONFIG = Path("configs/latam_ls/fund.yaml")
DEFAULT_MARKET = Path("data/market")
DEFAULT_AGENTS = Path("AGENTS.md")

_REPO_ROOT = Path(__file__).resolve().parents[3]


def _path(environ: Mapping[str, str], key: str, default: Path) -> Path:
    raw = (environ.get(key) or "").strip()
    return Path(raw).expanduser() if raw else default


@dataclass(frozen=True)
class AppPaths:
    """Raízes dos artefatos lidos pelo app."""

    book: Path
    reports: Path
    config: Path
    market: Path
    agents_md: Path

    @classmethod
    def from_env(cls, environ: Mapping[str, str] | None = None) -> AppPaths:
        env = os.environ if environ is None else environ
        agents = _path(env, ENV_AGENTS, DEFAULT_AGENTS)
        if not env.get(ENV_AGENTS) and not agents.exists():
            agents = _REPO_ROOT / DEFAULT_AGENTS
        return cls(book=_path(env, ENV_BOOK, DEFAULT_BOOK),
                   reports=_path(env, ENV_REPORTS, DEFAULT_REPORTS),
                   config=_path(env, ENV_CONFIG, DEFAULT_CONFIG),
                   market=_path(env, ENV_MARKET, DEFAULT_MARKET),
                   agents_md=agents)

    def describe(self) -> list[tuple[str, str]]:
        """Pares (rótulo, caminho) para exibição."""
        return [("Livro", self.book.as_posix()), ("Relatórios", self.reports.as_posix()),
                ("Mandato", self.config.as_posix()), ("Base de mercado", self.market.as_posix())]
