"""CLI do CDP — Cabra da Peste (interface comum a qualquer harness: Claude Code, Codex, Gemini CLI).

Fluxo semanal (dia de montagem: o último pregão da semana na NYSE — sexta-feira ou, com feriado
nos EUA, o pregão anterior; a carteira inaugural, na data de início do mandato). Pesquisa a partir
das 11h de Brasília com todos os dados disponíveis até o momento da análise; decisão gravada até o
prazo efetivo (15h ou o fechamento mais cedo entre NYSE, B3 e BMV menos 45 minutos); execução ao
preço oficial de fechamento de cada linha (MOC), limitada à capacidade do leilão, pela rotina
diária da mesma noite:
    cdp weekly prepare --date D --mind claude-code|codex|gemini|outro
    (a mente escreve book/<D>/inputs/research_pack.json e pm_decision.json)
    cdp validate --week D
    cdp weekly preview --week D --mind ...   (opcional: revisão pré-trade, não grava)
    cdp weekly decide --week D --mind ...
    cdp tese prepare --week D                (fatos e briefing da tese da carteira decidida;
                                              adota docs/cdp/teses/<D>.json se tese.json faltar)
    (a mente escreve book/<D>/tese/tese.json)
    cdp validate-tese --week D               (valida a tese sem publicar)
    cdp tese publish --week D                (publica a tese; imutável)

Fluxo diário (após o fechamento; no dia de montagem, também a execução MOC da decisão):
    cdp daily --date D
    (a mente escreve reports/daily/<D>/comentario.json)
    cdp validate-daily --date D             (valida o comentário sem publicar)
    cdp daily publish --date D
Noite do dia de montagem — relatório semanal de resultado:
    cdp weekly close-report --date D [--publish]
    cdp validate-weekly-report --date D

Rotinas agendadas (no app de IA: Claude Code, Codex ou Gemini; ver docs/cdp/AUTOMACAO.md):
    cdp agenda                       (o que fazer agora: semana, prazos, fechamentos pendentes,
                                      base de mercado, pedidos de kill switch)
    cdp risk [--live] [--date D]     (monitor de risco; grava reports/risk/<D>/risco_<HHMM>.md)
    cdp painel [--out-dir D] [--sem-local]  (painel de gestão: index.html + data.json)
    cdp painel --publicado           (registra a página publicada no artifact; só depois de publicar)

Kill switch (só redução de risco; docs/cdp/EXECUCAO.md, "Kill switch: procedimento do operador"):
    cdp kill-switch on --reason "..." --by "..."   (liga e grava o pedido mesclável em
                                                    reports/risk/<D>/kill_switch_<HHMM>.yaml)
    cdp kill-switch aplicar-pedidos                (aplica pedidos pendentes; execução exclusiva)
    cdp kill-switch off --reason "..." --by "..."  (só humano, em terminal interativo próprio,
                                                    com a senha do operador; recusado em rotina,
                                                    CI ou agente de IA)
    cdp kill-switch senha                          (só humano: define a senha do operador; hash
                                                    fora do repositório)
    cdp kill-switch revisar-squeeze --emissor IID --reason "..." --by "..."
                                                   (só humano: revisão do stop de squeeze por
                                                    nome; libera o veto de compra do emissor)

Pré-início (uma vez, pela rotina, quando ``agenda`` informa ``reinicio.pendente``):
    cdp reinicio [--executar] [--pesquisa DIR]   (sem --executar só mostra o plano, não grava)

Cobertura e notas de pesquisa (números só do código):
    cdp cobertura run --date D [--emissores IID,IID] [--offline]
    cdp cobertura verify
    cdp cobertura revisao-mensal preparar|validar|publicar --date D
                                     (último dia de montagem do mês; a gestão escreve
                                      book/cobertura/revisoes/<D>/revisao.json)
    cdp nota agenda [--date D]
    cdp nota prepare --issuer IID [--date D]
    cdp validate-nota --issuer IID --date D
    cdp nota publish --issuer IID --date D

Qualquer assistente de IA como mente (pacote markdown autocontido; o JSON devolvido é validado
pelos comandos acima; nada é gravado no livro):
    cdp mente pacote --etapa pesquisa|decisao|tese|nota|comentario-diario|comentario-semanal
                     [--semana D | --data D | --emissor IID --data D] [--mente M] --saida ARQ.md

Outros: status, verify, demo, backtest, fetch-base, kill-switch.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import date, datetime
from pathlib import Path

from . import SIMULATED_DATA_NOTICE
from .contracts import HARNESS_MINDS
from .workflow.pacote import ETAPAS_PACOTE, MENTE_PADRAO
from .workflow.painel_artifact import painel_artifact_check  # reexportado (skills/testes)

DEFAULT_BOOK = Path("book")
DEFAULT_MARKET = Path("data/market")
DEFAULT_REPORTS = Path("reports")
DEFAULT_TESES = Path("docs/cdp/teses")
DEFAULT_UNIVERSE = Path("data/universe/latam_universe.csv")


def _d(s: str) -> date:
    return date.fromisoformat(s)


# Identificador de emissor/instrumento (ex.: BR_VALE, ETF_EWZ, SIM001): também vira caminho
# (``book/cobertura/notas/<IID>/``), então só maiúsculas, dígitos e "_".
_IID_RE = re.compile(r"[A-Z][A-Z0-9_]{1,63}")


def _iid(s: str) -> str:
    if not _IID_RE.fullmatch(s):
        raise argparse.ArgumentTypeError(f"identificador de emissor inválido: {s!r}")
    return s


def _iids(s: str) -> tuple[str, ...]:
    """Lista ``IID,IID`` (sem vazios nem repetidos) em ordem."""
    out = tuple(_iid(x.strip()) for x in s.split(","))
    if len(set(out)) != len(out):
        raise argparse.ArgumentTypeError(f"emissor repetido em {s!r}")
    return out


def _today_brt() -> date:
    from zoneinfo import ZoneInfo

    return datetime.now(ZoneInfo("America/Sao_Paulo")).date()


def _print(obj) -> None:
    print(json.dumps(obj, ensure_ascii=False, indent=2, default=str))


# ----------------------------------------------------------------------------- comandos


def cmd_status(args: argparse.Namespace) -> int:
    from .calendar import chave_da_semana, dia_de_montagem, open_markets
    from .workflow.runtime import Runtime

    d = args.date or _today_brt()
    rt = Runtime.from_args(args)
    week = chave_da_semana(d, rt.cfg)
    info = {
        "data": d, "pregao_b3": open_markets(d).get("BR"), "mercados_abertos": open_markets(d),
        "dia_de_rebalanceamento": dia_de_montagem(d, rt.cfg) and not rt.pre_inicio(d),
        "semana": week,
        "kill_switch": rt.kill_switch_active(),
        "decisao_da_semana": bool(week and rt.book.list_decisions(week)),
        "ultimo_registro_diario": rt.last_record_date(),
        "nav_atual_usd": rt.current_nav(),
        "ultimo_pregao_gravado": rt.store_last_date(),
    }
    _print(info)
    return 0


def cmd_fetch_base(args: argparse.Namespace) -> int:
    from .data.store import MarketStore

    store = MarketStore(args.market)
    manifest = store.build_base(Path(args.universe), _d(args.as_of), start=_d(args.start))
    _print({"base": manifest.snapshot_id, "as_of": manifest.as_of,
            "arquivos": len(manifest.files), "faltantes": manifest.missing_tickers[:20],
            "limitacoes": manifest.limitations})
    return 0


def _reinicio_pendente(rt) -> str | None:
    """Motivo, se o livro ainda espera o pré-início (``cdp reinicio --executar``)."""
    from .workflow.reinicio import situacao

    sit = situacao(rt)
    return sit["motivo"] if sit["pendente"] else None


def cmd_weekly_prepare(args: argparse.Namespace) -> int:
    from .calendar import dia_de_montagem
    from .workflow.runtime import Runtime

    d = args.date or _today_brt()
    rt = Runtime.from_args(args)
    pendente = _reinicio_pendente(rt)
    if pendente:
        print(f"Pré-início pendente: {pendente}.", file=sys.stderr)
        return 1
    if not args.force and (rt.pre_inicio(d) or not dia_de_montagem(d, rt.cfg)):
        inicio = rt.cfg.fund.inception_date
        if d < inicio:
            print(f"Pré-início: carteira inaugural em {inicio:%d/%m/%Y}, ao preço de "
                  "fechamento — nada a fazer.")
        else:
            print(f"{d} não é dia de montagem da carteira — nada a fazer.")
        return 0
    out = rt.weekly_prepare(d, mind=args.mind, live=not args.offline)
    _print(out)
    return 0


def cmd_validate(args: argparse.Namespace) -> int:
    from .workflow.runtime import Runtime

    rt = Runtime.from_args(args)
    ok, issues = rt.validate_inputs(_d(args.week), mind=args.mind,
                                    so_pesquisa=bool(getattr(args, "so_pesquisa", False)))
    # Contrato único dos validadores: JSON com "ok" e "problemas" (código 0 válido, 1 não).
    _print({"semana": _d(args.week), "ok": ok, "problemas": list(issues)})
    return 0 if ok else 1


def cmd_weekly_decide(args: argparse.Namespace) -> int:
    from .workflow.runtime import Runtime

    rt = Runtime.from_args(args)
    out = rt.weekly_decide(_d(args.week), mind=args.mind)
    _print(out)
    return 0


def cmd_weekly_preview(args: argparse.Namespace) -> int:
    from .workflow.runtime import Runtime

    rt = Runtime.from_args(args)
    out = rt.weekly_preview(_d(args.week), mind=args.mind)
    if args.out:
        Path(args.out).parent.mkdir(parents=True, exist_ok=True)
        Path(args.out).write_text(json.dumps(out, ensure_ascii=False, indent=2, default=str),
                                  encoding="utf-8")
    _print({k: v for k, v in out.items() if k not in ("posicoes", "sombra_quant", "tentativas")})
    return 0


def cmd_daily(args: argparse.Namespace) -> int:
    from .workflow.runtime import Runtime

    rt = Runtime.from_args(args)
    d = args.date or _today_brt()
    pendente = _reinicio_pendente(rt) if args.action != "publish" else None
    if pendente:
        print(f"Pré-início pendente: {pendente}.", file=sys.stderr)
        return 1
    if args.action == "publish":
        out = rt.daily_publish(d)
    else:
        out = rt.daily_close(d, live=not args.offline, mind=args.mind)
    _print(out)
    return 0


def cmd_validate_daily(args: argparse.Namespace) -> int:
    """Valida ``comentario.json`` do dia SEM publicar (``daily publish`` é imutável)."""
    from .workflow.agenda import validate_daily_commentary
    from .workflow.runtime import Runtime

    d = args.date or _today_brt()
    ok, issues = validate_daily_commentary(Runtime.from_args(args), d)
    _print({"data": d, "ok": ok, "problemas": list(issues)})
    return 0 if ok else 1


def cmd_tese(args: argparse.Namespace) -> int:
    """Tese de investimento da carteira decidida: ``prepare`` (fatos) ou ``publish``."""
    from .workflow.runtime import Runtime

    rt = Runtime.from_args(args)
    week = _d(args.week)
    try:
        out = rt.thesis_publish(week) if args.action == "publish" else rt.thesis_prepare(week)
    except (OSError, ValueError) as exc:  # já publicada, sem decisão ou arquivo ausente
        print(f"Erro: {exc}", file=sys.stderr)
        return 1
    _print(out)
    return 0


def cmd_validate_tese(args: argparse.Namespace) -> int:
    """Valida ``book/<semana>/tese/tese.json`` SEM publicar (``tese publish`` é imutável)."""
    from .workflow.runtime import Runtime

    try:
        out = Runtime.from_args(args).validate_thesis(_d(args.week))
    except (OSError, ValueError) as exc:
        print(f"Erro: {exc}", file=sys.stderr)
        return 1
    _print(out)
    return 0 if out["ok"] else 1


def cmd_verify(args: argparse.Namespace) -> int:
    from .workflow.runtime import Runtime

    rt = Runtime.from_args(args)
    ok, msgs = rt.verify_all()
    print("ÍNTEGRO" if ok else "FALHA DE INTEGRIDADE")
    for m in msgs:
        print(f"- {m}")
    return 0 if ok else 1


def cmd_avaliacao(args: argparse.Namespace) -> int:
    """Lê coortes verificadas; não grava métricas, probabilidades ou fase do fundo."""
    from .research.evaluation import AuthenticatedViewTracker
    from .workflow.runtime import Runtime

    try:
        rt = Runtime.from_args(args)
        if args.action == "status":
            ok, errors = rt.verify_all()
            if not ok:
                raise ValueError("avaliação não autenticada: " + "; ".join(errors))
            _print({"coortes": rt.evaluation_status()})
            return 0
        tracker = AuthenticatedViewTracker(rt.book_root, mind=args.mind, channel=args.canal,
                                          include_synthetic=args.simulados, track=rt.track(),
                                          market_root=rt.market_root)
        hist = tracker.ic_history()
        phase, reason = tracker.phase_gate(rt.cfg)
        # Pandas converte NaN estatístico a null: a saída pública nunca inventa um zero.
        rows = json.loads(hist.to_json(orient="records", date_format="iso"))
        _print({"mente": args.mind, "canal": args.canal, "historico": rows,
                "dados": "DADOS SIMULADOS: diagnóstico" if args.simulados else "coortes reais verificadas",
                "fase_vigente": rt.cfg.research.llm_phase, "fase_recomendada": phase,
                "motivo_fase": reason,
                "brier": {"valor": None, "n": 0,
                          "motivo": "probabilidade, evento e horizonte explícitos ainda não registrados"}})
        return 0
    except (OSError, ValueError) as exc:
        print(f"Erro: {exc}", file=sys.stderr)
        return 1


#: Variáveis que indicam rotina, CI ou sessão de agente de IA (Claude Code, Codex, Gemini CLI,
#: Antigravity): nesses contextos ninguém desliga o kill switch — só um humano, num terminal
#: próprio. ``CDP_HARNESS`` é definido no ambiente de toda rotina (tabela ``set`` do Codex,
#: ambiente das rotinas na nuvem, scripts de agendamento).
CONTEXTO_NAO_HUMANO = ("CDP_EXECUTOR", "CDP_TRAVA_ID", "CDP_EXECUCAO", "CDP_ROTINA", "CDP_ENSAIO",
                       "CDP_HARNESS", "CI", "GITHUB_ACTIONS", "CLAUDECODE", "CLAUDE_CODE_REMOTE",
                       "CLAUDE_CODE_REMOTE_SESSION_ID", "CLAUDE_CODE_ENTRYPOINT",
                       "CODEX_SANDBOX", "CODEX_SANDBOX_NETWORK_DISABLED",
                       "CODEX_MANAGED_BY_NPM", "CODEX_THREAD_ID", "CODEX_CI", "GEMINI_CLI",
                       "ANTIGRAVITY_AGENT", "CURSOR_AGENT")
#: Prefixos de variáveis exportadas por apps de IA aos comandos que executam (a lista exata muda
#: entre versões). ``CODEX_HOME`` é configuração do próprio usuário e não conta. (O Claude Code
#: sempre exporta ``CLAUDECODE``; ``CLAUDE_CODE_*`` também aparece no perfil de quem usa o app.)
PREFIXOS_NAO_HUMANOS = ("CODEX_", "ANTIGRAVITY_")
_NAO_SAO_AGENTE = frozenset({"CODEX_HOME"})


def _contexto_nao_humano(env=None) -> list[str]:
    """Variáveis presentes que indicam rotina, CI ou agente de IA (vazio = possível humano)."""
    import os

    env = os.environ if env is None else env
    achadas = [k for k in CONTEXTO_NAO_HUMANO if env.get(k)]
    achadas += sorted(k for k in env if k.startswith(PREFIXOS_NAO_HUMANOS)
                      and k not in _NAO_SAO_AGENTE and k not in achadas and env.get(k))
    return achadas


def _desligamento_humano(args: argparse.Namespace,
                         acao: str = "desliga o kill switch") -> str | None:
    """Motivo da recusa do ``kill-switch off`` e do ``kill-switch revisar-squeeze`` (``None`` =
    operador humano confirmado).

    Vale em qualquer harness: rotinas, CI e agentes de IA rodam sem terminal interativo (ou com
    as variáveis de :data:`CONTEXTO_NAO_HUMANO`); o operador digita de novo o motivo e, como
    confirmação fora de banda, a senha do operador (:mod:`cdp.operador`: segredo que só o humano
    conhece, guardado fora do repositório como hash). Um agente com pseudoterminal chega no
    máximo ao pedido da senha — e não a tem."""
    from . import operador

    ctx = _contexto_nao_humano()
    if ctx:
        return (f"recusado: contexto de rotina, CI ou agente ({', '.join(ctx)}). Só um humano "
                f"{acao}, num terminal próprio (docs/cdp/EXECUCAO.md, "
                "\"Kill switch: procedimento do operador\").")
    if not (sys.stdin.isatty() and sys.stdout.isatty()):
        return (f"recusado: sem terminal interativo. Só um humano {acao}, num "
                "terminal próprio (docs/cdp/EXECUCAO.md, \"Kill switch: procedimento do "
                "operador\").")
    if len((args.reason or "").strip()) < 10 or args.by.strip().lower() in ("", "operador") \
            or args.by.strip().upper().startswith("CDP"):
        return ("informe --by com o seu nome e --reason com pelo menos 10 caracteres "
                "(a revisão que justifica o desligamento).")
    try:
        typed = input("Digite de novo o motivo para confirmar: ")
    except EOFError:
        return "recusado: confirmação não digitada."
    if " ".join(typed.split()) != " ".join(args.reason.split()):
        return "recusado: o motivo digitado não confere."
    if not operador.configurado():
        return ("recusado: senha do operador não definida. O humano define a senha uma vez, num "
                "terminal próprio: `uv run python -m cdp kill-switch senha` (hash guardado fora "
                f"do repositório, em {operador.caminho_segredo()}).")
    try:
        senha = operador.pedir_senha()
    except (EOFError, KeyboardInterrupt):
        return "recusado: senha do operador não digitada."
    if not operador.conferir(senha):
        return "recusado: a senha do operador não confere."
    return None


def _definir_senha_operador() -> int:
    """``kill-switch senha``: define (ou troca) a senha do operador — só humano, em terminal."""
    from . import operador

    ctx = _contexto_nao_humano()
    if ctx:
        print(f"recusado: contexto de rotina, CI ou agente ({', '.join(ctx)}). Só um humano "
              "define a senha do operador, num terminal próprio.", file=sys.stderr)
        return 2
    if not (sys.stdin.isatty() and sys.stdout.isatty()):
        print("recusado: sem terminal interativo.", file=sys.stderr)
        return 2
    try:
        if operador.configurado() and not operador.conferir(
                operador.pedir_senha("Senha atual do operador: ")):
            print("recusado: a senha atual não confere.", file=sys.stderr)
            return 2
        nova = operador.pedir_senha(
            f"Nova senha do operador (mínimo {operador.TAMANHO_MINIMO} caracteres): ")
        if operador.pedir_senha("Repita a nova senha: ") != nova:
            print("recusado: as senhas não conferem.", file=sys.stderr)
            return 2
        path = operador.definir(nova)
    except (EOFError, KeyboardInterrupt):
        print("recusado: senha não digitada.", file=sys.stderr)
        return 2
    except ValueError as exc:
        print(f"recusado: {exc}", file=sys.stderr)
        return 2
    _print({"senha_do_operador": "definida", "arquivo": str(path),
            "aviso": "guarde a senha fora do repositório; nunca a entregue a um app de IA"})
    return 0


def cmd_kill_switch(args: argparse.Namespace) -> int:
    from .workflow.runtime import Runtime

    rt = Runtime.from_args(args)
    if args.state == "on":
        if not args.reason or len(args.reason) < 10:
            print("Informe --reason com pelo menos 10 caracteres.", file=sys.stderr)
            return 2
        # Pedido mesclável primeiro (reports/risk/<data>/kill_switch_<HHMM>.yaml): se o livro
        # ficar retido sem a trava exclusiva, a próxima execução exclusiva aplica o pedido.
        pedido = rt.request_kill_switch(args.reason, args.by)
        rt.set_kill_switch(True, args.reason, args.by)
        rt.mark_kill_switch_request(pedido["sha256"], "aplicado", args.by)
        _print({"kill_switch": "on", "pedido": pedido["arquivo"]})
        return 0
    if args.state == "senha":
        return _definir_senha_operador()
    if args.state == "aplicar-pedidos":
        _print({"aplicados": rt.apply_kill_switch_requests(),
                "kill_switch": rt.kill_switch_active()})
        return 0
    if args.state == "revisar-squeeze":
        if not args.emissor:
            print("Informe --emissor.", file=sys.stderr)
            return 2
        recusa = _desligamento_humano(args, "revisa um stop de squeeze")
        if recusa:
            print(recusa, file=sys.stderr)
            return 2
        try:
            _print({"revisao_squeeze": rt.review_squeeze(args.emissor, args.reason, args.by)})
        except ValueError as exc:
            print(str(exc), file=sys.stderr)
            return 2
        return 0
    recusa = _desligamento_humano(args)
    if recusa:
        print(recusa, file=sys.stderr)
        return 2
    rt.set_kill_switch(False, args.reason, args.by)
    print("Kill switch: off")
    return 0


def cmd_demo(args: argparse.Namespace) -> int:
    from .workflow.demo import run_demo

    print(f"{SIMULATED_DATA_NOTICE}: demonstração offline com mercado sintético.")
    out = run_demo(Path(args.out), days=args.days)
    _print(out)
    return 0


def cmd_agenda(args: argparse.Namespace) -> int:
    from .workflow.agenda import agenda
    from .workflow.runtime import Runtime

    rt = Runtime.from_args(args)
    _print(agenda(rt, now=args.agora))
    return 0


def cmd_risk(args: argparse.Namespace) -> int:
    from .workflow.risk_monitor import (
        PRE_INICIO,
        RISK_DIRNAME,
        run_risk_monitor,
        summary_view,
        write_risk_report,
    )
    from .workflow.runtime import Runtime

    rt = Runtime.from_args(args)
    res = run_risk_monitor(rt, as_of=args.date, live=args.live)
    view = summary_view(res)
    if res.get("status") == PRE_INICIO:  # sem carteira: nada a monitorar nem a gravar
        view["relatorio"] = None
        _print(view)
        return 0
    out_root = Path(args.out) if args.out else Path(args.reports) / RISK_DIRNAME
    paths = write_risk_report(res, out_root, rt.cfg)
    view["relatorio"] = paths
    _print(view)
    return 0


DEFAULT_PAINEL_DIR = Path("artifacts/painel")


def cmd_painel(args: argparse.Namespace) -> int:
    """Grava o painel do artifact (casca ``index.html``, estilo e script versionados,
    ``data.json`` e a cópia local); só lê o livro, a trilha e os relatórios.

    A saída inclui ``artifact`` (:func:`painel_artifact_check`): as skills só leem e publicam
    quando ``artifact.publicavel`` é ``true``, lendo por inteiro ``artifact.arquivos_para_ler`` e
    publicando ``artifact.publicar``.
    ``--publicado`` não gera nada: registra (``PAGINA_PUBLICADA.sha256``) que o ``index.html``
    atual foi publicado no artifact — rode só depois de uma publicação bem-sucedida que incluiu
    a página.
    """
    from .workflow.painel import mark_published, write_painel
    from .workflow.runtime import Runtime

    out_dir = Path(args.out_dir)
    if args.publicado:
        try:
            _print({"pagina_publicada": mark_published(out_dir)})
        except ValueError as exc:
            print(f"Erro: {exc}", file=sys.stderr)
            return 2
        return 0
    rt = Runtime.from_args(args)
    out = write_painel(rt, out_dir, standalone=not args.sem_local)
    out = {**out, "artifact": painel_artifact_check(
        out_dir, page_changed=bool(out.get("page_changed")),
        page_version=out.get("page_sha256"))}
    _print(out)
    return 0


def _aware(s: str) -> datetime:
    dt = datetime.fromisoformat(s)
    if dt.tzinfo is None:
        from zoneinfo import ZoneInfo

        dt = dt.replace(tzinfo=ZoneInfo("America/Sao_Paulo"))
    return dt


def cmd_backtest(args: argparse.Namespace) -> int:
    from .workflow.runtime import Runtime

    rt = Runtime.from_args(args)
    out = rt.run_backtest(_d(args.start), _d(args.end) if args.end else None, Path(args.out))
    _print(out)
    return 0


# ----------------------------------------------------------------------------- comandos novos
# Registrados com os argumentos finais (contrato da CLI). Cada handler importa sob demanda a
# função do módulo dono, que responde "em implementação" (código 2) até a entrega.


def cmd_cobertura(args: argparse.Namespace) -> int:
    """``cdp cobertura run|verify`` (módulo :mod:`cdp.cobertura.cli`)."""
    from .cobertura import cli

    handler = {"run": cli.cmd_run, "verify": cli.cmd_verify}[args.action]
    return handler(args)


def cmd_cobertura_revisao(args: argparse.Namespace) -> int:
    """``cdp cobertura revisao-mensal preparar|validar|publicar`` (:mod:`cdp.cobertura.revisao`)."""
    from .cobertura.revisao import cmd_revisao

    return cmd_revisao(args)


def cmd_nota(args: argparse.Namespace) -> int:
    """``cdp nota agenda|prepare|publish`` (módulo :mod:`cdp.workflow.notas`)."""
    from .workflow import notas

    handler = {"agenda": notas.cmd_agenda, "prepare": notas.cmd_prepare,
               "publish": notas.cmd_publish}[args.action]
    return handler(args)


def cmd_validate_nota(args: argparse.Namespace) -> int:
    """Valida ``nota.json`` do emissor SEM publicar (``nota publish`` é imutável)."""
    from .workflow.notas import cmd_validate

    return cmd_validate(args)


def cmd_weekly_close_report(args: argparse.Namespace) -> int:
    """Relatório semanal de resultado (módulo :mod:`cdp.workflow.relatorio_semanal`)."""
    from .workflow.relatorio_semanal import cmd_close_report

    return cmd_close_report(args)


def cmd_validate_weekly_report(args: argparse.Namespace) -> int:
    """Valida ``reports/semanal/<D>/comentario.json`` SEM publicar."""
    from .workflow.relatorio_semanal import cmd_validate

    return cmd_validate(args)


def cmd_mente(args: argparse.Namespace) -> int:
    """``cdp mente pacote`` (módulo :mod:`cdp.workflow.pacote`)."""
    from .workflow.pacote import cmd_pacote

    return cmd_pacote(args)


def cmd_reinicio(args: argparse.Namespace) -> int:
    """Pré-início do fundo (módulo :mod:`cdp.workflow.reinicio`); sem ``--executar`` só mostra o
    plano e não grava nada."""
    from .workflow.reinicio import cmd_reinicio as handler

    return handler(args)


# ----------------------------------------------------------------------------- parser


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="cdp", description="CDP — Cabra da Peste (PM autônomo LatAm L/S)")
    p.add_argument("--config", default=None, help="fund.yaml (padrão: configs/cdp/fund.yaml)")
    p.add_argument("--book", default=str(DEFAULT_BOOK))
    p.add_argument("--market", default=str(DEFAULT_MARKET))
    p.add_argument("--reports", default=str(DEFAULT_REPORTS))
    p.add_argument("--teses", default=str(DEFAULT_TESES),
                   help="pasta versionada dos rascunhos de tese escritos fora do clone da rotina "
                        f"(<AAAA-MM-DD>.json; padrão: {DEFAULT_TESES.as_posix()})")
    sub = p.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("status", help="estado do fundo e do calendário")
    s.add_argument("--date", type=_d)
    s.set_defaults(func=cmd_status)

    s = sub.add_parser("fetch-base", help="constrói o histórico-base imutável (dados reais)")
    s.add_argument("--as-of", required=True)
    s.add_argument("--start", default="2019-01-02")
    s.add_argument("--universe", default=str(DEFAULT_UNIVERSE))
    s.set_defaults(func=cmd_fetch_base)

    w = sub.add_parser("weekly", help="montagem semanal da carteira")
    wsub = w.add_subparsers(dest="action", required=True)
    s = wsub.add_parser("prepare", help="coleta todos os dados até agora e gera o briefing")
    s.add_argument("--date", type=_d)
    s.add_argument("--mind", choices=HARNESS_MINDS, required=True)
    s.add_argument("--force", action="store_true", help="ignora a regra do primeiro pregão")
    s.add_argument("--offline", action="store_true", help="sem barra intradiária/coleta ao vivo")
    s.set_defaults(func=cmd_weekly_prepare)
    s = wsub.add_parser("preview", help="prévia pré-trade do livro (não grava nada)")
    s.add_argument("--week", required=True)
    s.add_argument("--mind", choices=HARNESS_MINDS, required=True)
    s.add_argument("--out", help="grava a prévia completa (JSON) neste caminho")
    s.set_defaults(func=cmd_weekly_preview)
    s = wsub.add_parser("decide", help="valida, otimiza, aplica gates e decide (autônomo)")
    s.add_argument("--week", required=True)
    s.add_argument("--mind", choices=HARNESS_MINDS, required=True)
    s.set_defaults(func=cmd_weekly_decide)
    s = wsub.add_parser("close-report",
                        help="relatório semanal de resultado após o fechamento do rebalanceamento")
    s.add_argument("--date", type=_d, required=True, help="pregão do rebalanceamento (AAAA-MM-DD)")
    s.add_argument("--publish", action="store_true",
                   help="publica o relatório (comentário da mente ou modelo de código); imutável")
    s.set_defaults(func=cmd_weekly_close_report)

    s = sub.add_parser("validate", help="valida os arquivos escritos pela mente")
    s.add_argument("--week", required=True)
    s.add_argument("--mind", choices=HARNESS_MINDS)
    s.add_argument("--so-pesquisa", action="store_true",
                   help="valida só research_pack.json (etapa de pesquisa, antes da decisão)")
    s.set_defaults(func=cmd_validate)

    s = sub.add_parser("daily", help="fechamento diário (close) ou publicação do relatório")
    s.add_argument("action", nargs="?", default="close", choices=["close", "publish"])
    s.add_argument("--date", type=_d)
    s.add_argument("--offline", action="store_true")
    s.add_argument("--mind", choices=HARNESS_MINDS)
    s.set_defaults(func=cmd_daily)

    s = sub.add_parser("validate-daily",
                       help="valida o comentario.json do dia sem publicar (publish é imutável)")
    s.add_argument("--date", type=_d)
    s.add_argument("--mind", choices=HARNESS_MINDS, default=None,
                   help="mente desta execução (padrão: a do CDP_HARNESS); o arquivo da mente "
                        "precisa declarar a mesma")
    s.set_defaults(func=cmd_validate_daily)

    t = sub.add_parser("tese", help="tese de investimento da carteira decidida (números só do "
                                    "código)")
    tsub = t.add_subparsers(dest="action", required=True)
    s = tsub.add_parser("prepare", help="gera fatos, análise e briefing da tese "
                                        "(book/<semana>/tese/)")
    s.add_argument("--week", required=True, help="semana da decisão (AAAA-MM-DD)")
    s.set_defaults(func=cmd_tese)
    s = tsub.add_parser("publish", help="publica a tese (mente ou automática); imutável")
    s.add_argument("--week", required=True, help="semana da decisão (AAAA-MM-DD)")
    s.add_argument("--mind", choices=HARNESS_MINDS, default=None,
                   help="mente desta execução (padrão: a do CDP_HARNESS); o arquivo da mente "
                        "precisa declarar a mesma")
    s.set_defaults(func=cmd_tese)

    s = sub.add_parser("validate-tese",
                       help="valida o tese.json da semana sem publicar (publish é imutável)")
    s.add_argument("--week", required=True, help="semana da decisão (AAAA-MM-DD)")
    s.add_argument("--mind", choices=HARNESS_MINDS, default=None,
                   help="mente desta execução (padrão: a do CDP_HARNESS); o arquivo da mente "
                        "precisa declarar a mesma")
    s.set_defaults(func=cmd_validate_tese)

    s = sub.add_parser("validate-weekly-report",
                       help="valida o comentario.json do relatório semanal sem publicar")
    s.add_argument("--date", type=_d, required=True, help="pregão do rebalanceamento (AAAA-MM-DD)")
    s.add_argument("--mind", choices=HARNESS_MINDS, default=None,
                   help="mente desta execução (padrão: a do CDP_HARNESS); o arquivo da mente "
                        "precisa declarar a mesma")
    s.set_defaults(func=cmd_validate_weekly_report)

    c = sub.add_parser("cobertura", help="cobertura de ações e ETFs: modelos e preços-alvo de 12 "
                                         "meses (números só do código)")
    csub = c.add_subparsers(dest="action", required=True)
    s = csub.add_parser("run", help="snapshot de cobertura do dia (book/cobertura/<D>/)")
    s.add_argument("--date", type=_d, required=True, help="pregão de referência (AAAA-MM-DD)")
    s.add_argument("--emissores", type=_iids, default=None,
                   help="execução parcial: IID,IID (ex.: após resultados)")
    s.add_argument("--offline", action="store_true", help="sem coleta ao vivo")
    s.add_argument("--raiz", default=None,
                   help="raiz do arquivo de dados públicos (<raiz>/publico/...; padrão: data/)")
    s.set_defaults(func=cmd_cobertura)
    s = csub.add_parser("verify", help="confere o livro da cobertura, manifestos e placar")
    s.add_argument("--sem-recalculo", action="store_true",
                   help="só confere cadeia e arquivos (não refaz os preços-alvo)")
    s.set_defaults(func=cmd_cobertura)
    r = csub.add_parser("revisao-mensal",
                        help="revisão mensal dos modelos (último dia de montagem do mês): pacote "
                             "do código, leitura da gestão e publicação imutável")
    rsub = r.add_subparsers(dest="etapa", required=True)
    for etapa, ajuda in (("preparar", "grava o pacote (fatos, quadros, lista de verificação)"),
                         ("validar", "valida revisao.json sem publicar"),
                         ("publicar", "publica a revisão (imutável) e grava o evento na trilha")):
        s = rsub.add_parser(etapa, help=ajuda)
        s.add_argument("--date", type=_d, required=True, help="data da revisão (AAAA-MM-DD)")
        if etapa != "preparar":
            s.add_argument("--mind", choices=HARNESS_MINDS, default=None,
                           help="mente desta execução (padrão: a do CDP_HARNESS)")
        s.set_defaults(func=cmd_cobertura_revisao)

    n = sub.add_parser("nota", help="notas de pesquisa por emissor (números só do código)")
    nsub = n.add_subparsers(dest="action", required=True)
    s = nsub.add_parser("agenda", help="fila determinística de notas a escrever")
    s.add_argument("--date", type=_d, default=None, help="data de referência (padrão: hoje)")
    s.set_defaults(func=cmd_nota)
    s = nsub.add_parser("prepare", help="gera fatos e briefing da nota do emissor")
    s.add_argument("--issuer", type=_iid, required=True, help="emissor (IID)")
    s.add_argument("--date", type=_d, default=None, help="data da nota (padrão: hoje)")
    s.set_defaults(func=cmd_nota)
    s = nsub.add_parser("publish", help="publica a nota do emissor (mente ou modelo); imutável")
    s.add_argument("--issuer", type=_iid, required=True, help="emissor (IID)")
    s.add_argument("--date", type=_d, required=True, help="data da nota (AAAA-MM-DD)")
    s.add_argument("--mind", choices=HARNESS_MINDS, default=None,
                   help="mente desta execução (padrão: a do CDP_HARNESS); o arquivo da mente "
                        "precisa declarar a mesma")
    s.set_defaults(func=cmd_nota)

    s = sub.add_parser("validate-nota",
                       help="valida o nota.json do emissor sem publicar (publish é imutável)")
    s.add_argument("--issuer", type=_iid, required=True, help="emissor (IID)")
    s.add_argument("--date", type=_d, required=True, help="data da nota (AAAA-MM-DD)")
    s.add_argument("--mind", choices=HARNESS_MINDS, default=None,
                   help="mente desta execução (padrão: a do CDP_HARNESS); o arquivo da mente "
                        "precisa declarar a mesma")
    s.set_defaults(func=cmd_validate_nota)

    m = sub.add_parser("mente", help="passos da mente com qualquer assistente de IA")
    msub = m.add_subparsers(dest="action", required=True)
    s = msub.add_parser("pacote", help="exporta um pacote markdown autocontido (papel, regras, "
                                       "fatos, schema, exemplo e validação) de uma etapa")
    s.add_argument("--etapa", required=True, choices=ETAPAS_PACOTE)
    s.add_argument("--semana", type=_d, default=None,
                   help="semana (pesquisa, decisao, tese; AAAA-MM-DD)")
    s.add_argument("--data", type=_d, default=None,
                   help="data (nota, comentario-diario, comentario-semanal; AAAA-MM-DD)")
    s.add_argument("--emissor", type=_iid, default=None, help="emissor da nota (IID)")
    s.add_argument("--mente", choices=HARNESS_MINDS, default=MENTE_PADRAO,
                   help=f"valor do campo mind no JSON (padrão: {MENTE_PADRAO})")
    s.add_argument("--saida", required=True, help="arquivo .md do pacote (fora do livro)")
    s.set_defaults(func=cmd_mente)

    s = sub.add_parser("reinicio",
                       help="pré-início: abre o livro na data de início do mandato (uma vez; sem "
                            "--executar só mostra o plano)")
    s.add_argument("--executar", action="store_true",
                   help="executa (sem a opção: simulação, nada é gravado)")
    s.add_argument("--pesquisa", default="pesquisa",
                   help="pasta do material de pesquisa da mente (padrão: pesquisa)")
    s.set_defaults(func=cmd_reinicio)

    s = sub.add_parser("verify", help="verifica trilha de auditoria, track record e decisões")
    s.set_defaults(func=cmd_verify)

    s = sub.add_parser("avaliacao", help="avaliação autenticada por mente e canal, somente leitura")
    asub = s.add_subparsers(dest="action", required=True)
    a = asub.add_parser("status", help="maturidade e pendências das coortes verificadas")
    a.set_defaults(func=cmd_avaliacao)
    a = asub.add_parser("ic", help="IC, amostra e recomendação de fase; não altera o mandato")
    a.add_argument("--mind", choices=HARNESS_MINDS, required=True, help="mente cujas coortes serão lidas")
    a.add_argument("--canal", choices=["quant", "pesquisa_ai", "mente_final"], default="mente_final")
    a.add_argument("--simulados", action="store_true", help="inclui DADOS SIMULADOS para diagnóstico")
    a.set_defaults(func=cmd_avaliacao)

    s = sub.add_parser("kill-switch",
                       help="liga o kill switch (só redução de risco); desligar é só para humano "
                            "em terminal interativo")
    s.add_argument("state", choices=["on", "off", "aplicar-pedidos", "revisar-squeeze", "senha"],
                   help="on: liga (grava também o pedido em reports/risk/<data>/); off: só humano, "
                        "terminal interativo, motivo digitado de novo e senha do operador; "
                        "aplicar-pedidos: aplica no livro os pedidos pendentes (execução "
                        "exclusiva); revisar-squeeze: só humano, libera o veto de compra do "
                        "emissor após stop de squeeze; senha: define a senha do operador (só "
                        "humano; hash fora do repositório)")
    s.add_argument("--emissor", default="", help="emissor revisado (revisar-squeeze)")
    s.add_argument("--reason", default="", help="motivo (pelo menos 10 caracteres)")
    s.add_argument("--by", default="operador", help="quem liga ou desliga")
    s.set_defaults(func=cmd_kill_switch)

    s = sub.add_parser("demo", help="demonstração offline completa (DADOS SIMULADOS)")
    s.add_argument("--out", default="outputs/cdp_demo")
    s.add_argument("--days", type=int, default=5)
    s.set_defaults(func=cmd_demo)

    s = sub.add_parser("agenda", help="o que a rotina local deve fazer agora (determinístico)")
    s.add_argument("--agora", type=_aware, default=None,
                   help="instante ISO (sem fuso = Brasília); padrão: agora")
    s.set_defaults(func=cmd_agenda)

    s = sub.add_parser("risk", help="monitor de risco (fechamento ou intradiário com --live)")
    s.add_argument("--date", type=_d, help="data de referência (padrão: hoje em Brasília)")
    s.add_argument("--live", action="store_true",
                   help="marca a carteira com cotações do momento (fonte atrasada)")
    s.add_argument("--out", default=None, help="pasta dos relatórios (padrão: <reports>/risk)")
    s.set_defaults(func=cmd_risk)

    s = sub.add_parser("painel", help="painel de gestão do fundo para o artifact (só leitura)")
    s.add_argument("--out-dir", default=str(DEFAULT_PAINEL_DIR),
                   help="pasta de index.html, data.json e da cópia local "
                        f"(padrão: {DEFAULT_PAINEL_DIR.as_posix()})")
    s.add_argument("--sem-local", action="store_true",
                   help="não grava a cópia autônoma cdp_painel_local.html")
    s.add_argument("--publicado", action="store_true",
                   help="só registra que o index.html atual foi publicado no artifact "
                        "(PAGINA_PUBLICADA.sha256); use depois de publicar a página")
    s.set_defaults(func=cmd_painel)

    s = sub.add_parser("backtest", help="backtest walk-forward semanal (sinais point-in-time)")
    s.add_argument("--start", required=True)
    s.add_argument("--end")
    s.add_argument("--out", default="reports/backtest")
    s.set_defaults(func=cmd_backtest)

    # Operação em qualquer harness (rotinas, executor, trava, estado, portal): docs/cdp/AUTOMACAO.md
    from . import estado as _estado
    from . import executor as _executor
    from . import rotinas as _rotinas
    from . import site as _site

    for _mod in (_estado, _rotinas, _executor, _site):
        _mod.registrar(sub)
    return p


def _utf8_stdio() -> None:
    """Saída UTF-8 mesmo em consoles/pipes do Windows (cp1252 não tem "≤", "Σ", "→")."""
    for stream in (sys.stdout, sys.stderr):
        enc = (getattr(stream, "encoding", None) or "").lower().replace("-", "")
        if enc != "utf8" and hasattr(stream, "reconfigure"):
            try:
                stream.reconfigure(encoding="utf-8", errors="replace")
            except (OSError, ValueError):  # pragma: no cover - stream já fechado/sem suporte
                pass


def main(argv: list[str] | None = None) -> int:
    _utf8_stdio()
    args = build_parser().parse_args(argv)
    from .ensaio import ErroEnsaio, ativar
    from .workflow.runtime import RecusaEstruturada

    try:
        ativar()  # relógio do cenário / substituto de dados: só com CDP_ENSAIO=1
    except ErroEnsaio as exc:
        print(f"cdp: {exc}", file=sys.stderr)
        return 2

    try:
        return int(args.func(args) or 0)
    except RecusaEstruturada as exc:
        # Recusa prevista (ex.: prazo vencido): saída estruturada, nunca traceback.
        _print(exc.as_dict())
        print(f"cdp: {exc.status}: {exc.motivo}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
