"""Recursos portáteis e recusa de fallback — DADOS SIMULADOS."""
import json
from pathlib import Path

import pandas as pd
import pytest

from cdp.config import config_json, load_config
from cdp.tecnicas import recursos
from cdp.universe import load_universe, nomes_canonicos


@pytest.fixture
def declarado(tmp_path):
    exemplo = recursos.carregar_exemplo("latam_simulado_v1")
    for n, raw in exemplo.arquivos.corpos.items():
        p = tmp_path / n
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(raw)
    paths = dict(fund=tmp_path / "fund.yaml", valuation=tmp_path / "valuation.yaml",
                 cobertura=tmp_path / "cobertura", universo=tmp_path / "universo.csv",
                 nomes=tmp_path / "nomes.yaml", catalogos={})
    return exemplo, paths


def test_exemplo_e_declarado_independentes_do_cwd(declarado, tmp_path, monkeypatch):
    exemplo, paths = declarado
    empty = tmp_path / "cwd-vazio"
    empty.mkdir()
    monkeypatch.chdir(empty)
    monkeypatch.setattr("cdp.universe.nomes_canonicos", lambda: pytest.fail("Nome default oculto"))
    result = recursos.carregar_arquivos_locais(**paths)
    installed_example = recursos.carregar_exemplo("latam_simulado_v1")
    assert result.origem.papel == "CONFIG_DECLARADA"
    assert installed_example.origem.aviso == "DADOS SIMULADOS"
    assert installed_example.fund.execution is None
    assert config_json(result.fund) == config_json(exemplo.fund)
    assert result.valuation.arquivos == exemplo.valuation.arquivos
    assert result.universo.source_sha256 == exemplo.universo.source_sha256
    pd.testing.assert_frame_equal(result.universo.lines, exemplo.universo.lines, check_exact=True)
    assert not list(empty.iterdir())


@pytest.mark.parametrize("campo", ["fund", "valuation", "universo", "nomes"])
def test_falta_explicita_nao_consume_default(declarado, campo, monkeypatch):
    _, paths = declarado
    monkeypatch.setattr("cdp.config.DEFAULT_CONFIG_PATH", paths["fund"])
    missing = Path(paths[campo]).with_name("ausente")
    paths[campo] = missing
    with pytest.raises(FileNotFoundError):
        recursos.carregar_arquivos_locais(**paths)


def test_membro_de_cobertura_declarado_nao_vira_texto_vazio(declarado):
    _, paths = declarado
    (paths["cobertura"] / "unidades.csv").unlink()
    with pytest.raises(FileNotFoundError):
        recursos.carregar_arquivos_locais(**paths)


def test_catalogo_explicito_ausente_nao_cai_no_cwd(declarado, tmp_path, monkeypatch):
    _, paths = declarado
    p = paths["valuation"]
    v = json.loads(p.read_bytes())
    v["projecao"]["normalizacao_resultado_metodo"] = "eventos_evidenciados"
    p.write_text(json.dumps(v))
    (tmp_path / "resultado_evidencias.json").write_text("{}")
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr("cdp.cobertura.parametros.DEFAULT_VALUATION", p)
    with pytest.raises(FileNotFoundError, match="Catálogo declarado"):
        recursos.carregar_arquivos_locais(**paths)


@pytest.mark.parametrize("func", [load_config, load_universe, nomes_canonicos])
def test_caminho_vazio_explicito_recusa(func):
    with pytest.raises(ValueError, match="vazio"):
        func("")


def test_nome_declarado_ausente_recusa(tmp_path):
    with pytest.raises(FileNotFoundError):
        nomes_canonicos(str(tmp_path / "nomes-ausentes.yaml"))


@pytest.mark.parametrize("alteracao", ["hash", "membro-extra", "nome-desconhecido"])
def test_integridade_e_conjunto_do_exemplo(declarado, tmp_path, monkeypatch, alteracao):
    example, _ = declarado
    base = tmp_path / "cdp/recursos/exemplos/latam_simulado_v1"
    base.mkdir(parents=True)
    for n, raw in example.arquivos.corpos.items():
        p = base / n
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(raw)
    from importlib.resources import files

    original = files("cdp").joinpath("recursos", "exemplos", "latam_simulado_v1", "manifesto.json").read_bytes()
    (base / "manifesto.json").write_bytes(original)
    if alteracao == "hash":
        (base / "fund.yaml").write_bytes(b"{}\n")
    elif alteracao == "membro-extra":
        (base / "executor.yaml").write_bytes(b"{}\n")
    monkeypatch.setattr(recursos, "files", lambda _: tmp_path / "cdp")
    with pytest.raises(ValueError):
        recursos.carregar_exemplo("desconhecido" if alteracao == "nome-desconhecido" else "latam_simulado_v1")


def test_fachada_nao_exporta_escritores():
    import cdp.tecnicas as tecnicas

    assert set(tecnicas.__all__) == {"calcular_ke", "avaliar_pb_justificado", "estimar_preenchimento"}
    assert all(not hasattr(tecnicas, n) for n in ["publish", "decide", "reinicio", "kill_switch"])
