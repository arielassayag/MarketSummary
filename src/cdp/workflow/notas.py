"""Notas de pesquisa por emissor — preparação, validação, publicação e fila (dono: workstream B).

Ciclo de vida espelhado na tese (DESIGN §B.3), em ``book/cobertura/notas/<IID>/<D>/``:
``fatos.md``, ``factbook.json``, ``contexto.json``, ``nota.schema.json`` (código), ``nota.json``
(mente; único arquivo editável), ``nota_publicada.json`` e ``nota.md`` (código, imutáveis).
Números só via ``{{fact:id}}``; evidências só de fontes públicas (URL), tratadas como dado não
confiável. O FactBook do emissor vem do modelo aberto da cobertura (``cobertura/fatos.py``) no
último snapshot até a data; sem snapshot (ou com o módulo indisponível), dos fatos de mercado do
emissor e dos pares definidos pelo código — a lacuna fica registrada, nunca vira zero.

- ``cdp nota agenda [--date D]``: fila determinística — rascunhos entregues pendentes
  (``docs/cdp/notas``), pós-resultado (até 4 dias corridos), vencidos pelo SLA (sem nota =
  iniciação; 7/14/90 dias para posições, candidatos Compra/Venda e demais) e, por último, a
  nova leitura de emissores cuja última nota é a automática do código; dentro de cada grupo,
  posições, candidatos e demais, do maior volume financeiro para o menor. No máximo
  :data:`LIMITE_POR_EXECUCAO` emissores por execução; cada item traz ``data_nota``.
- ``cdp nota prepare --issuer IID [--date D]``: fatos e briefing da nota (adota o rascunho
  entregue em ``docs/cdp/notas/<IID>/<D>.json`` se ``nota.json`` ainda não existir). A data
  nunca é posterior a hoje (Brasília) nem anterior à última nota publicada do emissor.
- ``cdp validate-nota --issuer IID --date D``: valida ``nota.json`` sem publicar.
- ``cdp nota publish --issuer IID --date D``: publica (mente ou nota automática do código);
  imutável; evento ``COVERAGE_NOTE`` na trilha.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import date, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

from ..contracts import FactBook
from ..hashing import sha256_file, sha256_obj, sha256_text

if TYPE_CHECKING:  # pragma: no cover
    from ..research.notas import ContextoNota, NotaEmpresa
    from .runtime import Runtime

NOTAS_DIRNAME = "notas"
FATOS_MD = "fatos.md"
FACTBOOK_JSON = "factbook.json"
CONTEXTO_JSON = "contexto.json"
SCHEMA_JSON = "nota.schema.json"
NOTA_JSON = "nota.json"
PUBLISHED_JSON = "nota_publicada.json"
NOTA_MD = "nota.md"
PREPARED_FILES = (FATOS_MD, FACTBOOK_JSON, CONTEXTO_JSON, SCHEMA_JSON)
AUDIT_EVENT = "COVERAGE_NOTE"
LIMITE_POR_EXECUCAO = 12
SLA_DIAS = {"posicao": 7, "candidato": 14, "demais": 90}
JANELA_POS_RESULTADO_DIAS = 4
MAX_PARES = 8
LINHAS_EUA = ("NYSE", "NASDAQ", "NYSE ARCA", "NYSEARCA", "AMEX", "NYSE AMERICAN")
EM_IMPLEMENTACAO = 2


# ==========================================================
# Caminhos
# ==========================================================

def notas_root(book_root: Path | str) -> Path:
    return Path(book_root) / "cobertura" / NOTAS_DIRNAME


def nota_dir(book_root: Path | str, issuer_id: str, d: date) -> Path:
    return notas_root(book_root) / issuer_id / d.isoformat()


def handoff_root(rt: Runtime) -> Path | None:
    """Rascunhos entregues fora do clone das rotinas: ``docs/cdp/notas`` (irmã da pasta das
    teses; ``None`` quando a adoção está desligada, como na demonstração)."""
    root = getattr(rt, "teses_root", None)
    return None if root is None else Path(root).parent / NOTAS_DIRNAME


def handoff_path(rt: Runtime, issuer_id: str, d: date) -> Path | None:
    root = handoff_root(rt)
    if root is None:
        return None
    path = root / issuer_id / f"{d.isoformat()}.json"
    return path if path.is_file() else None


def published_notes(book_root: Path | str, issuer_id: str | None = None) -> list[tuple[str, date]]:
    """``(emissor, data)`` de toda nota publicada (com ``nota_publicada.json``), em ordem."""
    root = notas_root(book_root)
    if not root.is_dir():
        return []
    out: list[tuple[str, date]] = []
    for idir in sorted(p for p in root.iterdir() if p.is_dir()):
        if issuer_id is not None and idir.name != issuer_id:
            continue
        for ddir in sorted(p for p in idir.iterdir() if p.is_dir()):
            try:
                d = date.fromisoformat(ddir.name)
            except ValueError:
                continue
            if (ddir / PUBLISHED_JSON).is_file():
                out.append((idir.name, d))
    return out


def load_published(book_root: Path | str, issuer_id: str, d: date) -> dict[str, Any] | None:
    path = nota_dir(book_root, issuer_id, d) / PUBLISHED_JSON
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return raw if isinstance(raw, dict) else None


def previous_note(book_root: Path | str, issuer_id: str, before: date) -> dict[str, Any] | None:
    """Resumo da última nota publicada do emissor ANTES de ``before`` (``None`` se não há)."""
    dates = [d for i, d in published_notes(book_root, issuer_id) if d < before]
    if not dates:
        return None
    doc = load_published(book_root, issuer_id, dates[-1]) or {}
    r = doc.get("rendered") or {}
    return {"data": dates[-1].isoformat(), "tipo": r.get("tipo"), "titulo": r.get("titulo"),
            "stance": r.get("stance"), "conviccao": r.get("conviccao"),
            "autoria": doc.get("autoria"), "proximo_resultado": doc.get("proximo_resultado")}


# ==========================================================
# Fatos e contexto (código, recalculados em memória)
# ==========================================================

def _dump(obj: Any) -> str:
    from ..research.pm_agent import _dump_json

    return _dump_json(obj)


def _snapshot(rt: Runtime, d: date) -> tuple[Any, str | None]:
    """Último snapshot da cobertura até ``d`` (``None`` + motivo quando indisponível)."""
    try:
        from ..cobertura.livro import ultimo_snapshot
    except ImportError:  # pragma: no cover - pacote ausente
        return None, "modelo de cobertura indisponível (módulo ausente)"
    try:
        snap = ultimo_snapshot(Path(rt.book_root), d)
    except NotImplementedError:
        return None, "modelo de cobertura em implementação"
    except Exception as exc:  # noqa: BLE001 - livro da cobertura com falha: nunca usado
        return None, f"livro da cobertura com falha de integridade ({exc.__class__.__name__})"
    if snap is None:
        return None, f"sem snapshot do modelo de cobertura até {d.isoformat()}"
    return snap, None


def _coverage_model(rt: Runtime, snap: Any, issuer_id: str) -> dict[str, Any] | None:
    """Modelo aberto do emissor no snapshot que o cobriu por último (até ``snap.as_of``)."""
    try:
        estado = snap.estado()
        if issuer_id not in estado.index:
            return None
        from ..cobertura.livro import snapshot

        d0 = date.fromisoformat(str(estado.loc[issuer_id, "snapshot"]))
        return snapshot(Path(rt.book_root), d0).modelo(issuer_id)
    except Exception:  # noqa: BLE001 - snapshot parcial/ilegível: sem modelo
        return None


def _code_peers(md: Any, issuer_id: str, liq: dict[str, float]) -> list[str]:
    """Pares sem modelo de cobertura: mesmo país e setor, do maior volume financeiro médio para o
    menor (sem volume conhecido, depois, em ordem alfabética)."""
    iss = md.universe.issuers
    row = iss.loc[issuer_id]
    same = iss[(iss["country"] == row["country"]) & (iss["gics_sector"] == row["gics_sector"])]
    ids = [str(i) for i in same.index if i != issuer_id]
    ids.sort(key=lambda i: (i not in liq, -liq.get(i, 0.0), i))
    return ids[:MAX_PARES]


def _next_earnings(md: Any, issuer_id: str) -> str | None:
    try:
        tkr = md.universe.primary_ticker(issuer_id)
        raw = md.fundamentals.loc[tkr, "next_earnings_date"]
    except (KeyError, AttributeError, ValueError):
        return None
    try:
        return date.fromisoformat(str(raw)[:10]).isoformat()
    except ValueError:
        return None


def build_note_inputs(rt: Runtime, issuer_id: str, d: date) -> tuple[FactBook, ContextoNota]:
    """FactBook e contexto do emissor na data ``d`` (sem look-ahead; nada é gravado)."""
    from ..analytics.panel import build_asset_panel
    from ..research.factbook import build_factbook
    from ..research.notas import (
        LACUNA_MODELO,
        ContextoNota,
        ficha,
        termos_permitidos,
        ticker_roots,
    )
    from .tese_analise import country_label, sector_label

    md = rt.store.load(d)
    if md.as_of > d:
        raise ValueError(f"Dados de mercado posteriores à data da nota ({md.as_of} > {d}).")
    iss = md.universe.issuers
    if issuer_id not in iss.index:
        raise ValueError(f"Emissor fora do universo: {issuer_id}.")
    lacunas: list[str] = []
    snap, aviso = _snapshot(rt, d)
    fb: FactBook | None = None
    snap_info: dict[str, Any] | None = None
    pares: list[str] = []
    if snap is not None:
        mod = _coverage_model(rt, snap, issuer_id)
        if mod is None:
            aviso = f"emissor sem modelo no snapshot de cobertura de {snap.as_of.isoformat()}"
        else:
            try:
                from ..cobertura.fatos import factbook_emissor

                fb = factbook_emissor(snap, issuer_id, md)
            except NotImplementedError:
                aviso = "fatos do modelo de cobertura em implementação"
            else:
                pares = [str(p) for p in (mod.get("pares") or {}).get("emissores", [])
                         if p != issuer_id and p in iss.index][:MAX_PARES]
                snap_info = {"as_of": snap.as_of.isoformat(),
                             "manifest_sha256": snap.manifest_sha256,
                             "modelo_as_of": str(mod.get("as_of"))}
    if fb is None:
        panel = build_asset_panel(md, rt.cfg)
        tv = panel.traded_value_usd.tail(20).median()
        pares = _code_peers(md, issuer_id, {str(k): float(v) for k, v in tv.items() if v == v})
        fb = build_factbook(panel, md, [issuer_id, *pares])
    avisos: list[str] = []
    if aviso:
        lacunas.append(LACUNA_MODELO)
        avisos.append(f"Modelo de cobertura: {aviso}.")
    ids = [issuer_id, *pares]
    lines = md.universe.lines
    nomes = {i: str(iss.loc[i, "issuer_name"]) for i in ids}
    own_lines = lines[lines["issuer_id"] == issuer_id]
    tickers = ticker_roots(own_lines.index)
    all_tickers = ticker_roots(lines[lines["issuer_id"].isin(ids)].index)
    exch = {str(x).upper() for x in own_lines.get("exchange", [])}
    ltype = {str(x).upper() for x in own_lines.get("line_type", [])}
    tem_eua = bool(exch & set(LINHAS_EUA)) or bool(ltype & {"ADR", "US_LISTED"})
    lacunas += [f"{r['rotulo']}: sem dado na data." for r in ficha(fb, issuer_id)
                if fb.facts[r["fato"]].value is None]
    row = iss.loc[issuer_id]
    ctx = ContextoNota(
        issuer_id=issuer_id, nome=nomes[issuer_id], pais=str(row["country"]),
        pais_pt=country_label(str(row["country"])), setor=str(row["gics_sector"]),
        setor_pt=sector_label(str(row["gics_sector"])), data=d, dados_ate=md.as_of,
        is_synthetic=bool(md.is_synthetic or fb.is_synthetic), pares=tuple(pares),
        nomes=nomes, termos=termos_permitidos(nomes, all_tickers), tickers=tuple(tickers),
        tem_linha_eua=tem_eua, nota_anterior=previous_note(rt.book_root, issuer_id, d),
        snapshot=snap_info, proximo_resultado=_next_earnings(md, issuer_id),
        lacunas=tuple(lacunas), avisos_tecnicos=tuple(avisos))
    return fb, ctx


def _commands(rt: Runtime, issuer_id: str, d: date) -> tuple[str, str]:
    base = "uv run python -m cdp"
    if Path(rt.book_root) != Path("book"):
        base += f" --book {Path(rt.book_root).as_posix()}"
    if Path(rt.market_root) != Path("data/market"):
        base += f" --market {Path(rt.market_root).as_posix()}"
    args = f"--issuer {issuer_id} --date {d.isoformat()}"
    return f"{base} validate-nota {args}", f"{base} nota publish {args}"


def _build_prepared(rt: Runtime, issuer_id: str, d: date
                    ) -> tuple[FactBook, ContextoNota, dict[str, str]]:
    from ..research.commentary import factbook_json
    from ..research.notas import NotaEmpresa, render_fatos_md

    fb, ctx = build_note_inputs(rt, issuer_id, d)
    folder = nota_dir(rt.book_root, issuer_id, d)
    val_cmd, pub_cmd = _commands(rt, issuer_id, d)
    texts = {
        FATOS_MD: render_fatos_md(fb, ctx, nota_path=(folder / NOTA_JSON).as_posix(),
                                  schema_name=SCHEMA_JSON, validate_cmd=val_cmd,
                                  publish_cmd=pub_cmd),
        FACTBOOK_JSON: factbook_json(fb),
        CONTEXTO_JSON: _dump(ctx.to_json()),
        SCHEMA_JSON: json.dumps(NotaEmpresa.model_json_schema(), ensure_ascii=False, indent=2,
                                sort_keys=True) + "\n",
    }
    return fb, ctx, texts


def today_local(rt: Runtime) -> date:
    """Data de hoje no fuso do fundo (Brasília), pelo relógio da rotina."""
    from zoneinfo import ZoneInfo

    try:
        tz = ZoneInfo(rt.cfg.fund.timezone)
    except (KeyError, ValueError):
        tz = ZoneInfo("America/Sao_Paulo")
    return rt.now().astimezone(tz).date()


def check_note_date(rt: Runtime, issuer_id: str, d: date) -> None:
    """Recusa (``ValueError``) uma nota nova com data posterior a hoje (Brasília) ou anterior à
    última nota publicada do emissor (a sequência de notas só anda para a frente)."""
    hoje = today_local(rt)
    if d > hoje:
        raise ValueError(f"Data da nota {d.isoformat()} posterior a hoje ({hoje.isoformat()}, "
                         "Brasília): uma nota tem data até hoje.")
    later = [x for _, x in published_notes(rt.book_root, issuer_id) if x > d]
    if later:
        raise ValueError(f"Já há nota de {issuer_id} publicada em {later[-1].isoformat()}, "
                         f"posterior a {d.isoformat()}: uma nota nova tem data igual ou "
                         "posterior à última publicada.")


def _copy_exclusive(src: Path, dst: Path) -> bool:
    from .tese import _copy_exclusive as copy

    return copy(src, dst)


def prepare_note(rt: Runtime, issuer_id: str, d: date) -> dict[str, Any]:
    """Grava ``fatos.md``, ``factbook.json``, ``contexto.json`` e ``nota.schema.json`` e adota o
    rascunho entregue (sem sobrescrever ``nota.json``). Publicada ⇒ não regrava nada."""
    from ..research.pm_agent import _write_files

    folder = nota_dir(rt.book_root, issuer_id, d)
    nota_path = folder / NOTA_JSON
    draft = handoff_path(rt, issuer_id, d)
    if (folder / PUBLISHED_JSON).exists():
        return {"emissor": issuer_id, "data": d, "pasta": folder.as_posix(), "publicada": True,
                "nota_path": nota_path.as_posix(), "arquivos": {},
                "rascunho_entregue": draft.as_posix() if draft else None,
                "rascunho_adotado": False,
                "mensagem": f"Nota de {issuer_id} em {d} já publicada (imutável): nada foi "
                            "regravado."}
    check_note_date(rt, issuer_id, d)
    fb, ctx, texts = _build_prepared(rt, issuer_id, d)
    paths = _write_files(folder, texts, overwrite=True)
    adopted = _copy_exclusive(draft, nota_path) if draft is not None else False
    return {"emissor": issuer_id, "data": d, "pasta": folder.as_posix(), "publicada": False,
            "nota_path": nota_path.as_posix(), "n_fatos": len(fb.facts),
            "tipo_esperado": "iniciacao" if ctx.nota_anterior is None else "atualizacao",
            "modelo_de_cobertura": (ctx.snapshot or {}).get("as_of"),
            "pares": list(ctx.pares), "lacunas": list(ctx.lacunas),
            "avisos_tecnicos": list(ctx.avisos_tecnicos),
            "arquivos": {k: v.as_posix() for k, v in paths.items()},
            "rascunho_entregue": draft.as_posix() if draft else None,
            "rascunho_adotado": adopted}


def load_prepared(folder: Path) -> tuple[FactBook, ContextoNota]:
    from ..research.notas import contexto_de_json

    fb = FactBook.model_validate(json.loads((folder / FACTBOOK_JSON).read_text(encoding="utf-8")))
    ctx = contexto_de_json(json.loads((folder / CONTEXTO_JSON).read_text(encoding="utf-8")))
    return fb, ctx


def load_note_file(path: Path, fb: FactBook, ctx: ContextoNota, *,
                   expected_mind: str | None = None) -> tuple[NotaEmpresa | None, list[str]]:
    """``nota.json`` validado (schema + guardrails + mente da execução); ausente ou inválido ⇒
    ``(None, problemas)``."""
    from ..contracts import mente_divergente
    from ..research.notas import parse_nota, verify_nota

    if not path.is_file():
        return None, [f"{NOTA_JSON} ausente ({path.as_posix()})"]
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        return None, [f"{NOTA_JSON}: JSON inválido ({exc})"]
    nota, issues = parse_nota(raw)
    if nota is None:
        return None, issues
    issues = verify_nota(nota, fb, ctx)
    if (divergente := mente_divergente(nota.mind, expected_mind)):
        issues = [divergente, *issues]
    return (None, issues) if issues else (nota, [])


def _mente_esperada(rt: Runtime, issuer_id: str, d: date) -> str | None:
    """Mente que a nota deve declarar (rascunho entregue mantém a de quem o escreveu)."""
    fn = getattr(rt, "mente_esperada", None)
    if fn is None:
        return None
    return fn(nota_dir(rt.book_root, issuer_id, d) / NOTA_JSON, handoff_path(rt, issuer_id, d))


def validate_note(rt: Runtime, issuer_id: str, d: date) -> dict[str, Any]:
    """Valida ``nota.json`` SEM publicar; prepara os fatos se faltarem."""
    folder = nota_dir(rt.book_root, issuer_id, d)
    if not (folder / PUBLISHED_JSON).exists():
        check_note_date(rt, issuer_id, d)
    if not all((folder / n).is_file() for n in (FACTBOOK_JSON, CONTEXTO_JSON)):
        if (folder / PUBLISHED_JSON).exists():
            raise FileNotFoundError(f"Nota publicada sem os fatos preparados em "
                                    f"{folder.as_posix()}.")
        prepare_note(rt, issuer_id, d)
    fb, ctx = load_prepared(folder)
    nota, issues = load_note_file(folder / NOTA_JSON, fb, ctx,
                                  expected_mind=_mente_esperada(rt, issuer_id, d))
    return {"ok": nota is not None, "problemas": issues, "nota_path":
            (folder / NOTA_JSON).as_posix(),
            "tipo_esperado": "iniciacao" if ctx.nota_anterior is None else "atualizacao"}


# ==========================================================
# Publicação
# ==========================================================

def _compose(fb: FactBook, ctx: ContextoNota, nota_path: Path, *, published_at: str,
             expected_mind: str | None = None) -> tuple[str, str, str, list[str], str | None]:
    """``(nota_publicada.json, nota.md, autoria, problemas, mind)`` — determinístico dado o
    instante de publicação."""
    from ..research.notas import (
        NOTA_PUBLICADA_SCHEMA,
        render_markdown,
        render_nota,
        template_nota,
    )

    nota, problems = load_note_file(nota_path, fb, ctx, expected_mind=expected_mind)
    fallback = "Nota da mente não publicada: usada a nota automática do código."
    if nota is None:
        autoria, used, mind, modelo = "codigo", template_nota(fb, ctx), None, None
        problems = problems + [fallback]
    else:
        autoria, used, mind, modelo = "mente", nota, nota.mind, nota.modelo_ia
    rendered = render_nota(used, fb, ctx, autoria=autoria, published_at=published_at)
    if autoria == "mente" and "{{" in json.dumps(rendered, ensure_ascii=False):
        nota = None
        autoria, used, mind, modelo = "codigo", template_nota(fb, ctx), None, None
        problems = problems + ["Placeholder não resolvido na narrativa da mente.", fallback]
        rendered = render_nota(used, fb, ctx, autoria=autoria, published_at=published_at)
    if "{{" in json.dumps(rendered, ensure_ascii=False):
        raise ValueError("Placeholder não resolvido na nota renderizada: publicação recusada.")
    markdown = render_markdown(rendered)
    doc = {"schema": NOTA_PUBLICADA_SCHEMA, "issuer_id": ctx.issuer_id,
           "data": ctx.data.isoformat(), "published_at": published_at, "autoria": autoria,
           "mind": mind, "modelo_ia": modelo, "is_synthetic": ctx.is_synthetic,
           "proximo_resultado": ctx.proximo_resultado, "problems": problems,
           "stance": used.stance, "conviccao": used.conviccao,
           "hashes": {"factbook": fb.factbook_hash(), "contexto": sha256_obj(ctx.to_json()),
                      "nota_json": sha256_file(nota_path) if nota is not None else None},
           "cobertura": ctx.snapshot, "rendered": rendered}
    return _dump(doc), markdown, autoria, problems, mind


def _payload(pub: Path, md_path: Path, ctx: ContextoNota, autoria: str) -> dict[str, Any]:
    return {"issuer_id": ctx.issuer_id, "data": ctx.data.isoformat(),
            "nota_publicada": sha256_file(pub), "nota_md": sha256_file(md_path),
            "snapshot": (ctx.snapshot or {}).get("as_of"), "autoria": autoria}


def _anchored(rt: Runtime, payload: dict[str, Any]) -> bool:
    h = sha256_obj(payload)
    return any(e.event_type == AUDIT_EVENT and e.payload_hash == h
               for e in rt.book.audit.events())


def _anchor(rt: Runtime, payload: dict[str, Any], autoria: str) -> Any:
    return rt.book.audit.append(AUDIT_EVENT, "CDP", payload,
                                summary=f"Nota de pesquisa {payload['issuer_id']} "
                                        f"{payload['data']} publicada (autoria: {autoria}).")


def publish_note(rt: Runtime, issuer_id: str, d: date) -> dict[str, Any]:
    """Publica a nota (imutável) e anexa ``COVERAGE_NOTE``. Fatos RECALCULADOS (nunca os do
    disco); ``nota.json`` válido ⇒ narrativa da mente; senão a nota automática do código, com os
    problemas listados. Falha no meio ⇒ arquivos removidos (nada publicado sem evento). Já
    publicada ⇒ ``FileExistsError``; publicação interrompida antes do evento ⇒ retomada se os
    arquivos conferirem byte a byte com o recálculo."""
    from ..research.pm_agent import _write_files
    from .book import _write_exclusive

    folder = nota_dir(rt.book_root, issuer_id, d)
    pub, md_path = folder / PUBLISHED_JSON, folder / NOTA_MD
    if pub.exists() or md_path.exists():
        return _resume(rt, issuer_id, d)
    check_note_date(rt, issuer_id, d)
    fb, ctx, texts = _build_prepared(rt, issuer_id, d)
    notes: list[str] = []
    changed = [n for n in (FACTBOOK_JSON, CONTEXTO_JSON)
               if (folder / n).is_file() and (folder / n).read_text(encoding="utf-8") != texts[n]]
    if changed:
        notes.append("Arquivos preparados diferentes do recálculo do código (" + ", ".join(changed)
                     + "): regravados; a publicação usa o recálculo.")
    missing = not (folder / FACTBOOK_JSON).is_file()
    _write_files(folder, texts, overwrite=True)
    if missing and (draft := handoff_path(rt, issuer_id, d)) is not None:
        _copy_exclusive(draft, folder / NOTA_JSON)
    doc, markdown, autoria, problems, mind = _compose(
        fb, ctx, folder / NOTA_JSON, published_at=rt.now().isoformat(),
        expected_mind=_mente_esperada(rt, issuer_id, d))
    _write_exclusive(pub, doc)
    try:
        _write_exclusive(md_path, markdown)
        ev = _anchor(rt, _payload(pub, md_path, ctx, autoria), autoria)
    except BaseException:
        md_path.unlink(missing_ok=True)
        pub.unlink(missing_ok=True)
        raise
    return {"emissor": issuer_id, "data": d, "publicada": True, "autoria": autoria,
            "mind": mind, "problemas": notes + problems,
            "arquivos": {PUBLISHED_JSON: pub.as_posix(), NOTA_MD: md_path.as_posix()},
            "evento": {"seq": ev.seq, "hash": ev.event_hash}}


def _resume(rt: Runtime, issuer_id: str, d: date) -> dict[str, Any]:
    from .book import _write_exclusive

    folder = nota_dir(rt.book_root, issuer_id, d)
    pub, md_path = folder / PUBLISHED_JSON, folder / NOTA_MD
    done = FileExistsError(f"Nota de {issuer_id} em {d} já publicada (imutável).")
    if not pub.exists():
        raise FileExistsError(f"Nota de {issuer_id} em {d}: {md_path.as_posix()} existe sem "
                              f"{PUBLISHED_JSON}; intervenção manual.")
    doc = load_published(rt.book_root, issuer_id, d)
    if doc is None:
        raise ValueError(f"Publicação incompleta da nota de {issuer_id} em {d}: "
                         f"{pub.as_posix()} ilegível; intervenção manual.")
    fb, ctx = load_prepared(folder)
    autoria = str(doc.get("autoria"))
    if md_path.exists() and _anchored(rt, _payload(pub, md_path, ctx, autoria)):
        raise done
    fb, ctx, _texts = _build_prepared(rt, issuer_id, d)
    text, markdown, autoria2, problems, mind = _compose(
        fb, ctx, folder / NOTA_JSON, published_at=str(doc.get("published_at")),
        expected_mind=_mente_esperada(rt, issuer_id, d))
    if pub.read_text(encoding="utf-8") != text or autoria2 != autoria or (
            md_path.exists() and md_path.read_text(encoding="utf-8") != markdown):
        raise ValueError(f"Publicação incompleta da nota de {issuer_id} em {d}: os arquivos "
                         "existentes não conferem com o recálculo do código e não estão na "
                         "trilha; publicação recusada (intervenção manual).")
    if not md_path.exists():
        payload = {**_payload(pub, pub, ctx, autoria), "nota_md": sha256_text(markdown)}
        if _anchored(rt, payload):
            raise done
        _write_exclusive(md_path, markdown)
    ev = _anchor(rt, _payload(pub, md_path, ctx, autoria), autoria)
    return {"emissor": issuer_id, "data": d, "publicada": True, "autoria": autoria,
            "mind": mind, "problemas": problems, "retomada": True,
            "arquivos": {PUBLISHED_JSON: pub.as_posix(), NOTA_MD: md_path.as_posix()},
            "evento": {"seq": ev.seq, "hash": ev.event_hash}}


def verify_notes(rt: Runtime) -> list[str]:
    """Toda nota publicada tem o evento ``COVERAGE_NOTE`` com os hashes dos arquivos, e todo
    evento aponta para arquivos íntegros (vazio = íntegro)."""
    events = [e for e in rt.book.audit.events() if e.event_type == AUDIT_EVENT]
    hashes = {e.payload_hash for e in events}
    problems: list[str] = []
    seen: set[str] = set()
    for iid, d in published_notes(rt.book_root):
        folder = nota_dir(rt.book_root, iid, d)
        pub, md_path = folder / PUBLISHED_JSON, folder / NOTA_MD
        doc = load_published(rt.book_root, iid, d) or {}
        if not md_path.is_file():
            problems.append(f"nota {iid} {d}: {NOTA_MD} ausente")
            continue
        payload = {"issuer_id": iid, "data": d.isoformat(), "nota_publicada": sha256_file(pub),
                   "nota_md": sha256_file(md_path),
                   "snapshot": (doc.get("cobertura") or {}).get("as_of"),
                   "autoria": doc.get("autoria")}
        h = sha256_obj(payload)
        if h not in hashes:
            problems.append(f"nota {iid} {d}: arquivos publicados sem evento {AUDIT_EVENT} "
                            "correspondente (alterados ou fora da trilha)")
        seen.add(h)
    orphan = len([e for e in events if e.payload_hash not in seen])
    if orphan:
        problems.append(f"{orphan} evento(s) {AUDIT_EVENT} sem os arquivos publicados")
    return problems


# ==========================================================
# Fila (agenda das notas)
# ==========================================================

def _liquidity(md: Any, cfg: Any) -> dict[str, float]:
    """Mediana do volume financeiro diário (USD, 20 pregões) por emissor (ausente ⇒ sem chave)."""
    try:
        from ..analytics.panel import build_asset_panel

        tv = build_asset_panel(md, cfg).traded_value_usd.tail(20).median()
    except Exception:  # noqa: BLE001 - sem painel: ordem só alfabética
        return {}
    return {str(k): float(v) for k, v in tv.items() if v == v}


def _held(rt: Runtime) -> set[str]:
    try:
        entry = rt.book.latest_booked()
    except Exception:  # noqa: BLE001
        return set()
    return {p.issuer_id for p in entry.positions if p.weight} if entry else set()


def _candidates(rt: Runtime, d: date) -> set[str]:
    snap, _ = _snapshot(rt, d)
    if snap is None:
        return set()
    try:
        estado = snap.estado()
        return {str(i) for i, r in estado.iterrows()
                if str(r.get("rating", "")) in ("Compra", "Venda")}
    except Exception:  # noqa: BLE001
        return set()


def handoff_drafts(rt: Runtime, d: date) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Rascunhos entregues em ``docs/cdp/notas/<IID>/<data>.json`` com data até ``d`` e ainda
    sem nota publicada nessa data: ``(pendentes, obsoletos)``. Obsoleto = o emissor já tem nota
    publicada depois da data do rascunho (a sequência só anda para a frente) ou está fora do
    universo; nunca é adotado."""
    root = handoff_root(rt)
    if root is None or not root.is_dir():
        return [], []
    try:
        universo = set(rt.store.load(d).universe.issuers.index)
    except Exception:  # noqa: BLE001 - sem base de mercado: o prepare acusa depois
        universo = None
    pend: list[dict[str, Any]] = []
    obs: list[dict[str, Any]] = []
    for idir in sorted(x for x in root.iterdir() if x.is_dir()):
        pubs = [x for _, x in published_notes(rt.book_root, idir.name)]
        for f in sorted(idir.glob("*.json")):
            try:
                dd = date.fromisoformat(f.stem)
            except ValueError:
                continue
            if dd > d or dd in pubs:
                continue
            item = {"issuer_id": idir.name, "data_nota": dd.isoformat(),
                    "rascunho": f.as_posix()}
            if universo is not None and idir.name not in universo:
                obs.append({**item, "motivo": "emissor fora do universo"})
            elif any(x > dd for x in pubs):
                obs.append({**item, "motivo": "há nota publicada depois da data do rascunho"})
            else:
                pend.append(item)
    return pend, obs


def mind_history(book_root: Path | str) -> list[dict[str, Any]]:
    """Visões ordinais publicadas por mente (só ``autoria: mente``; a nota automática do código
    não é visão): base do acompanhamento por mente — visões de mentes diferentes nunca se
    somam (SOTA_GAP CR-3.5)."""
    out: list[dict[str, Any]] = []
    for iid, d in published_notes(book_root):
        doc = load_published(book_root, iid, d) or {}
        if doc.get("autoria") != "mente":
            continue
        out.append({"issuer_id": iid, "data": d.isoformat(), "mind": doc.get("mind"),
                    "modelo_ia": doc.get("modelo_ia"), "stance": doc.get("stance"),
                    "conviccao": doc.get("conviccao")})
    return out


#: Grupos da fila, nesta ordem (dentro de cada um: posições, candidatos, demais; liquidez).
GRUPOS_FILA = ("rascunho", "pos_resultado", "vencida", "nota_automatica")


def note_agenda(rt: Runtime, d: date, limit: int = LIMITE_POR_EXECUCAO) -> dict[str, Any]:
    """Fila determinística de notas a escrever em ``d`` (ver docstring do módulo)."""
    md = rt.store.load(d)
    iss = md.universe.issuers
    held, cands = _held(rt), _candidates(rt, d)
    liq = _liquidity(md, rt.cfg)
    pubs = published_notes(rt.book_root)
    last: dict[str, date] = {}
    for iid, nd in pubs:
        if nd <= d:
            last[iid] = max(last.get(iid, nd), nd)
    rascunhos, obsoletos = handoff_drafts(rt, d)
    com_rascunho: dict[str, dict[str, Any]] = {}
    for r in rascunhos:  # um rascunho por emissor por execução: o mais antigo primeiro
        com_rascunho.setdefault(r["issuer_id"], r)

    def classe_de(iid: str) -> str:
        return "posicao" if iid in held else "candidato" if iid in cands else "demais"

    def ordem(grupo: str, iid: str) -> tuple:
        return (GRUPOS_FILA.index(grupo), ("posicao", "candidato", "demais").index(classe_de(iid)),
                -liq[iid] if iid in liq else float("inf"), iid)

    due: list[dict[str, Any]] = []
    for iid, r in com_rascunho.items():
        dd = date.fromisoformat(r["data_nota"])
        anterior = [x for i, x in pubs if i == iid and x < dd]
        due.append({"issuer_id": iid, "nome": str(iss.loc[iid, "issuer_name"]),
                    "classe": classe_de(iid), "grupo": "rascunho",
                    "motivo": f"rascunho entregue ({r['data_nota']})",
                    "tipo_sugerido": "atualizacao" if anterior else "iniciacao",
                    "data_nota": r["data_nota"],
                    "ultima_nota": max(anterior).isoformat() if anterior else None,
                    "_ordem": ordem("rascunho", iid)})
    for iid in sorted(iss.index):
        if iid in com_rascunho:
            continue
        prev = last.get(iid)
        if prev is None:
            grupo, motivo, tipo = "vencida", "iniciação de cobertura", "iniciacao"
        else:
            if prev == d:
                continue
            doc = load_published(rt.book_root, iid, prev) or {}
            pr = doc.get("proximo_resultado")
            try:
                prd = date.fromisoformat(str(pr)) if pr else None
            except ValueError:
                prd = None
            idade = (d - prev).days
            if prd is not None and prev < prd <= d and (d - prd).days <= JANELA_POS_RESULTADO_DIAS:
                grupo, motivo, tipo = ("pos_resultado", f"pós-resultado ({prd.isoformat()})",
                                       "pos_resultado")
            elif idade >= SLA_DIAS[classe_de(iid)]:
                grupo, motivo, tipo = "vencida", f"atualização: nota com {idade} dias", "atualizacao"
            elif doc.get("autoria") == "codigo":
                grupo, tipo = "nota_automatica", "atualizacao"
                motivo = (f"nota automática de {prev.isoformat()}; leitura qualitativa "
                          "pendente")
            else:
                continue
        due.append({"issuer_id": iid, "nome": str(iss.loc[iid, "issuer_name"]),
                    "classe": classe_de(iid), "grupo": grupo, "motivo": motivo,
                    "tipo_sugerido": tipo, "data_nota": d.isoformat(),
                    "ultima_nota": prev.isoformat() if prev else None,
                    "_ordem": ordem(grupo, iid)})
    due.sort(key=lambda x: x["_ordem"])
    fila = [{k: v for k, v in x.items() if k != "_ordem"} for x in due[:limit]]
    snap, aviso = _snapshot(rt, d)
    por_mente: dict[str, int] = {}
    for h in mind_history(rt.book_root):
        por_mente[str(h["mind"])] = por_mente.get(str(h["mind"]), 0) + 1
    return {"data": d, "dados_ate": md.as_of, "limite_por_execucao": limit, "fila": fila,
            "pendentes": len(due), "publicadas": len(pubs),
            "rascunhos_pendentes": rascunhos, "rascunhos_obsoletos": obsoletos,
            "notas_da_mente_por_mente": dict(sorted(por_mente.items())),
            "modelo_de_cobertura": snap.as_of if snap is not None else None,
            "aviso_cobertura": aviso, "integridade_notas": verify_notes(rt) or ["íntegras"]}


# ==========================================================
# Demonstração
# ==========================================================

def write_demo_note(rt: Runtime, issuer_id: str, d: date) -> Path:
    """A mente ``demo`` escreve ``nota.json`` (a nota automática, só fatos citados)."""
    from ..research.notas import template_nota

    prepare_note(rt, issuer_id, d)
    folder = nota_dir(rt.book_root, issuer_id, d)
    fb, ctx = load_prepared(folder)
    path = folder / NOTA_JSON
    path.write_text(json.dumps(template_nota(fb, ctx, "demo").model_dump(mode="json"),
                               ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return path


# ==========================================================
# CLI
# ==========================================================

def _today_brt() -> date:
    from zoneinfo import ZoneInfo

    return datetime.now(ZoneInfo("America/Sao_Paulo")).date()


def _print(obj: Any) -> None:
    print(json.dumps(obj, ensure_ascii=False, indent=2, default=str))


def _rt(args: argparse.Namespace) -> Runtime:
    from .runtime import Runtime

    return Runtime.from_args(args)


def cmd_agenda(args: argparse.Namespace) -> int:
    """``cdp nota agenda`` (``args.date`` ou ``None`` = hoje em Brasília)."""
    try:
        out = note_agenda(_rt(args), args.date or _today_brt())
    except (OSError, ValueError, KeyError) as exc:
        print(f"Erro: {exc}", file=sys.stderr)
        return 1
    _print(out)
    return 0


def cmd_prepare(args: argparse.Namespace) -> int:
    """``cdp nota prepare`` (``args.issuer``, ``args.date`` ou ``None``)."""
    try:
        out = prepare_note(_rt(args), args.issuer, args.date or _today_brt())
    except (OSError, ValueError, KeyError) as exc:
        print(f"Erro: {exc}", file=sys.stderr)
        return 1
    _print(out)
    return 0


def cmd_publish(args: argparse.Namespace) -> int:
    """``cdp nota publish`` (``args.issuer``, ``args.date``)."""
    try:
        out = publish_note(_rt(args), args.issuer, args.date)
    except (OSError, ValueError, KeyError) as exc:
        print(f"Erro: {exc}", file=sys.stderr)
        return 1
    _print(out)
    return 0


def cmd_validate(args: argparse.Namespace) -> int:
    """``cdp validate-nota`` (``args.issuer``, ``args.date``; código 0 válida, 1 inválida)."""
    try:
        out = validate_note(_rt(args), args.issuer, args.date)
    except (OSError, ValueError, KeyError) as exc:
        print(f"Erro: {exc}", file=sys.stderr)
        return 1
    _print(out)
    return 0 if out["ok"] else 1


__all__ = [
    "AUDIT_EVENT", "CONTEXTO_JSON", "EM_IMPLEMENTACAO", "FACTBOOK_JSON", "FATOS_MD",
    "LIMITE_POR_EXECUCAO", "NOTA_JSON", "NOTA_MD", "PUBLISHED_JSON", "SCHEMA_JSON",
    "GRUPOS_FILA", "build_note_inputs", "check_note_date", "cmd_agenda", "cmd_prepare",
    "cmd_publish", "cmd_validate", "handoff_drafts", "handoff_path", "load_note_file",
    "load_prepared", "load_published", "mind_history", "nota_dir", "note_agenda", "notas_root",
    "prepare_note", "previous_note", "publish_note", "published_notes", "today_local",
    "validate_note", "verify_notes", "write_demo_note",
]
