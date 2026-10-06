"""``cdp estado`` — um retrato só de leitura para qualquer agente (ou pessoa) "pegar o bonde
andando": fase do fundo, executor designado × este ambiente, trava, integridade, últimos
registros, últimas execuções das rotinas (trailers dos commits), pendências da agenda,
incidentes derivados (SLAs), próximas rotinas e o roteiro sugerido.

Offline por padrão (``--rede`` consulta o remoto, a trava e o manifesto do portal); ``--rapido``
pula a verificação de integridade; ``--sla`` sai com 1 quando há incidente de severidade alta
(vigia agendada). Nunca grava nada.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import urllib.request
from collections.abc import Mapping
from datetime import date, datetime, time, timedelta
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from . import executor as ex
from .rotinas import (
    CAMINHOS_DO_LIVRO,
    ROTINAS_PADRAO,
    Cron,
    ErroRotinas,
    Rotinas,
    avaliar_gate,
    carregar,
    contexto_do_runtime,
    mente_do_harness,
)

FUSO = ZoneInfo("America/Sao_Paulo")
SEVERIDADES = ("alta", "media", "baixa")
PRIORIDADE_PLAYBOOK = ("cdp-diario", "cdp-semanal", "cdp-calibracao", "cdp-cobertura")
_TRAILER_RE = re.compile(r"^(CDP-[A-Za-z]+):\s*(.+)$", re.MULTILINE)


def _d(v: Any) -> date | None:
    if v is None:
        return None
    if isinstance(v, datetime):
        return v.date()
    if isinstance(v, date):
        return v
    try:
        return date.fromisoformat(str(v)[:10])
    except ValueError:
        return None


def _em(d: date, hhmm: str) -> datetime:
    h, m = (int(x) for x in hhmm.split(":"))
    return datetime.combine(d, time(h, m), tzinfo=FUSO)


def _inc(codigo: str, severidade: str, mensagem: str, acao: str,
         desde: datetime | None = None) -> dict[str, Any]:
    return {"codigo": codigo, "severidade": severidade, "mensagem": mensagem, "acao": acao,
            "desde": desde.isoformat(timespec="minutes") if desde else None}


# ------------------------------------------------------------------------------------ git


def _repositorio(raiz: Path, rede: bool) -> dict[str, Any]:
    out: dict[str, Any] = {"ramo": None, "head": None, "origin_main": None, "atras": None,
                           "a_frente": None, "alterado": None, "remoto_consultado": False}
    head = ex.git_head(raiz)
    if head is None:
        return out
    out["head"] = head
    out["ramo"] = ex.git(["branch", "--show-current"], raiz).stdout.strip() or "(destacado)"
    if rede:
        out["remoto_consultado"] = ex.git(["fetch", "--quiet", ex.REMOTO, "main"], raiz,
                                          rede=True).returncode == 0
    om = ex.git(["rev-parse", "--verify", "--quiet", f"{ex.REMOTO}/main"], raiz).stdout.strip()
    out["origin_main"] = om or None
    if om:
        cnt = ex.git(["rev-list", "--left-right", "--count", f"HEAD...{ex.REMOTO}/main"],
                     raiz).stdout.split()
        if len(cnt) == 2:
            out["a_frente"], out["atras"] = int(cnt[0]), int(cnt[1])
    st = ex.git(["status", "--porcelain", "--untracked-files=no"], raiz).stdout
    out["alterado"] = bool(st.strip())
    return out


def ultimas_execucoes(raiz: Path, rot: Rotinas | None, n: int = 10,
                      limite: int = 300) -> list[dict[str, Any]]:
    """Commits de rotina mais recentes: os que têm o trailer ``CDP-Tarefa`` (gravados por
    ``cdp publicar``) e os de assunto "CDP: …" que só tocam o livro (rotinas anteriores ao
    ``cdp publicar``). Para os com tarefa, indica se ficaram dentro dos caminhos dela."""
    ref = f"{ex.REMOTO}/main" if ex.git(["rev-parse", "--verify", "--quiet",
                                         f"{ex.REMOTO}/main"], raiz).returncode == 0 else "HEAD"
    r = ex.git(["log", f"-n{limite}", "--name-only", "--format=%x1e%H%x1f%cI%x1f%B%x1f", ref],
               raiz)
    out: list[dict[str, Any]] = []
    for bloco in r.stdout.split("\x1e"):
        partes = bloco.split("\x1f")
        if len(partes) != 4:
            continue
        sha, quando, corpo, nomes_txt = partes
        nomes = [x for x in nomes_txt.splitlines() if x.strip()]
        assunto = corpo.strip().splitlines()[0] if corpo.strip() else ""
        tr = dict(_TRAILER_RE.findall(corpo))
        so_livro = bool(nomes) and all(ex._no_livro(p, CAMINHOS_DO_LIVRO) for p in nomes)
        if "CDP-Tarefa" not in tr and not (assunto.startswith("CDP:") and so_livro):
            continue
        item: dict[str, Any] = {
            "tarefa": tr.get("CDP-Tarefa"), "commit": sha, "quando": quando,
            "executor": tr.get("CDP-Executor"), "harness": tr.get("CDP-Harness"),
            "sessao": tr.get("CDP-Sessao"), "execucao": tr.get("CDP-Execucao"),
            "mensagem": assunto}
        if item["tarefa"] and rot is not None and item["tarefa"] in rot.tarefas:
            caminhos = rot.tarefas[item["tarefa"]].caminhos
            item["fora_do_escopo"] = [p for p in nomes if not ex._no_livro(p, caminhos)]
        out.append(item)
        if len(out) >= n:
            break
    return out


# ------------------------------------------------------------------------------- livro


def _ultimos_registros(rt: Any, ag: Mapping[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = {"fechamento": ag.get("ultimo_registro_diario"), "decisao": None,
                           "tese": None, "relatorio_semanal": None, "cobertura": None,
                           "risco": None}
    try:
        from .workflow.tese import is_published

        semanas = rt.book.list_weeks()
        decididas = [w for w in semanas if rt.book.list_decisions(w)]
        out["decisao"] = decididas[-1] if decididas else None
        teses = [w for w in decididas if is_published(rt.book_root, w)]
        out["tese"] = teses[-1] if teses else None
    except Exception:  # noqa: BLE001 - livro ausente ou ilegível: o estado continua
        pass
    rs = ag.get("relatorio_semanal") or {}
    if rs.get("publicado"):
        out["relatorio_semanal"] = rs.get("data")
    try:
        from .cobertura.livro import datas_snapshots

        snaps = sorted(datas_snapshots(rt.book_root))
        out["cobertura"] = snaps[-1] if snaps else None
    except Exception:  # noqa: BLE001 - módulo de cobertura ausente nesta versão
        pass
    risco = Path(rt.reports_root) / "risk"
    if risco.is_dir():
        datas = sorted(p for p in risco.iterdir() if p.is_dir() and _d(p.name))
        for pasta in reversed(datas):
            arqs = sorted(pasta.glob("risco_*.md"))
            if arqs:
                hhmm = arqs[-1].stem.removeprefix("risco_")
                d = date.fromisoformat(pasta.name)
                out["risco"] = f"{d:%d/%m/%Y} {hhmm[:2]}:{hhmm[2:4]}"
                break
    return out


def _reinicio_pendente(ag: Mapping[str, Any]) -> bool:
    return bool((ag.get("reinicio") or {}).get("pendente"))


def _pendencias(ag: Mapping[str, Any]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    if _reinicio_pendente(ag):
        # Antes da abertura, o livro ainda é o do ensaio: as pendências dele não são do fundo.
        return [{"tipo": "pre_inicio", "tarefa": "cdp-semanal ou cdp-diario (a que rodar antes)",
                 "data": _d(ag.get("data_de_inicio")),
                 "detalhe": (ag.get("reinicio") or {}).get("motivo")}]
    sem = ag.get("semanal") or {}
    if sem.get("acao") in ("montar", "tese"):
        out.append({"tipo": sem["acao"], "tarefa": "cdp-semanal", "data": sem.get("semana"),
                    "detalhe": sem.get("motivo")})
    for d in ag.get("fechamentos_pendentes") or []:
        out.append({"tipo": "fechamento", "tarefa": "cdp-diario", "data": _d(d)})
    for p in ag.get("publicacoes_pendentes") or []:
        out.append({"tipo": "relatorio_diario", "tarefa": "cdp-diario", "data": _d(p.get("data"))})
    for w in ag.get("teses_pendentes") or []:
        out.append({"tipo": "tese", "tarefa": "cdp-semanal", "data": _d(w)})
    rs = ag.get("relatorio_semanal") or {}
    if rs.get("pendente"):
        out.append({"tipo": "relatorio_semanal", "tarefa": "cdp-diario", "data": _d(rs.get("data"))})
    cob = ag.get("cobertura") or {}
    if cob.get("snapshot_pendente"):
        out.append({"tipo": "retrato_cobertura", "tarefa": "cdp-diario",
                    "data": _d(cob.get("data"))})
    return out


def _proximo_dia_util(d: date) -> date:
    d += timedelta(days=1)
    while d.weekday() >= 5:
        d += timedelta(days=1)
    return d


def incidentes(ag: Mapping[str, Any], *, agora: datetime, integridade: Mapping[str, Any] | None,
               executor: Mapping[str, Any], codigo_executor: int, trava: Mapping[str, Any] | None,
               execucoes: list[dict[str, Any]], repo: Mapping[str, Any], raiz: Path,
               portal: Mapping[str, Any] | None = None, reports_root: Path | None = None
               ) -> list[dict[str, Any]]:
    """Incidentes determinísticos (tabela em docs/cdp/AUTOMACAO.md, seção 9)."""
    local = agora.astimezone(FUSO)
    hoje = local.date()
    out: list[dict[str, Any]] = []
    if integridade is not None and not integridade.get("ok"):
        out.append(_inc("INTEGRIDADE", "alta", "Falha de integridade no livro ou nos dados.",
                        "Nenhuma rotina publica até `cdp verify` voltar a ÍNTEGRO; investigar "
                        "numa sessão de operador."))
    if ag.get("kill_switch"):
        out.append(_inc("KILL_SWITCH", "alta", "Kill switch ligado: só redução de risco.",
                        "Revisão humana; só um humano desliga (`cdp kill-switch off`)."))
    inicio = _d(ag.get("data_de_inicio"))
    pre = _reinicio_pendente(ag)
    if pre:
        # alta só depois da primeira rotina do dia de início (semanal 11:07, reservas até 14:07)
        sev = ("alta" if inicio is not None and (hoje > inicio or (hoje == inicio
                                                                  and local >= _em(hoje, "12:30")))
               else "media")
        out.append(_inc("REINICIO_PENDENTE", sev, "Livro aguardando a abertura na data de início.",
                        "A primeira rotina que rodar (semanal ou diária) abre o livro "
                        "(`cdp reinicio --executar`)."))
    for d in ([] if pre else ag.get("fechamentos_pendentes") or []):
        dd = _d(d)
        if dd is not None and local > _em(dd, "22:00"):
            out.append(_inc("SLA_FECHAMENTO", "alta",
                            f"Fechamento de {dd:%d/%m/%Y} pendente após o reforço das 21:07.",
                            "Ver o registro da rotina cdp-diario-reforco; a repescagem de "
                            "sábado tenta de novo.", _em(dd, "22:00")))
            break
    if not pre and (ag.get("semanal") or {}).get("decisao_perdida"):
        out.append(_inc("DECISAO_PERDIDA", "alta", str((ag.get("semanal") or {}).get("motivo")),
                        "Carteira anterior mantida; conferir o registro das rotinas semanais."))
    for w in ([] if pre else ag.get("teses_pendentes") or []):
        wd = _d(w)
        if wd is not None and local > _em(wd + timedelta(days=1), "12:00"):
            out.append(_inc("SLA_TESE", "media", f"Tese da semana {wd:%d/%m/%Y} não publicada.",
                            "A rotina diária recupera a tese da semana corrente.",
                            _em(wd + timedelta(days=1), "12:00")))
    rs = ag.get("relatorio_semanal") or {}
    rsd = _d(rs.get("data"))
    if not pre and rs.get("pendente") and rsd is not None and \
            local > _em(rsd + timedelta(days=1), "12:00"):
        out.append(_inc("SLA_RELATORIO_SEMANAL", "media",
                        f"Relatório semanal de {rsd:%d/%m/%Y} pendente.",
                        "A repescagem de sábado (cdp-diario-sabado) publica.",
                        _em(rsd + timedelta(days=1), "12:00")))
    cob = ag.get("cobertura") or {}
    cd = _d(cob.get("data"))
    if not pre and cob.get("snapshot_pendente") and cd is not None and \
            local > _em(_proximo_dia_util(cd), "22:00"):
        out.append(_inc("SLA_COBERTURA", "media", f"Retrato da cobertura de {cd:%d/%m/%Y} "
                        "pendente há mais de um dia útil.", "Ver o registro da rotina diária."))
    if (not pre and ag.get("fase") == "operacao" and ag.get("ultimo_registro_diario") is not None
            and ag.get("pregao_b3_hoje") and local > _em(hoje, "16:45") and reports_root):
        if not (reports_root / "risk" / hoje.isoformat()).is_dir():
            out.append(_inc("SLA_RISCO", "baixa", "Nenhum relatório de risco hoje até 16:45.",
                            "Conferir as rotinas cdp-risco-1330 e cdp-risco-1603."))
    if codigo_executor == ex.CONFIG:
        out.append(_inc("EXECUTOR_INVALIDO", "alta", str(executor.get("motivo")),
                        "Corrigir configs/cdp/executor.yaml numa sessão de operador."))
    elif executor.get("designado") == "nenhum":
        desde = ex._dt(executor.get("desde"))
        if desde is None or agora - desde > timedelta(hours=24):
            out.append(_inc("EXECUTOR_PAUSADO", "media", "Executor pausado (nenhum) há mais de "
                            "24 h: ninguém grava o livro.", "Concluir a troca de executor."))
    if trava and trava.get("estado") == "ocupada":
        exp = ex._dt(trava.get("expira"))
        if exp is not None and agora - exp > timedelta(hours=2):
            out.append(_inc("TRAVA_EXPIRADA", "baixa", f"Trava de {trava.get('tarefa')} "
                            "expirada há mais de 2 h (execução interrompida).",
                            "A próxima rotina assume a trava; nada a fazer se repetir."))
    for e in execucoes:
        if e.get("fora_do_escopo"):
            out.append(_inc("COMMIT_FORA_DO_ESCOPO", "alta",
                            f"Commit {str(e['commit'])[:10]} da tarefa {e['tarefa']} gravou fora "
                            f"dos seus caminhos: {', '.join(e['fora_do_escopo'][:5])}.",
                            "Auditar o commit numa sessão de operador."))
    if repo.get("a_frente"):
        loc = ex.git(["log", "--format=", "--name-only", f"{ex.REMOTO}/main..HEAD"], raiz).stdout
        if any(ex._no_livro(p, CAMINHOS_DO_LIVRO) for p in loc.splitlines() if p.strip()):
            out.append(_inc("CLONE_DIVERGENTE", "media", "Há gravações do livro neste clone que "
                            "não estão em origin/main (push retido).",
                            "Rodar `cdp publicar` no executor ou investigar a recusa."))
    trava_local = raiz / "logs" / "cdp" / ".lock"
    if trava_local.exists():
        idade = datetime.now().timestamp() - trava_local.stat().st_mtime
        if idade > 6 * 3600:
            out.append(_inc("TRAVA_LOCAL_ORFA", "baixa", "Trava local logs/cdp/.lock com mais de "
                            "6 h.", "Remover o arquivo se nenhuma rotina estiver rodando."))
    if portal and portal.get("defasado"):
        out.append(_inc("PORTAL_DEFASADO", "media", "O portal publicado não corresponde a "
                        "origin/main.", "Rodar o workflow cdp-site (Actions) e conferir o "
                        "registro."))
    ordem = {s: i for i, s in enumerate(SEVERIDADES)}
    return sorted(out, key=lambda i: (ordem[i["severidade"]], i["codigo"]))


def ultimo_commit_do_portal(raiz: Path, ref: str = f"{ex.REMOTO}/main") -> str | None:
    """Último commit de ``ref`` que muda o portal (mesmos caminhos do filtro de
    ``.github/workflows/cdp-site.yml``: :data:`cdp.site.CAMINHOS_DO_PORTAL`)."""
    from .site import CAMINHOS_DO_PORTAL

    r = ex.git(["log", "-1", "--format=%H", ref, "--", *CAMINHOS_DO_PORTAL], raiz)
    return r.stdout.strip() or None if r.returncode == 0 else None


def portal_defasado(raiz: Path, fonte: str | None, ultimo: str | None) -> bool:
    """O portal publicado (``fonte``) não contém a última mudança que o afeta (``ultimo``)?"""
    if not fonte or not ultimo or fonte == ultimo:
        return False
    r = ex.git(["merge-base", "--is-ancestor", ultimo, fonte], raiz)
    if r.returncode in (0, 1):
        return r.returncode == 1
    return True  # versão publicada desconhecida aqui (sem fetch): conta como defasado


def _portal(base_url: str, raiz: Path, agora: datetime) -> dict[str, Any]:
    url = base_url.rstrip("/") + "/manifest.json"
    try:
        with urllib.request.urlopen(url, timeout=10) as r:  # noqa: S310 - URL de configuração
            man = json.loads(r.read().decode("utf-8"))
    except Exception as exc:  # noqa: BLE001 - portal fora do ar ou ainda não publicado
        return {"url": url, "erro": f"{exc.__class__.__name__}: {exc}"[:200], "defasado": False}
    fonte = man.get("source_commit")
    ultimo = ultimo_commit_do_portal(raiz)
    return {"url": url, "source_commit": fonte, "agora": man.get("agora"),
            "ultima_mudanca_do_portal": ultimo, "defasado": portal_defasado(raiz, fonte, ultimo)}


# ------------------------------------------------------------------------------ estado


def playbook_sugerido(rot: Rotinas, ag: Mapping[str, Any], ctx: Any, local: datetime,
                      info_ex: Mapping[str, Any]) -> dict[str, Any] | None:
    """Entre as rotinas com trabalho agora (gate verdadeiro), a de disparo mais próximo da
    família (principal ou reservas); empate pela prioridade. Ex.: no dia de montagem, antes do
    prazo, a semanal (11:07) vem antes do fechamento (19:22)."""
    candidatos = []
    for ordem, tid in enumerate(PRIORIDADE_PLAYBOOK):
        if tid not in rot.tarefas:
            continue
        t = rot.tarefas[tid]
        try:
            dec = avaliar_gate(t.gate, ag, ctx)
        except Exception:  # noqa: BLE001 - previsão é informativa
            continue
        if not dec.executar:
            continue
        familia = [x for x in rot.tarefas.values() if x.familia == t.familia]
        disparos = [q for x in familia if (q := Cron.ler(x.cron).proximo(local, FUSO))]
        candidatos.append((min(disparos) if disparos else local + timedelta(days=400), ordem,
                           t, dec))
    if not candidatos:
        return None
    quando, _, t, dec = min(candidatos, key=lambda c: (c[0], c[1]))
    if info_ex.get("sou_o_executor"):
        condicao = ("rotina agendada: rode a skill da tarefa; sessão de operador: só a pedido da "
                    "pessoa (AGENTS.md, seção 1)")
    else:
        condicao = (f"só no executor designado ({info_ex.get('designado')}); aqui, somente "
                    "leitura")
    return {"tarefa": t.id, "playbook": t.playbook, "motivo": dec.motivo,
            "proximo_disparo": quando.isoformat(timespec="minutes"), "condicao": condicao}


def estado(rt: Any, raiz: Path | str = ".", *, agora: datetime | None = None,
           rapido: bool = False, rede: bool = False, rot: Rotinas | None = None,
           env: Mapping[str, str] | None = None, proximas: int = 6,
           avaliar_proximas: int = 4) -> dict[str, Any]:
    from .workflow.agenda import agenda

    raiz = Path(raiz)
    env = dict(os.environ if env is None else env)
    agora = agora or datetime.now(FUSO)
    local = agora.astimezone(FUSO)
    if rot is None:
        try:
            rot = carregar(raiz / ROTINAS_PADRAO)
        except ErroRotinas:
            rot = None
    ag = agenda(rt, agora)
    repo = _repositorio(raiz, rede)
    cod_ex, info_ex = ex.verificar(raiz, None, env=env)
    trava: dict[str, Any] | None
    if rede:
        t_estado, _, erro = ex.trava_ler(raiz, env)
        trava = {"erro": erro} if erro else (t_estado or {"estado": "livre"})
    else:
        r = ex.git(["show", f"refs/remotes/{ex.REMOTO}/{ex.RAMO_TRAVA}:{ex.ARQUIVO_TRAVA}"], raiz)
        try:
            trava = json.loads(r.stdout) if r.returncode == 0 else None
        except ValueError:
            trava = None
        if trava is not None:
            trava["consultada"] = "cópia local (use --rede para o estado atual)"
    integridade = None
    if not rapido:
        ok, msgs = rt.verify_all()
        integridade = {"ok": ok, "resultado": "ÍNTEGRO" if ok else "FALHA DE INTEGRIDADE",
                       "mensagens": msgs}
    execs = ultimas_execucoes(raiz, rot)
    portal = None
    if rede:
        from .site import carregar_site

        portal = _portal(carregar_site(raiz)["base_url"], raiz, agora)
    incs = incidentes(ag, agora=agora, integridade=integridade, executor=info_ex,
                      codigo_executor=cod_ex, trava=trava, execucoes=execs, repo=repo, raiz=raiz,
                      portal=portal, reports_root=Path(rt.reports_root))
    prox: list[dict[str, Any]] = []
    sugerido: dict[str, Any] = {"tarefa": None, "playbook": "docs/cdp/playbooks/RETOMAR.md",
                                "condicao": "somente leitura: nenhuma rotina tem trabalho agora "
                                            "neste ambiente"}
    if rot is not None:
        for k, (quando, t) in enumerate(rot.proximas(agora, proximas)):
            item: dict[str, Any] = {"tarefa": t.id, "quando": quando.isoformat(timespec="minutes"),
                                    "gate": t.gate}
            if k < avaliar_proximas:
                try:
                    dec = avaliar_gate(t.gate, agenda(rt, quando), contexto_do_runtime(rt, quando))
                    item.update({"vai_agir": dec.executar, "motivo": dec.motivo})
                except Exception as exc:  # noqa: BLE001 - previsão é informativa
                    item.update({"vai_agir": None, "motivo": f"{exc.__class__.__name__}"})
            prox.append(item)
        sugerido = playbook_sugerido(rot, ag, contexto_do_runtime(rt, agora), local,
                                     info_ex) or sugerido
    pre = _reinicio_pendente(ag)
    avisos = []
    if ex.detectar_ambiente(env) == "claude-cloud" and info_ex.get("sou_o_executor"):
        avisos.append("Sessão na nuvem com a identidade do executor (CDP_EXECUTOR): só rotinas "
                      "agendadas gravam o livro. Sessão interativa ou de desenvolvimento: use o "
                      "ambiente Default (ou CDP-dev), sem CDP_EXECUTOR, e não grave nada aqui.")
    ultimos = ({"nota": "livro anterior à data de início (ensaio): é arquivado na abertura; "
                        "nenhum registro do fundo ainda"} if pre else _ultimos_registros(rt, ag))
    return {
        "versao": 1, "agora_brasilia": local.isoformat(timespec="seconds"),
        "fase": "pre_inicio" if pre else ag.get("fase"), "reinicio_pendente": pre,
        "data_de_inicio": ag.get("data_de_inicio"),
        "mente": mente_do_harness(ex.identidade(raiz, env).get("harness")), "avisos": avisos,
        "repositorio": repo, "executor": info_ex, "trava": trava, "integridade": integridade,
        "kill_switch": ag.get("kill_switch"),
        "ultimos_registros": ultimos, "ultimas_execucoes": execs,
        "pendencias": _pendencias(ag), "incidentes": incs, "proximas_tarefas": prox,
        "playbook_sugerido": sugerido, "portal": portal, "agenda": ag,
    }


# ----------------------------------------------------------------------------- markdown

_SEV_PT = {"alta": "ALTA", "media": "média", "baixa": "baixa"}
_TIPOS_PT = {"pre_inicio": "abertura do livro na data de início", "montar": "montagem da carteira",
             "tese": "tese de investimento", "fechamento": "fechamento",
             "relatorio_diario": "relatório diário", "relatorio_semanal": "relatório semanal",
             "retrato_cobertura": "retrato da cobertura"}


def _fmt_d(v: Any) -> str:
    d = _d(v)
    return f"{d:%d/%m/%Y}" if d else "—"


def _fmt_dt(v: Any) -> str:
    try:
        d = datetime.fromisoformat(str(v))
    except (TypeError, ValueError):
        return str(v) if v else "—"
    return f"{d.astimezone(FUSO):%d/%m %H:%M}"


def para_markdown(e: Mapping[str, Any]) -> str:
    ex_ = e["executor"]
    if e.get("reinicio_pendente"):
        fase = ("pré-início (abertura do livro pendente; carteira inaugural em "
                f"{_fmt_d(e.get('data_de_inicio'))})")
    elif e.get("fase") == "pre_inicio":
        fase = "pré-início — carteira inaugural em " + _fmt_d(e.get("data_de_inicio"))
    else:
        fase = "operação"
    integ = (e.get("integridade") or {}).get("resultado") or "não verificada (--rapido)"
    repo = e["repositorio"]
    if repo.get("head") is None:
        sinc = "fora de um repositório git"
    elif repo.get("origin_main") is None:
        sinc = f"ramo {repo.get('ramo')}, sem referência de origin/main"
    else:
        sinc = (f"ramo {repo.get('ramo')}, {repo.get('a_frente')} à frente e "
                f"{repo.get('atras')} atrás de origin/main"
                + (" (sem consultar o remoto)" if not repo.get("remoto_consultado") else ""))
    tr = e.get("trava") or {}
    trava = ("desconhecida (use --rede)" if not tr else tr.get("erro") or
             (f"ocupada por {tr.get('tarefa')} até {_fmt_dt(tr.get('expira'))}"
              if tr.get("estado") == "ocupada" else "livre"))
    linhas = [f"# CDP — estado da operação ({_fmt_dt(e['agora_brasilia'])}, Brasília)", "",
              f"- **Fase:** {fase}",
              f"- **Integridade:** {integ} · **Kill switch:** "
              f"{'ligado' if e.get('kill_switch') else 'desligado'}",
              f"- **Executor designado:** {ex_.get('designado')} (desde "
              f"{_fmt_dt(ex_.get('desde'))}, por {ex_.get('por')}) · **este ambiente:** "
              f"{ex_.get('este_ambiente')} — "
              f"{'grava o livro' if ex_.get('sou_o_executor') else 'somente leitura'}",
              f"- **Trava das rotinas:** {trava}", f"- **Repositório:** {sinc}"]
    linhas += [f"- **Atenção:** {a}" for a in e.get("avisos") or []]
    linhas.append("")
    linhas.append("## Incidentes")
    incs = e.get("incidentes") or []
    linhas += ([f"- [{_SEV_PT[i['severidade']]}] {i['mensagem']} → {i['acao']}" for i in incs]
               or ["- Nenhum incidente."])
    linhas += ["", "## Pendências"]
    pend = e.get("pendencias") or []
    linhas += ([f"- {_TIPOS_PT.get(p['tipo'], p['tipo'])}"
                + (f" de {_fmt_d(p.get('data'))}" if p.get("data") else "")
                + f" — {p['tarefa']}" for p in pend] or ["- Nada pendente."])
    ur = e.get("ultimos_registros") or {}
    linhas += ["", "## Últimos registros"]
    if ur.get("nota"):
        linhas.append(f"- {ur['nota'][0].upper()}{ur['nota'][1:]}.")
    else:
        linhas.append(
            f"- Fechamento {_fmt_d(ur.get('fechamento'))} · decisão {_fmt_d(ur.get('decisao'))}"
            f" · tese {_fmt_d(ur.get('tese'))} · relatório semanal "
            f"{_fmt_d(ur.get('relatorio_semanal'))} · cobertura {_fmt_d(ur.get('cobertura'))}"
            f" · risco {ur.get('risco') or '—'}")
    execs = e.get("ultimas_execucoes") or []
    linhas += ["", "## Últimas execuções das rotinas"]
    if execs:
        linhas += ["| Quando | Tarefa | Executor | Registro |", "|---|---|---|---|"]
        for x in execs[:6]:
            linhas.append(f"| {_fmt_dt(x['quando'])} | {x.get('tarefa') or '—'} | "
                          f"{x.get('executor') or '—'} | {x['mensagem'][:60]} |")
    else:
        linhas.append("- Nenhuma registrada neste histórico.")
    prox = e.get("proximas_tarefas") or []
    linhas += ["", "## Próximas rotinas", "| Quando | Tarefa | Vai agir? |", "|---|---|---|"]
    for p in prox:
        va = {True: "sim", False: "não", None: "—"}[p.get("vai_agir")] \
            if "vai_agir" in p else "—"
        mot = f" ({p['motivo']})" if p.get("motivo") else ""
        linhas.append(f"| {_fmt_dt(p['quando'])} | {p['tarefa']} | {va}{mot[:90]} |")
    s = e.get("playbook_sugerido") or {}
    linhas += ["", "## Próximo passo",
               f"- {s.get('tarefa') or 'nenhuma rotina'}: `{s.get('playbook')}` — "
               f"{s.get('condicao')}"]
    return "\n".join(linhas) + "\n"


# --------------------------------------------------------------------------------- CLI


def _aware(s: str) -> datetime:
    dt = datetime.fromisoformat(s)
    return dt if dt.tzinfo else dt.replace(tzinfo=FUSO)


def cmd_estado(args: argparse.Namespace) -> int:
    from .workflow.runtime import Runtime

    rt = Runtime.from_args(args)
    e = estado(rt, Path(args.raiz), agora=args.agora, rapido=args.rapido, rede=args.rede)
    if args.formato == "md":
        print(para_markdown(e), end="")
    else:
        print(json.dumps(e, ensure_ascii=False, indent=2, default=str))
    if args.sla and any(i["severidade"] == "alta" for i in e["incidentes"]):
        print("SLA: incidente de severidade alta", file=sys.stderr)
        return 1
    return 0


def registrar(sub: argparse._SubParsersAction) -> None:
    s = sub.add_parser("estado", help="retrato da operação para qualquer agente: fase, executor, "
                                      "pendências, incidentes e próximo passo (só leitura)")
    s.add_argument("--raiz", default=".")
    s.add_argument("--formato", choices=["json", "md"], default="json")
    s.add_argument("--rapido", action="store_true", help="sem a verificação de integridade")
    s.add_argument("--rede", action="store_true",
                   help="consulta o remoto, a trava e o manifesto do portal")
    s.add_argument("--sla", action="store_true", help="sai com 1 se houver incidente alto")
    s.add_argument("--agora", type=_aware, default=None,
                   help="instante ISO (sem fuso = Brasília); padrão: agora")
    s.set_defaults(func=cmd_estado)


__all__ = ["estado", "incidentes", "para_markdown", "registrar", "ultimas_execucoes"]
