"""DADOS SIMULADOS. Fronteira EPS-only não autora, APIs normais e sem receita nova."""

import io
import os
from contextlib import contextmanager
from decimal import Decimal

import pandas as pd
import pytest
import test_publico_eps_por_periodo as f

from cdp.cobertura.fontes import coletar, csv_canonico
from cdp.data.publico_eps import autenticar_linha

# isort: split
from cdp_audit_guardas import registrar, remover


@contextmanager
def sem_efeitos():
    state = {"active": True, "reads": 0, "forbidden": []}

    def audit(event, args):
        if not state["active"]:
            return
        forbidden = False
        if event == "open":
            _, mode, flags = args
            forbidden = (isinstance(mode, str) and any(c in mode for c in "wax+")) or (
                isinstance(flags, int)
                and flags & (os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_TRUNC | os.O_APPEND)
            )
            if not forbidden:
                state["reads"] += 1
        elif event.startswith(("socket.", "subprocess.", "os.exec", "os.spawn")) or event in {
            "os.system", "os.fork", "os.mkdir", "os.remove", "os.rename", "os.rmdir",
            "os.utime", "os.chmod", "os.link", "os.symlink",
        }:
            forbidden = True
        if forbidden:
            state["forbidden"].append(event)
            raise AssertionError("Efeito vedado na API: " + event)

    token = registrar(audit)
    try:
        yield state
    finally:
        state["active"] = False
        remover(token)
        assert state["forbidden"] == []


def preparar(root, *, sem_eps=False):
    doc = f.documento()
    if sem_eps:
        for cell in f.trend(doc):
            cell["earningsEstimate"]["avg"].pop("raw")
    archive, record, raw = f.arquivo(root, f.corpo(doc))
    index = (archive.base / "indice.jsonl").read_bytes()
    with sem_efeitos():
        data = coletar(f.mercado(), f.DATA, [], [f.TICKER], [], offline=True,
                       raiz=root, eps_por_periodo=True, conhecimento_ate=f.RECEBIDO)
        row = pd.read_csv(io.StringIO(csv_canonico(data.consenso))).iloc[0]
        assert autenticar_linha(row, root) is not None
        pk = f.participante(row, root)
    assert archive.ler(record) == raw and (archive.base / "indice.jsonl").read_bytes() == index
    return row, pk, archive, record, raw, index


def preservar(row, changed, archive, record, raw, index):
    for field in ("eps_contexto", "sha256", "data_coleta"):
        assert changed[field] == row[field]
    assert archive.ler(record) == raw
    assert (archive.base / "indice.jsonl").read_bytes() == index


@pytest.mark.parametrize("field,value", [
    ("receita_fy2", 1100), ("moeda_receita_auxiliar", "ARS"),
    ("poder_aquisitivo_receita", "2026-12-31"), ("receita_extra", float("inf")),
    ("receita_extra", float("-inf")), ("receita_extra", Decimal("NaN")),
])
def test_namespace_presente_recusado_sem_mudar_corpo(tmp_path, field, value):
    row, _, archive, record, raw, index = preparar(tmp_path)
    changed = row.copy()
    changed[field] = value
    with sem_efeitos():
        with pytest.raises(ValueError, match="não admite campo de receita"):
            autenticar_linha(changed, tmp_path)
        with pytest.raises(ValueError, match="não admite campo de receita"):
            f.participante(changed, tmp_path)
    preservar(row, changed, archive, record, raw, index)


@pytest.mark.parametrize("serializar", [False, True])
def test_eps_ausente_nao_concede_receita_no_consumo(tmp_path, serializar):
    row, _, archive, record, raw, index = preparar(tmp_path, sem_eps=True)
    changed = row.copy()
    changed["receita_fy1"], changed["receita_fy2"] = 1000, 1100
    if serializar:
        changed = pd.read_csv(io.StringIO(csv_canonico(pd.DataFrame([changed])))).iloc[0]
    with sem_efeitos():
        with pytest.raises(ValueError, match="não admite campo de receita"):
            f.participante(changed, tmp_path)
    preservar(row, changed, archive, record, raw, index)


def test_ausencia_csv_e_metadado_fora_namespace_preservam_saida(tmp_path):
    row, expected, _, _, _, _ = preparar(tmp_path)
    changed = row.copy()
    changed["receita_extra"] = None
    changed["comentario_eps"] = "DADOS SIMULADOS; não autoriza receita"
    changed = pd.read_csv(io.StringIO(csv_canonico(pd.DataFrame([changed])))).iloc[0]
    with sem_efeitos():
        actual = f.participante(changed, tmp_path)
    assert actual.v == expected.v and actual.fontes == expected.fontes
    assert actual.tabela == expected.tabela and actual.lacunas == expected.lacunas
    assert actual.avisos == expected.avisos


@pytest.mark.parametrize("field", ["eps_contexto", "eps_origem_moeda"])
def test_marcador_parcial_recusa_sem_fallback(tmp_path, field):
    row, _, _, _, _, _ = preparar(tmp_path)
    changed = row.copy()
    changed[field] = None
    changed["receita_fy1"], changed["receita_fy2"] = 1000, 1100
    with sem_efeitos():
        with pytest.raises(ValueError, match="Contexto EPS parcial"):
            f.participante(changed, tmp_path)


def test_ausencia_dois_marcadores_conserva_legado(tmp_path):
    row, _, _, _, _, _ = preparar(tmp_path)
    changed = row.copy()
    changed["eps_contexto"] = changed["eps_origem_moeda"] = None
    changed["receita_fy1"], changed["receita_fy2"], changed["moeda_receita"] = 1000, 1100, "ARS"
    with sem_efeitos():
        assert autenticar_linha(changed, tmp_path) is None
        actual = f.participante(changed, tmp_path)
    expected = Decimal("1100") / Decimal("1000") - Decimal("1")
    assert Decimal(str(actual.v["g_receita_fy2"])) == expected
