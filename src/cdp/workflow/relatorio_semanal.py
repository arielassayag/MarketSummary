"""Relatório semanal de resultado, na noite do pregão de rebalanceamento (registrado no W0 com os
argumentos finais; dono: workstream D).

Depois do booking de sexta (DESIGN §D.6):

- ``cdp weekly close-report --date D``: o código grava ``reports/semanal/<D>/{fatos.md,
  factbook.json, comentario.schema.json}`` (P&L da semana e desde o início, atribuição por grupo
  de fatores / específico / país / setor / emissor, giro, custos, taxa de execução, emissores
  congelados, vol ex-ante e fatia idiossincrática da carteira nova); a mente escreve
  ``comentario.json``. Com ``--publish``: renderiza ``relatorio.md/.html`` (modelo de código se
  o comentário for inválido) e grava o evento ``WEEKLY_CLOSE_REPORT``.
- ``cdp validate-weekly-report --date D``: valida ``comentario.json`` sem publicar.

O relatório da decisão (``reports/weekly/<W>/``, ``WEEKLY_REPORT``) não muda.
Enquanto a implementação não chega, cada comando responde "em implementação" com código 2.
"""

from __future__ import annotations

import argparse
import sys

EM_IMPLEMENTACAO = 2


def _em_implementacao(comando: str) -> int:
    print(f"cdp {comando}: em implementação.", file=sys.stderr)
    return EM_IMPLEMENTACAO


def cmd_close_report(args: argparse.Namespace) -> int:
    """``cdp weekly close-report`` (``args.date``, ``args.publish``)."""
    return _em_implementacao("weekly close-report")


def cmd_validate(args: argparse.Namespace) -> int:
    """``cdp validate-weekly-report`` (``args.date``; código 0 válido, 1 inválido)."""
    return _em_implementacao("validate-weekly-report")


__all__ = ["EM_IMPLEMENTACAO", "cmd_close_report", "cmd_validate"]
