"""Mapa documental portátil de um snapshot CDP; não executa modelos financeiros.

Derivação revisável do mapa histórico não autor de 09/10/2026.
Entradas e destino são explícitos; nenhum caminho pessoal ou pacote privado é exigido.
"""

from __future__ import annotations

import argparse
import csv
import gzip
import hashlib
import json
import os
import sys
from collections import Counter, defaultdict
from decimal import Decimal, localcontext
from pathlib import Path

import yaml


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def invalid_constant(value):
    raise ValueError("Constante JSON não finita: " + value)


def load(path: Path):
    data = path.read_bytes()
    if path.suffix == ".gz":
        data = gzip.decompress(data)
    return json.loads(data, parse_float=Decimal, parse_constant=invalid_constant)


def serial(value):
    if isinstance(value, Decimal):
        return str(value)
    raise TypeError(type(value).__name__)


def write_json(output: Path, name: str, value) -> None:
    (output / name).write_text(
        json.dumps(value, ensure_ascii=False, indent=2, default=serial, allow_nan=False) + "\n"
    )


def write_csv(output: Path, name: str, rows: list[dict]) -> None:
    fields = list(dict.fromkeys(k for row in rows for k in row))
    with (output / name).open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        for row in rows:
            writer.writerow(
                {
                    k: json.dumps(v, ensure_ascii=False, default=serial)
                    if isinstance(v, (dict, list))
                    else v
                    for k, v in row.items()
                }
            )


def confined(root: Path, path: Path) -> Path:
    resolved = path.resolve()
    if not resolved.is_relative_to(root):
        raise ValueError("Arquivo escapou da raiz documental")
    if path.is_symlink() or not path.is_file():
        raise ValueError("Arquivo documental ausente ou link")
    return resolved


def percent(count: int, total: int) -> str | None:
    if not total:
        return None
    with localcontext() as ctx:
        ctx.prec = 80
        return str((Decimal(count) * 100 / Decimal(total)).quantize(Decimal(".000001")))


def support(entry: dict) -> str:
    if entry.get("valor") is None:
        return "missing_data"
    if entry.get("fonte") == "CODIGO":
        return "derived_calculation_or_policy"
    if "consenso" in str(entry.get("documento", "")).lower() or entry["id"].startswith(
        ("eps_fy", "g_receita_fy")
    ):
        return "estimate_consensus"
    if entry.get("fonte") == "YAHOO":
        return "fact_provider_standardized"
    if entry.get("fonte") in ("CVM", "SEC", "RI"):
        return "fact_source_reported_declared_not_retied_here"
    return "public_reference_or_policy_transcription"


def build(
    snapshot: Path,
    root: Path,
    universe: Path,
    registry: Path,
    source: Path,
    priorities: Path,
    commit: str,
    repo_url: str,
) -> dict:
    snapshot, root, source = snapshot.resolve(), root.resolve(), source.resolve()
    confined(root, snapshot / "manifest.json")
    manifest = load(snapshot / "manifest.json")
    checks = []
    for relative, expected in sorted(manifest["arquivos"].items()):
        path = confined(root, snapshot / relative)
        digest = sha(path)
        if digest != expected:
            raise ValueError("SHA divergente no manifesto: " + relative)
        checks.append({"arquivo_manifesto": relative, "sha256": digest})
    def checked_file(relative: str) -> Path:
        if relative not in manifest["arquivos"]:
            raise ValueError("Arquivo consumido não manifestado: " + relative)
        path = confined(root, snapshot / relative)
        if sha(path) != manifest["arquivos"][relative]:
            raise ValueError("SHA divergente no manifesto: " + relative)
        return path

    packages = load(checked_file("insumos/emissores.json.gz"))
    etf_inputs = load(checked_file("insumos/etfs.json.gz"))
    models = {
        p.stem: load(checked_file("modelos/" + p.name))
        for p in sorted((snapshot / "modelos").glob("*.json"))
    }
    etfs = {
        p.stem: load(checked_file("etfs/" + p.name))
        for p in sorted((snapshot / "etfs").glob("*.json"))
    }
    with universe.open(newline="", encoding="utf-8") as stream:
        listed = list(csv.DictReader(stream))
    lines = defaultdict(list)
    for row in listed:
        lines[row["issuer_id"]].append(row)
    if set(models) != set(packages) or set(models) != set(lines):
        raise ValueError("Universo/modelos/pacotes têm identidades divergentes")
    if set(etfs) != set(etf_inputs):
        raise ValueError("ETFs/modelos/pacotes têm identidades divergentes")
    valuation = yaml.safe_load(checked_file("configuracao/valuation.yaml").read_text())
    records = [json.loads(line) for line in registry.read_text().splitlines() if line]
    raw_hashes = defaultdict(list)
    for row in records:
        raw_hashes[row["sha256"]].append(row)
    config_hashes = {value: key for key, value in manifest["configuracao"]["arquivos"].items()}
    baseurl = repo_url.rstrip("/") + "/blob/" + commit + "/"
    snapshot_git = "book/cobertura/" + manifest["as_of"] + "/"
    companies, methods, gates, ledger = [], [], [], []
    for iid, model in models.items():
        p, summary = packages[iid], model["resumo"]
        relative = snapshot_git + "modelos/" + iid + ".json"
        available = []
        for family, weight in valuation["pesos_metodos"][p["arquetipo"]].items():
            step = next((s for s in model["passos"] if s["id"] == "metodo." + family), None)
            used = (
                step is not None and step.get("resultado") is not None and bool(step.get("formula"))
            )
            if used:
                available.append(family)
            methods.append(
                {
                    "issuer_id": iid,
                    "metodo": family,
                    "peso_configurado": weight,
                    "peso_final": None,
                    "disponivel_na_memoria": used,
                    "resultado_publicado": step.get("resultado") if step else None,
                    "formula": step.get("formula") if step else None,
                    "motivo_na_memoria": (step.get("resultado_texto") or step.get("substituicao"))
                    if step and not used
                    else None,
                }
            )
        for gate in model["portoes"]:
            gates.append(
                {
                    "issuer_id": iid,
                    **gate,
                    "alcance": "estado de cobertura recebido; não gate operacional universal",
                }
            )
        absent, unknown, no_hash = [], [], []
        for entry in model["insumos"]:
            if entry.get("valor") is None:
                absent.append(entry["id"])
            if entry.get("valor") is not None and entry.get("fonte") != "CODIGO":
                if entry.get("data_publicacao") is None:
                    unknown.append(entry["id"])
                if not entry.get("sha256"):
                    no_hash.append(entry["id"])
            digest = entry.get("sha256")
            domain = (
                "configuração/transcrição"
                if digest in config_hashes
                else "hash declarado com registro de bruto público"
                if digest in raw_hashes
                else "não informado"
                if not digest
                else "hash declarado sem domínio vinculado"
            )
            ledger.append(
                {
                    "issuer_id": iid,
                    "insumo": entry["id"],
                    "valor": entry.get("valor"),
                    "unidade": entry.get("unidade"),
                    "periodo": entry.get("periodo"),
                    "fonte": entry.get("fonte"),
                    "url": entry.get("url"),
                    "documento": entry.get("documento"),
                    "sha256_declarado": digest,
                    "dominio_hash": domain,
                    "config_ref": config_hashes.get(digest),
                    "data_coleta_declarada": entry.get("data_coleta"),
                    "data_publicacao_declarada": entry.get("data_publicacao"),
                    "data_estimada": entry.get("data_estimada"),
                    "support_label": support(entry),
                    "tie_out_primario": "not_tested_primary",
                    "registro_bruto_presente": digest in raw_hashes,
                    "modelo": relative,
                }
            )
        blocked = [g["codigo"] for g in model["portoes"] if g["status"] in ("bloqueio", "sem_alvo")]
        warned = [g["codigo"] for g in model["portoes"] if g["status"] == "aviso"]
        grid = (model.get("sensibilidade") or {}).get("preco_alvo")
        shocks = (model.get("sensibilidade") or {}).get("choques_colunas")
        flat = None
        if (
            grid
            and shocks
            and len(set(shocks)) >= 2
            and all(row and all(v is not None for v in row) for row in grid)
        ):
            flat = all(len(set(row)) == 1 for row in grid)
        companies.append(
            {
                "id": iid,
                "nome": model["nome"],
                "pais": model["pais"],
                "setor": model.get("setor"),
                "arquetipo": model["arquetipo"],
                "linhas_universo": lines[iid],
                "linha_modelo": model["linha"],
                "moeda_modelo": model["moeda"],
                "as_of": model["as_of"],
                "rating": summary.get("rating"),
                "confianca": summary.get("confianca"),
                "alvo_citavel": summary.get("alvo_citavel"),
                "preco_alvo_snapshot": summary.get("preco_alvo"),
                "metodos_disponiveis": available,
                "portoes_bloqueantes": blocked,
                "avisos_portoes": warned,
                "pit_ok_declarado": p.get("pit_ok"),
                "datas_estimadas": p.get("datas_estimadas"),
                "moeda_demonstrativos_declarada": p.get("moeda_demonstrativos"),
                "moeda_consenso_original": (p.get("consenso") or {}).get("moeda_lpa"),
                "insumos_ausentes": absent,
                "publicacoes_desconhecidas": unknown,
                "hashes_ausentes": no_hash,
                "sensibilidade_colunas_invariantes": flat,
                "lacunas": model.get("lacunas"),
                "sha256_modelo": sha(checked_file("modelos/" + iid + ".json")),
                "github": baseurl + relative,
                "adequacao_economica": "não certificada por este inventário",
            }
        )
    etf_rows, indices, positions = [], [], []
    for iid, model in etfs.items():
        ins = etf_inputs[iid]
        relative = snapshot_git + "etfs/" + iid + ".json"
        declared_index = ins.get("fonte_indice") or {}
        etf_rows.append(
            {
                "id": iid,
                "ticker": model["ticker"],
                "nome": model.get("nome"),
                "indice": model.get("indice"),
                "pais": model["pais"],
                "moeda": model["moeda"],
                "as_of": model["as_of"],
                "tem_alvo": model.get("tem_alvo"),
                "preco_alvo_snapshot": model.get("preco_alvo"),
                "r_td": model.get("r_td"),
                "r_bu": model.get("r_bu"),
                "cobertura_bu": model.get("cobertura"),
                "composicao_aproximada": model.get("composicao_aproximada"),
                "fonte_composicao_declarada": model.get("fonte_composicao"),
                "portoes": model.get("portoes"),
                "lacunas": model.get("lacunas"),
                "sha256_modelo": sha(snapshot / "etfs" / (iid + ".json")),
                "github": baseurl + relative,
                "limite": "Modelo na cota do ETF; composição parcial e imputações não certificam índice em pontos",
            }
        )
        indices.append(
            {
                "id": "INDICE_" + iid,
                "indice": model.get("indice"),
                "proxy": iid,
                "modelo_independente_pontos": False,
                "fonte_indice_declarada": declared_index,
                "dominio_hash_indice": "configuração/transcrição"
                if declared_index.get("sha256") in config_hashes
                else "não vinculado",
                "documento_primario_indice_confirmado": None,
                "limite": "Configuração e página do ETF não autenticam documento primário do provedor do índice",
                "github": baseurl + relative,
            }
        )
        for row in model.get("posicoes") or []:
            p = packages.get(row.get("issuer_id")) or {}
            positions.append(
                {
                    "etf": iid,
                    **row,
                    "moeda_linha_filho": p.get("moeda"),
                    "moeda_consenso_original": (p.get("consenso") or {}).get("moeda_lpa"),
                    "moeda_demonstrativos_declarada": p.get("moeda_demonstrativos"),
                    "eps_fy1": p.get("eps_fy1"),
                    "eps_fy2": p.get("eps_fy2"),
                    "coerencia_economica": "não inferida pela contagem ou pelo país",
                }
            )
    ratings = Counter(x["rating"] for x in companies)
    confidence = Counter(x["confianca"] for x in companies)
    citables = [x for x in companies if x["alvo_citavel"]]
    citable_ratings = Counter(x["rating"] for x in citables)
    summary = {
        "empresas": len(companies),
        "linhas": len(listed),
        "etfs": len(etf_rows),
        "indices_proxy": len(indices),
        "modelos_financeiros": len(companies) + len(etf_rows),
        "vistas_mapa": len(companies) + len(etf_rows) + len(indices),
        "ratings": ratings,
        "confiancas": confidence,
        "citaveis": len(citables),
        "ratings_citaveis": citable_ratings,
        "percentual_compra_citavel": percent(citable_ratings["Compra"], len(citables)),
        "percentual_venda_citavel": percent(citable_ratings["Venda"], len(citables)),
        "percentual_confianca_c": percent(confidence["C"], len(companies)),
        "percentual_em_revisao": percent(ratings["Em revisão"], len(companies)),
        "sem_alvo": [x["id"] for x in companies if x["preco_alvo_snapshot"] is None],
        "sensibilidade_colunas_invariantes": [
            x["id"] for x in companies if x["sensibilidade_colunas_invariantes"]
        ],
        "n_manifesto_hashes_conferidos": len(checks),
        "valor_financeiro_recalculado": False,
    }
    source_hashes = {
        p.relative_to(source).as_posix(): sha(p) for p in sorted(source.rglob("*")) if p.is_file()
    }
    meta = {
        "schema": "cdp.auditoria.mapa_publico/v1",
        "as_of": manifest["as_of"],
        "commit_snapshot": commit,
        "codigo_gerador_declarado": manifest["codigo"]["git"],
        "manifesto_sha256": sha(snapshot / "manifest.json"),
        "universo_sha256": sha(universe),
        "indice_publico_sha256": sha(registry),
        "prioridades_historicas_sha256": sha(priorities),
        "fonte_geradora_arquivos_sha256": source_hashes,
        "fonte_commit_vinculo": "Commit declarado pelo snapshot; origem Git da cópia deve ser conferida pelo terceiro.",
        "valores": "recebidos sem recálculo financeiro",
        "recepcao_nova": False,
        "PIT_recertificado": False,
        "limites": [
            "flags e portões históricos conservados",
            "hash de configuração não é documento primário",
            "registro bruto por hash não é tie-out do conteúdo primário",
            "adequação de investimento não certificada",
            "estado atual de produção não inferido de um snapshot histórico",
        ],
    }
    return {
        "EMPRESAS.json": companies,
        "ETFS.json": etf_rows,
        "INDICES.json": indices,
        "METODOS.json": methods,
        "PORTOES.json": gates,
        "LEDGER.json": ledger,
        "POSICOES_ETFS_MOEDAS.json": positions,
        "RESUMO.json": summary,
        "PRIORIDADES_HISTORICAS.json": load(priorities),
        "METADADOS.json": meta,
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    for name in [
        "snapshot",
        "raiz-arquivos",
        "universo",
        "indice-publico",
        "fonte-geradora",
        "prioridades-historicas",
        "saida",
    ]:
        parser.add_argument("--" + name, required=True, type=Path)
    parser.add_argument("--commit-snapshot", required=True)
    parser.add_argument("--repo-url", default="https://github.com/arielassayag/MarketSummary")
    args = parser.parse_args(argv)
    output = args.saida.resolve()
    inputs = [args.raiz_arquivos.resolve(), args.fonte_geradora.resolve()]
    if output.exists() or any(output.is_relative_to(p) or p.is_relative_to(output) for p in inputs):
        raise ValueError("Destino existente ou sobreposto às fontes")

    def guard(event, values):
        if event.startswith(("socket.", "subprocess.", "os.system", "os.posix_spawn")):
            raise RuntimeError("Rede/processo proibido no mapa")
        if event == "import" and str(values[0]).split(".")[0] == "cdp":
            raise RuntimeError("Mapa não importa CDP")
        if event == "open":
            path, mode, flags = values
            writing = (isinstance(mode, str) and any(x in mode for x in "wax+")) or bool(
                flags & (os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_TRUNC | os.O_APPEND)
            )
            if writing and not Path(os.fsdecode(path)).resolve().is_relative_to(output):
                raise RuntimeError("Escrita fora da saída explícita")

    sys.addaudithook(guard)
    data = build(
        args.snapshot,
        args.raiz_arquivos,
        args.universo,
        args.indice_publico,
        args.fonte_geradora,
        args.prioridades_historicas,
        args.commit_snapshot,
        args.repo_url,
    )
    output.mkdir(parents=True)
    for name, value in data.items():
        write_json(output, name, value)
        if isinstance(value, list):
            write_csv(output, name.removesuffix(".json") + ".csv", value)
    print(json.dumps(data["RESUMO.json"], ensure_ascii=False))


if __name__ == "__main__":
    main()
