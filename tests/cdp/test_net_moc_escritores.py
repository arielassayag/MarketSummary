"""DADOS SIMULADOS: fronteira NET decimal e autoridade dos novos escritores."""
from datetime import UTC, date, datetime
from pathlib import Path

import pytest

from cdp.config import load_config
from cdp.contracts import BookEntry, DailyPosition, DailyRecord, DailyRisk, Side
from cdp.workflow.book import Book
from cdp.workflow.net_moc import NetLimitExceeded, NetUnverifiable, compose, exact_net

ROOT = Path(__file__).resolve().parents[2]


def record(net=5., nav=100.):
    risk = DailyRisk(gross=.05, net=.05, long_exposure=.05, short_exposure=0,
                     n_long=1, n_short=0)
    pos = DailyPosition(issuer_id="SIM", ticker="SIM", currency="USD", side=Side.LONG,
                        market_value_usd=net, weight=.05, day_pnl_usd=0)
    return DailyRecord(date=date(2026, 11, 13), fund_name="DADOS SIMULADOS",
                       track_record_type="main", nav_start_usd=100, nav_end_usd=nav,
                       pnl_usd=nav-100, ret=(nav-100)/100, risk=risk, positions=[pos],
                       is_synthetic=True, data_notice="DADOS SIMULADOS",
                       prev_record_hash="0"*64)


@pytest.mark.parametrize("sign", [-1, 1])
def test_limite_decimal_inclusivo_lexema_imediatamente_menor_recusado(sign):
    rec = record(sign*5)
    assert exact_net(rec, '{"risk":{"net_exposure_max_abs":0.05}}')["passed"]
    with pytest.raises(NetLimitExceeded):
        exact_net(rec, '{"risk":{"net_exposure_max_abs":0.049999999999999999999999999999}}')


def test_nav_apos_custos_e_denominador_sem_epsilon():
    with pytest.raises(NetLimitExceeded):
        exact_net(record(nav=99.99), '{"risk":{"net_exposure_max_abs":0.05}}')


@pytest.mark.parametrize("raw", ['{}', '{"risk":{}}',
                                '{"risk":{"net_exposure_max_abs":null}}',
                                '{"risk":{"net_exposure_max_abs":true}}',
                                '{"risk":{"net_exposure_max_abs":-0.05}}',
                                '{"risk":{"net_exposure_max_abs":"NaN"}}'])
def test_limite_ausente_invalido_nao_vira_zero(raw):
    with pytest.raises(NetUnverifiable):
        exact_net(record(), raw)


@pytest.mark.parametrize("configured", [False, True])
def test_cfg_none_e_store_livre_nao_autorizam_nova_efetivacao(tmp_path, configured):
    cfg = load_config(ROOT / "configs/cdp/fund.yaml") if configured else None
    book = Book(tmp_path / "book", config=cfg, market_store=object())
    entry = BookEntry(week=date(2026, 11, 13), proposal_id="sem-origem",
                      approval_hash="0"*64, booked_at=datetime(2026, 11, 13, 20, tzinfo=UTC),
                      nav_usd=100, positions=[])
    before = list(book.root.rglob("*.json"))
    with pytest.raises(NetUnverifiable):
        compose(book, entry)
    assert list(book.root.rglob("*.json")) == before


def test_configuracao_legada_do_prior_e_leitura_propria_sem_autorizar_escrita(tmp_path):
    """A mesma recepção usada pelos priors main/sombra exige seu arquivo e hash.

    Proposta histórica de fixture; não chama save_booked nem cria autorização NET.
    """
    from test_book import make_proposal

    from cdp.config import config_json
    from cdp.hashing import sha256_text
    from cdp.workflow.net_moc import _configuration_of_prior

    cfg = load_config(Path(__file__).parent / 'fixtures/fund_legado.yaml')
    proposal = make_proposal().model_copy(update={'config_hash': cfg.config_hash()})
    book = Book(tmp_path / 'book')
    book.save_proposal(proposal)
    path = book.week_dir(proposal.week) / 'config_decisao.json'
    with pytest.raises(NetUnverifiable, match='configuração própria'):
        _configuration_of_prior(book, proposal)
    raw = config_json(cfg)
    path.write_text(raw)
    before = {p: p.read_bytes() for p in book.root.rglob('*') if p.is_file()}
    received = _configuration_of_prior(book, proposal)
    assert received['raw'] == raw and received['raw_sha256'] == sha256_text(raw)
    assert received['proposal_config_hash'] == proposal.config_hash
    assert {p: p.read_bytes() for p in book.root.rglob('*') if p.is_file()} == before
    path.write_text(raw.replace('100000000.0', '100000001.0'))
    assert path.read_text() != raw
    with pytest.raises(NetUnverifiable, match='configuração própria'):
        _configuration_of_prior(book, proposal)
