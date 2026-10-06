"""Compatibilidade do ``config_hash`` entre versões do esquema da configuração (W0).

O hash da configuração entra na aprovação de cada decisão e é recalculado pelo booking, pela tese
e pelo painel. Regras testadas (ver docstring de ``cdp.config``):

- o mandato da inception (2026-10-05) está arquivado em ``configs/cdp/historico/<hash>.json`` e
  reproduz o hash gravado na proposta, byte a byte, com o esquema ATUAL;
- campos novos no valor legado saem do dump (hash e ``config_decisao.json`` inalterados); fora do
  valor legado entram no hash;
- arquivos arquivados são autenticados pelo hash do JSON BRUTO antes da validação, então uma
  mudança futura de esquema não os torna "divergentes" (``decision_config``);
- os padrões legados são inertes: o otimizador, com o mandato da inception, produz exatamente os
  pesos do código anterior ao W0 (golden gerado com esse código; DADOS SIMULADOS).
"""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from cdp.analytics.panel import build_asset_panel
from cdp.config import FundConfig, load_config
from cdp.data.synthetic import make_synthetic_market
from cdp.hashing import sha256_obj
from cdp.portfolio.costs import build_cost_model
from cdp.portfolio.optimizer import build_asset_constraints, model_implied_betas, optimize
from cdp.risk.types import STYLE_FACTORS, RiskModel, country_factor, sector_factor

ROOT = Path(__file__).resolve().parents[2]
INCEPTION_HASH = "5b8bdd690f10bf79488a78f22787d60fd4de05eef791166dfae1426de551abda"
ARCHIVE = ROOT / "configs" / "cdp" / "historico" / f"{INCEPTION_HASH}.json"
GOLDEN = Path(__file__).parent / "golden" / "config_compat_optimizer.json"
NAV = 100_000_000.0
AS_OF = date(2026, 10, 2)

# Campos novos -> um valor FORA do legado (cada um precisa mudar o hash).
NEW_FIELDS = [
    ("risk", "idio_share_goal", 0.90),
    ("risk", "idio_share_floor", 0.85),
    ("risk", "factor_risk_basis", "achieved"),
    ("risk", "factor_risk_aversion_multiplier", 5.0),
    ("risk", "second_order_inflation", 1.25),
    ("risk", "idio_gate_models", ("decisao", "base")),
    ("risk", "operational", {}),
    ("risk_model", "macro_factors", ("BZ=F", "HG=F", "GC=F", "DX-Y.NYB")),
    ("risk_model", "macro_beta_halflife", 63),
    ("risk_model", "min_names_per_country", 5),
]


def _raw_archive() -> dict:
    return json.loads(ARCHIVE.read_text(encoding="utf-8"))


# ----------------------------------------------------------------------------- arquivo


def test_inception_mandate_archive_reproduces_its_hash():
    """O arquivo tem o nome do hash, o hash do JSON bruto confere e o esquema atual relê e
    regrava o MESMO texto (convenção de ``config_decisao.json``: sem sort_keys, indentado)."""
    from cdp.config import archived_config, config_json, load_archived_config

    raw = _raw_archive()
    assert sha256_obj(raw) == INCEPTION_HASH
    cfg = FundConfig.model_validate(raw)
    assert cfg.config_hash() == INCEPTION_HASH
    assert config_json(cfg) == ARCHIVE.read_text(encoding="utf-8")
    assert cfg.model_dump(mode="json") == raw  # nenhum campo novo aparece no valor legado
    found = load_archived_config(ARCHIVE, INCEPTION_HASH)
    assert found is not None and found.hash == INCEPTION_HASH and found.cfg == cfg
    via_dir = archived_config(INCEPTION_HASH, ARCHIVE.parent)
    assert via_dir is not None and via_dir.cfg == cfg and via_dir.origem == ARCHIVE


def test_every_archived_mandate_matches_its_file_name():
    files = sorted(ARCHIVE.parent.glob("*.json"))
    assert ARCHIVE in files
    for f in files:
        raw = json.loads(f.read_text(encoding="utf-8"))
        assert sha256_obj(raw) == f.stem, f.name
        assert FundConfig.model_validate(raw).config_hash() == f.stem, f.name


def test_live_config_round_trips_through_archive_text(tmp_path):
    from cdp.config import config_json, load_archived_config

    cfg = load_config(ROOT / "configs" / "cdp" / "fund.yaml")
    path = tmp_path / "config_decisao.json"
    path.write_text(config_json(cfg), encoding="utf-8")
    found = load_archived_config(path, cfg.config_hash())
    assert found is not None and found.cfg == cfg and found.cfg.config_hash() == found.hash


# ----------------------------------------------------------------------------- campos novos


def test_new_fields_are_omitted_at_legacy_values():
    from cdp.config import RiskModelSection, RiskSection

    dump = FundConfig().model_dump(mode="json")
    assert "execution" not in dump
    assert not set(RiskSection.LEGACY_DEFAULTS) & set(dump["risk"])
    assert not set(RiskModelSection.LEGACY_DEFAULTS) & set(dump["risk_model"])
    # Os valores legados declarados são os padrões dos campos (nada "inerte" por acaso).
    for section in (RiskSection, RiskModelSection):
        for name, legacy in section.LEGACY_DEFAULTS.items():
            assert section.model_fields[name].get_default(call_default_factory=True) == legacy


def test_explicit_legacy_values_keep_the_hash():
    cfg = FundConfig.model_validate(_raw_archive())
    same = cfg.with_overrides({
        "fund": {"rebalance_weekday": "MON"},
        "risk": {"idio_share_goal": None, "idio_share_floor": None, "factor_risk_basis": "target",
                 "factor_risk_aversion_multiplier": 0.0, "second_order_inflation": 1.0,
                 "idio_gate_models": ["decisao"], "operational": None},
        "risk_model": {"macro_factors": [], "macro_beta_halflife": 126,
                       "min_names_per_country": None},
    })
    assert same == cfg and same.config_hash() == INCEPTION_HASH


@pytest.mark.parametrize(("section", "name", "value"), NEW_FIELDS)
def test_new_field_outside_legacy_changes_hash_and_round_trips(section, name, value):
    from cdp.config import config_json, load_archived_config

    base = FundConfig.model_validate(_raw_archive())
    if section == "risk" and name == "idio_share_floor":
        changed = base.with_overrides({section: {"idio_share_goal": 0.9, name: value}})
    else:
        changed = base.with_overrides({section: {name: value}})
    assert changed.config_hash() != INCEPTION_HASH
    assert name in changed.model_dump(mode="json")[section]
    raw = json.loads(config_json(changed))
    assert FundConfig.model_validate(raw) == changed
    assert sha256_obj(raw) == changed.config_hash()
    assert load_archived_config  # importado: contrato público


def test_execution_section_is_optional_and_validated():
    from pydantic import ValidationError

    from cdp.config import ExecutionSection

    base = FundConfig.model_validate(_raw_archive())
    with pytest.raises(ValidationError):  # regra nova sem parâmetros de execução
        base.with_overrides({"fund": {"rebalance_weekday": "LAST_US_SESSION"}})
    new = base.with_overrides({"fund": {"rebalance_weekday": "LAST_US_SESSION"}, "execution": {}})
    assert new.execution == ExecutionSection()
    assert new.config_hash() != INCEPTION_HASH
    ex = new.execution
    assert ex.rebalance_calendar == "XNYS" and ex.decision_deadline_cap_local == "15:00"
    assert ex.capacity.auction_participation == 0.10 and ex.max_closes == 1
    assert ex.close_times["XBOG"].close is None  # horário não verificado: linha inelegível
    with pytest.raises(KeyError):
        base.with_overrides({"inexistente": {}})
    for bad in ({"decision_deadline_cap_local": "15h"},
                {"close_times": {"XNYS": {"tz": "Lua/Base", "close": "16:00"}}},
                {"close_times": {"XNYS": {"tz": "America/New_York", "close": "25:00"}}},
                {"close_times": {"BVMF": {"tz": "America/New_York", "close": "16:00"}}},
                {"capacity": {"auction_participation": 0.2}},
                {"max_closes": 6},
                {"close_impact_discount": {"BR": 1.5}}):
        with pytest.raises(ValidationError):
            ExecutionSection.model_validate(bad)


# Bloco de ativação da regra nova como escrito no DESIGN §D.3 (o commit de ativação o copia
# literalmente para ``fund.yaml``), com a data de início de §15.1.
ACTIVATION_YAML = """
fund:
  inception_date: "2026-10-09"
  rebalance_weekday: LAST_US_SESSION
  rebalance_rule: "último pregão da semana na NYSE (sexta-feira, ou o dia útil anterior em feriado nos EUA)"
  execution_convention: "Decisão antes do fechamento com todos os dados até o momento da análise; ordens em quantidade de ações; execução ao preço oficial de fechamento de cada linha (MOC), limitada à capacidade do leilão e da janela pré-fechamento; linha sem pregão não negocia"
  weekly_research_start_local: "11:00"
  decision_deadline_local: "15:00"
  primary_calendar: BVMF
execution:
  rebalance_calendar: XNYS
  decision_deadline_cap_local: "15:00"
  decision_buffer_minutes: 45
  close_times:
    XNYS: {tz: America/New_York, close: "16:00", moc_cutoff: "15:50"}
    XNAS: {tz: America/New_York, close: "16:00", moc_cutoff: "15:55"}
    ARCX: {tz: America/New_York, close: "16:00", moc_cutoff: "15:50"}
    BVMF: {tz: America/New_York, close: "16:00", moc_cutoff: "15:55"}
    XMEX: {tz: America/New_York, close: "16:00", moc_cutoff: "15:40"}
    XSGO: {tz: America/Santiago, close: "16:00", moc_cutoff: "15:55"}
    XBOG: {tz: America/Bogota, close: "verificar"}
    XLIM: {tz: America/Lima, close: "verificar"}
    XBUE: {tz: America/Argentina/Buenos_Aires, close: "17:00", moc_cutoff: "16:50"}
  capacity:
    adv_statistic: p25
    adv_window_days: 20
    auction_participation: 0.10
    preclose_participation: 0.10
    preclose_volume_share: 0.25
    auction_share: {US_STOCK: 0.10, ADR: 0.06, ETF_US: 0.01, BR: 0.08, MX: 0.10, CL: 0.10, CO: 0.05, PE: 0.05, AR: 0.05}
    short_multiplier: 0.75
    early_close_multiplier: 0.5
  min_trade_weight: 0.0005
  local_closed_policy: adr_if_eligible_else_freeze
  early_close_mode: capacity_half
  max_closes: 1
  fill_volume_source: realized_daily
  close_impact_discount: {US_STOCK: 0.6, ADR: 0.6, BR: 0.6, MX: 0.6, CL: 0.6, ETF_US: 1.0, CO: 1.0, PE: 1.0, AR: 1.0}
  closed_home_market_spread_mult: 1.5
"""


def test_activation_block_of_the_design_loads_with_the_live_mandate(tmp_path):
    """O bloco ``execution`` do §D.3, copiado literalmente sobre o ``fund.yaml`` vigente com
    ``LAST_US_SESSION``, carrega; ``"verificar"`` vira horário não verificado (``None``) e o
    mandato ativado sobrevive ao arquivamento pelo hash bruto."""
    import yaml

    from cdp.config import ExecutionSection, config_json, load_archived_config

    live = yaml.safe_load((ROOT / "configs" / "cdp" / "fund.yaml").read_text(encoding="utf-8"))
    block = yaml.safe_load(ACTIVATION_YAML)
    live["fund"].update(block["fund"])
    live["execution"] = block["execution"]
    path = tmp_path / "fund.yaml"
    path.write_text(yaml.safe_dump(live, allow_unicode=True, sort_keys=False), encoding="utf-8")
    cfg = load_config(path)
    assert cfg.fund.rebalance_weekday == "LAST_US_SESSION"
    assert cfg.fund.inception_date == date(2026, 10, 9)
    ex = cfg.execution
    assert ex is not None and ex.rebalance_calendar == "XNYS"
    for mic in ("XBOG", "XLIM"):
        assert ex.close_times[mic].close is None and ex.close_times[mic].moc_cutoff is None
    assert ex.close_times["XNYS"].close == "16:00" and ex.close_times["XMEX"].moc_cutoff == "15:40"
    # Os valores do §D.3 são os padrões da seção (o bloco documenta, não recalibra).
    assert ex == ExecutionSection()
    dump = cfg.model_dump(mode="json")
    assert dump["execution"]["close_times"]["XBOG"] == {"tz": "America/Bogota", "close": None,
                                                         "moc_cutoff": None}
    assert cfg.config_hash() != INCEPTION_HASH
    arq = tmp_path / "config_decisao.json"
    arq.write_text(config_json(cfg), encoding="utf-8")
    found = load_archived_config(arq, cfg.config_hash())
    assert found is not None and found.cfg == cfg


def test_risk_section_new_validations():
    from pydantic import ValidationError

    from cdp.config import OperationalLimits, RiskModelSection, RiskSection

    with pytest.raises(ValidationError):
        RiskSection(idio_share_goal=0.85, idio_share_floor=0.90)
    with pytest.raises(ValidationError):
        RiskSection(idio_gate_models=("decisao", "decisao"))
    with pytest.raises(ValidationError):
        RiskSection(idio_gate_models=())
    with pytest.raises(ValidationError):
        RiskSection(second_order_inflation=0.9)
    with pytest.raises(ValidationError):
        RiskModelSection(macro_factors=("BZ=F", "BZ=F"))
    op = OperationalLimits()
    assert (op.beta, op.style, op.sector_net, op.commodity_beta) == (0.02, 0.05, 0.015, 0.01)
    assert op.country_net_limit("BR") == 0.01 and op.country_net_limit("CL") == 0.005
    assert OperationalLimits(country_net={"BR": 0.01}).country_net_limit("CL") is None
    with pytest.raises(ValidationError):
        OperationalLimits(country_net={"BR": -0.01})


# ----------------------------------------------------------------------------- caminho do hash bruto


def test_raw_hash_path_survives_a_later_schema_change(tmp_path, monkeypatch):
    """Arquivo gravado no esquema N; no esquema N+1 um campo novo passa a aparecer no dump (aqui
    simulado retirando a omissão do valor legado). ``cfg.config_hash()`` muda, mas o arquivo
    continua autenticado pelo hash bruto e reconstrói a mesma configuração."""
    from cdp.config import RiskSection, config_json, load_archived_config
    from cdp.workflow.tese_analise import decision_config

    cfg_n = FundConfig.model_validate(_raw_archive())
    week = tmp_path / "book" / "2026-10-05"
    week.mkdir(parents=True)
    (week / "config_decisao.json").write_text(config_json(cfg_n), encoding="utf-8")
    monkeypatch.setattr(RiskSection, "LEGACY_DEFAULTS", {})  # esquema N+1
    reloaded = FundConfig.model_validate(_raw_archive())
    assert reloaded.config_hash() != INCEPTION_HASH  # o dump revalidado mudou
    found = load_archived_config(week / "config_decisao.json", INCEPTION_HASH)
    assert found is not None and found.hash == INCEPTION_HASH and found.cfg == reloaded
    dec = decision_config(week, INCEPTION_HASH, historico=tmp_path / "vazio")
    assert dec is not None and dec.origem == week / "config_decisao.json"


def test_load_archived_config_rejects_tampering_and_bad_input(tmp_path):
    from cdp.config import archived_config, config_json, load_archived_config

    good = tmp_path / f"{INCEPTION_HASH}.json"
    good.write_text(ARCHIVE.read_text(encoding="utf-8"), encoding="utf-8")
    assert load_archived_config(good, INCEPTION_HASH) is not None
    assert load_archived_config(good, "f" * 64) is None                # hash diferente
    assert load_archived_config(good, "../" + INCEPTION_HASH) is None  # não é hash
    assert load_archived_config(tmp_path / "nada.json", INCEPTION_HASH) is None
    tampered = _raw_archive()
    tampered["risk"]["vol_target_annual"] = 0.06
    bad = tmp_path / "adulterado.json"
    bad.write_text(json.dumps(tampered), encoding="utf-8")
    assert load_archived_config(bad, INCEPTION_HASH) is None
    invalid = {"risk": {"vol_target_annual": "alto"}}  # hash confere, esquema não valida
    inv = tmp_path / "invalido.json"
    inv.write_text(json.dumps(invalid), encoding="utf-8")
    assert load_archived_config(inv, sha256_obj(invalid)) is None
    (tmp_path / "x.json").write_text("{nao json", encoding="utf-8")
    assert load_archived_config(tmp_path / "x.json", INCEPTION_HASH) is None
    assert archived_config("nao-hash", tmp_path) is None
    assert config_json(FundConfig()).endswith("}\n")


def test_decision_config_prefers_the_week_file_then_the_archive(tmp_path):
    from cdp.config import config_json
    from cdp.workflow.tese_analise import decision_config

    base = FundConfig.model_validate(_raw_archive())
    other = base.with_overrides({"risk": {"max_factor_risk_share": 0.10}})
    hist = tmp_path / "historico"
    hist.mkdir()
    (hist / f"{INCEPTION_HASH}.json").write_text(ARCHIVE.read_text(encoding="utf-8"),
                                                 encoding="utf-8")
    week = tmp_path / "2026-10-05"
    week.mkdir()
    # Sem config_decisao.json (caso real da inception): cai no histórico.
    dec = decision_config(week, INCEPTION_HASH, historico=hist)
    assert dec is not None and dec.cfg == base and dec.origem == hist / f"{INCEPTION_HASH}.json"
    # Arquivo da semana com o hash da proposta tem prioridade.
    (week / "config_decisao.json").write_text(config_json(other), encoding="utf-8")
    dec2 = decision_config(week, other.config_hash(), historico=hist)
    assert dec2 is not None and dec2.cfg == other and dec2.origem == week / "config_decisao.json"
    # Arquivo da semana com outro hash não bloqueia o histórico; nada confere ⇒ None.
    assert decision_config(week, INCEPTION_HASH, historico=hist).origem.parent == hist
    assert decision_config(week, "e" * 64, historico=hist) is None
    # Pasta padrão: configs/cdp/historico do repositório que contém o livro (irmão de book/).
    repo = tmp_path / "clone"
    (repo / "configs" / "cdp" / "historico").mkdir(parents=True)
    (repo / "configs" / "cdp" / "historico" / f"{INCEPTION_HASH}.json").write_text(
        ARCHIVE.read_text(encoding="utf-8"), encoding="utf-8")
    (repo / "book" / "2026-10-05").mkdir(parents=True)
    dec3 = decision_config(repo / "book" / "2026-10-05", INCEPTION_HASH)
    assert dec3 is not None and dec3.origem.parent == repo / "configs" / "cdp" / "historico"
    # Livro fora do repositório (demonstração, cópia): não herda o histórico do código.
    assert decision_config(tmp_path / "outro" / "book" / "2026-10-05", INCEPTION_HASH) is None


def test_inception_week_of_the_repository_resolves_the_archive():
    """O livro versionado (sem ``config_decisao.json`` na inception) encontra o mandato no
    histórico irmão — o caso real que a regra corrige (só leitura)."""
    from cdp.config import book_historico_dir
    from cdp.workflow.tese_analise import decision_config

    assert book_historico_dir(ROOT / "book") == ARCHIVE.parent
    week = ROOT / "book" / "2026-10-05"
    if not (week / "proposal_v1.json").is_file():
        pytest.skip("livro da inception ausente neste clone")
    proposal = json.loads((week / "proposal_v1.json").read_text(encoding="utf-8"))
    assert proposal["config_hash"] == INCEPTION_HASH
    dec = decision_config(week, proposal["config_hash"])
    assert dec is not None and dec.hash == INCEPTION_HASH


# ----------------------------------------------------------------------------- inércia no otimizador


def _sides(panel) -> pd.DataFrame:
    rows = {}
    for iid, g in panel.lines.groupby("issuer_id"):
        g = g.assign(_adr=(g["line_type"] != "LOCAL").astype(int))
        g = g.sort_values(["adtv_usd", "_adr"], ascending=[False, False])
        lg = g.iloc[0]
        row = dict(long_ticker=lg.name, long_line_type=lg["line_type"],
                   long_currency=lg["currency"], adtv_long_usd=lg["adtv_usd"])
        sh = g[(g["line_type"] != "LOCAL") | (g["market"] == "BR")]
        if len(sh):
            s = sh.iloc[0]
            row.update(short_ticker=s.name, short_line_type=s["line_type"],
                       short_currency=s["currency"], adtv_short_usd=s["adtv_usd"],
                       can_short=True, borrow_fee_annual=0.006, fee_source="SIMULADO")
        else:
            row.update(short_ticker=np.nan, short_line_type=np.nan, short_currency=np.nan,
                       adtv_short_usd=np.nan, can_short=False, borrow_fee_annual=np.nan,
                       fee_source="")
        rows[iid] = row
    return pd.DataFrame.from_dict(rows, orient="index").rename_axis("issuer_id")


def _model(assets: pd.DataFrame, seed: int = 3) -> RiskModel:
    rng = np.random.default_rng(seed)
    ids = list(assets.index)
    countries = sorted(assets["country"].unique())
    sectors = sorted(assets["sector"].unique())
    cols = (["market"] + [country_factor(c) for c in countries]
            + [sector_factor(s) for s in sectors] + STYLE_FACTORS)
    B = pd.DataFrame(0.0, index=ids, columns=cols)
    B["market"] = 1.0
    for i in ids:
        B.loc[i, country_factor(assets.loc[i, "country"])] = 1.0
        B.loc[i, sector_factor(assets.loc[i, "sector"])] = 1.0
    for s in STYLE_FACTORS:
        B[s] = rng.normal(0.0, 1.0, len(ids))
    var = {"market": 0.20 ** 2}
    var.update({country_factor(c): 0.12 ** 2 for c in countries})
    var.update({sector_factor(s): 0.07 ** 2 for s in sectors})
    var.update({s: 0.04 ** 2 for s in STYLE_FACTORS})
    sd = np.sqrt([var[c] for c in cols])
    corr = np.full((len(cols), len(cols)), 0.1) + 0.9 * np.eye(len(cols))
    F = pd.DataFrame(corr * np.outer(sd, sd), index=cols, columns=cols)
    D = pd.Series(rng.uniform(0.28, 0.45, len(ids)) ** 2, index=ids)
    groups = {c: "market" if c == "market" else c.split(":")[0] if ":" in c else "style"
              for c in cols}
    return RiskModel(as_of=AS_OF, exposures=B, factor_cov=F, specific_var=D,
                     factor_returns=pd.DataFrame(), specific_returns=pd.DataFrame(),
                     factor_groups=groups)


def optimizer_weights(cfg: FundConfig) -> dict[str, float]:
    """Pesos da inception otimizada num mercado sintético fixo (só APIs anteriores ao W0, para
    que o golden possa ser gerado com o código antigo)."""
    md = make_synthetic_market(seed=11, start=date(2024, 1, 2))
    panel = build_asset_panel(md, cfg)
    assets = panel.assets
    sides = _sides(panel)
    model = _model(assets)
    market_w = assets["market_cap_usd"]
    betas = model_implied_betas(model, market_w)
    cov = model.cov_matrix()
    daily_vol = pd.Series(np.sqrt(np.diag(cov)) / np.sqrt(252), index=cov.index)
    alpha = pd.Series(np.random.default_rng(5).normal(0.0, 0.15, len(assets)), index=assets.index)
    squeeze = pd.DataFrame({"squeeze_score": 20.0, "bucket": "LOW"}, index=assets.index)
    views = pd.DataFrame({"no_short": False, "no_long": False, "max_abs_weight": np.nan},
                         index=assets.index)
    cm = build_cost_model(sides, assets, daily_vol, cfg, NAV)
    cons = build_asset_constraints(list(assets.index), sides, squeeze, views, betas, assets, cfg,
                                   NAV, None, True)
    res = optimize(alpha, model, cons, cm, cfg, NAV, None, True, market_w)
    return {str(k): round(float(v), 10) for k, v in res.weights.items()}


def test_legacy_defaults_are_inert_in_the_optimizer():
    """Com o mandato da inception (arquivado), o otimizador do código atual reproduz os pesos do
    código anterior ao W0 — e escrever os campos novos no valor legado não muda nada."""
    golden = json.loads(GOLDEN.read_text(encoding="utf-8"))
    assert golden["config_hash"] == INCEPTION_HASH
    assert "DADOS SIMULADOS" in golden["aviso"]
    cfg = FundConfig.model_validate(_raw_archive())
    explicit = cfg.with_overrides({
        "risk": {"factor_risk_basis": "target", "factor_risk_aversion_multiplier": 0.0,
                 "second_order_inflation": 1.0, "idio_gate_models": ["decisao"]},
        "risk_model": {"macro_factors": [], "min_names_per_country": None}})
    got = optimizer_weights(cfg)
    assert optimizer_weights(explicit) == got
    names = sorted(set(got) | set(golden["weights"]))
    a = np.array([got.get(n, 0.0) for n in names])
    b = np.array([golden["weights"].get(n, 0.0) for n in names])
    assert np.abs(b).sum() > 0.4  # carteira de verdade (gross relevante), não um vetor nulo
    np.testing.assert_allclose(a, b, rtol=0, atol=1e-6)
