"""Discovery regression fixtures never require a live Yahoo connection."""
import json
from unittest.mock import Mock

from financial_assistant import instruments
from financial_assistant.newsflow import NewsRepository, YahooNewsSource, news_feed, admissible_headlines, company_aliases
from financial_assistant.retrieval.archive import ArchiveSearchProvider


def quote(ticker='CRWV'):
    return dict(symbol=ticker, longname='CoreWeave, Inc.', quoteType='EQUITY')


def test_search_catalog_dynamic_dedup_and_outage(monkeypatch):
    catalog = [dict(identity='NVDA', ticker='NVDA', name='NVIDIA', universes=['nasdaq100'], memberships=[{'universe':'nasdaq100'}])]
    monkeypatch.setattr(instruments, 'catalog', lambda: catalog)
    result = instruments.resolve('NVDA', searcher=lambda *_: [quote('NVDA'), quote('NVDA')])
    assert len(result['securities']) == 1
    assert result['securities'][0]['catalogued']
    result = instruments.resolve('CRWV', searcher=lambda *_: [quote(), quote()], market_tickers=set(), fit_tickers=set())
    assert len(result['securities']) == 1
    security = result['securities'][0]
    assert security['name'] == 'CoreWeave, Inc.'
    assert security['dynamically_resolved'] and not security['catalogued']
    assert security['universes'] == security['memberships'] == []
    assert security['coverage'] == dict(market_cache=False, precomputed_pairs=False)
    assert len(catalog) == 1
    result = instruments.resolve('NVDA', searcher=Mock(side_effect=RuntimeError('offline')))
    assert result['yahoo_status'] == 'unavailable' and len(result['securities']) == 1
    assert instruments.resolve(' ', searcher=Mock(side_effect=AssertionError()))['securities'] == []


def story(id, title='CoreWeave earnings', stamp='2026-09-18T10:00:00Z', **kw):
    return dict(news_id=id, ticker='CRWV', title=title, published_at=stamp,
                url=f'https://publisher.example/{id}', summary='', source='fixture', **kw)


def repository(tmp_path, remote):
    archive = tmp_path/'archive'
    archive.mkdir()
    return NewsRepository(tmp_path/'cache', yahoo=remote, archive_dir=archive, cache_seconds=0)


def test_merge_rank_dedup_cutoff_and_source_outage(tmp_path):
    remote = Mock()
    remote.fetch.return_value = [story('duplicate', title='COREWEAVE earnings!', publisher='Wire'),
        story('passing', title='Market news', stamp='2026-09-18T11:59:00Z'),
        story('future', stamp='2026-09-19T10:00:00Z', title='CoreWeave future headline')]
    repo = repository(tmp_path, remote)
    rows = [story('archive', summary_unused='x'), story('date', title='CoreWeave date uncertain', stamp='2026-09-18'),
            story('summary', title='Shares fall', stamp='2026-09-18T11:00:00Z')]
    rows[0]['summary'] = 'Fuller archive summary'
    rows[2]['summary'] = 'CoreWeave mentioned in passing'
    (repo.archive_dir/'CRWV.jsonl').write_text('\n'.join(map(json.dumps, rows)))
    feed = news_feed(['CRWV'], '2026-09-18T12:00:00Z', repo=repo, describe=lambda _: 'CoreWeave, Inc.')
    assert [i['news_id'] for i in feed['admissible']] == ['archive', 'summary', 'passing']
    assert {i['news_id'] for i in feed['hindsight']} == {'future', 'date'}
    assert len(feed['admissible'][0]['provenance']) == 2
    assert all(i['role'] == 'discovery_candidate' for i in feed['items'])
    assert not any(key in feed for key in ('edges', 'nodes', 'supports', 'weakens', 'contradicts'))
    assert {i['news_id'] for i in admissible_headlines(feed)} == {'archive', 'summary', 'passing'}
    # Even a contaminated caller cannot pass future rows into the triage seam.
    feed['admissible'] += feed['hindsight']
    assert not {'future', 'date'} & {i['news_id'] for i in admissible_headlines(feed)}
    remote.fetch.side_effect = RuntimeError('Yahoo offline')
    fallback = news_feed(['CRWV'], '2026-09-18T12:00:00Z', repo=repo, describe=lambda _: 'CoreWeave')
    assert fallback['availability']['CRWV']['yahoo-finance'] == 'unavailable'
    assert len(fallback['admissible']) == 3  # archive plus accumulated Yahoo cache
    # ClaimGraph archive retrieval still admits only contemporaneous candidates.
    hits = ArchiveSearchProvider(repo.archive_dir).search('CoreWeave', task_id='T', as_of='2026-09-18T12:00:00Z')
    assert {h.hit_id for h in hits} == {'archive:archive', 'archive:summary'}


def test_aliases_and_bounded_triage_input():
    aliases = company_aliases('BAC', 'Bank of America Corporation')
    assert 'Bank of America' in aliases and 'Bank' not in aliases and 'Bank of' not in aliases
    feed = dict(cutoff='2026-09-18T12:00:00Z', admissible=[story(str(i)) for i in range(30)])
    assert len(admissible_headlines(feed)) == 12


def test_yahoo_source_preserves_publisher_summary_time(monkeypatch):
    ticker = Mock()
    ticker.get_news.return_value = [dict(content=dict(title='CoreWeave earnings', summary='Revenue rose',
        pubDate='2026-09-18T10:30:00Z', canonicalUrl=dict(url='https://example.com/news'), provider=dict(displayName='Wire')))]
    monkeypatch.setattr('financial_assistant.newsflow.yf.Ticker', lambda _: ticker)
    item = YahooNewsSource().fetch('CRWV')[0]
    ticker.get_news.assert_called_once_with(count=200, tab='news')
    assert item['source'] == 'yahoo-finance' and item['publisher'] == 'Wire'
    assert item['summary'] == 'Revenue rose' and item['published_at'] == '2026-09-18T10:30:00Z'


def test_portfolio_story_dedup_and_generous_limit(tmp_path):
    remote = Mock()
    remote.fetch.return_value = [story(str(i), title=f'CoreWeave story {i}') for i in range(150)]
    repo = repository(tmp_path, remote)
    feed = news_feed(['CRWV', 'NVDA'], '2026-09-18', repo=repo, describe=lambda _: 'CoreWeave')
    assert len(feed['items']) == 150
    assert set(feed['availability']) == {'CRWV', 'NVDA'}


def test_duplicate_future_copy_cannot_backdate_and_offline_archive_survives(tmp_path):
    remote = Mock()
    remote.fetch.return_value = [story('late-copy', stamp='2026-09-18T13:00:00Z')]
    repo = repository(tmp_path, remote)
    (repo.archive_dir/'CRWV.jsonl').write_text(json.dumps(story('early-copy')))
    feed = news_feed(['CRWV'], '2026-09-18T12:00:00Z', repo=repo, describe=lambda _: 'CoreWeave')
    assert feed['admissible'] == []
    assert len(feed['hindsight']) == 1
    assert len(feed['hindsight'][0]['provenance']) == 2
    assert admissible_headlines(feed) == []
    offline = NewsRepository(tmp_path/'empty-cache', yahoo=Mock(fetch=Mock(side_effect=RuntimeError())), archive_dir=repo.archive_dir)
    feed = news_feed(['CRWV'], '2026-09-18T12:00:00Z', repo=offline, describe=lambda _: 'CoreWeave')
    assert [i['news_id'] for i in feed['admissible']] == ['early-copy']
    assert feed['availability']['CRWV']['yahoo-finance'] == 'unavailable'
