"""Retificação editorial finita do lado de posição; somente anexação.

O relatório original e seus eventos são preservados. O recibo original completo precisa
conferir com o payload_hash de WEEKLY_CLOSE_REPORT; nenhum cálculo financeiro é refeito.
"""
from __future__ import annotations

import argparse
import html
import json
import os
import re
import sys
from datetime import date
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from ..audit import AuditLog
from ..contracts import FactBook, mente_divergente
from ..hashing import sha256_file, sha256_obj
from ..research.comentario_semanal import (
    ComentarioSemanal,
    afirmacoes_lado_renderizadas,
    lado_depois,
    slug,
)
from ..research.guardrails import render_placeholders
from ..research.pm_agent import MindName

EVENT = "WEEKLY_EDITORIAL_RECTIFICATION"
HASH = r"^[a-f0-9]{64}$"


class ReciboOriginal(BaseModel):
    """Payload literal do evento original, sem campos opcionais ou modelos financeiros."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    md: str
    html: str
    md_sha256: str = Field(pattern=HASH)
    html_sha256: str = Field(pattern=HASH)
    registro: str = Field(pattern=HASH)
    factbook: str = Field(pattern=HASH)
    comentario_da_mente: Literal[True]
    apontamentos: list[str] = Field(max_length=0)
    tipo: Literal["montagem", "semanal"]


class CorrecaoLado(BaseModel):
    """Alvo editorial exato; o texto novo é produzido exclusivamente pelo código."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    emissor: str = Field(min_length=1, max_length=80)
    texto_original: str = Field(min_length=1, max_length=600)


class RetificacaoSemanal(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    schema_version: Literal["cdp.weekly.editorial/v1"]
    data: date
    mind: MindName
    evento_original: str = Field(pattern=HASH)
    recibo_original: ReciboOriginal
    comentario_original_sha256: str = Field(pattern=HASH)
    factbook_original_sha256: str = Field(pattern=HASH)
    correcoes: list[CorrecaoLado] = Field(min_length=1, max_length=40)


def _regular(path: Path) -> None:
    if not path.is_file() or path.is_symlink() or path.stat().st_nlink != 1:
        raise ValueError(f"Artefato deve ser físico regular, sem alias: {path.name}")


def _folder(rt, day: date) -> Path:
    return Path(rt.reports_root) / "semanal" / day.isoformat()


def _audit(rt) -> AuditLog:
    path = Path(rt.book_root) / "audit_log.jsonl"
    _regular(path)
    log = AuditLog(path)
    ok, message = log.verify_chain()
    if not ok:
        raise ValueError(message)
    return log


def _checked(rt, entry: RetificacaoSemanal, *, expected_mind: str | None = None):
    if (problem := mente_divergente(entry.mind, expected_mind)):
        raise ValueError(problem)
    folder = _folder(rt, entry.data)
    for name in ("relatorio.md", "relatorio.html", "factbook.json", "comentario.json"):
        _regular(folder / name)
    original = entry.recibo_original
    if (sha256_file(folder / "relatorio.md") != original.md_sha256
            or sha256_file(folder / "relatorio.html") != original.html_sha256
            or sha256_file(folder / "factbook.json") != entry.factbook_original_sha256
            or sha256_file(folder / "comentario.json") != entry.comentario_original_sha256):
        raise ValueError("Hashes dos originais divergem do recibo")
    # Os caminhos são somente strings do recibo autenticado, nunca caminhos de leitura.
    for name, path in (("relatorio.md", original.md), ("relatorio.html", original.html)):
        if Path(path).parts[-3:] != ("semanal", entry.data.isoformat(), name):
            raise ValueError("Caminho do recibo não corresponde ao relatório semanal")
    fb = FactBook.model_validate_json((folder / "factbook.json").read_bytes())
    if fb.as_of != entry.data or fb.factbook_hash() != original.factbook:
        raise ValueError("FactBook original não confere com o recibo")
    log = _audit(rt)
    events = log.events()
    target = [event for event in events if event.event_hash == entry.evento_original
              and event.event_type == "WEEKLY_CLOSE_REPORT" and event.week == entry.data]
    if (len(target) != 1 or target[0].actor != "CDP"
            or target[0].payload_hash != sha256_obj(original.model_dump(mode="json"))):
        raise ValueError("Recibo original não confere com WEEKLY_CLOSE_REPORT")
    comment = ComentarioSemanal.model_validate_json((folder / "comentario.json").read_bytes())
    changes = {item.emissor: item for item in comment.mudancas_carteira}
    if len(changes) != len(comment.mudancas_carteira):
        raise ValueError("Emissor repetido no comentário original")
    md = (folder / "relatorio.md").read_text(encoding="utf-8")
    markup = (folder / "relatorio.html").read_text(encoding="utf-8")
    seen = set()
    corrected = []
    for item in entry.correcoes:
        if item.emissor in seen:
            raise ValueError("Emissor repetido na retificação")
        seen.add(item.emissor)
        change = changes.get(item.emissor)
        if change is None or change.racional != item.texto_original:
            raise ValueError("Alvo editorial diverge do comentário original")
        prior = render_placeholders(item.texto_original, fb)
        if prior not in md or html.escape(prior) not in markup:
            raise ValueError("Alvo editorial não consta nos dois relatórios autenticados")
        side = lado_depois(fb, item.emissor)
        fid = f"mud.{slug(item.emissor)}.depois"
        fact = fb.facts.get(fid)
        if side is None or fact is None or fact.issuer_id != item.emissor:
            raise ValueError("Peso publicado ausente ou de outro emissor; não inventar lado")
        claims, problems = afirmacoes_lado_renderizadas(change, fb)
        if problems:
            raise ValueError("Alvo editorial sem texto renderizado válido: " + "; ".join(problems))
        if not any(claim != side for claim in claims):
            raise ValueError("Alvo editorial sem contradição direcional canônica comprovada")
        name = fb.facts.get(f"mud.{slug(item.emissor)}.nome")
        label = name.formatted if name is not None else item.emissor
        new = f"{label}: posição {side} após o fechamento; peso {{{{fact:{fid}}}}}."
        corrected.append({"emissor": item.emissor, "antes": prior,
                          "depois": render_placeholders(new, fb), "lado_depois": side,
                          "peso_fact_id": fid, "peso_publicado": fact.value})
    return fb, corrected, log


def validar(rt, entry: RetificacaoSemanal, *, expected_mind: str | None = None) -> list[str]:
    try:
        _checked(rt, entry, expected_mind=expected_mind)
        _confirmar_alvos_novos(rt, entry)
    except (ValueError, OSError, KeyError, TypeError) as error:
        return [str(error)]
    return []


def _texts(entry, corrected, synthetic):
    label = "DADOS SIMULADOS" if synthetic else "Carteira simulada com preços reais"
    lines = [f"# Retificação editorial — {entry.data.isoformat()}", "", label, "",
             "Esta nota retifica somente a indicação do lado da posição. O relatório original, "
             "seus números, a decisão, a efetivação e o NAV permanecem preservados.", "",
             "[Relatório original](../../relatorio.html)", ""]
    for row in corrected:
        lines.extend([f"## {row['emissor']}", "", f"Onde se lê: {row['antes']}", "",
                      f"Leia-se: {row['depois']}", ""])
    lines.extend(["Autoria: a gestão, com apoio de IA [IA]; lado derivado do fato e peso copiado pelo código.", "",
                  f"SHA-256 relatório original: {entry.recibo_original.md_sha256}",
                  f"Evento original: {entry.evento_original}", ""])
    md = "\n".join(lines)
    markup = ("<!doctype html><html lang='pt-BR'><meta charset='utf-8'>"
              "<title>Retificação editorial</title><body>"
              "<p><a href='../../relatorio.html'>Relatório original preservado</a></p><pre>"
              + html.escape(md) + "</pre></body></html>")
    return md, markup


def publicar(rt, entry: RetificacaoSemanal, *, expected_mind: str):
    """Anexa novo artefato e novo evento; CLI exige execução/trava do executor."""
    fb, corrected, log = _checked(rt, entry, expected_mind=expected_mind)
    _confirmar_alvos_novos(rt, entry)
    rid = sha256_obj(entry.model_dump(mode="json"))
    folder = _folder(rt, entry.data) / "retificacoes" / rid
    if folder.exists():
        raise FileExistsError("Retificação já existente; nunca sobrescrever")
    artifact = {"schema_version": "cdp.weekly.editorial.artifact/v1",
                "entrada": entry.model_dump(mode="json"), "correcoes_calculadas": corrected,
                "is_synthetic": fb.is_synthetic, "audit_head_anterior": log.events()[-1].event_hash}
    md, markup = _texts(entry, corrected, fb.is_synthetic)
    # Criações exclusivas; falha parcial/orfandade é detectada por verificar, sem reparo tácito.
    folder.mkdir(parents=True, exist_ok=False)
    for name, text in (("retificacao.json", json.dumps(artifact, ensure_ascii=False, indent=2, allow_nan=False) + "\n"),
                       ("retificacao.md", md), ("retificacao.html", markup)):
        with (folder / name).open("x", encoding="utf-8") as handle:
            handle.write(text)
    payload = _payload(entry.data, rid, folder)
    log.append(EVENT, entry.mind, payload, week=entry.data,
               summary=f"Retificação editorial do relatório semanal de {entry.data}; original preservado.")
    return payload


def _payload(day, rid, folder):
    return {"data": day.isoformat(), "id": rid,
            "arquivos": {name: sha256_file(folder / name) for name in (
                "retificacao.json", "retificacao.md", "retificacao.html")}}


def _alvos(entry: RetificacaoSemanal) -> set[tuple[date, str, str]]:
    return {(entry.data, entry.evento_original, item.emissor) for item in entry.correcoes}


def _confirmar_alvos_novos(rt, entry: RetificacaoSemanal) -> None:
    issues, targets = _historico(rt)
    if issues:
        raise ValueError("Retificações anteriores não íntegras: " + "; ".join(issues))
    if _alvos(entry) & targets:
        raise FileExistsError("Alvo/evento original já retificado; mente e id não autorizam repetição")


def _historico(rt) -> tuple[list[str], set[tuple[date, str, str]]]:
    """Leitor acíclico do histórico; autentica e exige unicidade por alvo/evento."""
    root = Path(rt.reports_root) / "semanal"
    dirs = sorted(root.glob("*/retificacoes/*")) if root.exists() else []
    audit_path = Path(rt.book_root) / "audit_log.jsonl"
    if not dirs and not audit_path.is_file():
        return [], set()
    try:
        log = _audit(rt)
        events = [event for event in log.events() if event.event_type == EVENT]
        remaining = {(event.week, event.payload_hash): event for event in events}
        if len(remaining) != len(events):
            raise ValueError("Evento de retificação duplicado")
        targets: set[tuple[date, str, str]] = set()
        for folder in dirs:
            if folder.is_symlink() or not folder.is_dir() or not re.fullmatch(HASH, folder.name):
                raise ValueError("Pasta de retificação inválida/alias")
            names = {path.name for path in folder.iterdir()}
            if names != {"retificacao.json", "retificacao.md", "retificacao.html"}:
                raise ValueError("Artefato parcial ou com arquivo extra")
            for path in folder.iterdir():
                _regular(path)
            artifact = json.loads((folder / "retificacao.json").read_bytes())
            if set(artifact) != {"schema_version", "entrada", "correcoes_calculadas", "is_synthetic", "audit_head_anterior"}:
                raise ValueError("Campos extras/ausentes no artefato")
            if artifact["schema_version"] != "cdp.weekly.editorial.artifact/v1":
                raise ValueError("Schema de artefato inválido")
            entry = RetificacaoSemanal.model_validate(artifact["entrada"])
            if folder.name != sha256_obj(entry.model_dump(mode="json")) or folder.parent.parent.name != entry.data.isoformat():
                raise ValueError("Identificador/data não correspondem ao conteúdo")
            fb, corrected, _ = _checked(rt, entry)
            if _alvos(entry) & targets:
                raise ValueError("Alvo/evento original retificado mais de uma vez")
            targets.update(_alvos(entry))
            if artifact["correcoes_calculadas"] != corrected or artifact["is_synthetic"] is not fb.is_synthetic:
                raise ValueError("Retificação alterou valores ou lado do fato publicado")
            md, markup = _texts(entry, corrected, fb.is_synthetic)
            if (folder / "retificacao.md").read_text() != md or (folder / "retificacao.html").read_text() != markup:
                raise ValueError("Texto derivado foi alterado")
            payload = _payload(entry.data, folder.name, folder)
            event = remaining.pop((entry.data, sha256_obj(payload)), None)
            if event is None or event.actor != entry.mind or event.prev_hash != artifact["audit_head_anterior"]:
                raise ValueError("Artefato de retificação não confere com o evento/trilha/mente")
        if remaining:
            raise ValueError("Evento de retificação sem artefato correspondente")
    except (ValueError, OSError, KeyError, TypeError) as error:
        return [str(error)], set()
    return [], targets


def verificar(rt) -> list[str]:
    """Cruza artefatos/eventos e alvos únicos, sem writer ou cálculo financeiro."""
    return _historico(rt)[0]


def listar(rt, day: date) -> list[dict]:
    if verificar(rt):
        return []  # Nunca mostrar nota não autenticada como retificação publicada.
    return [{"id": folder.name, "data": day.isoformat(),
             "sha256": sha256_file(folder / "retificacao.json")}
            for folder in sorted((_folder(rt, day) / "retificacoes").glob("*")) if folder.is_dir()]


def status(rt) -> dict:
    """Pendência editorial lexical, sem recolocar MOC/registro/relatório original na agenda."""
    root = Path(rt.reports_root) / "semanal"
    result = {"pendente": False, "relatorios": [], "nao_observados": [], "problemas": verificar(rt)}
    if result["problemas"]:
        result["pendente"] = True
        return result
    for folder in sorted(root.glob("*")) if root.is_dir() else []:
        if not (folder / "relatorio.md").is_file():
            continue
        if not (folder / "factbook.json").is_file() or not (folder / "comentario.json").is_file():
            result["nao_observados"].append(folder.name)
            continue  # Legado/modelo sem insumo editorial: não afirmar ausência de contradição.
        try:
            day = date.fromisoformat(folder.name)
            fb = FactBook.model_validate_json((folder / "factbook.json").read_bytes())
            comment = ComentarioSemanal.model_validate_json((folder / "comentario.json").read_bytes())
            md = (folder / "relatorio.md").read_text(encoding="utf-8")
            markup = (folder / "relatorio.html").read_text(encoding="utf-8")
            wrong = []
            for item in comment.mudancas_carteira:
                prior = render_placeholders(item.racional, fb)
                if prior in md and html.escape(prior) in markup:
                    claims, problems = afirmacoes_lado_renderizadas(item, fb)
                    side = lado_depois(fb, item.emissor)
                    if problems or side is None:
                        raise ValueError(f"{item.emissor}: lado/texto renderizado não observado")
                    if any(claim != side for claim in claims):
                        wrong.append(item.emissor)
            completed = set()
            for correction in listar(rt, day):
                path = folder / "retificacoes" / correction["id"] / "retificacao.json"
                artifact = json.loads(path.read_bytes())
                completed.update(item["emissor"] for item in artifact["correcoes_calculadas"])
            pending = sorted(set(wrong) - completed)
            if wrong or completed:
                result["relatorios"].append({"data": day.isoformat(), "pendentes": pending,
                                              "corrigidos": sorted(completed), "pendente": bool(pending)})
                result["pendente"] |= bool(pending)
        except (ValueError, OSError, KeyError, TypeError) as error:
            result["problemas"].append(f"{folder.name}: {error}")
            result["pendente"] = True
    return result


def cmd(args: argparse.Namespace) -> int:
    from .runtime import Runtime

    rt = Runtime.from_args(args)
    if args.arquivo is None:
        if args.publish:
            print("Retificação requer --arquivo; não publicar schema.", file=sys.stderr)
            return 1
        print(json.dumps(RetificacaoSemanal.model_json_schema(), ensure_ascii=False, indent=2))
        return 0
    try:
        entry = RetificacaoSemanal.model_validate_json(Path(args.arquivo).read_bytes())
        if entry.data != args.date:
            raise ValueError("Data do arquivo diverge do comando")
        issues = validar(rt, entry, expected_mind=rt.mente_esperada())
        if issues:
            raise ValueError("; ".join(issues))
        if args.publish:
            _autorizar_cli(args, entry.mind, rt)
            result = publicar(rt, entry, expected_mind=rt.mente_esperada())
        else:
            result = {"ok": True, "problemas": [], "publicado": False}
    except (ValueError, OSError, KeyError, TypeError) as error:
        print(f"cdp weekly rectify-report: {error}", file=sys.stderr)
        return 1
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


def _autorizar_cli(args, mind, rt):
    from .. import executor

    if not args.execucao or not args.trava:
        raise ValueError("Retificação exige execução e trava normais do executor")
    root = Path(args.raiz)
    if (not re.fullmatch(r"[a-zA-Z0-9-]{1,80}", args.execucao)
            or not re.fullmatch(r"[a-zA-Z0-9-]{1,80}", args.trava)
            or Path(rt.book_root).resolve() != (root / "book").resolve()
            or Path(rt.reports_root).resolve() != (root / "reports").resolve()):
        raise ValueError("Identificadores/caminhos fora do clone executor")
    record = executor.ler_execucao(root, args.execucao)
    if (not record or record.get("tarefa") not in {"cdp-diario", "cdp-diario-reforco", "cdp-diario-sabado"}
            or record.get("trava") != args.trava or mente_divergente(mind, record.get("mente"))
            or record.get("ensaio") is not False or record.get("sem_trava") is not False):
        raise ValueError("Execução/trava/mente não vinculadas à rotina diária")
    code, identity = executor.verificar(root)
    if code != executor.OK or not identity.get("sou_o_executor"):
        raise ValueError("Este ambiente não é o executor autorizado")
    state = executor._confirmar_trava(root, args.trava, dict(os.environ))
    if state.get("estado") != "renovada":
        raise ValueError("Trava distribuída não confirmada")
