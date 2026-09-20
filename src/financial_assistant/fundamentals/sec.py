"""Backend-only bounded SEC client, with a process-wide <=4 requests/sec limiter."""
from datetime import datetime, timezone
from hashlib import sha256
import json
import os
from pathlib import Path
import re
import threading
import time
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen
from uuid import uuid4
from .models import ProviderResponse
from .provider import FundamentalsUnavailable

_LOCK = threading.Lock()
_LAST = 0.0
MAX_BYTES = 40 * 1024 * 1024


def _throttle():
    global _LAST
    with _LOCK:
        time.sleep(max(0, .25 - (time.monotonic() - _LAST)))
        _LAST = time.monotonic()


class SECProvider:
    def __init__(self, cache_dir='.run/fundamentals', *, user_agent=None, timeout=10, retries=2):
        self.user_agent = user_agent or os.environ.get('SEC_USER_AGENT', '')
        if (len(self.user_agent.split()) < 2 or not re.search(r'@|https?://', self.user_agent)
                or '\n' in self.user_agent or '\r' in self.user_agent):
            raise FundamentalsUnavailable('SEC_USER_AGENT must declare application and contact information')
        self.cache_dir = Path(cache_dir)
        self.timeout = min(max(timeout, 1), 20)
        self.retries = min(max(retries, 0), 2)

    def _get(self, url, key):
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        path = self.cache_dir / f'{key}-v1.json'
        try:
            cached = json.loads(path.read_text())
            age = (datetime.now(timezone.utc) - datetime.fromisoformat(cached['retrieved_at'])).total_seconds()
            if 0 <= age < 86400:
                return cached
        except (OSError, ValueError, KeyError, TypeError):
            pass
        for attempt in range(self.retries + 1):
            _throttle()
            try:
                request = Request(url, headers={'User-Agent': self.user_agent, 'Accept': 'application/json'})
                deadline = time.monotonic() + self.timeout
                with urlopen(request, timeout=self.timeout) as stream:
                    chunks, size = [], 0
                    while True:
                        if time.monotonic() > deadline:
                            raise TimeoutError('SEC response deadline exceeded')
                        chunk = stream.read1(min(65536, MAX_BYTES + 1 - size))
                        if not chunk:
                            break
                        chunks.append(chunk)
                        size += len(chunk)
                        if size > MAX_BYTES:
                            raise FundamentalsUnavailable('SEC response exceeded size limit')
                raw = b''.join(chunks)
                result = dict(payload=json.loads(raw), retrieved_at=datetime.now(timezone.utc).isoformat(),
                              sha256=sha256(raw).hexdigest())
                temp = path.with_suffix(f'.{uuid4().hex}.tmp')
                temp.write_text(json.dumps(result))
                temp.replace(path)
                return result
            except HTTPError as exc:
                if exc.code not in (429, 500, 502, 503, 504):
                    break
            except (URLError, TimeoutError, OSError, ValueError):
                pass
            if attempt < self.retries:
                time.sleep(.5 * (attempt + 1))
        raise FundamentalsUnavailable('SEC retrieval unavailable after bounded attempts')

    def get_company_facts(self, ticker, as_of):
        ticker = ticker.upper().strip()
        if re.fullmatch(r'\d{1,10}', ticker):
            cik = ticker.zfill(10)
        else:
            mapping = self._get('https://www.sec.gov/files/company_tickers.json', 'tickers')['payload']
            matches = {str(row['cik_str']).zfill(10) for row in mapping.values() if row['ticker'].upper() == ticker}
            if len(matches) != 1:
                raise FundamentalsUnavailable('Ticker has no unambiguous SEC mapping')
            cik = matches.pop()
        facts = self._get(f'https://data.sec.gov/api/xbrl/companyfacts/CIK{cik}.json', f'{cik}-facts')
        submissions = self._get(f'https://data.sec.gov/submissions/CIK{cik}.json', f'{cik}-submissions')
        return ProviderResponse(ticker=ticker, cik=cik, facts=facts['payload'], submissions=submissions['payload'],
                                retrieved_at=datetime.fromisoformat(facts['retrieved_at']),
                                metadata={'provider': 'SEC EDGAR', 'raw_sha256': facts['sha256'],
                                          'cache_version': 'v1', 'selection_cutoff': as_of.isoformat()})
