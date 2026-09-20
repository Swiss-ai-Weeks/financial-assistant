from pathlib import Path
import sys
from unittest.mock import Mock
import pytest
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import bookreader_viewer as viewer
from financial_assistant.retrieval import bookreader
from test_bookreader import FakeResponse


@pytest.fixture
def configured(monkeypatch):
    monkeypatch.setenv('BOOKREADER_BASE_URL', 'https://corpus.test')
    monkeypatch.setenv('BOOKREADER_API_TOKEN', 'private-token')


def test_authenticated_escaped_document_no_token(configured, monkeypatch):
    seen = []
    def fetch(request, timeout):
        seen.append(request)
        return FakeResponse({'document_id':'NEWS-123', 'publication':'FT', 'issue_date':'2026-01-06',
                             'text':'<script>private-token</script>', 'secret':'private-token'})
    monkeypatch.setattr(bookreader, 'urlopen', fetch)
    response = viewer.document_page('NEWS-123').decode()
    assert seen[0].get_header('Authorization') == 'Bearer private-token'
    assert seen[0].full_url == 'https://corpus.test/documents/NEWS-123'
    assert 'private-token' not in response and '<script>' not in response
    assert '&lt;script&gt;' in response
    assert 'private-token' not in str(viewer.source_links())


@pytest.mark.parametrize('identifier', ['../secret', '%2e%2e%2fsecret', '%252e%252e', 'https://evil.test/a', '//evil.test', 'id?token=x', 'id#fragment', 'a\\b', 'a/b'])
def test_rejects_paths_and_external_urls(configured, monkeypatch, identifier):
    fetch = Mock()
    monkeypatch.setattr(bookreader, 'urlopen', fetch)
    with pytest.raises(ValueError):
        viewer.document_page(identifier)
    fetch.assert_not_called()


def test_adapter_rejects_external_origin_before_auth(configured, monkeypatch):
    fetch = Mock()
    monkeypatch.setattr(bookreader, 'urlopen', fetch)
    with pytest.raises(ValueError):
        bookreader._BookReaderClient().get_json('https://evil.test/documents/123')
    fetch.assert_not_called()
    with pytest.raises(ValueError):
        bookreader._NoRedirect().redirect_request(None, None, 302, '', {}, 'https://evil.test')
