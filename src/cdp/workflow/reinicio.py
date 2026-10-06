"""Pré-início do fundo (registrado no W0 com os argumentos finais; dono: workstream F', DESIGN
§15.2). Operação interna, uma única vez: nunca aparece em texto para o investidor.

``cdp reinicio [--executar]`` — rodado SÓ pelo clone da rotina (escritor único), na primeira vez em
que ``cdp agenda`` informa ``reinicio.pendente`` (``fund.inception_date`` posterior à primeira
chave viva do livro). Sem ``--executar`` é uma simulação: mostra o plano (o que seria movido, o
destino e as guardas) e não grava nada. Com ``--executar``:

1. Guardas (recusa com código diferente de 0 se alguma falha): nenhuma chave viva do livro é
   ``>= fund.inception_date``; a pasta de destino ainda não existe; ``cdp verify`` íntegro antes.
2. Move (semântica de ``git mv``; preparado numa área temporária e aplicado de forma atômica, com
   reversão em caso de falha) todo o conteúdo vivo de ``book/`` (chaves anteriores à inception,
   ``audit_log.jsonl``, ``track_record*`` e o resto), o conteúdo de ``reports/`` produzido para
   essas chaves e as marcas de tese/painel publicados para ``arquivo/ensaio-<primeira chave>/``
   (irmã de ``book/`` na raiz do repositório). Nenhum caminho de código lê ou publica o arquivo.
   ``data/`` (dados públicos de mercado) fica onde está.
3. Abre uma trilha NOVA em ``book/audit_log.jsonl`` cujo evento de gênese ``FUND_GENESIS``
   registra ``inception_date``, o hash da configuração, a versão do código e (campo interno) o
   sha256 da cabeça da cadeia arquivada.
4. ``cdp verify`` íntegro depois.

Idempotente: depois de executado, ``agenda`` deixa de informar ``reinicio.pendente`` e uma nova
chamada nunca altera nada (o destino já existe ⇒ recusa sem gravar).

Enquanto a implementação não chega, o comando responde "em implementação" com código 2.
"""

from __future__ import annotations

import argparse
import sys

EM_IMPLEMENTACAO = 2


def _em_implementacao(comando: str) -> int:
    print(f"cdp {comando}: em implementação.", file=sys.stderr)
    return EM_IMPLEMENTACAO


def cmd_reinicio(args: argparse.Namespace) -> int:
    """``cdp reinicio`` (``args.executar``: ``False`` = simulação sem gravar; ``args.book``,
    ``args.reports``)."""
    return _em_implementacao("reinicio")


__all__ = ["EM_IMPLEMENTACAO", "cmd_reinicio"]
