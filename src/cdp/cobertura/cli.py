"""Comandos ``cdp cobertura`` (dono: workstream A).

- ``cdp cobertura run --date D [--emissores IID,IID] [--offline] [--raiz DIR]``: snapshot de
  cobertura do dia ``D`` (depois do fechamento; parcial com ``--emissores`` após resultados).
  Usa a base de mercado (``--market``) e os dados públicos arquivados sob ``--raiz`` (padrão:
  ``data/``); ``--offline`` lê só o arquivo local, sem rede. Recusa ``D`` anterior ou igual ao
  último snapshot e insumos publicados depois de ``D``. Grava ``<book>/cobertura/<D>/`` e o
  evento ``COVERAGE_SNAPSHOT`` na trilha do fundo.
- ``cdp cobertura verify [--sem-recalculo]``: confere o livro encadeado (terminando exatamente no
  último selo), cada manifesto, selo, arquivo e ``eventos.jsonl``, a correspondência um a um com
  os eventos ``COVERAGE_SNAPSHOT`` da trilha do fundo e o placar; refaz por completo o snapshot
  mais recente (contexto, custo de capital, cenários com semente, α relativo, rating e ETFs) e o
  preço-alvo do caso-base dos anteriores, a partir dos insumos públicos e da configuração
  arquivados no próprio snapshot (tolerância relativa de 1e-5, o arredondamento a 6 algarismos
  significativos do armazenamento).

Para refazer os modelos de uma data sem tocar no livro do repositório, use um livro de trabalho:
``cdp --book <livro de trabalho> cobertura run --date D --offline --raiz <arquivo público>`` (preços-
alvo, cenários e α coincidem com os publicados; o rating pode diferir pela histerese); para
conferir o publicado, ``verify``. As recusas que não dependem do cálculo (data já coberta,
retrodatação, livro sem selo) são feitas antes dele.

Códigos de saída: 0 ok; 1 recusa ou falha de integridade; 2 dados públicos indisponíveis.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import date
from pathlib import Path

from .fontes import FontePublicaIndisponivel, coletar
from .livro import (
    LivroErro,
    carregar_anterior,
    checar_data,
    gravar_snapshot,
    reparar_pendencias,
    selado,
    verificar,
)
from .motor import executar
from .parametros import DEFAULT_COBERTURA_DIR, DEFAULT_VALUATION, carregar_parametros

EM_IMPLEMENTACAO = 2
OK, FALHA, INDISPONIVEL = 0, 1, 2


def config_paths(valuation: Path = DEFAULT_VALUATION, pasta: Path = DEFAULT_COBERTURA_DIR) -> dict[str, Path]:
    out = {"valuation.yaml": Path(valuation)}
    for nome in ("arquetipos.csv", "betas_setor.csv", "unidades.csv", "sotp.yaml", "etfs.yaml"):
        out[f"cobertura/{nome}"] = Path(pasta) / nome
    return out


def executar_snapshot(book: Path, md, as_of: date, *, emissores=None, offline: bool = False,
                      raiz: Path | None = None, params=None, agora=None, codigo=None, audit: bool = True) -> dict:
    """Execução completa (coleta pública → modelos → gravação) sobre um ``MarketData`` dado."""
    reparar_pendencias(book, audit, agora)
    checar_data(book, as_of)
    ok_s, msg_s = selado(book)
    if not ok_s:
        raise LivroErro(f"Livro da cobertura não confere com o último selo: {msg_s}.")
    params = params or carregar_parametros()
    ids = sorted(str(i) for i in md.universe.issuers.index)
    tickers = sorted(str(t) for t in md.universe.lines.index)
    etfs = [str(e["ticker"]) for e in params.etfs.get("etfs", []) if e["ticker"] in md.benchmarks.columns]
    dados = coletar(md, as_of, ids, tickers, etfs, offline=offline, raiz=raiz)
    anterior = carregar_anterior(book, as_of)
    ex = executar(md, dados, params, as_of, emissores=emissores, anterior=anterior)
    res = gravar_snapshot(book, ex, dados, params, md_manifest=md.manifest, config_paths=config_paths(),
                          agora=agora, codigo=codigo, audit=audit)
    res["distribuicao"] = ex.distribuicao.get("distribuicao")
    return res


def cmd_run(args: argparse.Namespace) -> int:
    """``cdp cobertura run`` (``args.date``, ``args.emissores``: tupla de IIDs ou ``None``,
    ``args.offline``, ``args.raiz``)."""
    from ..workflow.runtime import Runtime

    rt = Runtime.from_args(args)
    as_of: date = args.date
    try:
        md = rt.store.load(as_of)
    except FileNotFoundError as exc:
        print(f"cdp cobertura run: base de mercado indisponível ({exc}).", file=sys.stderr)
        return INDISPONIVEL
    if md.as_of != as_of:
        print(f"cdp cobertura run: a base de mercado termina em {md.as_of}, não em {as_of}.", file=sys.stderr)
        return FALHA
    raiz = getattr(args, "raiz", None)
    try:
        res = executar_snapshot(Path(args.book), md, as_of, emissores=args.emissores,
                                offline=bool(args.offline), raiz=Path(raiz) if raiz else None)
    except FontePublicaIndisponivel as exc:
        print(f"cdp cobertura run: {exc}.", file=sys.stderr)
        return INDISPONIVEL
    except (LivroErro, KeyError) as exc:
        print(f"cdp cobertura run: recusado — {exc}", file=sys.stderr)
        return FALHA
    print(json.dumps(res, ensure_ascii=False, indent=1, default=str))
    return OK


def cmd_verify(args: argparse.Namespace) -> int:
    """``cdp cobertura verify`` (só leitura; código 0 íntegro, 1 falha)."""
    ok, msgs = verificar(Path(args.book), recalcular=not bool(getattr(args, "sem_recalculo", False)))
    for m in msgs:
        print(m)
    return OK if ok else FALHA


__all__ = ["EM_IMPLEMENTACAO", "cmd_run", "cmd_verify", "config_paths", "executar_snapshot"]
