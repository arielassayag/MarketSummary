"""O ensaio usa Git temporário e distingue proposta de revisão efetivada."""

from pathlib import Path

from cdp.memoria import Fontes
from cdp.memoria_ensaio_sonho import avaliar_sonho


def test_ensaio_sonho_separa_devolutiva_da_adocao(monkeypatch, tmp_path):
    monkeypatch.setattr("tempfile.tempdir", str(tmp_path))
    fontes = Fontes(Path(__file__).resolve().parents[2])
    resultado = avaliar_sonho(fontes)

    assert list(tmp_path.iterdir()) == []
    assert Fontes(fontes.raiz).revisao == fontes.revisao
    assert resultado["natureza"] == "DADOS SIMULADOS"
    c = resultado["consolidacao"]
    assert c["somente_leitura"]
    assert c["elegibilidade_conferiu_antes"] and c["elegibilidade_conferiu_apos_revisao"]
    assert c["candidatas_conferidas"] == ["ensaio-recibo-comprovado"]
    assert c["candidatas_conferidas"][0] not in c["elegiveis_antes"]
    assert c["candidatas_conferidas"][0] in c["elegiveis_apos_revisao"]
    assert all(d["diagnosticada"] and d["revisada"] and d["elegivel_apos_revisao"]
               for d in c["decisoes"])
    assert {"ensaio-recibo-avulso", "ensaio-retidos-risco", "ensaio-retidos-execucao",
            "ensaio-rascunho-em-aberto", "ensaio-calibracao-sem-renovacao"}.isdisjoint(
        c["elegiveis_apos_revisao"]
    )
    estado = [caso for caso in resultado["casos"] if caso["tipo"] == "estado_atual"]
    assert estado and all(caso["modos"]["apos_revisao"]["encaminhou_explicito"] for caso in estado)
