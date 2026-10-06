"""Comandos ``cdp cobertura`` (registrados no W0 com os argumentos finais; dono: workstream A).

- ``cdp cobertura run --date D [--emissores IID,IID] [--offline]``: snapshot de cobertura do dia
  ``D`` (depois do fechamento do pregão de rebalanceamento; parcial com ``--emissores`` após
  resultados). Recusa ``D`` anterior ao último snapshot e insumos com ``available_date > D``.
  Grava ``book/cobertura/<D>/`` (manifesto, modelos, insumos, placar) e o evento
  ``COVERAGE_SNAPSHOT``; ``--offline`` usa só dados locais/sintéticos.
- ``cdp cobertura verify``: recalcula a cadeia do ``livro.jsonl``, o hash de cada manifesto e o
  ``placar.json`` e refaz os modelos a partir dos insumos públicos arquivados (cada insumo com
  fonte, URL, data de publicação, data de coleta e sha256 do arquivo): qualquer pessoa reproduz
  o resultado só com dados públicos.

Enquanto a implementação não chega, cada comando responde "em implementação" com código 2.
"""

from __future__ import annotations

import argparse
import sys

EM_IMPLEMENTACAO = 2


def _em_implementacao(comando: str) -> int:
    print(f"cdp {comando}: em implementação.", file=sys.stderr)
    return EM_IMPLEMENTACAO


def cmd_run(args: argparse.Namespace) -> int:
    """``cdp cobertura run`` (``args.date``, ``args.emissores``: tupla de IIDs ou ``None``,
    ``args.offline``)."""
    return _em_implementacao("cobertura run")


def cmd_verify(args: argparse.Namespace) -> int:
    """``cdp cobertura verify`` (só leitura; código 0 íntegro, 1 falha)."""
    return _em_implementacao("cobertura verify")


__all__ = ["EM_IMPLEMENTACAO", "cmd_run", "cmd_verify"]
