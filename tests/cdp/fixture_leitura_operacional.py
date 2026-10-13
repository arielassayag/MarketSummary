"""Corpus privado TESTE, DADOS SIMULADOS; produzido hoje, sem PIT/autoridade operacional.

Importável pelo qualificador instalado somente como helper privado, fora do wheel. Recebe
paths absolutos das configurações e da saída temporária; nenhuma fonte/raiz é descoberta.
"""

from __future__ import annotations

import hashlib
import json
import shutil
from datetime import date
from pathlib import Path

import pandas as pd

from cdp.config import config_json, load_config
from cdp.contracts import DailyRecord, DailyRisk
from cdp.research.commentary import (
    build_daily_factbook,
    example_commentary,
    factbook_json,
    write_daily_commentary_inputs,
)
from cdp.risk.types import RiskModel
from cdp.workflow import risco_diario
from cdp.workflow.track_record import GENESIS_RECORD_HASH, TrackRecord

DATA = date(2026, 10, 8)
AGORA = "2026-10-10T19:00:00Z"
CORTE = "2026-10-10T18:00:00Z"


def criar_corpus(root: Path, configuracoes: Path, mandato: Path) -> dict:
    """Receita literal finita: caixa simulado, modelo arquivado, FB e snapshot nativos."""
    if type(root) is not type(Path("/")) or not root.is_absolute() or root.exists():
        raise ValueError("Saída privada exige Path absoluto novo")
    if (
        type(configuracoes) is not type(Path("/"))
        or type(mandato) is not type(Path("/"))
        or not configuracoes.is_absolute()
        or not mandato.is_absolute()
    ):
        raise ValueError("Configurações explicitamente recebidas")
    root.mkdir()
    roots = {
        "repositorio": root / "repositorio",
        "livro": root / "livro",
        "mercado": root / "mercado",
        "relatorios": root / "relatorios",
        "publico": root / "publico",
        "rascunhos": root / "rascunhos",
    }
    for p in roots.values():
        p.mkdir()
    configs = roots["repositorio"] / "configs/cdp"
    shutil.copytree(configuracoes, configs)
    # Configuração apenas da fixture; nenhum arquivo recebido é alterado no local.
    cfg = load_config(mandato).with_overrides(
        {"fund": {"name": "DADOS SIMULADOS — corpus de leitura", "inception_date": "2026-10-09"}}
    )
    (configs / "fund.yaml").write_text(config_json(cfg), encoding="utf-8")
    (roots["repositorio"] / ".cdp").mkdir()
    (roots["repositorio"] / ".cdp/local.yaml").write_text(
        "executor: outro\nharness: codex\n", encoding="utf-8"
    )
    (configs / "universo.csv").write_text(
        "issuer_id,issuer_name,country,gics_sector,line_type,yahoo_ticker,exchange,currency,adr_ratio,primary_line\nSIM001,DADOS SIMULADOS,BR,Financials,LOCAL,SIM1.SA,B3,BRL,1,true\n",
        encoding="utf-8",
    )
    # Modelo nativo explícito; nenhuma estimação, seed, solver, leilão ou aquisição.
    model = RiskModel(
        DATA,
        pd.DataFrame([[1.0]], index=["SIM001"], columns=["market"]),
        pd.DataFrame([[0.04]], index=["market"], columns=["market"]),
        pd.Series([0.01], index=["SIM001"]),
        pd.DataFrame([[0.001]], index=pd.DatetimeIndex([DATA]), columns=["market"]),
        pd.DataFrame([[0.0]], index=pd.DatetimeIndex([DATA]), columns=["SIM001"]),
        factor_groups={"market": "market"},
        meta={"aviso": "DADOS SIMULADOS"},
    )
    diagnostic = {
        "policy": risco_diario.POLICY,
        "session": str(DATA),
        "weights": {},
        "models": {
            "base": risco_diario.model_data(model),
            "evento": risco_diario.model_data(model),
        },
        "is_synthetic": True,
        "data_notice": "DADOS SIMULADOS",
    }
    h = hashlib.sha256(risco_diario.text(diagnostic).encode()).hexdigest()
    record = DailyRecord(
        date=DATA,
        fund_name=cfg.fund.name,
        track_record_type="efetiva",
        nav_start_usd=1000000.0,
        nav_end_usd=1000000.0,
        pnl_usd=0.0,
        ret=0.0,
        positions=[],
        risk=DailyRisk(
            gross=0.0, net=0.0, long_exposure=0.0, short_exposure=0.0, n_long=0, n_short=0
        ),
        input_hashes={risco_diario.MARKER: h},
        is_synthetic=True,
        data_notice="DADOS SIMULADOS",
        prev_record_hash=GENESIS_RECORD_HASH,
    )
    record = record.model_copy(update={"record_hash": record.compute_hash()})
    track = TrackRecord(roots["livro"] / "track_record")
    risco_diario.append(track, record, diagnostic)  # TESTE tmp, protocolo nativo sem MOC/NET novo.
    fb = build_daily_factbook(record, [], cfg=cfg)
    folder = roots["relatorios"] / "daily" / str(DATA)
    write_daily_commentary_inputs(folder, record, fb, mind_hint="codex")
    (folder / "factbook.json").write_text(factbook_json(fb), encoding="utf-8")
    doc = roots["rascunhos"] / "comentario.json"
    doc.write_text(
        json.dumps(example_commentary(fb, "codex"), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    doc_sha = hashlib.sha256(doc.read_bytes()).hexdigest()
    # Snapshot de teste no formato nativo legado recebido hoje, com corpo e selo próprios.
    snap = roots["livro"] / "cobertura" / str(DATA)
    (snap / "modelos").mkdir(parents=True)
    (snap / "configuracao").mkdir()
    (snap / "modelos/SIM001.json").write_text(
        json.dumps(
            {
                "issuer_id": "SIM001",
                "data_notice": "DADOS SIMULADOS",
                "valor_ausente": None,
                "resultado_observado": 1.0,
                "nan_observado": float("nan"),
                "infinito_observado": float("inf"),
                "menos_infinito_observado": -float("inf"),
            }
        ),
        encoding="utf-8",
    )
    (snap / "modelos.csv").write_text(
        "issuer_id,rating,tp\nSIM001,Sem preço-alvo,\n", encoding="utf-8"
    )
    (snap / "configuracao/valuation.yaml").write_text("projecao: {}\n", encoding="utf-8")
    files = {
        p.relative_to(snap).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
        for p in sorted(snap.rglob("*"))
        if p.is_file()
    }
    manifest = {
        "as_of": str(DATA),
        "is_synthetic": True,
        "data_notice": "DADOS SIMULADOS",
        "concluido_em": "2026-10-10T17:00:00Z",
        "arquivos": files,
    }
    (snap / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    snap_sha = hashlib.sha256((snap / "manifest.json").read_bytes()).hexdigest()
    (snap / "selo.json").write_text(
        json.dumps({"manifest_sha256": snap_sha}) + "\n", encoding="utf-8"
    )
    members = {}
    ids = {}
    for rid, rpath in roots.items():
        for p in sorted(rpath.rglob("*")):
            if p.is_file():
                rel = p.relative_to(rpath).as_posix()
                mid = f"{rid}:{rel}"
                members[mid] = {
                    "raiz": rid,
                    "relativo": rel,
                    "sha256": hashlib.sha256(p.read_bytes()).hexdigest(),
                }
                ids[(rid, rel)] = mid
    entries = {
        k: ids[("repositorio", v)]
        for k, v in {
            "mandato": "configs/cdp/fund.yaml",
            "universo": "configs/cdp/universo.csv",
            "nomes": "configs/cdp/nomes.yaml",
            "rotinas": "configs/cdp/rotinas.yaml",
            "executor": "configs/cdp/executor.yaml",
            "identidade": ".cdp/local.yaml",
            "eventos_macro": "configs/cdp/cobertura/eventos_macro.yaml",
        }.items()
    }
    params = {
        name: ids[("repositorio", "configs/cdp/" + name)]
        for name in (
            "valuation.yaml",
            "cobertura/arquetipos.csv",
            "cobertura/betas_setor.csv",
            "cobertura/unidades.csv",
            "cobertura/sotp.yaml",
            "cobertura/etfs.yaml",
            "resultado_evidencias.json",
        )
    }
    context = {
        "schema": "cdp.contexto_leitura/v1",
        "somente_leitura": True,
        "raizes": {k: str(v) for k, v in roots.items()},
        "membros": members,
        "entradas": entries,
        "parametros": params,
        "documentos": {doc_sha: ids[("rascunhos", "comentario.json")]},
        "ambiente_identidade": {"CDP_HARNESS": "codex"},
        "mente_esperada": "codex",
        "as_of": str(DATA),
        "conhecimento_ate": CORTE,
        "agora": AGORA,
        "offset_pc_minutos": -180,
    }
    cp = root / "contexto.json"
    cp.write_text(json.dumps(context, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    context_sha = hashlib.sha256(cp.read_bytes()).hexdigest()
    common = {"contexto_sha256": context_sha}
    inputs = {
        "consultar_estado": {**common, "agora": AGORA, "rapido": True},
        "consultar_agenda": {**common, "agora": AGORA, "offset_pc_minutos": -180},
        "verificar_integridade": {**common, "escopo": "track"},
        "ler_fatos": {**common, "etapa": "comentario-diario", "data": str(DATA), "fact_ids": []},
        "validar_documento": {
            **common,
            "etapa": "comentario-diario",
            "data": str(DATA),
            "documento_sha256": doc_sha,
            "mente_esperada": "codex",
        },
        "ler_carteira": {**common, "data": str(DATA), "lado": "efetiva", "visao": "diaria"},
        "decompor_risco_operacional": {
            **common,
            "sessao": str(DATA),
            "lado": "efetiva",
            "modelo": "base",
        },
        "ler_modelo_cobertura": {
            **common,
            "data": str(DATA),
            "conhecimento_ate": CORTE,
            "instrumento_tipo": "emissor",
            "instrumento_id": "SIM001",
            "visao": "modelo",
        },
        "ler_pacote_mente": {
            **common,
            "etapa": "comentario-diario",
            "data": str(DATA),
            "mente": "codex",
            "gerado_em": AGORA,
        },
    }
    (root / "ingressos.json").write_text(
        json.dumps(inputs, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    expectations = {
        "aviso": "DADOS SIMULADOS — receita de teste feita hoje; sem PIT/autoridade operacional",
        "contexto_sha256": context_sha,
        "expectativas": {
            tool: {"status": "disponivel", "autoridade_operacional": False, "ingresso": entry}
            for tool, entry in inputs.items()
        },
        "readset_membros_admitidos": members,
        "limite": "Readset efetivo e resultado/hash só são observados na consulta; esta receita não os presume",
    }
    (root / "expectativas.json").write_text(
        json.dumps(expectations, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return {
        "contexto": cp,
        "ingressos": inputs,
        "record": record,
        "factbook": fb,
        "modelo": model,
        "roots": roots,
    }


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--saida", type=Path, required=True)
    parser.add_argument("--configuracoes", type=Path, required=True)
    parser.add_argument("--mandato", type=Path, required=True)
    args = parser.parse_args()
    built = criar_corpus(args.saida, args.configuracoes, args.mandato)
    print(
        json.dumps(
            {
                "aviso": "DADOS SIMULADOS",
                "contexto": str(built["contexto"]),
                "contexto_sha256": hashlib.sha256(built["contexto"].read_bytes()).hexdigest(),
                "ingressos": str(args.saida / "ingressos.json"),
                "expectativas": str(args.saida / "expectativas.json"),
            }
        )
    )
