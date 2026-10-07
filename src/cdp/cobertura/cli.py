"""Comandos ``cdp cobertura`` (dono: workstream A).

- ``cdp cobertura run --date D [--emissores IID,IID] [--offline] [--raiz DIR]``: snapshot de
  cobertura do dia ``D`` (depois do fechamento; parcial com ``--emissores`` após resultados).
  Usa a base de mercado (``--market``) e os dados públicos arquivados sob ``--raiz`` (padrão:
  ``data/``); ``--offline`` lê só o arquivo local, sem rede. A política temporal explícita
  separa D (base dos preços), data local do modelo e instante de conhecimento pós-coleta;
  grava na data do modelo e reutiliza somente o último retrato íntegro equivalente. Sem essa
  política, recusa D anterior ou igual ao último snapshot e publicações posteriores a D. Grava ``<book>/cobertura/<D>/`` e o
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
from dataclasses import replace
from datetime import UTC, date
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
    if carregar_parametros(valuation, pasta).sec("projecao").get("normalizacao_resultado_metodo") == "eventos_evidenciados":
        out["resultado_evidencias.json"] = Path(valuation).parent / "resultado_evidencias.json"
    return out


def executar_snapshot(book: Path, md, as_of: date, *, emissores=None, offline: bool = False,
                      raiz: Path | None = None, params=None, agora=None, codigo=None, audit: bool = True,
                      relogio=None, ri_autoridade=None, ri_mercado=None, arquivos_config=None, ri_cortes=None) -> dict:
    """Execução completa (coleta pública → modelos → gravação) sobre um ``MarketData`` dado."""
    params = params or carregar_parametros()
    from .temporal import ativo as temporal_ativo
    from .temporal import construir as corte_temporal
    temporal = temporal_ativo(params)
    if temporal:
        if agora is None and relogio is None:
            raise LivroErro("Política temporal exige instante ou relógio explícito do executor.")
        agora = agora or relogio()
        as_of = date.fromisoformat(corte_temporal(md.as_of, agora)["data_modelo"])
    from .ri_fluxo import (
        conferir_configuracao,
        conferir_livro_antes_de_escrita,
        conferir_mercado,
        exigir,
    )
    from .ri_observada import ativo as ri_ativo
    contexto_ri = exigir(params, ri_autoridade, agora if ri_ativo(params) else None, md)
    if ri_ativo(params):
        conferir_mercado(md, ri_mercado)
    conferir_configuracao(params, arquivos_config)
    conferir_livro_antes_de_escrita(book, params, autoridade=ri_autoridade,
                                  cortes=ri_cortes, agora=agora)
    if not ri_ativo(params):
        reparar_pendencias(book, audit, agora)
    if temporal:
        from .livro import datas_snapshots, snapshot
        datas = datas_snapshots(Path(book))
        if datas and as_of < datas[-1]:
            checar_data(book, as_of)
        pasta_existente = Path(book) / "cobertura" / as_of.isoformat()
        if pasta_existente.exists():
            existente = snapshot(Path(book), as_of)
            from .livro import conferir_corte
            conferir_corte(existente, agora)
            escopo = sorted(set(emissores)) if emissores else sorted(str(i) for i in md.universe.issuers.index)
            if sorted(existente.manifest["emissores"]) != escopo:
                raise LivroErro("Snapshot do dia já concluído com outro escopo de emissores; não sobrescreve.")
            if (existente.manifest["base_mercado"]["content_hash"] != md.manifest.content_hash()
                    or existente.manifest["configuracao"]["hash"] != params.hash()):
                raise LivroErro("Snapshot do dia já concluído com outra base/configuração; não sobrescreve.")
            reparos_ri = (reparar_pendencias(book, audit, agora, params=params,
                            ri_autoridade=ri_autoridade, ri_cortes=ri_cortes) if ri_ativo(params) else [])
            cortes_ri = ri_cortes if ri_ativo(params) else None
            integro, problemas = verificar(Path(book), recalcular=False,
                                            ri_autoridade=ri_autoridade, ri_cortes=cortes_ri)
            if not integro:
                raise LivroErro("Reserva recusada: livro de cobertura não íntegro: " + "; ".join(problemas))
            return {"pasta": str(pasta_existente), "manifest_sha256": existente.manifest_sha256,
                    "selo": json.loads((pasta_existente / "selo.json").read_text()),
                    "n_eventos": 0, "reparos": reparos_ri, "ja_concluido": True,
                    "corte_temporal": existente.manifest["corte_temporal"],
                    **({"ri_conhecimento_ate": ri_cortes[as_of.isoformat()].isoformat()}
                       if ri_ativo(params) else {})}
    if ri_ativo(params):
        checar_data(book, as_of)
        destino = Path(book) / "cobertura" / as_of.isoformat()
        if destino.exists():
            raise LivroErro(f"Snapshot {as_of} já existe.")
        reparar_pendencias(book, audit, agora, params=params,
                           ri_autoridade=ri_autoridade, ri_cortes=ri_cortes)
    checar_data(book, as_of)
    ok_s, msg_s = selado(book)
    if not ok_s:
        raise LivroErro(f"Livro da cobertura não confere com o último selo: {msg_s}.")
    ids = sorted(str(i) for i in md.universe.issuers.index)
    tickers = sorted(str(t) for t in md.universe.lines.index)
    etfs = [str(e["ticker"]) for e in params.etfs.get("etfs", []) if e["ticker"] in md.benchmarks.columns]
    dados = coletar(md, as_of, ids, tickers, etfs, offline=offline, raiz=raiz, params=params, conhecimento_ate=agora, ri_contexto=contexto_ri)
    if temporal:
        inicio = agora
        fim = relogio() if relogio is not None else agora
        if fim < inicio:
            raise LivroErro("Relógio de coleta retrocedeu.")
        corte = corte_temporal(md.as_of, fim)
        corte.update(coleta_inicio=inicio.astimezone(UTC).isoformat(),
                     coleta_fim=fim.astimezone(UTC).isoformat())
        as_of = date.fromisoformat(corte["data_modelo"])
        checar_data(book, as_of)
        dados = coletar(md, as_of, ids, tickers, etfs, offline=True, raiz=raiz, params=params, conhecimento_ate=fim, ri_contexto=contexto_ri)
        dados = replace(dados, corte_temporal=corte)
    anterior = carregar_anterior(book, as_of)
    from .ri_consumo import FornecedorConsumoRI
    fornecedor = FornecedorConsumoRI(md, dados) if ri_ativo(params) else None
    if ri_ativo(params):
        from .ri_fluxo import preparar_anterior
        anterior, fornecedores_anteriores = preparar_anterior(book, as_of, params,
            autoridade=ri_autoridade, cortes=ri_cortes)
        fornecedor = replace(fornecedor, anteriores=fornecedores_anteriores)
    conhecimento = fim if temporal else None
    kwargs_ri = {"ri_fornecedor": fornecedor, "conhecimento_ate": conhecimento} if ri_ativo(params) else {}
    ex = executar(md, dados, params, as_of, emissores=emissores, anterior=anterior, **kwargs_ri)
    res = gravar_snapshot(book, ex, dados, params, md_manifest=md.manifest, config_paths=arquivos_config or config_paths(),
                          agora=(relogio() if temporal and relogio is not None else agora),
                          codigo=codigo, audit=audit, ri_autoridade=ri_autoridade,
                          ri_mercado=ri_mercado, ri_cortes=ri_cortes, **kwargs_ri)
    if ri_ativo(params):
        res["ri_conhecimento_ate"] = dados.corte_temporal["conhecimento_ate"]
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
        valuation = Path(args.valuation) if getattr(args, "valuation", None) else DEFAULT_VALUATION
        pasta_params = (Path(args.parametros_cobertura) if getattr(args, "parametros_cobertura", None)
                        else DEFAULT_COBERTURA_DIR)
        params = carregar_parametros(valuation, pasta_params)
        from ..data.ri_captura.observado import instant
        from .ri_fluxo import autoridade_args, cortes_args
        from .ri_observada import ativo as ri_ativo
        autoridade = autoridade_args(args)
        if ri_ativo(params) and not getattr(args, "ri_conhecimento_ate", None):
            raise ValueError("RI fluxo: --ri-conhecimento-ate atual explícito obrigatório")
        from .temporal import ativo as temporal_ativo
        clocks = {"agora": rt.now(), "relogio": rt.now} if temporal_ativo(params) else {}
        if ri_ativo(params):
            clocks = {"agora": instant(args.ri_conhecimento_ate), "relogio": rt.now}
            if clocks["agora"] > rt.now():
                raise ValueError("RI fluxo: conhecimento futuro recusado")
        res = executar_snapshot(Path(args.book), md, as_of, emissores=args.emissores,
                                offline=bool(args.offline), raiz=Path(raiz) if raiz else None,
                                params=params, ri_autoridade=autoridade, ri_cortes=cortes_args(args),
                                ri_mercado=rt.market_root if ri_ativo(params) else None,
                                arquivos_config=config_paths(valuation, pasta_params), **clocks)
    except FontePublicaIndisponivel as exc:
        print(f"cdp cobertura run: {exc}.", file=sys.stderr)
        return INDISPONIVEL
    except (LivroErro, KeyError, ValueError) as exc:
        print(f"cdp cobertura run: recusado — {exc}", file=sys.stderr)
        return FALHA
    print(json.dumps(res, ensure_ascii=False, indent=1, default=str))
    return OK


def cmd_verify(args: argparse.Namespace) -> int:
    """``cdp cobertura verify`` (só leitura; código 0 íntegro, 1 falha)."""
    from .ri_fluxo import autoridade_args, cortes_args
    try:
        ok, msgs = verificar(Path(args.book), recalcular=not bool(getattr(args, "sem_recalculo", False)),
                             ri_autoridade=autoridade_args(args), ri_cortes=cortes_args(args))
    except (ValueError, OSError) as exc:
        ok, msgs = False, [str(exc)]
    for m in msgs:
        print(m)
    return OK if ok else FALHA


__all__ = ["EM_IMPLEMENTACAO", "cmd_run", "cmd_verify", "config_paths", "executar_snapshot"]
