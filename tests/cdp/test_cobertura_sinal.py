"""Sinal de valuation em sombra, fatos ``val.*`` do FactBook e CLI da cobertura (DADOS SIMULADOS)."""

from __future__ import annotations

from datetime import UTC, date, datetime

import numpy as np
import pandas as pd
import pytest

from cdp.alpha.signals import SIGNALS, valuation_gap_sombra
from cdp.cobertura.cli import executar_snapshot
from cdp.cobertura.fatos import factbook_emissor
from cdp.cobertura.livro import snapshot
from cdp.cobertura.parametros import carregar_parametros
from cdp.cobertura.sinal import alpha_cobertura, m_frescor, valuation_gap, z_por_grupo
from cdp.config import load_config
from cdp.data.synthetic import make_synthetic_market
from cdp.research.factbook import com_fatos_valuation, fatos_valuation
from cdp.workflow.demo import DemoStore

D = date(2026, 10, 8)


@pytest.fixture(scope="module")
def snap(tmp_path_factory):
    md = make_synthetic_market(seed=7, as_of=D)
    book = tmp_path_factory.mktemp("sinal") / "book"
    executar_snapshot(book, DemoStore(md).load(D), D, offline=True,
                      agora=datetime(2026, 10, 8, 23, tzinfo=UTC), codigo={"git": None})
    return md, snapshot(book, D)


def test_valuation_gap_is_shadow_and_nan_without_target(snap):
    md, s = snap
    assert "valuation_gap" not in SIGNALS
    assert "valuation_gap" not in load_config().alpha.signal_weights
    z = valuation_gap(s)
    tab = s.tabela()
    sem = tab.index[tab["rating"].isin(["Sem preço-alvo", "Em revisão"])]
    assert len(sem) and z.reindex(sem).isna().all()
    assert z.dropna().abs().max() <= 3.0
    ids = list(md.universe.issuers.index)
    sg = valuation_gap_sombra(s, ids)
    assert list(sg.index) == ids and sg.name == "valuation_gap"
    assert valuation_gap_sombra(None, ids).isna().all()


def test_z_within_country_sector_groups():
    tab = pd.DataFrame({"alpha_rel": [0.1, 0.2, 0.3, 0.4, 0.5, 5.0, -5.0],
                        "rating": ["Neutro"] * 7, "pais": ["BR"] * 5 + ["MX", "MX"],
                        "setor": ["Utilities"] * 7}, index=list("abcdefg"))
    z = z_por_grupo(tab)
    assert z["c"] == pytest.approx(0.0) and z["a"] < 0 < z["e"]
    assert z.abs().max() <= 3.0


def test_alpha_translation_and_freshness(snap):
    _, s = snap
    params = carregar_parametros()
    assert m_frescor(10) == 1.0 and m_frescor(90) == pytest.approx(0.5) and m_frescor(200) == 0.0
    tab = s.tabela()
    sig = pd.Series(0.25, index=tab.index)
    a = alpha_cobertura(s, sig, params)
    ok = a.dropna()
    assert len(ok) > 0
    exp = 0.02 * ok["m_incerteza"] * ok["m_confianca"] * ok["m_frescor"] * 0.25 * ok["z"]
    assert np.allclose(ok["alpha"], exp)


def test_val_facts_from_open_model(snap):
    md, s = snap
    tab = s.tabela()
    iid = next(i for i in tab.index if tab.loc[i, "rating"] in ("Compra", "Neutro", "Venda"))
    mod = s.modelo(iid)
    f = fatos_valuation(mod, [], D)
    assert f[f"val.{iid}.preco_alvo"].unit == "preco"
    assert f[f"val.{iid}.preco_alvo"].formatted.startswith(("R$", "US$", "MXN", "CLP", "COP", "PEN", "ARS"))
    assert f[f"val.{iid}.rating_codigo"].formatted == tab.loc[iid, "rating"]
    assert f[f"val.{iid}.upside"].value == pytest.approx(mod["resumo"]["upside"])
    assert f[f"cob.{iid}.alvo_anterior"].value is None  # sem histórico ⇒ n/d, nunca zero
    fb = factbook_emissor(s, iid, md)
    assert f"val.{iid}.preco_alvo" in fb.facts and fb.is_synthetic
    assert any(k.startswith("etf.") for k in fb.facts)
    with pytest.raises(ValueError):
        com_fatos_valuation(fb.model_copy(update={"as_of": date(2026, 10, 1)}), s, [iid])
