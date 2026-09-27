"""Regressões: falhas de rede não podem virar fatos; rota gratuita não pode cobrar."""
import json
import urllib.error
from datetime import UTC, datetime
from unittest.mock import MagicMock, patch

import pytest

from fechamento.live_fetcher import (
    build_live_market_package,
    fetch_awesomeapi_usd_brl,
    fetch_brasilapi_taxas,
    fetch_real_market_news,
    fetch_yahoo_chart,
)
from fechamento.providers.openrouter_provider import OpenRouterProvider


def response(payload):
    resp = MagicMock()
    resp.__enter__.return_value = resp
    resp.read.return_value = payload if isinstance(payload, bytes) else json.dumps(payload).encode()
    return resp


@pytest.mark.parametrize('call', [fetch_brasilapi_taxas, fetch_awesomeapi_usd_brl, lambda: fetch_yahoo_chart('NOEXIST.SA')])
def test_network_failure_never_returns_invented_values(call):
    with patch('urllib.request.urlopen', side_effect=urllib.error.URLError('offline')):
        with pytest.raises(RuntimeError):
            call()


@pytest.mark.parametrize('call,payload', [(fetch_brasilapi_taxas, []), (fetch_awesomeapi_usd_brl, {'USDBRL': {}})])
def test_empty_response_is_not_a_zero_or_fixed_quote(call, payload):
    with patch('urllib.request.urlopen', return_value=response(payload)):
        with pytest.raises(RuntimeError):
            call()


def test_yahoo_uses_previous_daily_bar_not_range_baseline():
    payload = {'chart': {'result': [{
        'meta': {'regularMarketPrice': 183476.86, 'chartPreviousClose': 185229,
                 'regularMarketTime': 1790367480, 'currency': 'BRL'},
        'timestamp': [1789995600, 1790082000, 1790168400, 1790254800, 1790341200],
        'indicators': {'quote': [{'close': [186596, 187423, 185814, 183966, 183477]}]},
    }]}}
    with patch('urllib.request.urlopen', return_value=response(payload)):
        data = fetch_yahoo_chart('^BVSP')
    assert data['previous_price'] == 183966
    assert data['reference_date'] == '2026-09-25'
    assert data['previous_session'] == '2026-09-24'
    assert data['observed_at'] == datetime.fromtimestamp(1790367480, UTC).isoformat()


def test_rss_preserves_publication_date_and_link():
    xml = b'''<rss><channel><item><title>Ibovespa</title><source>Agencia</source>
    <link>https://news.google.com/rss/articles/exemplo</link>
    <pubDate>Fri, 25 Sep 2026 19:00:00 GMT</pubDate></item></channel></rss>'''
    with patch('urllib.request.urlopen', return_value=response(xml)):
        news = fetch_real_market_news()
    assert news[0]['published_at'] == '2026-09-25T19:00:00+00:00'
    assert news[0]['url'] == 'https://news.google.com/rss/articles/exemplo'
    assert 'verificada' not in news[0]['body'].lower()


def test_failed_collection_leaves_no_valid_looking_package(tmp_path):
    target = tmp_path / 'failed'
    with patch('urllib.request.urlopen', side_effect=urllib.error.URLError('offline')):
        with pytest.raises(RuntimeError):
            build_live_market_package(target)
    assert not (target / 'manifest.json').exists()


def test_collection_refuses_to_overwrite_input(tmp_path):
    (tmp_path / 'quotes.csv').write_text('original')
    with pytest.raises((FileExistsError, ValueError)):
        build_live_market_package(tmp_path)
    assert (tmp_path / 'quotes.csv').read_text() == 'original'


def test_free_provider_default_request_has_zero_price_cap():
    payloads = []
    def record(req, **kwargs):
        payloads.append(json.loads(req.data))
        return response({'choices': [{'message': {'content': '{}'}}], 'usage': {'cost': 0}})
    with patch('urllib.request.urlopen', side_effect=record):
        OpenRouterProvider(api_key='test')._call_openrouter('test', 'test')
    assert payloads[0]['model'] == 'openrouter/free'
    assert payloads[0]['provider']['max_price'] == {'prompt': 0, 'completion': 0}


def test_free_fallback_on_missing_model_stays_free():
    payloads = []
    def record(req, **kwargs):
        payloads.append(json.loads(req.data))
        if len(payloads) == 1:
            raise urllib.error.HTTPError(req.full_url, 404, 'model removed', {}, None)
        return response({'choices': [{'message': {'content': '{}'}}], 'usage': {'cost': 0}})
    with patch('urllib.request.urlopen', side_effect=record):
        text, _, cost = OpenRouterProvider(api_key='test', model_name='removed/model:free')._call_openrouter('test', 'test')
    assert text == '{}'
    assert cost == 0
    assert [p['model'] for p in payloads] == ['removed/model:free', 'openrouter/free']
    assert all(p['provider']['max_price'] == {'prompt': 0, 'completion': 0} for p in payloads)


def test_cli_fetch_exists_and_missing_key_is_actionable(monkeypatch, capsys, tmp_path):
    from fechamento.__main__ import main
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr('sys.argv', ['fechamento', 'fetch', '--help'])
    with pytest.raises(SystemExit) as exc:
        main()
    assert exc.value.code == 0
    monkeypatch.setattr('sys.argv', ['fechamento', 'run', '--scenario-dir', str(tmp_path), '--provider', 'openrouter'])
    monkeypatch.delenv('OPENROUTER_API_KEY', raising=False)
    with patch('fechamento.providers.openrouter_provider.load_dotenv'):
        with pytest.raises(SystemExit) as exc:
            main()
    assert exc.value.code == 1
    assert 'OPENROUTER_API_KEY' in capsys.readouterr().err


def test_demo_without_news_does_not_assert_market_causes():
    from fechamento.evidence import organize_evidence
    from fechamento.ingestion import load_and_validate_package
    from fechamento.metrics import compute_all_metrics
    from fechamento.providers import DemoProvider, NarrativeRequest
    pkg = load_and_validate_package('data/demo/normal')
    ev = organize_evidence(compute_all_metrics(pkg.quotes, pkg.positions), pkg.manifest, [], [])
    draft = DemoProvider().generate(NarrativeRequest(factbook=ev.factbook, eligible_news=[])).draft
    text = ' '.join(p.text for p in draft.paragraphs)
    assert 'fluxos técnicos de liquidação' not in text
    assert 'recomposição de posições' not in text
    assert 'volatilidade externa observada' not in text
    assert 'SIMULAD' in text


def test_article_example_missing_key_exits_before_network(monkeypatch):
    import runpy
    monkeypatch.delenv('OPENROUTER_API_KEY', raising=False)
    with patch('dotenv.load_dotenv'), patch('urllib.request.urlopen', side_effect=AssertionError('rede proibida')):
        with pytest.raises(SystemExit, match='OPENROUTER_API_KEY'):
            runpy.run_path('examples/chamada_ia.py', run_name='__main__')


def test_article_example_sends_only_free_request(monkeypatch, capsys):
    import runpy
    monkeypatch.setenv('OPENROUTER_API_KEY', 'test-only')
    def api(req, **kwargs):
        payload = json.loads(req.data)
        assert payload['model'] == 'openrouter/free'
        assert payload['provider']['max_price'] == {'prompt': 0, 'completion': 0}
        return response({'choices': [{'message': {'content': 'Dados fictícios.'}}]})
    with patch('dotenv.load_dotenv'), patch('urllib.request.urlopen', side_effect=api):
        runpy.run_path('examples/chamada_ia.py', run_name='__main__')
    assert 'Dados fictícios.' in capsys.readouterr().out


def test_article_example_rejects_truncated_response(monkeypatch, capsys):
    import runpy
    monkeypatch.setenv('OPENROUTER_API_KEY', 'test-only')
    payload = {'choices': [{'finish_reason': 'length', 'message': {'content': 'Texto cortado'}}]}
    with patch('dotenv.load_dotenv'), patch('urllib.request.urlopen', return_value=response(payload)):
        with pytest.raises(SystemExit, match='incompleta'):
            runpy.run_path('examples/chamada_ia.py', run_name='__main__')
    assert 'Texto cortado' not in capsys.readouterr().out


def test_provider_rejects_truncated_json_even_when_parseable():
    payload = {'choices': [{'finish_reason': 'length', 'message': {'content': '{"paragraphs": []}'}}]}
    with patch('urllib.request.urlopen', return_value=response(payload)):
        with pytest.raises(ValueError, match='incompleta'):
            OpenRouterProvider(api_key='test')._call_openrouter('system', 'user')


def test_json_repair_keeps_original_factbook():
    from fechamento.evidence import organize_evidence
    from fechamento.ingestion import load_and_validate_package
    from fechamento.metrics import compute_all_metrics
    from fechamento.providers import NarrativeRequest
    pkg = load_and_validate_package('data/demo/normal')
    ev = organize_evidence(compute_all_metrics(pkg.quotes, pkg.positions), pkg.manifest, pkg.eligible_news, [])
    prompts = []
    def answer(system, user):
        prompts.append(user)
        if len(prompts) == 1:
            return 'safe', {}, 0
        return '{"paragraphs":[{"paragraph_id":1,"text":"IBOV: {{fact:ibov.return_pct}}.","claim_type":"factual"}]}', {}, 0
    provider = OpenRouterProvider(api_key='test')
    with patch.object(provider, '_call_openrouter', side_effect=answer):
        result = provider.generate(NarrativeRequest(factbook=ev.factbook, eligible_news=ev.eligible_news))
    assert result.success
    assert 'ibov.return_pct' in prompts[1]
    assert 'CATÁLOGO DE FATOS DISPONÍVEIS' in prompts[1]
