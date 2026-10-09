"""Dez controles próprios do delta ROOT; fixtures DADOS SIMULADOS."""

import gzip
import json

import pytest
from test_mapa_modelos_publico import build
from test_mapa_modelos_publico import source as source

FAMILIAS = ["modelos/TEST.json", "etfs/ETF_TEST.json", "insumos/emissores.json.gz",
            "insumos/etfs.json.gz", "configuracao/valuation.yaml"]


@pytest.mark.parametrize("relative", FAMILIAS)
def test_omissao_sem_adulteracao_recusada(source, relative):
    path = source / "snapshot/manifest.json"
    data = json.loads(path.read_text())
    del data["arquivos"][relative]
    path.write_text(json.dumps(data))
    with pytest.raises(ValueError, match="não manifestado"):
        build(source)


@pytest.mark.parametrize("relative", FAMILIAS)
def test_adulteracao_com_pin_antigo_recusada(source, relative):
    path = source / "snapshot" / relative
    raw = path.read_bytes()
    path.write_bytes(gzip.compress(gzip.decompress(raw) + b"\n", mtime=0)
                     if relative.endswith(".gz") else raw + b"\n")
    with pytest.raises(ValueError, match="SHA divergente"):
        build(source)
