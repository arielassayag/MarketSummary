"""Regressão dos casos operacionais e de auditoria congelados antes do ajuste."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from runpy import run_path

from cdp.memoria import Catalogo, Fontes, Local
from cdp.memoria_avaliacao import CorpusReservado, _atingidos, _grupos

RAIZ = Path(__file__).resolve().parents[2]
PASTA = RAIZ / "docs/cdp/memoria"
LACRE = {
    "operacional": "877c5b294bee0509e09a292ac22eaa91f89304c385872214fe13f22a06660b56",
    "auditoria": "68cb21b52cbfcae97b57612b6953189f19b197653e9a46f328a7a75b650c3f37",
}


def test_preflight_exige_que_as_provas_caibam_juntas():
    cabe = run_path(str(RAIZ / "scripts/cdp_memoria_benchmark.py"))["_cabe_em_conjunto"]
    a = Local("a.md", 2, 3, "")
    b = Local("a.md", 5, 6, "")
    c = Local("c.md", 1, 2, "")
    grupos = [[a], [b], [c]]
    assert not cabe({a: 1500, b: 1500, c: 1500}, grupos)
    assert cabe({a: 1500, b: 1500, c: 1498}, grupos)
    assert cabe({Local("a.md", 1, 8, ""): 1800, c: 1500}, grupos)


def test_benchmark_de_evidencia_e_guardas_da_memoria():
    lotes = []
    for nome, sha256 in LACRE.items():
        bruto = (PASTA / f"benchmark-{nome}.json").read_bytes()
        assert hashlib.sha256(bruto).hexdigest() == sha256
        dados = json.loads(bruto)
        dados.pop("revisao_fontes", None)
        for caso in dados["casos"]:
            caso.pop("familia")
            caso.pop("expectativa", None)
        lotes.append(CorpusReservado.model_validate_json(json.dumps(dados)))

    fontes = Fontes(RAIZ, trabalho=os.name == "posix")
    catalogo = Catalogo(fontes, lotes[0].data)
    assert not catalogo.problemas
    falhas = []
    for lote in lotes:
        for caso in lote.casos:
            saida = catalogo.buscar(caso.escopo, caso.consulta, 5)
            passagens = [Local(**p) for p in saida["passagens"]]
            encaminhou = bool(saida["orientacao_atual"])
            if caso.tipo == "evidencia":
                passou = not encaminhou and all(_atingidos(passagens, _grupos(fontes, caso)))
            elif caso.tipo == "estado_atual":
                passou = encaminhou and not (saida["notas"] or saida["fontes"] or saida["passagens"])
            else:
                passou = not (encaminhou or passagens or saida["notas"])
            if not passou:
                falhas.append(caso.id)
    assert not falhas, falhas
