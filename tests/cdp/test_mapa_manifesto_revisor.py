"""Controles independentes: entradas consumidas devem integrar o manifesto."""
import gzip
import json

import pytest
from test_mapa_modelos_publico import build
from test_mapa_modelos_publico import source as source


@pytest.mark.parametrize("relative", ["modelos/TEST.json", "etfs/ETF_TEST.json", "insumos/emissores.json.gz", "insumos/etfs.json.gz", "configuracao/valuation.yaml"])
def test_consumo_fora_manifesto_recusado(source, relative):
    path = source / "snapshot/manifest.json"
    data = json.loads(path.read_text())
    del data["arquivos"][relative]
    path.write_text(json.dumps(data))
    omitted = source / "snapshot" / relative
    raw = omitted.read_bytes()
    if relative.endswith(".gz"):
        omitted.write_bytes(gzip.compress(gzip.decompress(raw) + b"\n", mtime=0))
    else:
        omitted.write_bytes(raw + b"\n")
    with pytest.raises(ValueError, match="não manifestado"):
        build(source)
