"""Mapa documental offline com DADOS SIMULADOS; não depende de capturas privadas."""

import gzip
import hashlib
import importlib.util
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[2] / "scripts/cdp_mapear_modelos.py"
SPEC = importlib.util.spec_from_file_location("cdp_mapa_documental_portatil", SCRIPT)
MAP = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MAP)


def put(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    content = json.dumps(data, ensure_ascii=False).encode()
    path.write_bytes(gzip.compress(content, mtime=0) if path.suffix == ".gz" else content)


def manifest(root):
    snap = root / "snapshot"
    paths = [p for p in snap.rglob("*") if p.is_file() and p.name != "manifest.json"]
    rows = {
        p.relative_to(snap).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest() for p in paths
    }
    rows["../publico/celula.csv"] = hashlib.sha256(
        (root / "publico/celula.csv").read_bytes()
    ).hexdigest()
    cfg = hashlib.sha256((snap / "configuracao/valuation.yaml").read_bytes()).hexdigest()
    put(
        snap / "manifest.json",
        {
            "as_of": "2026-10-07",
            "codigo": {"git": "5" * 40},
            "configuracao": {"arquivos": {"valuation.yaml": cfg}},
            "arquivos": rows,
        },
    )


@pytest.fixture
def source(tmp_path):
    root = tmp_path / "recebidos"
    snap = root / "snapshot"
    (snap / "configuracao").mkdir(parents=True)
    (snap / "configuracao/valuation.yaml").write_text(
        "pesos_metodos:\n  banco:\n    rim: 0.4\n    ddm: 0.6\n"
    )
    cfg_hash = hashlib.sha256((snap / "configuracao/valuation.yaml").read_bytes()).hexdigest()
    model = {
        "nome": "Empresa DADOS SIMULADOS",
        "pais": "AR",
        "arquetipo": "banco",
        "linha": "TEST",
        "moeda": "USD",
        "as_of": "2026-10-07",
        "resumo": {
            "rating": "Sem preço-alvo",
            "confianca": "Insuficiente",
            "alvo_citavel": False,
            "preco_alvo": None,
        },
        "passos": [
            {
                "id": "metodo.rim",
                "formula": None,
                "resultado": None,
                "resultado_texto": "Dado ausente",
            }
        ],
        "portoes": [{"codigo": "G13", "status": "sem_alvo"}],
        "insumos": [
            {"id": "eps_fy1", "valor": None, "fonte": "YAHOO", "data_publicacao": None},
            {
                "id": "referencia",
                "valor": 0.04,
                "fonte": "DAMODARAN",
                "sha256": cfg_hash,
                "data_publicacao": None,
                "documento": "Transcrição DADOS SIMULADOS",
            },
        ],
        "lacunas": ["DADOS SIMULADOS"],
    }
    put(snap / "modelos/TEST.json", model)
    put(
        snap / "insumos/emissores.json.gz",
        {"TEST": {"arquetipo": "banco", "pit_ok": False, "consenso": {"moeda_lpa": "ARS"}}},
    )
    etf = {
        "ticker": "ETF_TEST",
        "nome": "ETF DADOS SIMULADOS",
        "indice": "Índice DADOS SIMULADOS",
        "pais": "AR",
        "moeda": "USD",
        "as_of": "2026-10-07",
        "tem_alvo": False,
        "preco_alvo": None,
        "posicoes": [{"issuer_id": "TEST", "peso": 1, "imputado": True}],
        "portoes": [],
    }
    put(snap / "etfs/ETF_TEST.json", etf)
    put(
        snap / "insumos/etfs.json.gz",
        {
            "ETF_TEST": {
                "fonte_indice": {"sha256": cfg_hash, "documento": "Configuração DADOS SIMULADOS"}
            }
        },
    )
    (root / "publico").mkdir()
    (root / "publico/celula.csv").write_text("valor\n1\n")
    (root / "universo.csv").write_text("issuer_id,ticker\nTEST,TEST\n")
    (root / "indice.jsonl").write_text(
        json.dumps({"sha256": cfg_hash, "fonte": "DADOS SIMULADOS"}) + "\n"
    )
    put(root / "prioridades.json", [{"id": "A10", "tipo": "hipótese histórica DADOS SIMULADOS"}])
    (root / "src/cdp").mkdir(parents=True)
    (root / "src/cdp/__init__.py").write_text("# DADOS SIMULADOS; não importar\n")
    manifest(root)
    return root


def build(root):
    return MAP.build(
        root / "snapshot",
        root,
        root / "universo.csv",
        root / "indice.jsonl",
        root / "src",
        root / "prioridades.json",
        "a" * 40,
        "https://example.org/repo",
    )


def cli_args(root, out):
    return [
        "--snapshot",
        str(root / "snapshot"),
        "--raiz-arquivos",
        str(root),
        "--universo",
        str(root / "universo.csv"),
        "--indice-publico",
        str(root / "indice.jsonl"),
        "--fonte-geradora",
        str(root / "src"),
        "--prioridades-historicas",
        str(root / "prioridades.json"),
        "--commit-snapshot",
        "a" * 40,
        "--saida",
        str(out),
    ]


def test_ausencia_nao_vira_zero_nem_ready(source):
    result = build(source)
    company = result["EMPRESAS.json"][0]
    assert company["preco_alvo_snapshot"] is None
    assert company["portoes_bloqueantes"] == ["G13"] and company["insumos_ausentes"] == ["eps_fy1"]
    assert result["RESUMO.json"]["citaveis"] == 0
    assert result["RESUMO.json"]["percentual_compra_citavel"] is None


def test_publicacao_desconhecida_preservada(source):
    ledger = build(source)["LEDGER.json"]
    assert all(q["data_publicacao_declarada"] is None for q in ledger)
    assert all(q["tie_out_primario"] == "not_tested_primary" for q in ledger)
    assert ledger[0]["support_label"] == "missing_data"


def test_hash_configuracao_nao_vira_documento_primario(source):
    result = build(source)
    row = result["LEDGER.json"][1]
    assert row["dominio_hash"] == "configuração/transcrição" and row["registro_bruto_presente"]
    index = result["INDICES.json"][0]
    assert index["dominio_hash_indice"] == "configuração/transcrição"
    assert index["documento_primario_indice_confirmado"] is None
    assert not index["modelo_independente_pontos"]


def test_manifesto_sibling_legitimo_e_contagens(source):
    result = build(source)
    summary = result["RESUMO.json"]
    assert (
        summary["empresas"] == summary["linhas"] == summary["etfs"] == summary["indices_proxy"] == 1
    )
    assert summary["modelos_financeiros"] == 2 and summary["vistas_mapa"] == 3
    assert summary["n_manifesto_hashes_conferidos"] == 6
    assert not summary["valor_financeiro_recalculado"]


def test_hash_mutado_recusado(source):
    (source / "publico/celula.csv").write_text("valor\n2\n")
    with pytest.raises(ValueError, match="SHA divergente"):
        build(source)


def test_escape_manifesto_recusado(source):
    path = source / "snapshot/manifest.json"
    data = json.loads(path.read_text())
    data["arquivos"]["../../fora.txt"] = "0" * 64
    put(path, data)
    with pytest.raises(ValueError, match="escapou"):
        build(source)


def test_identidade_emissor_divergente_recusada(source):
    put(source / "snapshot/insumos/emissores.json.gz", {"OUTRO": {}})
    manifest(source)
    with pytest.raises(ValueError, match="identidades divergentes"):
        build(source)


def test_identidade_ETF_divergente_recusada(source):
    put(source / "snapshot/insumos/etfs.json.gz", {})
    manifest(source)
    with pytest.raises(ValueError, match="identidades divergentes"):
        build(source)


def test_prioridade_historica_e_metodo_sem_formula_preservados(source):
    data = build(source)
    assert data["PRIORIDADES_HISTORICAS.json"] == json.loads(
        (source / "prioridades.json").read_text()
    )
    method = data["METODOS.json"][0]
    assert not method["disponivel_na_memoria"] and method["motivo_na_memoria"] == "Dado ausente"
    assert method["peso_final"] is None


def test_paths_fisicos_diferentes_resultado_literal(source, tmp_path):
    other = tmp_path / "outro-layout"
    shutil.copytree(source, other, copy_function=shutil.copy2)
    assert build(source) == build(other)
    text = json.dumps(build(other), default=str)
    assert str(source) not in text and str(other) not in text


def test_CLI_offline_e_destino_existente_recusado(source, tmp_path):
    out = tmp_path / "mapa"
    env = {**os.environ, "PYTHONDONTWRITEBYTECODE": "1"}
    command = [sys.executable, "-B", str(SCRIPT), *cli_args(source, out)]
    first = subprocess.run(command, capture_output=True, text=True, env=env, check=False)
    assert first.returncode == 0, first.stderr
    assert (out / "EMPRESAS.csv").is_file() and (out / "METADADOS.json").is_file()
    before = {p.name: p.read_bytes() for p in out.iterdir()}
    second = subprocess.run(command, capture_output=True, text=True, env=env, check=False)
    assert second.returncode != 0 and "Destino existente" in second.stderr
    assert before == {p.name: p.read_bytes() for p in out.iterdir()}


def test_JSON_nao_finito_recusado(tmp_path):
    path = tmp_path / "invalido.json"
    path.write_text('{"x":NaN}')
    with pytest.raises(ValueError, match="não finita"):
        MAP.load(path)
