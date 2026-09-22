"""Presentation-only formatter for the existing investigation text.

No ranking, model, validation, or retrieval logic is changed. Strictly joins
ranked source records to group reviews by the original group identifier.
"""
import re
from pathlib import Path
import json

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


def render_clean_report(
    investigation_text,
    original_report="",
    validated=False,
    ranking=None,
):
    sections = _parse(investigation_text)

    if not sections:
        raise ValueError("No investigation sections found")

    status = (
        "PIPELINE VALIDATED — CAUSALITY UNVERIFIED"
        if validated
        else "UNVALIDATED DRAFT — requires review"
    )

    out = [
        f"# Financial anomaly report — {status}",
        "",
    ]

    if original_report.strip():
        out += [
            "**Market analysis:** See the original report.txt.",
            "",
        ]

    # Index the unified ranking by ticker/date.
    ranked_by_date = {}

    if ranking:
        for event in ranking.get("events", []):
            ranked_by_date.setdefault(
                event["anomaly_date"], []
            ).append(event)

    for sec in sections:
        day = sec["date"]
        events = ranked_by_date.get(day, [])

        out += [
            f"## {day} | Return {sec['return']} | "
            f"Volume z-score {sec['z']}",
            "",
        ]

        out += [
            "### News retrieval overview",
            "",
            "| Rank | Retrieval score | News / source | Model assessment |",
            "|---:|---:|---|---|",
        ]

        for i, source in enumerate(sec["sources"], 1):
            group = sec["groups"].get(source["id"])

            label = (
                _label(group["status"], group["relationship"])
                if group
                else "Review not found — check raw audit"
            )

            out.append(
                f"| {i} | {source['score']} | "
                f"[{_safe(source['title'])}]({source['url']}) "
                f"<br>Published: {_safe(source['time'])} "
                f"· Articles in group: {source['size']} "
                f"| {_safe(label)} |"
            )

        out.append("")

        if not events:
            out += [
                "**Result:** No scored hypothesis available "
                "for this anomaly.",
                "",
                "The cause remains unresolved.",
                "",
                "---",
                "",
            ]
            continue

        out += [
            f"**Identified event groups:** {len(events)}",
            "",
        ]

        # Lookup source records using the original evidence IDs.
        sources = {
            source["id"]: source
            for source in sec["sources"]
        }

        groups = sec["groups"]

        for index, event in enumerate(events, 1):
            out += [
                f"### Event {index}: {event['event']}",
                "",
                f"**Event score:** {event['causal_score']} / 100",
                "",
                f"**Status:** {event['status']}",
                "",
                f"**Classification:** {event['classification']}",
                "",
                f"**Evidence coverage:** {event['evidence_coverage']}",
                "",
                f"**Articles:** {event['article_count']}",
                "",
                "**Scoring method:** Score inherited from the "
                "selected assessment; not an average or independent "
                "multi-source confirmation.",
                "",
                "#### Supporting evidence and audit",
                "",
            ]

            event_reasons = event.get("review_reasons") or []

            if event_reasons:
                out += [
                    "**Event review reasons:** " + ", ".join(event_reasons),
                    "",
                ]

            for assessment in event["assessments"]:
                evidence_id = assessment["evidence_id"]

                source = sources.get(evidence_id)
                group = groups.get(evidence_id)

                selected = assessment.get(
                    "representative", False
                )

                out += [
                    f"**{'Selected assessment' if selected else 'Additional assessment'}**",
                    "",
                ]

                if source:
                    out += [
                        f"**Article:** [{source['title']}]"
                        f"({source['url']})",
                        "",
                        f"**Published:** {source['time']}",
                        "",
                        f"**Retrieval score:** {source['score']}",
                        "",
                    ]
                else:
                    out += [
                        f"**Evidence ID:** `{evidence_id}`",
                        "",
                        "**Source:** Not matched in investigation; "
                        "check raw audit.",
                        "",
                    ]

                out += [
                    f"**Assessment score:** {assessment['score']}",
                    "",
                    f"**Assessment status:** {assessment['status']}",
                    "",
                ]

                reasons = assessment.get("review_reasons") or []

                if reasons:
                    out += [
                        "**Review reasons:** "
                        + ", ".join(reasons),
                        "",
                    ]

                flags = assessment.get("claim_flags") or []

                if flags:
                    out += [
                        "**Claim flags:** "
                        + ", ".join(flags),
                        "",
                    ]

                if group:
                    if group["mechanism"]:
                        out += [
                            "**Model interpretation (unverified):** "
                            + group["mechanism"],
                            "",
                        ]

                    if group["reason"]:
                        out += [
                            "**Validator outcome:** "
                            + group["reason"],
                            "",
                        ]

                    if group["excerpt"]:
                        out += [
                            "**Source excerpt:** "
                            + group["excerpt"],
                            "",
                        ]


    out += [
        "## Audit references",
        "",
        "- Original market report: `report.txt`",
        "- Full news investigation: `news_investigation.txt`",
        "- Scoring records: `news_investigation.txt.scores.json`",
        "- Grouped event records: `final_ranking.json`",
        "",
    ]

    out += [
        "## Limitations",
        "",
        "- Event matching is narrow and heuristic; verify event identity manually.",
        "- Representative score is not recomputed from pooled evidence.",
        "- Article count is not independent-source count.",
        "- LLM criterion scores are uncalibrated and not causal probabilities.",
        "- Daily anomaly timing does not establish that news preceded the price move.",
        "",
    ]

    return "\n".join(out)


def write_clean_report(
    *,
    investigation_path,
    original_report_path,
    validated,
    output_path,
    ranking_path=None,
):
    investigation = Path(investigation_path).read_text(
        encoding="utf-8"
    )

    original = Path(original_report_path).read_text(
        encoding="utf-8"
    )

    ranking = None

    if ranking_path is not None:
        ranking_file = Path(ranking_path)

        if not ranking_file.is_file():
            raise FileNotFoundError(
                f"Ranking file not found: {ranking_file}"
            )

        ranking = json.loads(
            ranking_file.read_text(encoding="utf-8")
        )

    result = render_clean_report(
        investigation,
        original,
        validated,
        ranking=ranking,
    )

    Path(output_path).write_text(
        result,
        encoding="utf-8",
    )

    return output_path