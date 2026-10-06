"""Notas de pesquisa por emissor (registradas no W0 com os argumentos finais; dono: workstream B).

Ciclo de vida espelhado na tese (DESIGN §B.3), em ``book/cobertura/notas/<IID>/<D>/``:
``fatos.md``, ``factbook.json``, ``nota.schema.json`` (código), ``nota.json`` (mente; único
arquivo editável), ``nota_publicada.json`` e ``nota.md`` (código, imutáveis). Números só via
``{{fact:id}}``; evidências só de fontes públicas (URL), tratadas como dado não confiável.

- ``cdp nota agenda [--date D]``: fila determinística (posições, candidatos do próximo
  rebalanceamento, pós-resultado em até 2 pregões, depois liquidez; SLAs 7/14/90 dias).
- ``cdp nota prepare --issuer IID [--date D]``: fatos e briefing da nota (adota rascunho válido).
- ``cdp validate-nota --issuer IID --date D``: valida ``nota.json`` sem publicar.
- ``cdp nota publish --issuer IID --date D``: publica (mente ou modelo de código); imutável;
  evento ``COVERAGE_NOTE``.

Enquanto a implementação não chega, cada comando responde "em implementação" com código 2.
"""

from __future__ import annotations

import argparse
import sys

EM_IMPLEMENTACAO = 2


def _em_implementacao(comando: str) -> int:
    print(f"cdp {comando}: em implementação.", file=sys.stderr)
    return EM_IMPLEMENTACAO


def cmd_agenda(args: argparse.Namespace) -> int:
    """``cdp nota agenda`` (``args.date`` ou ``None`` = hoje em Brasília)."""
    return _em_implementacao("nota agenda")


def cmd_prepare(args: argparse.Namespace) -> int:
    """``cdp nota prepare`` (``args.issuer``, ``args.date`` ou ``None``)."""
    return _em_implementacao("nota prepare")


def cmd_publish(args: argparse.Namespace) -> int:
    """``cdp nota publish`` (``args.issuer``, ``args.date``)."""
    return _em_implementacao("nota publish")


def cmd_validate(args: argparse.Namespace) -> int:
    """``cdp validate-nota`` (``args.issuer``, ``args.date``; código 0 válida, 1 inválida)."""
    return _em_implementacao("validate-nota")


__all__ = ["EM_IMPLEMENTACAO", "cmd_agenda", "cmd_prepare", "cmd_publish", "cmd_validate"]
