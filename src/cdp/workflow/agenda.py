"""Agenda operacional do CDP — o que a rotina local deve fazer agora (determinístico).

Usada pelas skills do plugin ``cdp`` (tarefas agendadas no PC local) e pelo ``cdp agenda``: pelo
relógio de Brasília (independente do fuso do PC), diz se hoje é o dia de montagem da semana (com
``LAST_US_SESSION``, o último pregão da semana na NYSE), se a decisão já foi gravada, se a
janela de pesquisa abriu e se o prazo EFETIVO venceu (``semanal.prazo_efetivo``: o teto local ou
o fechamento mais cedo entre NYSE/B3/BMV menos a margem — 14h15 nos fechamentos antecipados dos
EUA), quais mercados não negociam no dia, quais fechamentos diários estão pendentes (inclusive
de dias em que o PC estava desligado ou dormindo), quais relatórios diários faltam publicar, se
o relatório semanal de resultado da noite do dia de montagem está pendente
(``relatorio_semanal``), a cadência dos modelos da cobertura (``cobertura``: atualização antes da
decisão no dia de montagem, retrato da noite — completo ou parcial — por resultado divulgado ou
evento macro, notas de pós-resultado e revisão mensal; ver :func:`coverage_status`) e quais
semanas decididas ainda não têm a tese de investimento da carteira publicada (``acao: "tese"``
na semana corrente e ``teses_pendentes``), o último pregão da base de mercado
(``base_ultimo_pregao``) e os pedidos de kill switch publicados por rotinas sem a trava exclusiva
e ainda não aplicados no livro (``kill_switch_pedidos``). Só calendário e arquivos — nenhum
número de mercado.

Data de início do mandato (``fund.inception_date``): antes dela, com o livro vazio, a fase é
``"pre_inicio"`` (``semanal.acao = "aguardar"``; sem fechamentos, relatórios nem monitor de
risco); a data de início é sempre dia de montagem (carteira inaugural, mesmo numa sexta), depois
vale a regra semanal. ``reinicio.pendente`` diz que o livro ainda tem chaves anteriores à data de
início sem gênese: a rotina roda ``cdp reinicio --executar`` antes de qualquer outra etapa.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from datetime import date, datetime, time, timedelta
from pathlib import Path
from typing import TYPE_CHECKING, Any
from zoneinfo import ZoneInfo

import pandas as pd

from ..calendar import _cal, chave_da_semana, is_session, open_markets, proximas_montagens

if TYPE_CHECKING:  # pragma: no cover
    from .runtime import Runtime

#: Calendários em que o fechamento diário registra (mesma regra de ``Runtime.daily_close``).
DAILY_EXCHANGES = ("BVMF", "XNYS", "XMEX")
#: Máximo de pregões listados como pendentes (acima disso, a rotina pede intervenção).
MAX_PENDING = 30
#: Semanas decididas mais recentes examinadas em ``teses_pendentes``.
THESIS_WEEKS = 4
_WEEKDAYS_PT = ("segunda-feira", "terça-feira", "quarta-feira", "quinta-feira", "sexta-feira",
                "sábado", "domingo")


def _at(d: date, hhmm: str, tz: ZoneInfo) -> datetime:
    h, m = (int(x) for x in hhmm.split(":"))
    return datetime(d.year, d.month, d.day, h, m, tzinfo=tz)


def is_close_session(d: date) -> bool:
    return any(is_session(d, ex) for ex in DAILY_EXCHANGES)


def b3_open_at(moment: datetime) -> bool | None:
    """B3 em pregão contínuo neste minuto (``None`` se o calendário não souber dizer)."""
    try:
        cal = _cal("BVMF")
        ts = pd.Timestamp(moment).tz_convert("UTC").floor("min")
        if not (cal.first_minute <= ts <= cal.last_minute):
            return None
        return bool(cal.is_open_on_minute(ts))
    except Exception:  # noqa: BLE001 - versão do exchange_calendars sem a API
        return None


def pending_closes(rt: Runtime, local: datetime) -> list[date]:
    """Pregões ainda sem registro diário, em ordem, até hoje (hoje só após o horário da rotina).

    Sem nenhum registro, começa na semana de decisão mais antiga do livro (efetivação inicial).
    """
    cfg = rt.cfg
    tz = ZoneInfo(cfg.fund.timezone)
    today = local.date()
    try:
        dates = rt.track().dates()
    except OSError:
        dates = []
    if dates:
        start = dates[-1] + timedelta(days=1)
    else:
        decided = [w for w in rt.book.list_weeks() if rt.book.list_decisions(w)]
        if not decided:
            return []
        start = decided[0]
    close_run = _at(today, cfg.fund.daily_close_run_local, tz)
    out: list[date] = []
    d = start
    while d <= today and len(out) < MAX_PENDING + 1:
        if is_close_session(d) and (d < today or local >= close_run):
            out.append(d)
        d += timedelta(days=1)
    return out


def pending_publications(rt: Runtime) -> list[dict[str, Any]]:
    """Registros diários sem ``relatorio.md`` publicado (com o estado do comentário da mente)."""
    try:
        dates = rt.track().dates()
    except OSError:
        return []
    out = []
    for d in dates[-MAX_PENDING:]:
        folder = rt.daily_dir(d)
        if (folder / "relatorio.md").exists():
            continue
        out.append({"data": d, "fatos": (folder / "facts.md").exists(),
                    "comentario_escrito": (folder / "comentario.json").exists()})
    return out


def _sem_carteira(rt: Runtime, antes_de: date) -> bool:
    """Nenhuma semana decidida antes de ``antes_de`` (o fundo ainda não tem carteira: a próxima
    montagem é a carteira inaugural)."""
    try:
        return not any(rt.book.list_decisions(w) for w in rt.book.list_weeks() if w < antes_de)
    except OSError:  # pragma: no cover - disco
        return False


def _weekly(rt: Runtime, local: datetime) -> dict[str, Any]:
    from .runtime import briefing_completo
    from .tese import is_published, thesis_applicable

    cfg = rt.cfg
    tz = ZoneInfo(cfg.fund.timezone)
    today = local.date()
    if rt.pre_inicio(today):
        inicio = cfg.fund.inception_date
        out = {"semana": inicio, "hoje_e_dia_de_rebalanceamento": False,
               "inicio_pesquisa": cfg.fund.weekly_research_start_local,
               "prazo_decisao": cfg.fund.decision_deadline_local,
               "decisao_gravada": False, "briefing_preparado": False,
               "entradas_escritas": {"research_pack.json": False, "pm_decision.json": False},
               "tese_publicada": False, "acao": "aguardar",
               "motivo": (f"pré-início: carteira inaugural em {inicio:%d/%m/%Y} "
                          f"({_dia(inicio).split(',')[0]}), ao preço de fechamento")}
        out.update(_janela_info(rt, inicio, local))
        return out
    week = chave_da_semana(today, cfg)
    info: dict[str, Any] = {"semana": week, "hoje_e_dia_de_rebalanceamento": week == today,
                            "inicio_pesquisa": cfg.fund.weekly_research_start_local,
                            "prazo_decisao": cfg.fund.decision_deadline_local}
    if week is None:
        info.update({"acao": "nenhuma", "motivo": "semana sem pregão no calendário de "
                                                  "rebalanceamento"})
        return info
    info.update(_janela_info(rt, week if week >= today else _proxima(rt, today), local))
    wd = rt.week_dir(week)
    decided = bool(rt.book.list_decisions(week))
    # Briefing pronto = manifesto, briefing.md e context.json (um briefing parcial, deixado por
    # uma falha no meio do ``prepare``, não conta: o próximo ``prepare`` o afasta e refaz).
    briefing = briefing_completo(wd / "briefing")
    incompleto = (wd / "briefing").exists() and not briefing
    inputs = {n: (wd / "inputs" / n).exists() for n in ("research_pack.json", "pm_decision.json")}
    thesis = is_published(rt.book_root, week)
    info.update({"decisao_gravada": decided, "briefing_preparado": briefing,
                 "entradas_escritas": inputs, "tese_publicada": thesis})
    if incompleto:
        info["briefing_incompleto"] = True
    needs_thesis = decided and not thesis and thesis_applicable(rt.book, week)
    pending_thesis = {"acao": "tese",
                      "motivo": "decisão da semana gravada; a tese de investimento da carteira "
                                "ainda não foi publicada (cdp tese prepare → tese.json → "
                                "validate-tese → tese publish)"}
    start = _at(today, cfg.fund.weekly_research_start_local, tz)
    deadline = rt.decision_deadline(today).astimezone(tz)
    # Sem carteira anterior (nenhuma semana decidida antes desta), a montagem é a carteira
    # inaugural — na data de início ou, se ela passou sem decisão, na próxima data de montagem.
    inaugural = week >= cfg.fund.inception_date and _sem_carteira(rt, week)
    mantida = ("fundo sem carteira até a próxima data de montagem" if inaugural
               else "carteira anterior mantida até a próxima semana")
    if week != today:
        info["acao"] = "nenhuma"
        if week > today:
            info["motivo"] = (f"a carteira inaugural é montada em {week}" if inaugural
                              else f"a montagem desta semana é {_dia(week)}")
        elif needs_thesis:
            info.update(pending_thesis)
        elif decided:
            info["motivo"] = f"hoje não é o dia de montagem da semana ({week}); decisão já gravada"
        else:
            info["motivo"] = (f"hoje não é o dia de montagem da semana ({week}) e a semana NÃO "
                              f"teve decisão gravada: {mantida} (o código não permite decidir "
                              "fora do dia de montagem)")
            info["decisao_perdida"] = True
        return info
    info["minutos_ate_o_prazo"] = int((deadline - local).total_seconds() // 60)
    if needs_thesis:
        info.update(pending_thesis)
    elif decided:
        info.update({"acao": "nenhuma", "motivo": "decisão da semana já gravada"})
    elif local >= deadline:
        info.update({"acao": "prazo_vencido", "decisao_perdida": True,
                     "motivo": (f"prazo efetivo de {deadline:%H:%M} vencido sem "
                                "decisão: NÃO decidir (o fechamento seria conhecido); "
                                + ("carteira inaugural não montada, " if inaugural else "")
                                + mantida)})
    elif local < start:
        info.update({"acao": "aguardar",
                     "motivo": f"a pesquisa começa às {cfg.fund.weekly_research_start_local}"})
    else:
        etapa = ("prepare" if not briefing else
                 "pesquisa" if not all(inputs.values()) else "validar_e_decidir")
        info.update({"acao": "montar", "etapa": etapa,
                     "motivo": ("carteira inaugural, dentro da janela de decisão" if inaugural
                                else "dia de montagem da semana, dentro da janela de decisão")})
    if inaugural:
        info["carteira_inaugural"] = True
    return info


def _dia(d: date) -> str:
    return f"{_WEEKDAYS_PT[d.weekday()]}, {d:%d/%m}"


def _proxima(rt: Runtime, today: date) -> date:
    for d in proximas_montagens(today, rt.cfg):
        return d
    return today  # pragma: no cover - calendário sem pregão por semanas


def _janela_info(rt: Runtime, dia: date, local: datetime) -> dict[str, Any]:
    """Prazo efetivo, mercados fechados e fechamento antecipado do dia de montagem ``dia``."""
    cfg = rt.cfg
    tz = ZoneInfo(cfg.fund.timezone)
    deadline = rt.decision_deadline(dia).astimezone(tz)
    out: dict[str, Any] = {
        "proximo_rebalanceamento": dia, "prazo_efetivo": deadline,
        "mercados_fechados": sorted(m for m, ok in open_markets(dia).items() if not ok),
        "fechamento_antecipado": False, "mercados_fechamento_antecipado": [],
    }
    if cfg.execution is not None:
        from ..portfolio.execucao import MIC_NOME, janela_execucao, mics_antecipados

        j = janela_execucao(dia, cfg)
        # Sinal do dia: NYSE, B3 ou BMV fecham mais cedo (definem o prazo); fechamentos
        # antecipados de outros mercados só reduzem a capacidade deles.
        out["fechamento_antecipado"] = j.fechamento_antecipado
        out["mercados_fechamento_antecipado"] = sorted(MIC_NOME.get(m, m)
                                                       for m in mics_antecipados(j, cfg))
    if dia == local.date():
        out["minutos_ate_o_prazo"] = int((deadline - local).total_seconds() // 60)
    return out


#: Dias de montagem mais recentes examinados no relatório semanal pendente.
WEEKLY_REPORT_LOOKBACK = 8


def weekly_report_status(rt: Runtime, local: datetime) -> dict[str, Any]:
    """Relatório semanal de resultado (noite de TODO dia de montagem da regra, com ou sem
    decisão gravada — sem decisão, a carteira foi mantida e o relatório traz resultado,
    atribuição e risco da semana).

    Pendente quando algum dos dias de montagem mais recentes até hoje já tem o registro diário
    do fechamento e ainda não tem ``reports/semanal/<data>/relatorio.md``; ``pendentes`` lista
    todos (do mais antigo ao mais recente) e ``data`` é o mais antigo — nenhum relatório fica
    para trás quando o seguinte é decidido. Só com a seção ``execution`` no mandato (o
    relatório semanal pertence à execução no fechamento; na regra anterior nada é pendente)."""
    from .relatorio_semanal import dia_de_relatorio, report_dir

    out: dict[str, Any] = {"pendente": False, "data": None, "pendentes": []}
    if rt.cfg.execution is None:
        out["motivo"] = "relatório semanal de resultado ativado com a seção execution do mandato"
        return out
    try:
        dates = [d for d in rt.track().dates() if d <= local.date()]
        dias = [d for d in dates if dia_de_relatorio(rt, d)][-WEEKLY_REPORT_LOOKBACK:]
    except OSError:  # pragma: no cover - disco
        return out
    if not dias:
        return out
    pend = [d for d in dias if not (report_dir(rt, d) / "relatorio.md").exists()]
    w = pend[0] if pend else dias[-1]
    folder = report_dir(rt, w)
    out.update({"data": w, "registro_do_fechamento": True,
                "publicado": (folder / "relatorio.md").exists(),
                "decisao_gravada": bool(rt.book.list_decisions(w)),
                "fatos": (folder / "fatos.md").exists(),
                "comentario_escrito": (folder / "comentario.json").exists(),
                "pendentes": pend})
    out["pendente"] = bool(pend)
    if out["pendente"]:
        out["passos"] = (f"cdp weekly close-report --date {w} → comentario.json → "
                         f"cdp validate-weekly-report --date {w} → "
                         f"cdp weekly close-report --date {w} --publish")
    return out


# ============================================================================ cobertura
#
# Cadência dos modelos da cobertura (decisão do titular, 06/10/2026):
#
# - **Atualização no dia de montagem.** Em todo dia de montagem (inclusive a carteira inaugural),
#   antes do ``weekly prepare``, a rotina semanal grava o retrato COMPLETO da data-base da decisão
#   (o pregão de dados anterior, ``Runtime.information_session``) — com os dados até aquele
#   fechamento e o que o código coleta ao vivo publicado até ela (sem look-ahead: o motor recusa
#   insumo publicado depois da data). A decisão, a tese e o portal usam esses modelos.
# - **Sem retrato completo fixo na sexta à noite**: o retrato da véspera, gravado na manhã do dia de
#   montagem, é o que sustentou a decisão; um segundo retrato completo na mesma noite seria
#   substituído na semana seguinte, dobraria o volume do livro e pesaria na noite mais carregada
#   (efetivação no leilão, relatório semanal). A noite do dia de montagem só roda o retrato quando
#   há motivo: atualização antes da decisão não feita, evento macro ou resultado divulgado.
# - **Ad hoc**: resultado divulgado depois do último modelo do emissor (CVM, SEC, Yahoo; datas de
#   ``cdp.data.publico.eventos_corporativos``) ⇒ execução parcial (``--emissores``) no fechamento do
#   pregão seguinte, pela rotina diária; nota de pós-resultado pela rotina de notas. Evento macro de
#   impacto alto do calendário público (``configs/cdp/cobertura/eventos_macro.yaml``) ⇒ execução
#   completa no fechamento do primeiro pregão que reagiu a ele (os modelos dependem de juros).
# - **Véspera do dia de montagem**: nada roda à noite; a atualização completa da manhã seguinte
#   cobre resultados e eventos macro (o motor grava um retrato por data).
# - **Revisão mensal** (último dia de montagem do mês): pacote do código, leitura da gestão e
#   publicação imutável (``cdp cobertura revisao-mensal``), na rotina diária daquela noite.

#: Data mínima de um retrato oficial. A gênese é o primeiro retrato gravado no livro (pré-início,
#: 06/10/2026); sem nenhum retrato, a rotina diária pede o retrato completo do último pregão
#: encerrado a partir desta data.
COBERTURA_INICIO = date(2026, 10, 5)
#: Minutos mínimos até o prazo efetivo para atualizar os modelos antes da decisão (o retrato
#: completo leva de 5 a 10 minutos; coleta, pesquisa e decisão vêm depois e têm prioridade).
MIN_MINUTOS_COBERTURA_ANTES_DA_DECISAO = 120
#: Acima deste número de emissores com resultado novo, a reavaliação é completa (não parcial).
MAX_EMISSORES_PARCIAL = 60
#: Dias corridos depois do resultado em que a nota de pós-resultado é pedida (como nas notas).
JANELA_NOTA_POS_RESULTADO_DIAS = 4
#: Dias para trás em que se procura revisão mensal não publicada.
REVISAO_MENSAL_LOOKBACK_DIAS = 45
#: Calendário macro público (decisões de juros e inflação).
EVENTOS_MACRO = Path("configs/cdp/cobertura/eventos_macro.yaml")
#: Fechamento de referência da reação a um evento macro: 16:00 em Nova York (NYSE). Evento antes
#: dele, num pregão, reage no próprio pregão; depois (ou sem horário), no pregão seguinte.
FECHAMENTO_REFERENCIA = (time(16, 0), "America/New_York")
IMPACTOS_MACRO = ("alto", "medio")

#: Fonte das datas de resultado: ``f(emissores, desde, ate, as_of) -> DataFrame`` com
#: ``issuer_id``, ``data``, ``tipo``, ``estimada``, ``fonte``, ``url`` e ``documento``.
FonteEventos = Callable[[list[str], date, date, date], Any]


def _comando_cobertura_indisponivel() -> str | None:
    try:
        import inspect

        from ..cobertura import cli as cob_cli

        src = inspect.getsource(cob_cli.cmd_run)
        if "NotImplementedError" in src or "em implementação" in src:
            raise ImportError("stub")
    except (ImportError, OSError, TypeError):
        return "comando de cobertura indisponível nesta versão"
    return None


def ultimo_pregao_encerrado(rt: Runtime, local: datetime) -> date | None:
    """Último pregão (B3, NYSE ou BMV) cujo fechamento a rotina diária já pode tratar: hoje
    depois do horário da rotina diária, senão o anterior."""
    tz = ZoneInfo(rt.cfg.fund.timezone)
    today = local.date()
    corte = _at(today, rt.cfg.fund.daily_close_run_local, tz)
    d = today
    for _ in range(15):
        if is_close_session(d) and (d < today or local >= corte):
            return d
        d -= timedelta(days=1)
    return None  # pragma: no cover - calendário sem pregão por duas semanas


def _br(ts: Any, tz: ZoneInfo) -> date | None:
    try:
        dt = datetime.fromisoformat(str(ts))
    except (TypeError, ValueError):
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=ZoneInfo("UTC"))
    return dt.astimezone(tz).date()


def retrato_info(book: Path, d: date) -> dict[str, Any]:
    """Resumo de um retrato gravado (só leitura): parcial ou completo, emissores cobertos,
    instante de conclusão (do primeiro evento do livro do retrato) e se é sintético."""
    pasta = Path(book) / "cobertura" / d.isoformat()
    out: dict[str, Any] = {"data": d, "parcial": None, "emissores": [], "concluido_em": None,
                           "sintetico": False}
    try:
        man = json.loads((pasta / "manifest.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return out
    out.update({"parcial": bool(man.get("parcial")), "emissores": list(man.get("emissores") or []),
                "sintetico": bool(man.get("is_synthetic"))})
    try:
        with open(pasta / "eventos.jsonl", encoding="utf-8") as f:
            primeira = f.readline()
        out["concluido_em"] = json.loads(primeira).get("concluido_em") if primeira.strip() else None
    except (OSError, ValueError):
        pass
    return out


def modelos_vigentes(book: Path, datas: list[date] | None = None) -> dict[str, dict[str, Any]]:
    """Para cada emissor do último retrato completo, a data do último modelo e o instante em que
    foi concluído (retratos parciais posteriores substituem só os seus emissores)."""
    from ..cobertura.livro import datas_snapshots

    datas = datas if datas is not None else datas_snapshots(book)
    out: dict[str, dict[str, Any]] = {}
    for d in reversed(datas):
        info = retrato_info(book, d)
        for iid in info["emissores"]:
            out.setdefault(str(iid), {"data": d, "concluido_em": info["concluido_em"]})
        if info["parcial"] is False:
            break
    return out


def carregar_eventos_macro(path: Path | str | None = None) -> dict[str, Any]:
    """Calendário macro público (``configs/cdp/cobertura/eventos_macro.yaml``), normalizado:
    ``eventos`` com ``data`` (date), ``hora`` (``time`` ou ``None``), ``fuso``, ``impacto`` e a
    ``sessao_de_reacao``; ``erro`` quando o arquivo falta ou é inválido (nunca "sem eventos")."""
    import yaml

    p = Path(path) if path is not None else EVENTOS_MACRO
    if path is None and not p.is_file():
        p = Path(__file__).resolve().parents[3] / EVENTOS_MACRO
    try:
        raw = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
    except (OSError, yaml.YAMLError) as exc:
        return {"eventos": [], "erro": f"calendário macro ilegível ({exc.__class__.__name__})",
                "publicado_ate": {}}
    eventos: list[dict[str, Any]] = []
    problemas: list[str] = []
    series = raw.get("series") or {}
    for i, bruto in enumerate(raw.get("eventos") or []):
        ev = {**(series.get(str(bruto.get("serie"))) or {}), **bruto}
        try:
            d = date.fromisoformat(str(ev["data"]))
            h = ev.get("hora")
            hora = time.fromisoformat(str(h)) if h not in (None, "") else None
            fuso = str(ev.get("fuso") or "America/Sao_Paulo")
            ZoneInfo(fuso)
            impacto = str(ev.get("impacto") or "medio")
            if impacto not in IMPACTOS_MACRO:
                raise ValueError(f"impacto {impacto!r}")
            fonte = str(ev["fonte"])
            if not fonte.startswith("https://"):
                raise ValueError("fonte sem https")
        except (KeyError, TypeError, ValueError) as exc:
            problemas.append(f"evento {i}: {exc}")
            continue
        item = {"id": str(ev.get("id") or f"{ev.get('serie', 'evento')}-{d.isoformat()}"),
                "serie": str(ev.get("serie") or ""), "data": d, "hora": hora, "fuso": fuso,
                "pais": str(ev.get("pais") or ""), "orgao": str(ev.get("orgao") or ""),
                "nome": str(ev.get("nome") or ""), "impacto": impacto, "fonte": fonte,
                "referencia": ev.get("referencia")}
        item["sessao_de_reacao"] = sessao_de_reacao(item)
        eventos.append(item)
    eventos.sort(key=lambda e: (e["data"], e["id"]))
    out = {"eventos": eventos, "publicado_ate": dict(raw.get("publicado_ate") or {}),
           "lacunas": list(raw.get("lacunas") or []), "erro": "; ".join(problemas) or None}
    return out


def sessao_de_reacao(ev: dict[str, Any]) -> date:
    """Primeiro pregão (B3, NYSE ou BMV) cujo fechamento vem depois do evento: o próprio dia se
    ele é pregão e o evento sai antes das 16:00 de Nova York; senão o pregão seguinte."""
    d: date = ev["data"]
    hora: time | None = ev.get("hora")
    if hora is not None and is_close_session(d):
        quando = datetime.combine(d, hora, ZoneInfo(ev.get("fuso") or "America/Sao_Paulo"))
        h, fz = FECHAMENTO_REFERENCIA
        if quando < datetime.combine(d, h, ZoneInfo(fz)):
            return d
    d += timedelta(days=1)
    for _ in range(15):
        if is_close_session(d):
            return d
        d += timedelta(days=1)
    return d  # pragma: no cover


def _fonte_eventos_publica(emissores: list[str], desde: date, ate: date, as_of: date) -> Any:
    """Datas de resultado do arquivo público local (CVM: entrega do ITR/DFP e calendário do IPE;
    SEC e Yahoo conforme ``eventos_corporativos``), sem rede: a agenda nunca espera a internet."""
    from ..data import publico
    from ..data.publico_arquivo import DEFAULT_RAIZ, INDICE, PASTA_ARQUIVO

    if not (DEFAULT_RAIZ / PASTA_ARQUIVO / INDICE).is_file():
        raise FileNotFoundError("arquivo público local ausente neste clone")
    return publico.eventos_corporativos(emissores, desde, ate, offline=True, as_of=as_of)


def resultados_desde_o_modelo(vigentes: dict[str, dict[str, Any]], ate: date, hoje: date,
                              tz: ZoneInfo, fonte: FonteEventos | None = None,
                              janela_notas: int = JANELA_NOTA_POS_RESULTADO_DIAS
                              ) -> dict[str, Any]:
    """Resultados divulgados (data efetiva ou anunciada; nunca estimada) até ``ate``.

    ``pendentes``: emissores cujo resultado saiu depois do último modelo — data posterior à do
    modelo, ou a mesma data quando o modelo foi concluído nesse mesmo dia (a divulgação pode ter
    vindo depois). ``recentes``: resultados dos últimos ``janela_notas`` dias já incorporados ao
    modelo (base das notas de pós-resultado). Fonte indisponível ⇒ ``falha`` (nunca "nenhum")."""
    out: dict[str, Any] = {"pendentes": [], "recentes": [], "falha": None, "fontes": []}
    if not vigentes:
        return out
    desde = min(min(v["data"] for v in vigentes.values()), ate - timedelta(days=janela_notas))
    try:
        df = (fonte or _fonte_eventos_publica)(sorted(vigentes), desde, ate, hoje)
    except Exception as exc:  # noqa: BLE001 - arquivo público ausente ou ilegível
        out["falha"] = f"datas de resultado indisponíveis ({exc.__class__.__name__}: {exc})"
        return out
    falhas = list(getattr(df, "attrs", {}).get("falhas") or [])
    if falhas:
        out["falha"] = f"{len(falhas)} fonte(s) de datas de resultado com falha no arquivo local"
    if df is None or len(df) == 0:
        return out
    pend: dict[str, dict[str, Any]] = {}
    rec: dict[str, dict[str, Any]] = {}
    for r in df.to_dict("records"):
        if str(r.get("tipo")) != "resultado" or bool(r.get("estimada")):
            continue
        iid = str(r.get("issuer_id"))
        v = vigentes.get(iid)
        try:
            d = r["data"] if isinstance(r["data"], date) else date.fromisoformat(str(r["data"])[:10])
        except (KeyError, ValueError):
            continue
        if isinstance(d, datetime):
            d = d.date()
        if v is None or d > ate:
            continue
        item = {"issuer_id": iid, "data": d, "fonte": r.get("fonte"),
                "documento": r.get("documento"), "url": r.get("url"), "modelo": v["data"]}
        mesmo_dia = _br(v.get("concluido_em"), tz) == v["data"]
        if d > v["data"] or (d == v["data"] and mesmo_dia):
            if iid not in pend or d > pend[iid]["data"]:
                pend[iid] = item
        elif d >= ate - timedelta(days=janela_notas):
            if iid not in rec or d > rec[iid]["data"]:
                rec[iid] = item
    out["pendentes"] = sorted(pend.values(), key=lambda x: (x["data"], x["issuer_id"]))
    out["recentes"] = sorted(rec.values(), key=lambda x: (x["data"], x["issuer_id"]))
    out["fontes"] = sorted({str(x["fonte"]) for x in [*pend.values(), *rec.values()]})
    return out


def _proximo_rebalanceamento(rt: Runtime, d: date) -> date:
    cfg = rt.cfg
    inicio = cfg.fund.inception_date
    if d <= inicio:
        return inicio
    return _proxima(rt, d)


def _ultimo_rebalanceamento_ate(rt: Runtime, d: date) -> date | None:
    from ..calendar import rebalance_schedule

    inicio = rt.cfg.fund.inception_date
    if d < inicio:
        return None
    dias = [x for x in rebalance_schedule(d - timedelta(days=21), d, rt.cfg) if x >= inicio]
    return max(dias) if dias else None


def _notas_publicadas(book: Path) -> dict[str, date]:
    try:
        from .notas import published_notes

        out: dict[str, date] = {}
        for iid, d in published_notes(book):
            out[iid] = max(out.get(iid, d), d)
        return out
    except Exception:  # noqa: BLE001 - módulo de notas ausente ou livro ilegível
        return {}


def coverage_status(rt: Runtime, local: datetime, *, fonte_eventos: FonteEventos | None = None,
                    eventos_macro: dict[str, Any] | None = None) -> dict[str, Any]:
    """Cadência dos modelos da cobertura (ver o bloco de comentários acima).

    Chaves lidas pelas rotinas: ``atualizar_antes_da_decisao`` (rotina semanal, antes do
    ``weekly prepare``: ``passo_antes_da_decisao``), ``snapshot_pendente``/``data``/``tipo``/
    ``emissores``/``passo`` (rotina diária: o retrato desta noite, completo ou parcial),
    ``adhoc`` (resultados divulgados depois do último modelo), ``macro`` (eventos do calendário
    público), ``notas_pos_resultado`` (rotina de notas) e ``revisao_mensal``."""
    from ..cobertura.livro import datas_snapshots

    cfg = rt.cfg
    tz = ZoneInfo(cfg.fund.timezone)
    today = local.date()
    out: dict[str, Any] = {"snapshot_pendente": False, "data": None, "tipo": None,
                           "emissores": None, "motivos": [], "atualizar_antes_da_decisao": False}
    indisponivel = _comando_cobertura_indisponivel()
    if indisponivel:
        out["motivo"] = indisponivel
        return out
    book = Path(rt.book_root)
    try:
        datas = datas_snapshots(book)
    except OSError:  # pragma: no cover - disco
        datas = []
    from ..cobertura.parametros import carregar_parametros
    from ..cobertura.temporal import ativo as temporal_ativo
    temporal = temporal_ativo(carregar_parametros())
    bases_precos = {}
    if temporal:
        from ..cobertura.livro import CortePosterior, conferir_corte, snapshot
        validas = []
        for data in datas:
            arquivo = book / "cobertura" / data.isoformat() / "manifest.json"
            man = json.loads(arquivo.read_text())
            if man.get("corte_temporal") is not None:
                try:
                    conferir_corte(snapshot(book, data), local)
                except CortePosterior:
                    continue
                bases_precos[data] = date.fromisoformat(man["corte_temporal"]["base_preco"])
            validas.append(data)
        datas = validas
    ultimo = datas[-1] if datas else None
    ultimo_completo: date | None = None
    sintetico = False
    for d in reversed(datas):  # do mais recente ao último completo (lê só esses manifestos)
        info = retrato_info(book, d)
        sintetico = sintetico or (d == ultimo and info["sintetico"])
        if info["parcial"] is False:
            ultimo_completo = d
            break
    out.update({"ultimo_retrato": ultimo, "ultimo_retrato_completo": ultimo_completo})

    # --------------------------------------------------- 1. dia de montagem: antes da decisão
    pre = rt.pre_inicio(today)
    prox = _proximo_rebalanceamento(rt, today)
    base = rt.information_session(prox)
    ultimo_preco = bases_precos.get(ultimo_completo, ultimo_completo)
    em_dia = ultimo_preco is not None and ultimo_preco >= base
    if temporal and bases_precos:
        out["ultima_base_preco_completa"] = ultimo_preco
    out.update({"proximo_rebalanceamento": prox, "data_base_decisao": base,
                "modelos_em_dia_para_a_decisao": em_dia})
    if prox == today and not pre:
        deadline = rt.decision_deadline(today).astimezone(tz)
        minutos = int((deadline - local).total_seconds() // 60)
        try:
            decidido = bool(rt.book.list_decisions(today))
        except OSError:  # pragma: no cover - disco
            decidido = False
        inputs = rt.week_dir(today) / "inputs"
        escrita = all((inputs / n).exists() for n in ("research_pack.json", "pm_decision.json"))
        mercado = _store_last(rt)
        if decidido:
            motivo = "decisão da semana já gravada"
        elif em_dia:
            motivo = (f"modelos já atualizados até a data-base da decisão ({base:%d/%m/%Y}; "
                      f"retrato de {ultimo_completo:%d/%m/%Y})")
        elif local >= deadline:
            motivo = "prazo efetivo vencido"
        elif minutos < MIN_MINUTOS_COBERTURA_ANTES_DA_DECISAO:
            motivo = (f"menos de {MIN_MINUTOS_COBERTURA_ANTES_DA_DECISAO} minutos até o prazo "
                      "efetivo: a decisão usa o último retrato e a rotina diária atualiza os "
                      "modelos à noite")
        elif escrita:
            motivo = "pesquisa da semana já escrita: a rotina diária atualiza os modelos à noite"
        elif ultimo is not None and ultimo >= base:
            motivo = (f"já há retrato parcial em {ultimo:%d/%m/%Y} (um retrato por data): a "
                      "rotina diária grava o retrato completo à noite")
        elif mercado is None or mercado < base:
            motivo = (f"a base de mercado termina em {mercado or 'data desconhecida'}, antes da "
                      f"data-base {base:%d/%m/%Y}: rode o retrato depois do `weekly prepare`, "
                      "que coleta o fechamento anterior")
            out["aguardando_base_de_mercado"] = True
        else:
            motivo = None
            out["atualizar_antes_da_decisao"] = True
            out["passo_antes_da_decisao"] = f"cdp cobertura run --date {base}"
        out["motivo_antes_da_decisao"] = motivo or (
            f"dia de montagem: atualizar os modelos com dados até {base:%d/%m/%Y} antes do "
            "`weekly prepare`")
        out["minutos_ate_o_prazo"] = minutos

    # --------------------------------------------------- 2. rotina diária: o retrato desta noite
    noite = ultimo_pregao_encerrado(rt, local)
    out["pregao_de_referencia"] = noite
    macro = eventos_macro if eventos_macro is not None else carregar_eventos_macro()
    if macro.get("erro"):
        out["macro_erro"] = macro["erro"]
    mac_pend: list[dict[str, Any]] = []
    proximos: list[dict[str, Any]] = []
    for ev in macro.get("eventos") or []:
        s = ev["sessao_de_reacao"]
        resumo = {"id": ev["id"], "nome": ev["nome"], "orgao": ev["orgao"], "pais": ev["pais"],
                  "data": ev["data"], "impacto": ev["impacto"], "sessao_de_reacao": s,
                  "fonte": ev["fonte"]}
        if noite is not None and ev["impacto"] == "alto" and s <= noite and (
                ultimo_completo is None or s > ultimo_completo):
            mac_pend.append(resumo)
        if today <= ev["data"] <= today + timedelta(days=7):
            proximos.append(resumo)
    out["macro"] = {"pendentes": mac_pend, "proximos_7_dias": proximos,
                    "publicado_ate": macro.get("publicado_ate") or {},
                    "lacunas": macro.get("lacunas") or []}

    vigentes = modelos_vigentes(book, datas) if datas else {}
    if sintetico:
        res = {"pendentes": [], "recentes": [], "falha": None,
               "motivo": "DADOS SIMULADOS: sem calendário público de resultados", "fontes": []}
    elif noite is not None and vigentes:
        res = resultados_desde_o_modelo(vigentes, noite, today, tz, fonte_eventos)
    else:
        res = {"pendentes": [], "recentes": [], "falha": None, "fontes": []}
    adhoc_ids = [x["issuer_id"] for x in res["pendentes"]]
    out["adhoc"] = {"emissores": adhoc_ids, "itens": res["pendentes"], "falha": res.get("falha"),
                    "fontes": res.get("fontes") or []}
    if res.get("motivo"):
        out["adhoc"]["motivo"] = res["motivo"]
    notas = _notas_publicadas(book)
    out["notas_pos_resultado"] = [
        {"issuer_id": x["issuer_id"], "resultado": x["data"], "modelo": x["modelo"],
         "ultima_nota": notas.get(x["issuer_id"])}
        for x in res["recentes"]
        if notas.get(x["issuer_id"]) is None or notas[x["issuer_id"]] < x["data"]]

    if noite is None or noite < COBERTURA_INICIO:
        out["motivo"] = (f"antes da gênese da cobertura (a partir de {COBERTURA_INICIO:%d/%m/%Y}, "
                         "depois do fechamento)")
        return out
    completo: list[str] = []
    if ultimo is None:
        completo.append("gênese da cobertura: primeiro retrato completo")
    else:
        r0 = _ultimo_rebalanceamento_ate(rt, noite)
        if r0 is not None:
            b0 = rt.information_session(r0)
            if ultimo_completo is None or ultimo_completo < b0:
                completo.append(f"a atualização completa antes da decisão de {r0:%d/%m/%Y} não foi "
                                "gravada")
        for ev in mac_pend:
            completo.append(f"evento macro: {ev['nome']} ({ev['data']:%d/%m/%Y})")
    prox_noite = _proximo_rebalanceamento(rt, noite + timedelta(days=1))
    vespera = rt.information_session(prox_noite) == noite
    out["data"] = noite
    if ultimo is not None and noite <= ultimo:
        pend = bool(completo or adhoc_ids)
        out["motivo"] = ("retrato do pregão de referência já gravado" + (
            "; pendências entram no próximo pregão" if pend else ""))
        out["motivos"] = completo + ([f"resultados: {', '.join(adhoc_ids)}"] if adhoc_ids else [])
        return out
    if vespera:
        out["adiado_para_a_decisao"] = prox_noite
        out["motivos"] = completo + ([f"resultados: {', '.join(adhoc_ids)}"] if adhoc_ids else [])
        out["motivo"] = (f"véspera do dia de montagem ({_dia(prox_noite)}): a atualização completa "
                         f"com dados até {noite:%d/%m/%Y} é feita antes da decisão, pela rotina "
                         "semanal (`cobertura.atualizar_antes_da_decisao`)")
        return out
    if completo or len(adhoc_ids) > MAX_EMISSORES_PARCIAL:
        if len(adhoc_ids) > MAX_EMISSORES_PARCIAL:
            completo.append(f"{len(adhoc_ids)} emissores com resultado novo (acima de "
                            f"{MAX_EMISSORES_PARCIAL}: execução completa)")
        out.update({"snapshot_pendente": True, "tipo": "completo", "motivos": completo,
                    "passo": f"cdp cobertura run --date {noite}"})
    elif adhoc_ids:
        out.update({"snapshot_pendente": True, "tipo": "parcial", "emissores": adhoc_ids,
                    "motivos": [f"resultados divulgados depois do último modelo: "
                                f"{', '.join(adhoc_ids)}"],
                    "passo": f"cdp cobertura run --date {noite} --emissores {','.join(adhoc_ids)}"})
    else:
        out["motivo"] = "modelos em dia: nenhum resultado novo nem evento macro pendente"
    return out


def monthly_review_status(rt: Runtime, local: datetime) -> dict[str, Any]:
    """Revisão mensal dos modelos da cobertura: no último dia de montagem de cada mês, depois do
    fechamento (rotina diária). Pendente enquanto a revisão do último desses dias (até
    :data:`REVISAO_MENSAL_LOOKBACK_DIAS` dias atrás) não estiver publicada."""
    from ..calendar import rebalance_schedule
    from ..cobertura import revisao

    cfg = rt.cfg
    tz = ZoneInfo(cfg.fund.timezone)
    today = local.date()
    inicio = cfg.fund.inception_date
    corte = _at(today, cfg.fund.daily_close_run_local, tz)
    dias = [d for d in rebalance_schedule(today - timedelta(days=REVISAO_MENSAL_LOOKBACK_DIAS),
                                          today, cfg)
            if d >= inicio and revisao.e_ultimo_rebalanceamento_do_mes(d, cfg)
            and (d < today or local >= corte)]
    proxima = revisao.proxima_revisao(today if local < corte else today + timedelta(days=1), cfg)
    out: dict[str, Any] = {"pendente": False, "data": None, "proxima": proxima}
    if not dias:
        out["motivo"] = (f"a primeira revisão mensal é no último dia de montagem de "
                         f"{proxima:%m/%Y}" if proxima else "sem dia de montagem no período")
        return out
    d = dias[-1]
    st = revisao.situacao(rt.book_root, d)
    out.update({"data": d, "etapa": st["etapa"], "publicada": st["publicada"]})
    out["pendente"] = not st["publicada"] and st["etapa"] != "sem_retrato"
    if st["etapa"] == "sem_retrato":
        out["motivo"] = "sem retrato da cobertura até a data: revisão impossível"
    if out["pendente"]:
        out["passos"] = (f"cdp cobertura revisao-mensal preparar --date {d} → revisao.json → "
                         f"cdp cobertura revisao-mensal validar --date {d} → "
                         f"cdp cobertura revisao-mensal publicar --date {d}")
    return out


def pending_theses(rt: Runtime, limit: int = THESIS_WEEKS) -> list[date]:
    """Semanas decididas (as ``limit`` mais recentes) com carteira nova e sem tese publicada."""
    from .tese import is_published, thesis_applicable

    try:
        weeks = rt.book.list_weeks()
    except OSError:
        return []
    decided = [w for w in weeks if rt.book.list_decisions(w)][-limit:]
    return [w for w in decided
            if not is_published(rt.book_root, w) and thesis_applicable(rt.book, w)]


def _next_events(rt: Runtime, local: datetime, weekly: dict[str, Any]) -> list[dict[str, Any]]:
    cfg = rt.cfg
    tz = ZoneInfo(cfg.fund.timezone)
    today = local.date()
    events: list[dict[str, Any]] = []
    pre = rt.pre_inicio(today)
    # Antes da data de início, nenhum dia de montagem anterior a ela (mesmo se a data de início
    # estiver a mais de uma semana).
    for first in proximas_montagens(cfg.fund.inception_date if pre else today, cfg):
        deadline = rt.decision_deadline(first).astimezone(tz)
        if first == today and (weekly.get("decisao_gravada") or deadline <= local):
            continue
        inaugural = first >= cfg.fund.inception_date and _sem_carteira(rt, first)
        events.append({"evento": ("carteira inaugural (decisão autônoma)" if inaugural
                                  else "decisão semanal (autônoma)"), "quando": deadline,
                       "nota": f"pesquisa a partir de {cfg.fund.weekly_research_start_local}; "
                               "execução no leilão de fechamento (MOC)"})
        run = _at(first, cfg.fund.daily_close_run_local, tz)
        if cfg.execution is not None and run > local:
            events.append({"evento": "relatório semanal de resultado", "quando": run,
                           "nota": "mudanças da carteira, resultado e atribuição da semana e "
                                   "desde o início"})
        break
    start = cfg.fund.inception_date if pre else today
    for k in range(0, 15):
        d = start + timedelta(days=k)
        if not is_close_session(d):
            continue
        run = _at(d, cfg.fund.daily_close_run_local, tz)
        if run <= local:
            continue
        events.append({"evento": "fechamento diário", "quando": run,
                       "nota": "marcação, risco, atribuição, comentário e relatório"})
        break
    return sorted(events, key=lambda e: e["quando"])


def agenda(rt: Runtime, now: datetime | None = None) -> dict[str, Any]:
    """Estado operacional determinístico para as rotinas locais (ver docstring do módulo)."""
    cfg = rt.cfg
    tz = ZoneInfo(cfg.fund.timezone)
    moment = now if now is not None else rt.now()
    local = moment.astimezone(tz)
    pc = datetime.now().astimezone()
    pc_off = pc.utcoffset() or timedelta(0)
    brt_off = pc.astimezone(tz).utcoffset() or timedelta(0)
    from .reinicio import situacao

    weekly = _weekly(rt, local)
    cobertura = coverage_status(rt, local)
    try:
        cobertura["revisao_mensal"] = monthly_review_status(rt, local)
    except Exception as exc:  # noqa: BLE001 - módulo da revisão ausente ou livro ilegível
        cobertura["revisao_mensal"] = {"pendente": False, "motivo": f"revisão mensal "
                                       f"indisponível ({exc.__class__.__name__})"}
    if (weekly.get("acao") == "montar" and weekly.get("etapa") == "prepare"
            and cobertura.get("atualizar_antes_da_decisao")):
        # Dia de montagem: os modelos da cobertura são atualizados antes da coleta e da pesquisa.
        weekly["etapa"] = "cobertura"
    closes = pending_closes(rt, local)
    pubs = pending_publications(rt)
    try:
        last = rt.track().dates()
    except OSError:
        last = []
    return {
        "agora_brasilia": local,
        "fuso_do_mandato": cfg.fund.timezone,
        "fuso_do_pc": str(pc.tzinfo),
        "pc_menos_brasilia_horas": round((pc_off - brt_off).total_seconds() / 3600.0, 2),
        "pregao_b3_hoje": is_session(local.date(), "BVMF"),
        "b3_aberta_agora": b3_open_at(local),
        "kill_switch": rt.kill_switch_active(),
        "kill_switch_pedidos": _kill_switch_requests(rt),
        "fase": "pre_inicio" if rt.pre_inicio(local.date()) else "operacao",
        "data_de_inicio": cfg.fund.inception_date,
        "reinicio": situacao(rt),
        "ultimo_registro_diario": last[-1] if last else None,
        "base_ultimo_pregao": _store_last(rt),
        "semanal": weekly,
        "fechamentos_pendentes": closes[:MAX_PENDING],
        "fechamentos_pendentes_excedem_limite": len(closes) > MAX_PENDING,
        "horario_fechamento_diario": cfg.fund.daily_close_run_local,
        "publicacoes_pendentes": pubs,
        "relatorio_semanal": weekly_report_status(rt, local),
        "cobertura": cobertura,
        "teses_pendentes": pending_theses(rt),
        "proximos_eventos": _next_events(rt, local, weekly),
    }


def _store_last(rt: Runtime) -> date | None:
    """Último pregão gravado na base de mercado (dados públicos); ``None`` sem base legível. Gate
    da rotina diária no pré-início: base defasada ⇒ atualizar antes da carteira inaugural."""
    try:
        v = rt.store_last_date()
    except Exception:  # noqa: BLE001 - base ausente ou ilegível
        return None
    if isinstance(v, datetime):
        return v.date()
    return v if isinstance(v, date) else None


def _kill_switch_requests(rt: Runtime) -> list[dict[str, Any]]:
    """Pedidos de kill switch publicados (``reports/risk/<data>/kill_switch_<HHMM>.yaml``) ainda
    não aplicados no livro: a próxima execução exclusiva (semanal ou diária) os aplica."""
    try:
        reqs = rt.kill_switch_requests()
    except (OSError, ValueError):
        return []
    return [{"arquivo": r["arquivo"], "em": r["em"], "motivo": r["motivo"],
             "superado": r["superado"]} for r in reqs]


def validate_daily_commentary(rt: Runtime, session: date) -> tuple[bool, list[str]]:
    """Valida ``reports/daily/<data>/comentario.json`` SEM publicar (``daily publish`` é
    imutável e, com problemas, publicaria o template determinístico)."""
    from ..research.commentary import COMMENTARY_JSON, load_commentary_file

    rec = rt.track().get(session)
    if rec is None:
        return False, [f"sem registro diário em {session}: rode `cdp daily close --date "
                       f"{session}` antes"]
    fb, _history = rt._daily_factbook(session, rec)
    esperada = getattr(rt, "mente_esperada", lambda *a, **k: None)()
    _md, issues = load_commentary_file(rt.daily_dir(session) / COMMENTARY_JSON, fb, record=rec,
                                       expected_mind=esperada)
    return not issues, list(issues)


__all__ = ["COBERTURA_INICIO", "DAILY_EXCHANGES", "EVENTOS_MACRO", "MAX_EMISSORES_PARCIAL",
           "MIN_MINUTOS_COBERTURA_ANTES_DA_DECISAO", "WEEKLY_REPORT_LOOKBACK", "agenda",
           "b3_open_at", "carregar_eventos_macro", "coverage_status", "is_close_session",
           "modelos_vigentes", "monthly_review_status", "pending_closes", "pending_publications",
           "pending_theses", "resultados_desde_o_modelo", "retrato_info", "sessao_de_reacao",
           "ultimo_pregao_encerrado", "validate_daily_commentary", "weekly_report_status"]
