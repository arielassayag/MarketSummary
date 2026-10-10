"""DADOS SIMULADOS: cinco controles novos de wheel real e fixture primária portátil."""
import gzip
import hashlib
import importlib.metadata
import json
import os
import stat
import subprocess
import sys
from datetime import datetime
from importlib.resources import files
from pathlib import Path

import pandas as pd
import pytest

from cdp.data import publico_enelchile_estoque as enel
from cdp.data import publico_sec as sec
from cdp.data.publico_fatos import selecionar_pit

FIXTURE = Path(__file__).resolve().parents[2] / "tests/cdp/fixtures/enelchile_20f_2025"
MANIFEST = json.loads((FIXTURE / "MANIFESTO.json").read_bytes())
pytestmark = pytest.mark.skipif("ENEL_INSTALACAO_AREA" not in os.environ,
    reason="qualificação especializada por wheel e área privada explícita")


def corpo(entry):
    path = FIXTURE / entry["path"]
    assert path.parent == FIXTURE and path.is_file()
    stored = path.read_bytes()
    assert hashlib.sha256(stored).hexdigest() == entry["stored_sha256"]
    assert len(stored) == entry["stored_bytes"]
    body = gzip.decompress(stored) if entry["compression"] == "gzip" else stored
    assert len(body) == entry["bytes"] and hashlib.sha256(body).hexdigest() == entry["sha256"]
    return body


def test_wheel_normal_instalada_e_dependencia_direta():
    import enelchile_documental
    from enelchile_documental import consumidor, leitor, produtor

    prefix = Path(sys.prefix).resolve()
    for module in (enelchile_documental, consumidor, leitor, produtor, enel, sec):
        path = Path(module.__file__).resolve()
        assert path.is_relative_to(prefix) and "site-packages" in path.parts
        if module.__name__.startswith("enelchile_documental"):
            expected = MANIFEST["modulos_documentais"][path.name]
            assert hashlib.sha256(path.read_bytes()).hexdigest() == expected["sha256"]
    requires = importlib.metadata.requires("fechamento")
    assert "lxml<7,>=6.1.3" in requires
    assert importlib.metadata.version("lxml") == MANIFEST["lxml_lock_recebido"]
    assert not os.environ.get("PYTHONPATH")


def test_catalogo_resource_literal_em_instalacao_fora_clone():
    expected = MANIFEST["catalogo"]
    resource = files("cdp").joinpath(expected["resource"])
    assert resource.is_file()
    body = resource.read_bytes()
    assert len(body) == expected["bytes"] and hashlib.sha256(body).hexdigest() == expected["sha256"]
    assert sec.CATALOGO_CLASSES == resource
    assert sec.ciks_classes_sec() == frozenset(doc["cik"] for doc in json.loads(body)["documentos"])


def test_composicao_whole_instalada_fixture_relativa_offline():
    bodies = tuple(corpo(entry) for entry in MANIFEST["corpos"])
    recent = json.loads(bodies[2])["filings"]["recent"]
    index = recent["accessionNumber"].index(enel.ACCESSION)
    metadata = {"accn": recent["accessionNumber"][index], "filed": recent["filingDate"][index],
                "form": recent["form"][index], "period_end": recent["reportDate"][index]}
    generic = sec.fatos_sec(sec.companyfacts_documento(bodies[0], enel.CIK, metadata))
    current = generic[generic["period_end"].eq(pd.Timestamp(metadata["period_end"]))].copy()
    cut = datetime.fromisoformat(MANIFEST["knowledge_cutoff_UTC"])
    merged = enel.compor_fatos_enel(current, *bodies, cut, enabled=True)
    actual = selecionar_pit(merged, cut, conhecimento_ate=cut)
    expected_body = (FIXTURE / MANIFEST["oraculo"]["path"]).read_bytes()
    assert hashlib.sha256(expected_body).hexdigest() == MANIFEST["oraculo"]["sha256"]
    assert json.loads(actual.to_json(orient="records", date_format="iso")) == json.loads(expected_body)
    output = Path(os.environ["ENEL_INSTALACAO_SAIDA"]) / "POSITIVO_WHOLE.json"
    with output.open("x", encoding="utf-8") as file:
        file.write(actual.to_json(orient="records", date_format="iso"))
        file.write("\n")


def test_default_inativo_instalado_nao_exige_fontes():
    simulated = pd.DataFrame({"DADOS SIMULADOS": [1]})
    output = enel.compor_fatos_enel(simulated, b"", b"", b"", b"", b"",
                                   datetime.fromisoformat(MANIFEST["knowledge_cutoff_UTC"]))
    pd.testing.assert_frame_equal(output, simulated)
    assert output is not simulated


def test_catalogo_presente_literal_e_invalido_nao_viram_fallback():
    destination = Path(sec.__file__).resolve().parents[3] / "configs/cdp/sec_classes_acoes.json"
    assert destination.is_relative_to(Path(sys.prefix).resolve())
    try:
        previous_stat = destination.lstat()
    except FileNotFoundError:
        previous_stat, previous_body = None, None
    else:
        assert stat.S_ISREG(previous_stat.st_mode), "Catálogo prévio não regular"
        previous_body = destination.read_bytes()
    source = files("cdp").joinpath(MANIFEST["catalogo"]["resource"])
    literal = source.read_bytes()
    probe = Path(os.environ["ENEL_INSTALACAO_PROBE"])
    try:
        destination.parent.mkdir(parents=True, exist_ok=True)
        for state, body in (("LITERAL", literal), ("INVALIDO", '{"DADOS SIMULADOS":"catálogo presente inválido"}'.encode())):
            destination.write_bytes(body)
            env = dict(os.environ)
            env.pop("PYTHONPATH", None)
            result = subprocess.run([sys.executable, "-I", "-B", str(probe), state,
                                    os.environ["ENEL_INSTALACAO_AREA"], str(destination)],
                                    capture_output=True, text=True, check=False, env=env)
            assert result.returncode == 0, result.stdout + result.stderr
            receipt = json.loads(result.stdout)
            assert receipt["catalogo_presente_preferido"] and receipt["guard_attempts"] == 0
    finally:
        if previous_stat is None:
            destination.unlink(missing_ok=True)
        else:
            destination.write_bytes(previous_body)
            os.utime(destination, ns=(previous_stat.st_atime_ns, previous_stat.st_mtime_ns))
