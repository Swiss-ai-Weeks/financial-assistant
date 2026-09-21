"""Transport safety tests: fake streams only, never live SEC calls."""
from datetime import datetime, timezone
import io
import json
from unittest.mock import Mock
from urllib.error import HTTPError

import pytest
from financial_assistant.fundamentals.sec import SECProvider
from financial_assistant.fundamentals.provider import FundamentalsUnavailable
from financial_assistant.fundamentals.service import FundamentalsService

D = datetime(2024,3,1,tzinfo=timezone.utc)


def test_requires_declared_agent(monkeypatch, tmp_path):
    monkeypatch.delenv('SEC_USER_AGENT', raising=False)
    with pytest.raises(FundamentalsUnavailable, match='SEC_USER_AGENT'):
        SECProvider(tmp_path)


def test_cache_still_applies_cutoff(monkeypatch, tmp_path):
    from pathlib import Path
    root = Path(__file__).parent/'fixtures/fundamentals'
    payloads = [dict(a=dict(ticker='AAA',cik_str=1)), json.loads((root/'companyfacts.json').read_text()),
                json.loads((root/'submissions.json').read_text())]
    requests = []
    def open_fake(request, timeout):
        requests.append((request,timeout))
        return io.BytesIO(json.dumps(payloads[len(requests)-1]).encode())
    monkeypatch.setattr('financial_assistant.fundamentals.sec.urlopen', open_fake)
    monkeypatch.setattr('financial_assistant.fundamentals.sec._throttle', lambda: None)
    provider = SECProvider(tmp_path, user_agent='Fixture application contact@example.invalid')
    service = FundamentalsService(provider)
    first = service.calculate_metrics('AAA', D)
    second = service.calculate_metrics('AAA', datetime(2025,6,1,tzinfo=timezone.utc))
    assert len(requests) == 3
    assert all(request.get_header('User-agent') == 'Fixture application contact@example.invalid' and timeout <= 20 for request, timeout in requests)
    assert len(list(tmp_path.glob('*.json'))) == 3
    def revenue(bundle):
        return next(f.value for f in bundle.facts if f.concept == 'revenue' and f.period_end.year == 2022)
    assert revenue(first) == 1000 and revenue(second) == 1700
    assert all('contact@example.invalid' not in b.model_dump_json() for b in (first, second))


@pytest.mark.parametrize('code,expected', [(403,1),(429,3),(503,3)])
def test_bounded_retry(monkeypatch, tmp_path, code, expected):
    transport = Mock(side_effect=HTTPError('https://data.sec.gov', code, 'failure', {}, None))
    monkeypatch.setattr('financial_assistant.fundamentals.sec.urlopen', transport)
    monkeypatch.setattr('financial_assistant.fundamentals.sec._throttle', lambda: None)
    monkeypatch.setattr('financial_assistant.fundamentals.sec.time.sleep', lambda _: None)
    provider = SECProvider(tmp_path, user_agent='Fixture contact@example.invalid', retries=100, timeout=100)
    with pytest.raises(FundamentalsUnavailable):
        provider.get_company_facts('1', D)
    assert transport.call_count == expected and provider.timeout == 20


def test_response_size_is_bounded(monkeypatch, tmp_path):
    monkeypatch.setattr('financial_assistant.fundamentals.sec.MAX_BYTES', 10)
    monkeypatch.setattr('financial_assistant.fundamentals.sec._throttle', lambda: None)
    monkeypatch.setattr('financial_assistant.fundamentals.sec.urlopen', lambda *a, **kw: io.BytesIO(b'x'*11))
    with pytest.raises(FundamentalsUnavailable, match='size limit'):
        SECProvider(tmp_path, user_agent='Fixture contact@example.invalid').get_company_facts('1', D)


def test_rate_limiter_waits_for_quarter_second(monkeypatch):
    import financial_assistant.fundamentals.sec as sec
    monkeypatch.setattr(sec, '_LAST', 10.0)
    monkeypatch.setattr(sec.time, 'monotonic', lambda: 10.05)
    sleep = Mock()
    monkeypatch.setattr(sec.time, 'sleep', sleep)
    sec._throttle()
    assert sleep.call_args.args[0] == pytest.approx(.2, abs=1e-10)
