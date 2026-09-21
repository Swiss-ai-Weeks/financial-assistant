"""
One human-triggered, bounded research cycle on one open
question of a ClaimGraph.

A graph records what is still missing. Someone reads it,
selects a Missing Evidence or Evidence Requirement node, and
asks the desk to look. This module does that once: it never
schedules another cycle, and a question that remains open
stays open until a person asks again.

Everything it needs from the outside arrives as a callable,
so it knows nothing about news providers, caches or HTTP:

    candidates(tickers, cutoff)  -> headlines already public
    search(query, task_id)       -> extra hits, or () without SearXNG
    read(item, retrieved_at)     -> SourceDocument or None
    extract(documents, llm)      -> (model runs, claims, failures)
    fundamentals(tickers, cutoff)-> SEC bundles
"""

from __future__ import annotations

import json
import re
from collections.abc import Callable
from copy import deepcopy
from datetime import datetime, timezone
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict

from financial_assistant.claimgraph.builder_v2 import build_investigation_graph
from financial_assistant.domain import (
    AnomalyEvent,
    Hypothesis,
    InvestigationState,
    ModelOperation,
    ModelRun,
)
from financial_assistant.fundamentals.service import domain_evidence
from financial_assistant.llm import assess_relationships
from financial_assistant.llm.evidence_arguments import relationship_diagnostics
from financial_assistant.llm.provider import (
    StructuredLLM,
    complete_structured,
    completion_metadata,
)


FOLLOWUP_STAGES: tuple[tuple[str, str], ...] = (
    ("plan", "Frame the open question"),
    ("retrieval", "Search the news cache and the web"),
    ("fundamentals", "Read SEC filings, point in time"),
    ("claims", "Extract source-grounded claims"),
    ("relations", "Weigh the new evidence"),
    ("resolution", "Decide whether the question is answered"),
    ("graph", "Merge into the ClaimGraph"),
)

OPEN_KINDS = ("missing_evidence", "evidence_requirement")
EPISTEMIC_EDGES = ("supports", "weakens", "contradicts", "context_for")

MAX_DOCUMENTS = 5
MAX_CLAIMS = 10
MAX_QUERIES = 3

STOPWORDS = frozenset(
    "the and for that with from this what which whether does did has have "
    "was were are is its their about into over than been would could should "
    "any there evidence information data company stock price".split()
)


class Resolution(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: Literal["unresolved", "partially_answered", "answered"]
    summary: str
    supporting_item_ids: list[str] = []
    contradicting_item_ids: list[str] = []
    remaining_question: str = ""


RESOLUTION_PROMPT = """
Decide whether an open evidence question of an investigation
has been answered, using ONLY the new evidence supplied.

Return JSON:
{
  "status": "answered" | "partially_answered" | "unresolved",
  "summary": "...",
  "supporting_item_ids": [],
  "contradicting_item_ids": [],
  "remaining_question": "..."
}

Rules:
1. "answered" requires evidence that actually resolves the
   question. A well-grounded negative answer counts.
2. Retrieval alone is not an answer. Relevant but incomplete
   evidence is "partially_answered"; nothing relevant is
   "unresolved".
3. Keep contradicting evidence: list it, do not drop it.
4. Behaviour of peers is context or analogy, never causal
   proof about the company in question.
5. Item ids must be ids that were supplied. Never invent a
   metric, a figure or a causal mechanism.
6. Unless the status is "answered", say in remaining_question
   what is still not known.
""".strip()


def keywords(text: str) -> set[str]:
    return {
        word
        for word in re.findall(r"[a-z][a-z0-9]{2,}", text.lower())
        if word not in STOPWORDS
    }


def rank_candidates(items, question: str, known_urls: set[str]):
    """
    Headlines most likely to bear on the question, first.
    Articles the graph already cites are left out: reading
    them again cannot add evidence.
    """

    terms = keywords(question)

    def score(item) -> tuple[int, datetime]:
        text = keywords(f"{item.title} {item.summary}")

        return (len(terms & text), item.published_at)

    fresh = [item for item in items if item.url not in known_urls]

    return sorted(fresh, key=score, reverse=True)


def search_queries(anomaly: AnomalyEvent, question: str) -> tuple[str, ...]:
    """
    Deterministic queries: the companies, and the words of the
    question. A query is a way to look, never evidence.
    """

    terms = " ".join(sorted(keywords(question), key=question.lower().find)[:6])
    subjects = (anomaly.ticker, *anomaly.related_entities)

    queries = [f"{subject} {terms}".strip() for subject in subjects]
    queries.append(f"{' '.join(subjects)} {terms} analyst".strip())

    return tuple(dict.fromkeys(queries))[:MAX_QUERIES]


def assess_resolution(
    provider: StructuredLLM,
    question: str,
    items: list[dict[str, Any]],
) -> Resolution:
    if not items:
        return Resolution(
            status="unresolved",
            summary="No new grounded evidence addresses the question.",
            remaining_question=question,
        )

    supplied = [
        {"id": item["node_id"], "kind": item["kind"], "text": item["label"]}
        for item in items
    ]

    schema = Resolution.model_json_schema()

    for field in ("supporting_item_ids", "contradicting_item_ids"):
        schema["properties"][field]["items"] = {
            "type": "string",
            "enum": [item["id"] for item in supplied],
        }

    result = Resolution.model_validate(
        complete_structured(
            provider,
            system=RESOLUTION_PROMPT,
            user=json.dumps({"question": question, "evidence": supplied}),
            response_model=Resolution,
            schema=schema,
            reasoning=False,
        )
    )

    ids = {item["id"] for item in supplied}
    cited = set(result.supporting_item_ids + result.contradicting_item_ids)

    if not cited <= ids:
        raise ValueError("Resolution cites evidence that was not supplied.")

    # "Answered" with nothing cited is an opinion, not a finding.
    if result.status != "unresolved" and not cited:
        result = result.model_copy(update={"status": "unresolved"})

    if result.status != "answered" and not result.remaining_question:
        result = result.model_copy(update={"remaining_question": question})

    return result


def parent_hypotheses(graph: dict, requirement_id: str) -> tuple[set[str], tuple[Hypothesis, ...]]:
    """
    The explanations the open question belongs to. A
    requirement attached to a claim reaches only the
    hypotheses that claim is linked to.
    """

    selected = next(n for n in graph["nodes"] if n["node_id"] == requirement_id)

    parents = {
        edge["source"]
        for edge in graph["edges"]
        if edge["target"] == requirement_id and edge["kind"] == "requires"
    }

    if selected["data"].get("hypothesis_id"):
        parents.add("hypothesis:" + selected["data"]["hypothesis_id"])

    parents |= {
        edge["target"]
        for edge in graph["edges"]
        if edge["source"] in parents and edge["kind"] in EPISTEMIC_EDGES
    }

    hypotheses = tuple(
        Hypothesis.model_validate(node["data"])
        for node in graph["nodes"]
        if node["node_id"] in parents and node["kind"] == "hypothesis"
    )

    if not hypotheses:
        # An investigation-wide gap concerns every explanation.
        hypotheses = tuple(
            Hypothesis.model_validate(node["data"])
            for node in graph["nodes"]
            if node["kind"] == "hypothesis"
        )

    return parents, hypotheses


def graph_cutoff(graph: dict) -> tuple[AnomalyEvent, datetime]:
    anomaly = AnomalyEvent.model_validate(
        next(n["data"] for n in graph["nodes"] if n["kind"] == "anomaly")
    )

    observed = anomaly.metadata.get("observed_at")
    cutoff = (
        datetime.fromisoformat(str(observed))
        if observed
        else anomaly.detected_at
    )

    if cutoff.tzinfo is None:
        cutoff = cutoff.replace(tzinfo=timezone.utc)

    return anomaly, cutoff


def run_followup(
    graph: dict,
    requirement_id: str,
    provider: StructuredLLM,
    *,
    run_id: str,
    candidates: Callable[[tuple[str, ...], datetime], list],
    read: Callable[[Any, datetime], Any],
    extract: Callable[[tuple, StructuredLLM], tuple],
    fundamentals: Callable[[tuple[str, ...], datetime], tuple] | None = None,
    search: Callable[[str, str], tuple] | None = None,
    stage: Callable[[str], Any],
    workers: int = 4,
) -> tuple[dict, Resolution]:
    """
    Returns the merged graph and the resolution. `stage(key)`
    is a context manager that reports progress; whatever it
    yields accepts a `.detail` string.
    """

    original = deepcopy(graph)

    selected = next(
        (n for n in graph["nodes"] if n["node_id"] == requirement_id),
        None,
    )

    if selected is None or selected["kind"] not in OPEN_KINDS:
        raise ValueError(
            "Select a Missing Evidence or Evidence Requirement node."
        )

    anomaly, cutoff = graph_cutoff(graph)
    question = selected["label"]
    tickers = (anomaly.ticker, *anomaly.related_entities)
    retrieved_at = datetime.now(timezone.utc)

    failures: list[dict[str, str]] = []
    tool_records: list[dict[str, Any]] = []

    with stage("plan") as step:
        _, hypotheses = parent_hypotheses(graph, requirement_id)
        queries = search_queries(anomaly, question)

        step.detail = (
            f"{len(hypotheses)} explanations concerned, "
            f"{len(queries)} search queries"
        )

    known_urls = {
        str(node["data"].get("url"))
        for node in graph["nodes"]
        if node["kind"] == "document" and node["data"].get("url")
    }

    with stage("retrieval") as step:
        pool = list(candidates(tickers, cutoff))

        tool_records.append(
            {
                "provider": "news-cache",
                "task_id": f"{run_id}-task-cache",
                "query": " ".join(tickers),
                "status": "complete",
                "hits": len(pool),
                "retrieved_at": retrieved_at.isoformat(),
            }
        )

        if search is not None:
            for index, query in enumerate(queries, start=1):
                task_id = f"{run_id}-task-{index}"
                record = {
                    "provider": "web-search",
                    "task_id": task_id,
                    "query": query,
                    "retrieved_at": datetime.now(timezone.utc).isoformat(),
                }

                try:
                    hits = [
                        hit for hit in search(query, task_id)
                        if hit.published_at <= cutoff
                    ]
                    pool.extend(hits)
                    record.update(status="complete", hits=len(hits))
                except Exception:
                    # One dead provider must not end the cycle.
                    record.update(status="failed", reason="Search unavailable")

                tool_records.append(record)

        ranked = rank_candidates(
            [item for item in pool if item.published_at <= cutoff],
            question,
            known_urls,
        )

        documents = []
        seen: set[str] = set()

        for item in ranked[: MAX_DOCUMENTS * 3]:
            if len(documents) >= MAX_DOCUMENTS:
                break

            document = read(item, retrieved_at)

            if document is None:
                continue

            key = document.lineage_id or document.document_id

            if key not in seen:
                seen.add(key)
                documents.append(document)

        documents = tuple(documents)

        step.detail = (
            f"{len(pool)} candidates published by {cutoff:%Y-%m-%d}, "
            f"{len(documents)} new documents read"
        )

    bundles: tuple = ()

    with stage("fundamentals") as step:
        already = any(
            node["kind"] == "context"
            and node["data"].get("subtype") == "fundamentals"
            for node in graph["nodes"]
        )

        if fundamentals is None:
            step.detail = "SEC enrichment is not configured"
        elif already:
            step.detail = "Already in the graph"
        else:
            bundles = fundamentals(tickers, cutoff)
            step.detail = ", ".join(
                f"{bundle.ticker}: {bundle.status}" for bundle in bundles
            )

    runs: list[ModelRun] = []
    claims: tuple = ()

    with stage("claims") as step:
        if documents:
            claim_runs, claims, skipped = extract(documents, provider)
            runs.extend(claim_runs)
            claims = claims[:MAX_CLAIMS]

            failures.extend(
                {"stage": "claim_extraction", "status": reason}
                for reason in skipped
            )

        step.detail = f"{len(claims)} claims from {len(documents)} documents"

    financial_documents, observations, calculations = domain_evidence(bundles)

    old_ids = {node["node_id"] for node in graph["nodes"]}

    new_claims = tuple(
        c for c in claims if "claim:" + c.claim_id not in old_ids
    )
    new_observations = tuple(
        o for o in observations
        if "observation:" + o.observation_id not in old_ids
    )
    new_calculations = tuple(
        c for c in calculations
        if "calculation:" + c.calculation_id not in old_ids
    )

    assessments: list = []
    reassessed: list[str] = []

    with stage("relations") as step:
        if new_claims or new_observations or new_calculations:
            for hypothesis in hypotheses:
                try:
                    relation_runs, judged = assess_relationships(
                        new_claims,
                        (hypothesis,),
                        provider,
                        observations=new_observations,
                        calculations=new_calculations,
                        max_workers=workers,
                    )
                except Exception:
                    failures.append(
                        {
                            "stage": "relationship_assessment",
                            "hypothesis_id": hypothesis.hypothesis_id,
                            "status": "failed",
                        }
                    )
                    continue

                runs.extend(relation_runs)
                reassessed.append("hypothesis:" + hypothesis.hypothesis_id)

                assessments.extend(
                    a.model_copy(
                        update={"assessment_id": f"{run_id}-{a.assessment_id}"}
                    )
                    for a in judged
                )

        step.detail = f"{len(assessments)} new evidence-to-explanation links"

    base_runs = tuple(
        ModelRun.model_validate(
            {k: v for k, v in node["data"].items() if k in ModelRun.model_fields}
        )
        for node in graph["nodes"]
        if node["kind"] == "model_run"
        and node["data"].get("run_id")
        in {h.model_run_id for h in hypotheses}
    )

    delta = build_investigation_graph(
        InvestigationState(
            investigation_id=graph["investigation_id"],
            anomaly=anomaly,
            fundamentals=bundles,
            documents=(*documents, *financial_documents),
            observations=observations,
            calculations=calculations,
            claims=claims,
            hypotheses=hypotheses,
            model_runs=(*base_runs, *runs),
            relationship_assessments=tuple(assessments),
        )
    ).model_dump(mode="json")

    new_nodes = [n for n in delta["nodes"] if n["node_id"] not in old_ids]

    # Raw XBRL observations never go to the resolution call:
    # the calculations built from them are what can be read.
    evidence = [
        n for n in new_nodes if n["kind"] in ("claim", "calculation")
    ]

    resolution_run_id = f"{run_id}-resolution"
    resolution_execution: dict[str, Any] = {}

    with stage("resolution") as step:
        try:
            resolution = assess_resolution(provider, question, evidence)
            resolution_execution = completion_metadata(provider)
        except Exception:
            failures.append(
                {"stage": "resolution_assessment", "status": "failed"}
            )
            resolution = Resolution(
                status="unresolved",
                summary="The resolution assessment was unavailable.",
                remaining_question=question,
            )

        step.detail = resolution.status.replace("_", " ")

    resolution_data = {
        **resolution.model_dump(),
        "requirement_id": requirement_id,
        "model_run_id": resolution_run_id,
    }

    with stage("graph") as step:
        merged = _merge(
            original,
            before=graph,
            delta=delta,
            new_nodes=new_nodes,
            run_id=run_id,
            requirement_id=requirement_id,
            question=question,
            cutoff=cutoff,
            provider=provider,
            queries=queries,
            tool_records=tool_records,
            documents=documents,
            bundles=bundles,
            observations=observations,
            calculations=calculations,
            claims=claims,
            assessments=assessments,
            reassessed=reassessed,
            resolution=resolution,
            resolution_data=resolution_data,
            resolution_run_id=resolution_run_id,
            resolution_execution=resolution_execution,
            evidence=evidence,
            failures=failures,
            hypotheses=hypotheses,
        )

        step.detail = (
            f"{len(merged['nodes']) - len(graph['nodes'])} nodes and "
            f"{len(merged['edges']) - len(graph['edges'])} edges added"
        )

    return merged, resolution


def _merge(
    original: dict,
    *,
    before: dict,
    delta: dict,
    new_nodes: list[dict],
    run_id: str,
    requirement_id: str,
    question: str,
    cutoff: datetime,
    provider: StructuredLLM,
    queries: tuple[str, ...],
    tool_records: list[dict],
    documents: tuple,
    bundles: tuple,
    observations: tuple,
    calculations: tuple,
    claims: tuple,
    assessments: list,
    reassessed: list[str],
    resolution: Resolution,
    resolution_data: dict,
    resolution_run_id: str,
    resolution_execution: dict,
    evidence: list[dict],
    failures: list[dict],
    hypotheses: tuple[Hypothesis, ...],
) -> dict:
    """
    Add what the cycle found, and how it was found, to the
    graph. Epistemic provenance (evidence, relations) and
    execution provenance (action, tasks, tool calls, model
    runs) stay separate node kinds.
    """

    now = datetime.now(timezone.utc).isoformat()
    action_id = f"action:{run_id}"
    edges: list[dict] = []

    def node(node_id: str, kind: str, label: str, data: dict) -> None:
        new_nodes.append(
            {"node_id": node_id, "kind": kind, "label": label, "data": data}
        )

    def edge(source: str, target: str, kind: str, data: dict | None = None) -> None:
        edges.append(
            {
                "edge_id": f"{run_id}-edge-{len(edges)}",
                "source": source,
                "target": target,
                "kind": kind,
                "data": data or {},
            }
        )

    produced = [
        n for n in new_nodes
        if n["kind"] in ("claim", "observation", "calculation", "document", "model_run")
    ]

    node(
        action_id,
        "agent_action",
        "Human-triggered follow-up research",
        {
            "run_id": run_id,
            "originating_requirement_id": requirement_id,
            "human_action": "Investigate this question",
            "cutoff": cutoff.isoformat(),
            "created_at": now,
            "provider": provider.provider_name,
            "model": provider.model_name,
            "resolution": resolution_data,
            "failures": failures,
            "relationship_diagnostics": relationship_diagnostics(assessments),
            "counts": {
                "documents": len(documents),
                "sec_calculations": len(calculations),
                "grounded_claims": len(claims),
            },
            "sec_status": [
                {
                    "ticker": bundle.ticker,
                    "status": bundle.status,
                    "warnings": list(bundle.warnings),
                }
                for bundle in bundles
            ],
        },
    )

    edge(action_id, requirement_id, "investigates")

    for index, bundle in enumerate(bundles):
        sec_id = f"{run_id}-sec-{index}"

        node(
            sec_id,
            "tool_call",
            f"SEC quarterly fundamentals: {bundle.ticker}",
            {
                "provider": "SEC EDGAR",
                "ticker": bundle.ticker,
                "status": bundle.status,
                "cutoff": cutoff.isoformat(),
                "retrieved_at": (
                    bundle.retrieved_at.isoformat()
                    if bundle.retrieved_at
                    else None
                ),
                "warnings": list(bundle.warnings),
                "operation": "quarterly snapshots and deterministic trends",
            },
        )

        edge(action_id, sec_id, "retrieved")

        for observation in observations:
            if observation.metadata.get("ticker") == bundle.ticker:
                edge(
                    "observation:" + observation.observation_id,
                    sec_id,
                    "produced_by",
                )

    tasks = {record["task_id"] for record in tool_records}

    for task_id in sorted(tasks):
        record = next(r for r in tool_records if r["task_id"] == task_id)

        node(
            task_id,
            "research_task",
            f"{record['provider']}: {record['query']}",
            {
                "question": question,
                "query": record["query"],
                "rationale": (
                    "Resolve the selected evidence requirement without "
                    "presuming its explanation is true."
                ),
                "as_of": cutoff.isoformat(),
            },
        )

        edge(action_id, task_id, "generated_task")

    for index, record in enumerate(tool_records):
        tool_id = f"{run_id}-tool-{index}"

        node(tool_id, "tool_call", f"{record['provider']}: {record['status']}", record)
        edge(record["task_id"], tool_id, "retrieved")

    node(
        resolution_run_id,
        "model_run",
        "Missing evidence resolution assessment",
        {
            "run_id": resolution_run_id,
            "provider": provider.provider_name,
            "model": provider.model_name,
            "operation": ModelOperation.RESOLUTION_ASSESSMENT.value,
            "prompt_version": "followup-resolution-v1",
            "created_at": now,
            "resolution": resolution_data,
            "status": (
                "failed"
                if any(f["stage"] == "resolution_assessment" for f in failures)
                else "complete"
                if evidence
                else "skipped_no_evidence"
            ),
            **resolution_execution,
        },
    )

    edge(requirement_id, resolution_run_id, "produced_by")

    for item_id in (
        resolution.supporting_item_ids + resolution.contradicting_item_ids
    ):
        edge(resolution_run_id, item_id, "derived_from")

        if resolution.status != "unresolved":
            edge(
                item_id,
                requirement_id,
                "resolves"
                if resolution.status == "answered"
                else "partially_resolves",
            )

    if resolution.remaining_question and resolution.remaining_question != question:
        gap_id = f"{run_id}-remaining"

        node(
            gap_id,
            "missing_evidence",
            resolution.remaining_question,
            {
                "resolution_status": "unresolved",
                "hypothesis_id": (
                    hypotheses[0].hypothesis_id if hypotheses else None
                ),
                "originating_run_id": run_id,
            },
        )

        edge(requirement_id, gap_id, "requires")

    for produced_node in produced:
        edge(produced_node["node_id"], action_id, "produced_by")

    for existing in original["nodes"]:
        if existing["node_id"] == requirement_id:
            existing["data"].update(
                resolution_status=resolution.status,
                resolution=resolution_data,
                followup_history=[
                    *existing["data"].get("followup_history", []),
                    action_id,
                ],
            )

    original["nodes"].extend(new_nodes)

    known_edges = {e["edge_id"] for e in original["edges"]}
    known_nodes = {n["node_id"] for n in original["nodes"]}

    original["edges"].extend(
        e
        for e in delta["edges"]
        if e["edge_id"] not in known_edges
        and e["source"] in known_nodes
        and e["target"] in known_nodes
    )
    original["edges"].extend(
        e for e in edges
        if e["source"] in known_nodes and e["target"] in known_nodes
    )

    original.setdefault("followups", []).append(
        {
            "run_id": run_id,
            "requirement_id": requirement_id,
            "cutoff": cutoff.isoformat(),
            "resolution": resolution_data,
            "action_id": action_id,
            "delta": {
                **followup_delta(
                    before, original, run_id, requirement_id, question, action_id
                ),
                "reassessed_hypothesis_ids": reassessed,
            },
        }
    )

    return original


def followup_delta(
    before: dict,
    after: dict,
    run_id: str,
    requirement_id: str,
    question: str,
    action_id: str,
) -> dict:
    """What one cycle changed, so the desk can show only that."""

    old_nodes = {n["node_id"] for n in before["nodes"]}
    old_edges = {e["edge_id"] for e in before["edges"]}

    edges = [e for e in after["edges"] if e["edge_id"] not in old_edges]

    previous = next(
        n for n in before["nodes"] if n["node_id"] == requirement_id
    )["data"]
    current = next(
        n for n in after["nodes"] if n["node_id"] == requirement_id
    )["data"]

    delta = {
        "run_id": run_id,
        "requirement_id": requirement_id,
        "question": question,
        "action_id": action_id,
        "added_node_ids": [
            n["node_id"] for n in after["nodes"] if n["node_id"] not in old_nodes
        ],
        "added_edge_ids": [e["edge_id"] for e in edges],
        "previous_resolution": previous.get("resolution_status", "unresolved"),
        "new_resolution": current.get("resolution_status", "unresolved"),
        "remaining_question": current.get("resolution", {}).get(
            "remaining_question"
        ),
    }

    for name, kind in (
        ("supporting", "supports"),
        ("weakening", "weakens"),
        ("contradicting", "contradicts"),
        ("context", "context_for"),
    ):
        delta[f"new_{name}_ids"] = [
            e["edge_id"] for e in edges if e["kind"] == kind
        ]

    return delta
