"""Restricted text viewer: fixed configured origin, bearer auth stays server-side."""
import html
import os
import re
from urllib.parse import unquote, urlparse
from financial_assistant.retrieval.bookreader import _BookReaderClient


def source_links():
    base = os.environ.get('BOOKREADER_BASE_URL', '').rstrip('/')
    parsed = urlparse(base)
    if parsed.scheme not in ('http', 'https') or parsed.username or parsed.password or parsed.query or parsed.fragment:
        base = ''
    return {'base_url': base}


def document_page(identifier):
    identifier = unquote(identifier)
    if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.-]{0,255}', identifier) or '..' in identifier:
        raise ValueError('Invalid document identifier')
    client = _BookReaderClient()
    payload = client.get_json(f'{client.base_url}/documents/{identifier}')
    if payload.get('document_id') != identifier:
        raise ValueError('Document identifier mismatch')
    def safe(key):
        # Only whitelisted content fields; never echo upstream headers/config/errors.
        return html.escape(str(payload.get(key, '')).replace(client.api_token, '[redacted]'))
    return (f'<!doctype html><meta charset="utf-8"><title>ClaimGraph source</title>'
            f'<h1>{safe("publication")}</h1><p>Publication date: {safe("issue_date")}</p>'
            f'<p>Document: {safe("document_id")} · Page: {safe("page_number")}</p>'
            f'<p>Source hash: {safe("source_sha256")}</p><pre>{safe("text")}</pre>').encode()
