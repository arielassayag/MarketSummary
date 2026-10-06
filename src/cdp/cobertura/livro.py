"""Livro imutável da cobertura (``book/cobertura/``) — snapshots, livro encadeado e verificação.

Layout (DESIGN §A.5; dono: workstream A):

```
book/cobertura/
  livro.jsonl                 # append-only, encadeado por hash (um evento por instrumento por execução)
  <D>/manifest.json           # data, preços, base de mercado, configuração, código, ambiente, arquivos {caminho: sha256}
  <D>/selo.json               # {as_of, manifest_sha256, livro_head, n_eventos, ...} = payload do evento COVERAGE_SNAPSHOT
  <D>/eventos.jsonl           # os eventos do livro desta execução (cópia selada pelo manifesto)
  <D>/modelos.csv             # uma linha por emissor (preço-alvo, ke, α, rating, valor por método, ...)
  <D>/modelos/<IID>.json      # modelo aberto completo (passos com fórmula e substituição, insumos, lacunas, ...)
  <D>/etfs.csv, <D>/etfs/<ETF>.json
  <D>/insumos/*.csv.gz        # tabelas públicas da execução (CSV canônico, gzip determinístico)
  publico/{demonstrativos,dividendos}/<chave>/<sha256>.csv.gz   # por emissor/linha, endereçadas pelo
                              # conteúdo e compartilhadas entre snapshots (listadas no manifesto de cada um)
  <D>/insumos/emissores.json.gz, etfs.json.gz   # pacotes de insumos normalizados (emissores e ETFs)
  <D>/contexto.json           # contexto transversal (medianas, β das financeiras, regressões)
  <D>/configuracao/...        # cópia dos arquivos de configuração usados (valuation.yaml, cobertura/*)
  <D>/placar.json             # placar de acertos (derivado; recalculável)
```

Regras:

- grava em pasta temporária e renomeia (criação exclusiva); recusa data anterior ou igual à do
  último snapshot (sem retrodatar) e recusa gravar quando o livro tem eventos além do último selo;
- ordem de gravação recuperável: pasta do snapshot (com ``eventos.jsonl``) → livro → trilha do
  fundo. Uma interrupção entre essas etapas é detectada e completada na execução seguinte
  (``reparar_pendencias``), sempre a partir dos arquivos já selados pelo manifesto;
- leitores (``SnapshotCobertura``) conferem o SHA-256 de cada arquivo lido contra o manifesto, e o
  manifesto contra o selo;
- ``verificar`` exige: livro encadeado e terminando exatamente no último selo; cada snapshot com
  manifesto, selo, arquivos e ``eventos.jsonl`` conferidos; correspondência um a um entre selos e
  eventos ``COVERAGE_SNAPSHOT`` da trilha do fundo; placar recalculado; e o recálculo completo de
  cada snapshot (contexto, custo de capital, cenários com semente, α relativo, confiança, rating,
  ETFs) a partir dos insumos e da configuração arquivados.

O snapshot ``D`` alimenta a decisão SEGUINTE (sem look-ahead).
"""

from __future__ import annotations

import gzip
import hashlib
import io
import json
import os
import platform
import shutil
import subprocess
from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from .. import SIMULATED_DATA_NOTICE
from ..audit import AuditLog
from ..hashing import sha256_file, sha256_obj
from .fontes import DadosPublicos, csv_canonico
from .motor import AVISO_REAL, Execucao, arredondar, modelo_json, resumo_linha
from .parametros import ParametrosCobertura

SCHEMA_EVENTO = "cdp.cobertura.evento/v1"
SCHEMA_MANIFESTO = "cdp.cobertura.manifesto/v1"
GENESIS = "0" * 64
TIPOS_EVENTO = ("INICIACAO", "REITERACAO", "REVISAO", "MUDANCA_RATING", "SUSPENSAO", "RETOMADA",
                "ENCERRAMENTO")
LIMIAR_REVISAO = 0.01
"""Variação do preço-alvo (|ΔTP|/TP) a partir da qual o evento é REVISAO e não REITERACAO."""
RATINGS_CITAVEIS = ("Compra", "Neutro", "Venda")
COLUNAS_MASCARADAS = ("preco_alvo", "upside", "etr", "pwr", "alpha", "alpha_rel", "alvo_otimista",
                      "alvo_pessimista", "diff_consenso")
"""Colunas sem valor citável quando o rating não é Compra, Neutro ou Venda ("Em revisão")."""


class LivroErro(RuntimeError):
    """Recusa de gravação ou falha de integridade do livro da cobertura."""


def _json_bytes(obj: Any, compacto: bool = False) -> bytes:
    if compacto:
        txt = json.dumps(obj, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)
    else:
        txt = json.dumps(obj, ensure_ascii=False, sort_keys=True, indent=1, allow_nan=False)
    return (txt + "\n").encode("utf-8")


def _linha_evento(ev: dict[str, Any]) -> str:
    return json.dumps(ev, ensure_ascii=False, sort_keys=True)


def _escrever(path: Path, data: bytes) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "xb") as f:  # criação exclusiva
        f.write(data)
    return sha256_file(path)


def _gz(data: bytes) -> bytes:
    """gzip determinístico (sem data nem nome no cabeçalho)."""
    return gzip.compress(data, compresslevel=9, mtime=0)


def _sha(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def ler_pacotes(pasta: Path, manifest: dict[str, Any] | None = None, nome: str = "emissores") -> dict[str, Any]:
    """Pacotes de insumos normalizados arquivados no snapshot (``insumos/<nome>.json.gz``);
    com ``manifest``, o arquivo é conferido contra o hash registrado."""
    rel = f"insumos/{nome}.json.gz"
    b = (Path(pasta) / rel).read_bytes()
    if manifest is not None and _sha(b) != (manifest.get("arquivos") or {}).get(rel):
        raise LivroErro(f"{rel} não confere com o manifesto")
    return json.loads(gzip.decompress(b).decode("utf-8"))


PARTICIONADAS = {"demonstrativos": "issuer_id", "dividendos": "ticker"}
"""Tabelas guardadas por emissor (ou linha) e endereçadas pelo conteúdo em
``book/cobertura/publico/<nome>/<chave>/<sha256>.csv.gz`` (compartilhadas entre snapshots: só o que
mudou ocupa espaço novo); o manifesto de cada snapshot lista as partes que usou, com o hash."""


def _chave_parte(x: str) -> str:
    return "".join(c if c.isalnum() or c in ".-_" else "_" for c in str(x)) or "_"


def ler_tabela(pasta: Path, nome: str) -> pd.DataFrame:
    """Tabela pública arquivada no snapshot (``insumos/<nome>.csv.gz`` ou, para as tabelas
    particionadas, as partes por emissor listadas no manifesto), CSV canônico."""
    pasta = Path(pasta)
    unica = pasta / "insumos" / f"{nome}.csv.gz"
    if unica.exists():
        return pd.read_csv(io.BytesIO(gzip.decompress(unica.read_bytes())))
    man = json.loads((pasta / "manifest.json").read_text(encoding="utf-8"))
    prefixo = f"../publico/{nome}/"
    partes = [pd.read_csv(io.BytesIO(gzip.decompress((pasta / rel).read_bytes())))
              for rel in sorted(man.get("arquivos", {})) if rel.startswith(prefixo)]
    return pd.concat(partes, ignore_index=True) if partes else pd.DataFrame()


def _gravar_parte(raiz: Path, nome: str, chave: str, data: bytes) -> tuple[str, str]:
    """Grava (se ainda não existe) uma parte endereçada pelo conteúdo; devolve ``(rel, sha)``
    com ``rel`` relativo à pasta do snapshot."""
    sha = _sha(data)
    destino = raiz / "publico" / nome / chave / f"{sha}.csv.gz"
    if destino.exists():
        if sha256_file(destino) != sha:
            raise LivroErro(f"parte arquivada adulterada: {destino}")
    else:
        destino.parent.mkdir(parents=True, exist_ok=True)
        tmp = destino.with_suffix(f".tmp-{os.getpid()}")
        tmp.write_bytes(data)
        tmp.rename(destino)
    return f"../publico/{nome}/{chave}/{sha}.csv.gz", sha


def raiz_cobertura(book: Path) -> Path:
    return Path(book) / "cobertura"


def datas_snapshots(book: Path) -> list[date]:
    r = raiz_cobertura(book)
    if not r.exists():
        return []
    out = []
    for p in r.iterdir():
        if p.is_dir() and (p / "manifest.json").exists():
            try:
                out.append(date.fromisoformat(p.name))
            except ValueError:
                continue
    return sorted(out)


# ============================================================ livro encadeado

def _hash_evento(ev: dict[str, Any]) -> str:
    return sha256_obj({k: v for k, v in ev.items() if k != "event_hash"})


def eventos(book: Path) -> list[dict[str, Any]]:
    p = raiz_cobertura(book) / "livro.jsonl"
    if not p.exists():
        return []
    return [json.loads(x) for x in p.read_text(encoding="utf-8").splitlines() if x.strip()]


def verificar_livro(book: Path) -> tuple[bool, list[str]]:
    prev, problemas = GENESIS, []
    for i, ev in enumerate(eventos(book)):
        if ev.get("seq") != i:
            problemas.append(f"livro: sequência quebrada no evento {i}")
        if ev.get("prev_hash") != prev:
            problemas.append(f"livro: encadeamento quebrado no evento {i}")
        if _hash_evento(ev) != ev.get("event_hash"):
            problemas.append(f"livro: conteúdo adulterado no evento {i}")
        prev = ev.get("event_hash", "")
    return not problemas, problemas


def _selo(book: Path, d: date) -> dict[str, Any]:
    return json.loads((raiz_cobertura(book) / d.isoformat() / "selo.json").read_text(encoding="utf-8"))


def selado(book: Path) -> tuple[bool, str]:
    """O livro termina exatamente no selo do último snapshot (nenhum evento sem selo, nada
    truncado)."""
    evs = eventos(book)
    ds = datas_snapshots(book)
    if not ds:
        return (not evs), ("livro com eventos sem snapshot" if evs else "livro vazio")
    s = _selo(book, ds[-1])
    n = int(s.get("n_eventos", 0))
    if len(evs) > n:
        return False, f"livro com {len(evs) - n} evento(s) além do último selo ({ds[-1]})"
    if len(evs) < n:
        return False, f"livro com {n - len(evs)} evento(s) a menos que o último selo ({ds[-1]})"
    if n and evs[-1].get("event_hash") != s.get("livro_head"):
        return False, f"último evento do livro não confere com o selo de {ds[-1]}"
    return True, "livro selado"


def _tipo_evento(iid: str, tem_alvo: bool, rating: str, tp: float | None, ant: dict[str, Any] | None) -> str:
    if ant is None:
        return "INICIACAO"
    ant_tem = ant.get("alvo", {}).get("base") is not None and ant.get("rating") not in ("Em revisão", "Sem preço-alvo")
    agora_tem = tem_alvo and rating not in ("Em revisão", "Sem preço-alvo")
    if ant_tem and not agora_tem:
        return "SUSPENSAO"
    if not ant_tem and agora_tem:
        return "RETOMADA"
    if not agora_tem:
        return "REITERACAO"
    if ant.get("rating") != rating:
        return "MUDANCA_RATING"
    tp_ant = ant.get("alvo", {}).get("base")
    if tp is not None and tp_ant and abs(tp / tp_ant - 1) >= LIMIAR_REVISAO:
        return "REVISAO"
    return "REITERACAO"


def ultimo_evento_por_instrumento(book: Path, ate: date | None = None) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    for ev in eventos(book):
        if ate is not None and date.fromisoformat(ev["as_of"]) > ate:
            continue
        out[ev["issuer_id"]] = ev
    return out


# ============================================================ gravação do snapshot

def _git_head() -> dict[str, Any]:
    try:
        sha = subprocess.run(["git", "rev-parse", "HEAD"], capture_output=True, text=True, timeout=5,
                             check=False).stdout.strip() or None
    except Exception:  # pragma: no cover
        sha = None
    return {"git": sha}


def ambiente() -> dict[str, str]:
    import scipy

    return {"python": platform.python_version(), "numpy": np.__version__, "pandas": pd.__version__,
            "scipy": scipy.__version__}


def checar_data(book: Path, d: date) -> None:
    """Recusas que não dependem do cálculo (feitas antes dele): data já coberta ou anterior ao
    último snapshot, livro com falha de encadeamento."""
    existentes = datas_snapshots(book)
    if existentes and d <= existentes[-1]:
        raise LivroErro(f"Snapshot {d} recusado: já existe snapshot em {existentes[-1]} (sem retrodatar).")
    ok, probs = verificar_livro(book)
    if not ok:
        raise LivroErro("Livro da cobertura íntegro é pré-requisito: " + "; ".join(probs))


def reparar_pendencias(book: Path, audit: bool = True, agora: datetime | None = None) -> list[str]:
    """Completa uma gravação interrompida do snapshot mais recente (só nas condições exatas de
    interrupção, a partir dos arquivos selados): eventos do ``eventos.jsonl`` que não chegaram ao
    livro e o evento ``COVERAGE_SNAPSHOT`` que não chegou à trilha do fundo."""
    ds = datas_snapshots(book)
    if not ds:
        return []
    d = ds[-1]
    pasta = raiz_cobertura(book) / d.isoformat()
    feitos: list[str] = []
    try:
        snap = _ler(book, d)
    except (LivroErro, FileNotFoundError):
        return []
    selo = _selo(book, d)
    evs = eventos(book)
    ant = snap.manifest.get("livro_anterior") or {}
    rel = "eventos.jsonl"
    if len(evs) < int(selo["n_eventos"]) and rel in snap.manifest.get("arquivos", {}):
        b = (pasta / rel).read_bytes()
        pend = [json.loads(x) for x in b.decode("utf-8").splitlines() if x.strip()]
        head = evs[-1]["event_hash"] if evs else GENESIS
        if (_sha(b) == snap.manifest["arquivos"][rel] and len(evs) == int(ant.get("n_eventos", -1))
                and head == ant.get("head") and pend and pend[-1]["event_hash"] == selo["livro_head"]
                and len(evs) + len(pend) == int(selo["n_eventos"])):
            with open(raiz_cobertura(book) / "livro.jsonl", "a", encoding="utf-8") as f:
                for ev in pend:
                    f.write(_linha_evento(ev) + "\n")
            feitos.append(f"{d}: {len(pend)} evento(s) acrescentados ao livro a partir do snapshot selado")
    if audit and selado(book)[0]:
        trilha = AuditLog(Path(book) / "audit_log.jsonl")
        hashes = {e.payload_hash for e in trilha.events() if e.event_type == "COVERAGE_SNAPSHOT"}
        if sha256_obj(selo) not in hashes:
            trilha.append("COVERAGE_SNAPSHOT", "CDP", selo,
                          summary=f"Cobertura {d.isoformat()}: {selo['n_instrumentos']} instrumentos, "
                                  f"{selo['n_com_alvo']} com preço-alvo", ts=agora)
            feitos.append(f"{d}: evento COVERAGE_SNAPSHOT acrescentado à trilha do fundo")
    return feitos


def gravar_snapshot(book: Path, ex: Execucao, dados: DadosPublicos, params: ParametrosCobertura, *,
                    md_manifest: Any, config_paths: dict[str, Path], agora: datetime | None = None,
                    codigo: dict[str, Any] | None = None, audit: bool = True) -> dict[str, Any]:
    """Grava ``book/cobertura/<D>/``, acrescenta os eventos ao livro e o selo à trilha do fundo."""
    from .placar import calcular_placar

    raiz = raiz_cobertura(book)
    d = ex.as_of
    reparos = reparar_pendencias(book, audit, agora)
    checar_data(book, d)
    ok_s, msg_s = selado(book)
    if not ok_s:
        raise LivroErro(f"Livro da cobertura não confere com o último selo: {msg_s}.")
    for t in dados.tabelas().values():
        if "data_publicacao" in t.columns and not t.empty:
            dp = pd.to_datetime(t["data_publicacao"], errors="coerce")
            if (dp > pd.Timestamp(d)).any():
                raise LivroErro("Insumo com data de publicação posterior à data do snapshot.")
    destino = raiz / d.isoformat()
    tmp = raiz / f".{d.isoformat()}.tmp-{os.getpid()}"
    if destino.exists():
        raise LivroErro(f"Snapshot {d} já existe.")
    if tmp.exists():
        shutil.rmtree(tmp)
    tmp.mkdir(parents=True)
    arquivos: dict[str, str] = {}
    parcial = sorted(ex.emissores) != sorted(ex.pacotes)
    try:
        ids = ex.emissores
        for iid in ids:
            arquivos[f"modelos/{iid}.json"] = _escrever(tmp / "modelos" / f"{iid}.json",
                                                         _json_bytes(modelo_json(ex, iid, params), compacto=True))
        tab = pd.DataFrame([resumo_linha(ex, i) for i in ids])
        arquivos["modelos.csv"] = _escrever(tmp / "modelos.csv", csv_canonico(tab).encode("utf-8"))
        etf_rows = []
        for k in sorted(ex.etfs):
            e = arredondar(ex.etfs[k])
            e["is_synthetic"] = ex.is_synthetic
            e["aviso_dados"] = SIMULATED_DATA_NOTICE if ex.is_synthetic else AVISO_REAL
            arquivos[f"etfs/{k}.json"] = _escrever(tmp / "etfs" / f"{k}.json", _json_bytes(e, compacto=True))
            etf_rows.append({c: e.get(c) for c in ("iid", "ticker", "moeda", "preco", "preco_alvo", "upside",
                                                   "retorno_esperado", "r_bu", "r_td", "cobertura", "visao_ilf",
                                                   "metodo", "tem_alvo")})
        arquivos["etfs.csv"] = _escrever(tmp / "etfs.csv", csv_canonico(pd.DataFrame(etf_rows)).encode("utf-8"))
        for nome, t in sorted(dados.tabelas().items()):
            col = PARTICIONADAS.get(nome)
            if col and col in t.columns and not t.empty:
                for chave, parte in t.groupby(t[col].astype(str).map(_chave_parte), sort=True):
                    rel, sha = _gravar_parte(raiz, nome, chave, _gz(csv_canonico(parte).encode("utf-8")))
                    arquivos[rel] = sha
                continue
            arquivos[f"insumos/{nome}.csv.gz"] = _escrever(tmp / "insumos" / f"{nome}.csv.gz",
                                                            _gz(csv_canonico(t).encode("utf-8")))
        arquivos["insumos/emissores.json.gz"] = _escrever(tmp / "insumos" / "emissores.json.gz",
                                                           _gz(_json_bytes(arredondar(ex.pacotes))))
        arquivos["insumos/etfs.json.gz"] = _escrever(tmp / "insumos" / "etfs.json.gz",
                                                      _gz(_json_bytes(arredondar(ex.insumos_etf))))
        arquivos["contexto.json"] = _escrever(tmp / "contexto.json", _json_bytes(arredondar(ex.contexto)))
        for rel, src in sorted(config_paths.items()):
            if Path(src).exists():
                arquivos[f"configuracao/{rel}"] = _escrever(tmp / "configuracao" / rel, Path(src).read_bytes())
        # eventos do livro (um por instrumento): gravados na pasta selada e depois no livro
        anteriores = ultimo_evento_por_instrumento(book)
        evs_ant = eventos(book)
        seq0 = len(evs_ant)
        head0 = evs_ant[-1]["event_hash"] if seq0 else GENESIS
        prev = head0
        concluido = (agora or datetime.now(UTC)).isoformat()
        novos: list[dict[str, Any]] = []
        for iid in ids:
            m = ex.modelos[iid]
            r = m["resumo"]
            pac = ex.pacotes[iid]
            ant = anteriores.get(iid)
            tipo = _tipo_evento(iid, bool(m.get("tem_alvo")), str(r["rating"]), r["preco_alvo"], ant)
            ref = {"fechamento": r["preco"], "data": r["data_preco"], **(ex.referencias.get(iid) or {})}
            ev = arredondar({
                "schema": SCHEMA_EVENTO, "seq": seq0 + len(novos), "prev_hash": prev, "tipo": tipo,
                "issuer_id": iid, "linha": pac["linha"], "moeda": pac["moeda"], "pais": pac["pais"],
                "setor": pac["setor"], "parcial": parcial, "as_of": d.isoformat(), "concluido_em": concluido,
                "preco_ref": ref,
                "alvo": {"base": r["preco_alvo"], "otimista": r["alvo_otimista"], "pessimista": r["alvo_pessimista"],
                         "p_mercado_otimista": r["prob_mercado_otimista"],
                         "p_mercado_pessimista": r["prob_mercado_pessimista"]},
                "alvo_citavel": r.get("alvo_citavel"),
                "alvo_anterior": None if ant is None else {"base": ant.get("alvo", {}).get("base"), "seq": ant["seq"]},
                "vencimento": r["vencimento"], "ke": r["ke"], "etr": r["etr"], "pwr": r["pwr"], "alpha": r["alpha"],
                "alpha_rel": r["alpha_rel"], "incerteza": r["incerteza"], "rating": r["rating"],
                "rating_anterior": None if ant is None else ant.get("rating"), "confianca": r["confianca"],
                "metodos": [{"m": x["m"], "w": x["peso"], "v": x.get("valor"), "motivo": x.get("motivo")}
                            for x in m.get("metodos", [])],
                "ponte": (m.get("ponte") or {}).get("componentes"),
                "motivos": [(m.get("ponte") or {}).get("motivo")] if m.get("ponte") else [],
                "consenso": None if not r["consenso"] else {k: r["consenso"].get(k) for k in
                                                           ("alvo_medio", "alvo_mediano", "alvo_alto", "alvo_baixo",
                                                            "n_alvo", "recomendacao")},
                "modelo": {"arquivo": f"{d.isoformat()}/modelos/{iid}.json", "sha256": arquivos[f"modelos/{iid}.json"]},
                "portoes": {"falhas": [p["codigo"] for p in m.get("portoes", []) if p["status"] == "bloqueio"],
                            "avisos": [p["codigo"] for p in m.get("portoes", []) if p["status"] == "aviso"]},
                "is_synthetic": ex.is_synthetic,
            })
            ev["event_hash"] = _hash_evento(ev)
            prev = ev["event_hash"]
            novos.append(ev)
        for k in sorted(ex.etfs):
            e = ex.etfs[k]
            ant = anteriores.get(k)
            tipo = "INICIACAO" if ant is None else ("REVISAO" if (e.get("preco_alvo") and ant.get("alvo", {}).get("base")
                                                                   and abs(e["preco_alvo"] / ant["alvo"]["base"] - 1) >= LIMIAR_REVISAO)
                                                     else "REITERACAO")
            ev = arredondar({"schema": SCHEMA_EVENTO, "seq": seq0 + len(novos), "prev_hash": prev, "tipo": tipo,
                             "issuer_id": k, "linha": e["ticker"], "moeda": e["moeda"], "pais": e.get("pais"),
                             "parcial": parcial, "as_of": d.isoformat(),
                             "concluido_em": concluido, "preco_ref": {"fechamento": e.get("preco"), "data": e.get("data_preco")},
                             "alvo": {"base": e.get("preco_alvo"), "faixa_90": e.get("banda_90")},
                             "alvo_citavel": bool(e.get("tem_alvo") and e.get("visao_ilf") != "Em revisão"),
                             "retorno_esperado": e.get("retorno_esperado"), "visao_ilf": e.get("visao_ilf"),
                             "rating": e.get("visao_ilf"), "modelo": {"arquivo": f"{d.isoformat()}/etfs/{k}.json",
                                                                     "sha256": arquivos[f"etfs/{k}.json"]},
                             "is_synthetic": ex.is_synthetic})
            ev["event_hash"] = _hash_evento(ev)
            prev = ev["event_hash"]
            novos.append(ev)
        if not parcial:
            for iid in sorted(anteriores):
                a = anteriores[iid]
                if iid.startswith("ETF_") or iid in ex.pacotes or a.get("tipo") == "ENCERRAMENTO":
                    continue
                ev = arredondar({"schema": SCHEMA_EVENTO, "seq": seq0 + len(novos), "prev_hash": prev,
                                 "tipo": "ENCERRAMENTO", "issuer_id": iid, "linha": a.get("linha"),
                                 "moeda": a.get("moeda"), "pais": a.get("pais"), "setor": a.get("setor"),
                                 "parcial": parcial, "as_of": d.isoformat(), "concluido_em": concluido,
                                 "preco_ref": None, "alvo": {"base": None}, "rating": "Encerrada",
                                 "rating_anterior": a.get("rating"),
                                 "alvo_anterior": {"base": (a.get("alvo") or {}).get("base"), "seq": a["seq"]},
                                 "motivo": "emissor fora do universo coberto", "is_synthetic": ex.is_synthetic})
                ev["event_hash"] = _hash_evento(ev)
                prev = ev["event_hash"]
                novos.append(ev)
        arquivos["eventos.jsonl"] = _escrever(tmp / "eventos.jsonl",
                                              "".join(_linha_evento(ev) + "\n" for ev in novos).encode("utf-8"))
        placar = calcular_placar(evs_ant + novos, None, d)
        arquivos["placar.json"] = _escrever(tmp / "placar.json", _json_bytes(arredondar(placar)))
        n_alvo = sum(1 for i in ids if ex.modelos[i].get("tem_alvo"))
        manifest = arredondar({
            "schema": SCHEMA_MANIFESTO, "as_of": d.isoformat(), "parcial": parcial,
            "emissores": ids, "prices_as_of": md_manifest.as_of.isoformat(),
            "base_mercado": {"snapshot_id": md_manifest.snapshot_id, "content_hash": md_manifest.content_hash()},
            "configuracao": {"versao": params.versao, "arquivos": params.arquivos, "hash": params.hash()},
            "codigo": codigo if codigo is not None else _git_head(), "ambiente": ambiente(),
            "taxa_livre_risco": ex.rf, "origem_dados": dados.origem,
            "arquivos": dict(sorted(arquivos.items())), "is_synthetic": ex.is_synthetic,
            "data_notice": SIMULATED_DATA_NOTICE if ex.is_synthetic else AVISO_REAL,
            "contagens": {"emissores": len(ids), "com_alvo": n_alvo, "etfs": len(ex.etfs),
                          "por_rating": ex.distribuicao.get("distribuicao"),
                          "alertas_distribuicao": ex.distribuicao.get("alertas_distribuicao")},
            "livro_anterior": {"n_eventos": seq0, "head": head0},
            "reparos": reparos,
        })
        msha = _escrever(tmp / "manifest.json", _json_bytes(manifest))
        selo = {"as_of": d.isoformat(), "manifest_sha256": msha, "livro_head": prev,
                "n_eventos": seq0 + len(novos), "n_instrumentos": len(ids) + len(ex.etfs), "n_com_alvo": n_alvo,
                "is_synthetic": ex.is_synthetic}
        _escrever(tmp / "selo.json", _json_bytes(selo))
        tmp.rename(destino)
    except Exception:
        shutil.rmtree(tmp, ignore_errors=True)
        raise
    with open(raiz / "livro.jsonl", "a", encoding="utf-8") as f:
        for ev in novos:
            f.write(_linha_evento(ev) + "\n")
    if audit:
        AuditLog(Path(book) / "audit_log.jsonl").append(
            "COVERAGE_SNAPSHOT", "CDP", selo,
            summary=f"Cobertura {d.isoformat()}: {selo['n_instrumentos']} instrumentos, {n_alvo} com preço-alvo",
            ts=agora)
    return {"pasta": str(destino), "manifest_sha256": msha, "selo": selo, "n_eventos": len(novos),
            "reparos": reparos}


# ============================================================ leitura

def _mascarar(t: pd.DataFrame) -> pd.DataFrame:
    if t.empty or "rating" not in t.columns:
        return t
    t = t.copy()
    sem = ~t["rating"].isin(RATINGS_CITAVEIS)
    for c in COLUNAS_MASCARADAS:
        if c in t.columns:
            t[c] = t[c].astype(float).where(~sem)
    t["alvo_citavel"] = ~sem & t["preco_alvo"].notna() if "preco_alvo" in t.columns else ~sem
    return t


@dataclass(frozen=True)
class SnapshotCobertura:
    """Snapshot semanal (ou parcial) da cobertura, lido e conferido do livro.

    ``as_of``: data do snapshot; ``pasta``: ``book/cobertura/<as_of>``; ``manifest``: conteúdo de
    ``manifest.json``; ``manifest_sha256``: hash do arquivo, conferido contra ``selo.json`` (o
    payload do evento ``COVERAGE_SNAPSHOT``). Tabelas e modelos são carregados sob demanda e cada
    arquivo lido é conferido contra o hash do manifesto (adulteração ⇒ ``LivroErro``).

    ``tabela()``/``estado()`` mascaram, por padrão, o preço-alvo e os retornos derivados dos
    emissores sem rating citável ("Em revisão", "Sem preço-alvo"): esses números existem no modelo
    aberto para auditoria, mas não são publicados nem citados."""

    as_of: date
    pasta: Path
    manifest: dict[str, Any] = field(default_factory=dict)
    manifest_sha256: str = ""
    is_synthetic: bool = False

    def _bytes(self, rel: str) -> bytes | None:
        p = self.pasta / rel
        if not p.exists():
            return None
        sha = (self.manifest.get("arquivos") or {}).get(rel)
        b = p.read_bytes()
        if sha is None or _sha(b) != sha:
            raise LivroErro(f"{self.as_of}: {rel} não confere com o manifesto do snapshot")
        return b

    def _json(self, rel: str) -> dict[str, Any] | None:
        b = self._bytes(rel)
        return None if b is None else json.loads(b.decode("utf-8"))

    def tabela(self, mascarar: bool = True) -> pd.DataFrame:
        """``modelos.csv`` deste snapshot (índice ``issuer_id``)."""
        t = pd.read_csv(io.BytesIO(self._bytes("modelos.csv") or b"issuer_id\n")).set_index("issuer_id")
        return _mascarar(t) if mascarar else t

    def modelo(self, issuer_id: str) -> dict[str, Any] | None:
        return self._json(f"modelos/{issuer_id}.json")

    def etfs(self) -> pd.DataFrame:
        b = self._bytes("etfs.csv")
        return pd.read_csv(io.BytesIO(b)).set_index("iid") if b else pd.DataFrame()

    def etf(self, iid: str) -> dict[str, Any] | None:
        return self._json(f"etfs/{iid}.json")

    def placar(self) -> dict[str, Any]:
        return self._json("placar.json") or {}

    def estado(self, mascarar: bool = True) -> pd.DataFrame:
        """Tabela consolidada até ``as_of``: para cada emissor, a linha do snapshot mais recente
        que o cobriu (snapshots parciais só substituem os emissores que reavaliaram); emissores
        cujo último evento até a data é ``ENCERRAMENTO`` saem da tabela."""
        book = self.pasta.parent.parent
        partes = []
        for d in datas_snapshots(book):
            if d > self.as_of:
                break
            snap = self if d == self.as_of else _ler(book, d)
            t = snap.tabela(mascarar=False).reset_index()
            t["snapshot"] = d.isoformat()
            partes.append(t)
        if not partes:
            return pd.DataFrame()
        tudo = pd.concat(partes, ignore_index=True)
        out = tudo.drop_duplicates("issuer_id", keep="last").set_index("issuer_id").sort_index()
        encerrados = [i for i, ev in ultimo_evento_por_instrumento(book, self.as_of).items()
                      if ev.get("tipo") == "ENCERRAMENTO"]
        out = out.drop(index=[i for i in encerrados if i in out.index])
        return _mascarar(out) if mascarar else out


def _ler(book: Path, d: date) -> SnapshotCobertura:
    pasta = raiz_cobertura(book) / d.isoformat()
    msha = sha256_file(pasta / "manifest.json")
    selo = json.loads((pasta / "selo.json").read_text(encoding="utf-8"))
    if selo.get("manifest_sha256") != msha:
        raise LivroErro(f"Manifesto do snapshot {d} não confere com o selo.")
    man = json.loads((pasta / "manifest.json").read_text(encoding="utf-8"))
    return SnapshotCobertura(as_of=d, pasta=pasta, manifest=man, manifest_sha256=msha,
                             is_synthetic=bool(man.get("is_synthetic")))


def ultimo_snapshot(root: Path, ate: date) -> SnapshotCobertura | None:
    """Último snapshot com ``as_of <= ate`` sob ``root`` (a pasta ``book``), com manifesto,
    cadeia e selo conferidos; ``None`` se não há snapshot até a data (nunca um posterior)."""
    ok, probs = verificar_livro(Path(root))
    if not ok:
        raise LivroErro("; ".join(probs))
    ok_s, msg = selado(Path(root))
    if not ok_s:
        raise LivroErro(msg)
    ds = [d for d in datas_snapshots(Path(root)) if d <= ate]
    return _ler(Path(root), ds[-1]) if ds else None


def snapshot(root: Path, d: date) -> SnapshotCobertura:
    return _ler(Path(root), d)


# ============================================================ verificação completa

def verificar(book: Path, params_por_snapshot: bool = True, recalcular: bool = True,
              tolerancia: float = 1e-6, completo_todos: bool = True) -> tuple[bool, list[str]]:
    """Confere o livro, cada manifesto/selo/arquivo, a correspondência com a trilha do fundo, o
    placar e (``recalcular``) refaz cada snapshot por completo a partir dos insumos arquivados
    (``completo_todos=False``: só o mais recente por completo; dos anteriores, o preço-alvo do
    caso-base)."""
    from .placar import calcular_placar

    book = Path(book)
    ok, probs = verificar_livro(book)
    msgs: list[str] = [] if ok else list(probs)
    evs = eventos(book)
    ds = datas_snapshots(book)
    trilha_log = AuditLog(book / "audit_log.jsonl")
    trilha = trilha_log.events() if (book / "audit_log.jsonl").exists() else []
    if trilha:
        ok_t, msg_t = trilha_log.verify_chain()
        if not ok_t:
            msgs.append(f"trilha do fundo: {msg_t}")
    cov = [e for e in trilha if e.event_type == "COVERAGE_SNAPSHOT"]
    if ds and not cov:
        msgs.append("trilha do fundo sem eventos COVERAGE_SNAPSHOT para os snapshots existentes")
    hashes_selos: dict[str, date] = {}
    n_prev, head_prev = 0, GENESIS
    for d in ds:
        pasta = raiz_cobertura(book) / d.isoformat()
        try:
            snap = _ler(book, d)
        except (LivroErro, FileNotFoundError) as exc:
            msgs.append(str(exc))
            continue
        selo = json.loads((pasta / "selo.json").read_text(encoding="utf-8"))
        hashes_selos[sha256_obj(selo)] = d
        for rel, sha in snap.manifest.get("arquivos", {}).items():
            p = pasta / rel
            if not p.exists():
                msgs.append(f"{d}: arquivo ausente {rel}")
            elif sha256_file(p) != sha:
                msgs.append(f"{d}: arquivo adulterado {rel}")
        ant = snap.manifest.get("livro_anterior") or {}
        if int(ant.get("n_eventos", -1)) != n_prev or ant.get("head") != head_prev:
            msgs.append(f"{d}: snapshot não continua o selo anterior (livro_anterior)")
        head = selo.get("livro_head")
        n = int(selo.get("n_eventos", 0))
        if n > len(evs) or (n and evs[n - 1]["event_hash"] != head):
            msgs.append(f"{d}: selo não confere com o livro (head/n_eventos)")
        elif (pasta / "eventos.jsonl").exists():
            proprios = [json.loads(x) for x in (pasta / "eventos.jsonl").read_text(encoding="utf-8").splitlines()
                        if x.strip()]
            if proprios != evs[int(ant.get("n_eventos", 0)):n]:
                msgs.append(f"{d}: eventos do snapshot não conferem com o livro")
        pl = calcular_placar(evs[:n], None, d)
        b_pl = (pasta / "placar.json").read_bytes() if (pasta / "placar.json").exists() else b"{}"
        if sha256_obj(arredondar(pl)) != sha256_obj(json.loads(b_pl)):
            msgs.append(f"{d}: placar.json não confere com o recálculo")
        n_prev, head_prev = n, head
        if recalcular:
            completo = completo_todos or d == ds[-1]
            try:
                msgs.extend(recalcular_snapshot(snap, tolerancia, completo=completo))
            except Exception as exc:  # noqa: BLE001 - qualquer falha de recálculo é divergência
                msgs.append(f"{d}: recálculo falhou ({type(exc).__name__}: {exc})")
    # livro termina exatamente no último selo
    if ds:
        ok_s, msg_s = selado(book)
        if not ok_s:
            msgs.append(f"livro: {msg_s}")
    elif evs:
        msgs.append("livro: eventos sem nenhum snapshot")
    # correspondência um a um entre selos e eventos da trilha do fundo
    vistos: dict[str, int] = {}
    for e in cov:
        vistos[e.payload_hash] = vistos.get(e.payload_hash, 0) + 1
        if e.payload_hash not in hashes_selos:
            msgs.append(f"trilha do fundo: evento COVERAGE_SNAPSHOT seq {e.seq} sem snapshot correspondente "
                        f"({e.summary})")
    for h, d in hashes_selos.items():
        if cov and h not in vistos:
            msgs.append(f"{d}: selo sem evento COVERAGE_SNAPSHOT correspondente na trilha do fundo")
        elif vistos.get(h, 0) > 1:
            msgs.append(f"{d}: selo registrado mais de uma vez na trilha do fundo")
    ok_final = not msgs
    return ok_final, msgs or ["Cobertura íntegra: livro, manifestos, arquivos, trilha, placar e modelos conferidos."]


def _rel(a: float | None, b: float | None, tol: float) -> bool:
    if a is None or b is None:
        return a is None and b is None
    if a == b:
        return True
    return abs(a - b) <= tol * max(abs(a), abs(b), 1e-12)


def recalcular_snapshot(snap: SnapshotCobertura, tolerancia: float = 1e-6, completo: bool = True) -> list[str]:
    """Refaz o snapshot a partir dos insumos e da configuração arquivados.

    ``completo``: contexto transversal (contra ``contexto.json``), custo de capital, métodos,
    cenários com semente, PWR, α, α relativo, confiança, rating e ETFs, comparados com os valores
    publicados (tolerância relativa de 1e-5: armazenamento a 6 algarismos significativos). Sem
    ``completo``: só o preço-alvo do caso-base. Falha num emissor vira divergência daquele emissor."""
    from .contexto import montar_contexto
    from .etf import calcular_etfs
    from .motor import arredondar as _arr
    from .motor import modelar, tp_deterministico
    from .parametros import carregar_parametros

    pasta = snap.pasta
    cfg = pasta / "configuracao"
    if not (cfg / "valuation.yaml").exists():
        return [f"{snap.as_of}: configuração arquivada ausente"]
    tol = max(tolerancia, 1e-5)
    params = carregar_parametros(cfg / "valuation.yaml", cfg / "cobertura")
    pacs = ler_pacotes(pasta, snap.manifest)
    ctx_arq = snap._json("contexto.json") or {}
    rf_info = snap.manifest.get("taxa_livre_risco") or {}
    rf = rf_info.get("valor")
    msgs: list[str] = []
    publicados = {iid: snap.modelo(iid) or {} for iid in snap.manifest.get("emissores", [])}
    if not completo:
        for iid, mod in publicados.items():
            tp_ok = (mod.get("resumo") or {}).get("preco_alvo")
            try:
                tp = tp_deterministico(pacs[iid], ctx_arq, params, rf)
            except Exception as exc:  # noqa: BLE001
                msgs.append(f"{snap.as_of}: {iid} recálculo falhou ({type(exc).__name__})")
                continue
            if not _rel(tp, tp_ok, tol):
                msgs.append(f"{snap.as_of}: {iid} preço-alvo recalculado {tp} ≠ {tp_ok}")
        return msgs
    ctx = montar_contexto(pacs, params)
    if sha256_obj(_arr(ctx)) != sha256_obj(ctx_arq):
        msgs.append(f"{snap.as_of}: contexto transversal recalculado não confere com contexto.json")
    anterior = carregar_anterior(pasta.parent.parent, snap.as_of, excluir=snap.as_of)
    modelos, _, _ = modelar(pacs, ctx_arq, params, rf, rf_info.get("fonte") or {}, anterior,
                            list(snap.manifest.get("emissores", [])))
    campos = ("preco_alvo", "upside", "etr", "pwr", "ke", "wacc", "alpha", "alpha_rel", "alvo_otimista",
              "alvo_pessimista")
    for iid, pub in publicados.items():
        r = pub.get("resumo") or {}
        m = modelos[iid]
        novo = {"preco_alvo": m.get("tp"), "upside": m.get("upside"), "etr": m.get("etr"), "pwr": m.get("pwr"),
                "ke": (m.get("custo_capital") or {}).get("ke"), "wacc": (m.get("custo_capital") or {}).get("wacc"),
                "alpha": m.get("alpha"), "alpha_rel": m.get("alpha_rel"), "alvo_otimista": m.get("tp_otimista"),
                "alvo_pessimista": m.get("tp_pessimista")}
        for c in campos:
            a, b = r.get(c), novo[c]
            b = None if b is None else float(_arr(float(b)))
            if not _rel(b, a, tol):
                msgs.append(f"{snap.as_of}: {iid} {c} recalculado {b} ≠ {a}")
        for c in ("rating", "confianca", "incerteza"):
            if r.get(c) != m.get(c):
                msgs.append(f"{snap.as_of}: {iid} {c} recalculado {m.get(c)} ≠ {r.get(c)}")
    ins_etf_rel = "insumos/etfs.json.gz"
    if ins_etf_rel in snap.manifest.get("arquivos", {}):
        ins_etf = ler_pacotes(pasta, snap.manifest, "etfs")
        etfs = calcular_etfs(ins_etf, params, pacs, modelos, rf)
        for k, e in etfs.items():
            pub = snap.etf(k) or {}
            for c in ("preco_alvo", "retorno_esperado", "r_bu", "r_td"):
                b = e.get(c)
                if not _rel(None if b is None else float(_arr(float(b))), pub.get(c), tol):
                    msgs.append(f"{snap.as_of}: {k} {c} recalculado {b} ≠ {pub.get(c)}")
            if e.get("visao_ilf") != pub.get("visao_ilf"):
                msgs.append(f"{snap.as_of}: {k} visão recalculada {e.get('visao_ilf')} ≠ {pub.get('visao_ilf')}")
    return msgs


def carregar_anterior(book: Path, ate: date, excluir: date | None = None):
    """Estado anterior até ``ate`` (exclusive de ``excluir``): ratings, alvos, α publicados,
    pacotes/contexto/rf do snapshot de origem de cada emissor, último snapshot completo e o último
    evento de cada emissor (referências de preço do placar)."""
    from .motor import Anterior

    book = Path(book)
    limite = ate
    todos = eventos(book)
    ds = datas_snapshots(book)
    if ds:  # só eventos selados alimentam a execução seguinte
        todos = todos[: int(_selo(book, ds[-1]).get("n_eventos", 0))]
    evs = [e for e in todos if date.fromisoformat(e["as_of"]) <= limite
           and (excluir is None or date.fromisoformat(e["as_of"]) < excluir)]
    ult: dict[str, dict[str, Any]] = {}
    for e in evs:
        ult[e["issuer_id"]] = e
    ant = Anterior()
    cache: dict[str, tuple[dict[str, Any], dict[str, Any], float | None]] = {}
    for iid, ev in ult.items():
        if ev.get("rating") is not None:
            ant.ratings[iid] = str(ev["rating"])
        ant.alphas[iid] = None if ev.get("rating") not in RATINGS_CITAVEIS else ev.get("alpha")
        base = (ev.get("alvo") or {}).get("base")
        if base is not None and not iid.startswith("ETF_"):
            ant.alvos[iid] = float(base)
        if ev.get("tipo") != "ENCERRAMENTO" and (ev.get("preco_ref") or {}).get("fechamento") is not None:
            ant.eventos[iid] = {"as_of": ev["as_of"], "linha": ev.get("linha"),
                                "fechamento": ev["preco_ref"]["fechamento"]}
        d = ev["as_of"]
        if d not in cache:
            pasta = raiz_cobertura(book) / d
            try:
                pacs = ler_pacotes(pasta)
                ctx = json.loads((pasta / "contexto.json").read_text(encoding="utf-8"))
                man = json.loads((pasta / "manifest.json").read_text(encoding="utf-8"))
                cache[d] = (pacs, ctx, (man.get("taxa_livre_risco") or {}).get("valor"))
            except FileNotFoundError:
                cache[d] = ({}, {}, None)
        pacs, ctx, rf = cache[d]
        if iid in pacs:
            ant.estado[iid] = (pacs[iid], ctx, rf)
    completas = [e for e in evs if not e.get("parcial")]
    if completas:
        dc = max(e["as_of"] for e in completas)
        ant.data_completa = date.fromisoformat(dc)
        ant.linhas_completa = {e["issuer_id"]: e.get("linha") for e in completas if e["as_of"] == dc}
    return ant


__all__ = ["COLUNAS_MASCARADAS", "LivroErro", "RATINGS_CITAVEIS", "SnapshotCobertura", "TIPOS_EVENTO", "ambiente",
           "carregar_anterior", "checar_data", "datas_snapshots", "eventos", "gravar_snapshot", "ler_pacotes",
           "ler_tabela", "raiz_cobertura", "recalcular_snapshot", "reparar_pendencias", "selado", "snapshot",
           "ultimo_evento_por_instrumento", "ultimo_snapshot", "verificar", "verificar_livro"]
