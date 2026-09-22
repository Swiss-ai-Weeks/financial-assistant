"""Presentation-only formatter for the existing investigation text.

No ranking, model, validation, or retrieval logic is changed. Strictly joins
ranked source records to group reviews by the original group identifier.
"""
import re
from pathlib import Path

HEADER = re.compile(r'^## (\d{4}-\d{2}-\d{2}) \| return=([^|]+) \| volume z=(.+)$')
GROUP = re.compile(r'^  Group (\d+)/(\d+) \[([0-9a-f]+)\] status=([^;]+); reason=(.*)$')
SOURCE = re.compile(r'^\[([0-9a-f]+)\] group_size=(\d+) rank=([\d.]+) (.*?) \| ([^|]+) \| (.*?) \| (https?://\S+)$')
FIELD = re.compile(r'    Event: (.*?) \| Possible mechanism \(unverified\): (.*?) \| Relationship: (.*?) \| (.*)$')


def _safe(value):
    return str(value).replace('|', '\\|').replace('\n', ' ').strip()


def _parse(text):
    sections = []
    section = None
    last = None
    in_sources = False
    for line in text.splitlines():
        h = HEADER.match(line)
        if h:
            section = {'date': h[1], 'return': h[2].strip(), 'z': h[3].strip(),
                       'groups': {}, 'sources': [], 'coverage': '', 'usage': ''}
            sections.append(section)
            last = None
            in_sources = False
            continue
        if section is None:
            continue
        if line.startswith('Source records and full group membership:'):
            in_sources = True
            last = None
            continue
        if in_sources:
            s = SOURCE.match(line)
            if s:
                section['sources'].append({'id': s[1], 'size': s[2], 'score': s[3],
                                           'time': s[5].strip(), 'title': s[6].strip(),
                                           'url': s[7]})
            continue
        g = GROUP.match(line)
        if g:
            last = {'position': int(g[1]), 'id': g[3], 'status': g[4],
                    'reason': g[5], 'event': '', 'mechanism': '', 'relationship': '',
                    'excerpt': '', 'flags': ''}
            section['groups'][g[3]] = last
            continue
        f = FIELD.match(line)
        if f and last:
            last['event'], last['mechanism'], last['relationship'] = f[1], f[2], f[3]
            rest = f[4]
            quote = re.search(r'\| Exact excerpt: (.*?)(?= \| Claim flags:| \| Original mechanism \(audit only\):|$)', rest)
            if quote:
                last['excerpt'] = quote[1]
            flags = re.search(r'\| Claim flags: (.*?)(?= \| Original mechanism \(audit only\):|$)', rest)
            if flags:
                last['flags'] = flags[1]
        if line.startswith('Review coverage:'):
            section['coverage'] = line
        if line.startswith('LLM usage:'):
            section['usage'] = line
    return sections


def _label(status, relationship):
    if status == 'supported_hypothesis':
        return 'Hypothesis identified — needs review' if relationship == 'needs_review' else 'Plausible hypothesis — not proven'
    return {'validation_rejected': 'Rejected by validator',
            'context_only': 'Context only — no supported link',
            'insufficient_evidence': 'Insufficient evidence',
            'llm_error': 'Model error'}.get(status, status.replace('_', ' '))


def render_clean_report(investigation_text, original_report='', validated=False):
    sections = _parse(investigation_text)
    if not sections:
        raise ValueError('No investigation sections found; original files remain untouched')
    status = 'VALIDATED' if validated else 'UNVALIDATED DRAFT — requires review'
    out = [f'# Financial anomaly report — {status}', '',
           '> News ranking is a retrieval score, NOT a probability of causation. '
           'Model hypotheses are not proven explanations.', '']
    if original_report.strip():
        out += ['**Market analysis:** the original report remains in `report.txt` or `report_draft.txt`; this readable view focuses on the news findings.', '', '---', '']
    out += ['# News investigation — readable view', '']
    for sec in sections:
        out += [f"## {sec['date']} · Return {sec['return']} · Volume z-score {sec['z']}", '']
        groups = sec['groups']
        hypotheses = [g for g in groups.values() if g['status'] == 'supported_hypothesis']
        rejected = sum(g['status'] == 'validation_rejected' for g in groups.values())
        out += [f"**Review:** {len(groups)} groups reviewed · {len(hypotheses)} hypotheses identified "
                f"(not proven) · {rejected} rejected.", '']
        if hypotheses:
            names = list(dict.fromkeys(g['event'] for g in hypotheses if g['event']))
            out += ['**Model findings:** ' + ('; '.join(_safe(n) for n in names) if names else
                    'See individual hypotheses below.') +
                    '. These are potential contextual links, not established causes.', '']
        else:
            out += ['**Model findings:** No supported hypothesis was identified in the reviewed news. '
                    'The cause of this price move remains unresolved.', '']
        out += ['### News ranked by the existing retrieval score', '',
                '| Rank | Score | News / source | Model assessment |',
                '|---:|---:|---|---|']
        for i, source in enumerate(sec['sources'], 1):
            g = groups.get(source['id'])
            label = _label(g['status'], g['relationship']) if g else 'Review not found — check raw audit'
            out.append(f"| {i} | {source['score']} | [{_safe(source['title'])}]({source['url']}) "
                       f"<br>Published: {_safe(source['time'])} · Articles in group: {source['size']} "
                       f"| {_safe(label)} |")
        out += ['', '### Detailed model interpretation (same ranking)', '']
        for i, source in enumerate(sec['sources'], 1):
            g = groups.get(source['id'])
            out += [f"#### #{i} · {source['title']}", '',
                    f"**Retrieval score:** {source['score']} · **Published:** {source['time']} · "
                    f"**Group size:** {source['size']}", '',
                    f"**Source:** [Open source record]({source['url']})", '']
            if not g:
                out += ['**Assessment:** Missing from investigation; see raw audit.', '']
                continue
            out += [f"**Assessment:** {_label(g['status'], g['relationship'])}", '']
            if g['event']:
                out += [f"**Event identified by model:** {g['event']}", '']
            if g['mechanism']:
                out += [f"**Model interpretation (unverified):** {g['mechanism']}", '']
            out += [f"**Reason / validator outcome:** {g['reason']}", '']
            if g['excerpt']:
                out += [f"**Source excerpt (as recorded):** {g['excerpt']}", '']
            if g['flags']:
                out += [f"**Review flags:** `{g['flags']}`", '']
        out += ['---', '']
    out += ['## How to read this report', '',
            '- **Rank / score:** order and score from the existing news retriever; not model confidence or causality.',
            '- **Plausible hypothesis:** model found a contextual link, not proof that the event caused the move.',
            '- **Needs review:** a claim-level check flagged an issue requiring human verification.',
            '- **Rejected / context only:** no accepted explanation from that news group.',
            '- **Source record:** the URL stored by the ingestion pipeline; it may be a Finnhub record rather than the publisher’s article URL.',
            '- **Technical audit:** see `news_investigation.txt` and the original evidence graphs.', '']
    return '\n'.join(out)


def write_clean_report(*, investigation_path, original_report_path, validated, output_path):
    investigation = Path(investigation_path).read_text(encoding='utf-8')
    original = Path(original_report_path).read_text(encoding='utf-8')
    result = render_clean_report(investigation, original, validated)
    Path(output_path).write_text(result, encoding='utf-8')
    return output_path
