"""Regressão dos casos operacionais e de auditoria congelados antes do ajuste."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

from cdp.memoria import Catalogo, Fontes, Local
from cdp.memoria_avaliacao import CorpusReservado, _atingidos, _grupos

RAIZ = Path(__file__).resolve().parents[2]
PASTA = RAIZ / "docs/cdp/memoria"
LACRE = {
    "operacional": "877c5b294bee0509e09a292ac22eaa91f89304c385872214fe13f22a06660b56",
    "auditoria": "68cb21b52cbfcae97b57612b6953189f19b197653e9a46f328a7a75b650c3f37",
}


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
