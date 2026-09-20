from __future__ import annotations

import json
import re
import time
from collections import Counter
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from datetime import datetime, timezone
from hashlib import sha1
from urllib.request import Request, urlopen

from financial_assistant.api.errors import NotFound, UpstreamUnavailable
from financial_assistant.api.models import (
    EvidenceClaim,
    HypothesisVerdict,
    Investigation,
    InvestigationStage,
    InvestigationStatus,
    NewsItem,
    StageStatus,
)
from financial_assistant.api.repositories import InvestigationRepository
from financial_assistant.api.schemas import ServiceStatus
from financial_assistant.api.services.anomaly_service import (
    AnomalyService,
    session_close,
)
from financial_assistant.api.services.news_service import NewsService
from financial_assistant.claimgraph.builder_v2 import (
    build_investigation_graph,
)
from financial_assistant.domain import (
    AnomalyEvent,
    ExtractedClaim,
    InvestigationState,
    RelationKind,
    RelationshipAssessment,
    SourceDocument,
)
from financial_assistant.llm import (
    LLMTransportError,
    StructuredLLM,
    assess_relationships,
    audit_hypotheses,
    extract_claims,
    generate_hypotheses,
)
from financial_assistant.research.planner import plan_research
from financial_assistant.retrieval import (
    DocumentFetcher,
    SearchHit,
    SearchProvider,
    execute_research_plan,
    is_published_by,
)


STAGES: tuple[tuple[str, str], ...] = (
    ("news", "Collect point-in-time news"),
    ("documents", "Read the articles"),
    ("claims", "Extract source-grounded claims"),
    ("hypotheses", "Generate competing explanations"),
    ("audit", "Audit unsupported premises"),
    ("relations", "Weigh every claim against every explanation"),
    ("graph", "Build the ClaimGraph"),
)

CLAIMS_PER_DOCUMENT = 3
MAX_DOCUMENT_CHARS = 6000
MIN_SUMMARY_CHARS = 80

# Contribution of one assessed relation to a verdict.
RELATION_WEIGHTS = {
    RelationKind.SUPPORTS: 1.0,
    RelationKind.CONTRADICTS: -1.0,
    RelationKind.WEAKENS: -0.5,
}

DEFAULT_STRENGTH = 0.5
HEALTH_CACHE_SECONDS = 10

HEADLINE_WORD_CHARS = 5
HEADLINE_WORDS_REQUIRED = 2


def matches_headline(text: str, headline: str) -> bool:
    """
    Whether fetched page text is plausibly the article
    behind a headline.

    Publishers answer automated requests with consent
    walls, paywalls and bot checks. Those pages extract
    cleanly into well-formed text that has nothing to do
    with the story, and must never become evidence.
    """

    words = {
        word
        for word in re.findall(r"[a-z0-9]+", headline.lower())
        if len(word) >= HEADLINE_WORD_CHARS
    }

    if not words:
        return True

    body = text.lower()
    found = sum(1 for word in words if word in body)

    return found >= min(HEADLINE_WORDS_REQUIRED, len(words))


class InvestigationService:
    """
    Explains one anomaly from the news that was public
    when it happened.

    The language model proposes claims, explanations and
    relations. Which documents are admissible, how
    verdicts are tallied and how the graph is built stay
    deterministic.
    """

    def __init__(
        self,
        investigations: InvestigationRepository,
        anomalies: AnomalyService,
        news: NewsService,
        *,
        llm_factory: Callable[[], StructuredLLM],
        llm_base_url: str,
        llm_api_key: str | None,
        llm_is_local: bool = True,
        model: str,
        provider: str,
        document_fetcher: DocumentFetcher,
        search_provider: SearchProvider | None = None,
        max_documents: int = 6,
        max_claims: int = 12,
        llm_workers: int = 8,
        run_inline: bool = False,
    ):
        self._investigations = investigations
        self._anomalies = anomalies
        self._news = news

        self._llm_factory = llm_factory
        self._llm_base_url = llm_base_url
        self._llm_api_key = llm_api_key
        self._llm_is_local = llm_is_local
        self._model = model
        self._provider = provider

        self._fetcher = document_fetcher
        self._search = search_provider

        self._max_documents = max_documents
        self._max_claims = max_claims
        self._llm_workers = llm_workers

        self._run_inline = run_inline
        self._executor = ThreadPoolExecutor(
            max_workers=2,
            thread_name_prefix="investigation",
        )

        self._health: tuple[float, ServiceStatus] | None = None

        self._recover_interrupted()

    def _recover_interrupted(self) -> None:
        """
        A run is carried by a thread of this process. If the
        process restarted, nobody is working on the runs it left
        "running": they would stay that way forever, and since
        an active run is handed back instead of starting a new
        one, that anomaly could never be explained again.
        """

        for run in self._investigations.list():
            if run.status not in (
                InvestigationStatus.QUEUED,
                InvestigationStatus.RUNNING,
            ):
                continue

            run.status = InvestigationStatus.FAILED
            run.error = "Interrupted by a restart of the desk. Explain again."
            run.finished_at = datetime.now(timezone.utc)

            for stage in run.stages:
                if stage.status in (StageStatus.PENDING, StageStatus.RUNNING):
                    stage.status = StageStatus.SKIPPED

            self._investigations.save(run)

    # -------------------------------------------------
    # Queries
    # -------------------------------------------------

    def list(self) -> list[Investigation]:
        return list(self._investigations.list())

    def get(self, investigation_id: str) -> Investigation:
        run = self._investigations.get(investigation_id)

        if run is None:
            raise NotFound(f"Unknown investigation {investigation_id}.")

        return run

    def llm_status(self) -> ServiceStatus:
        if (
            self._health is not None
            and time.time() - self._health[0] < HEALTH_CACHE_SECONDS
        ):
            return self._health[1]

        # A hosted gateway lists its models to anyone, so without
        # this check it would look online and then answer every
        # real request with 401.
        if not self._llm_is_local and not self._llm_api_key:
            return ServiceStatus(
                name=self._provider,
                online=False,
                detail="LLM_API_KEY is not set for the hosted endpoint",
            )

        headers = {}

        if self._llm_api_key:
            headers["Authorization"] = f"Bearer {self._llm_api_key}"

        try:
            request = Request(f"{self._llm_base_url}/models", headers=headers)

            with urlopen(request, timeout=2.5) as response:
                served = [
                    model.get("id")
                    for model in json.load(response).get("data", [])
                ]

            status = ServiceStatus(
                name=self._provider,
                online=True,
                detail=(
                    f"serving {self._model}"
                    if self._model in served or not served
                    else f"serving {', '.join(map(str, served))}"
                ),
            )

        except Exception:
            status = ServiceStatus(
                name=self._provider,
                online=False,
                detail=f"{self._llm_base_url} is not reachable",
            )

        self._health = (time.time(), status)

        return status

    # -------------------------------------------------
    # Commands
    # -------------------------------------------------

    def start(self, anomaly_id: str, *, ticker: str | None) -> Investigation:
        anomaly, event = self._anomalies.find(anomaly_id, ticker=ticker)

        for run in self._investigations.list():
            if (
                run.anomaly.anomaly_id == anomaly_id
                and run.status
                in (InvestigationStatus.QUEUED, InvestigationStatus.RUNNING)
            ):
                return run

        if not self._run_inline and not self.llm_status().online:
            raise UpstreamUnavailable(
                "The language model is offline. Start it with "
                "`make llm` or point LLM_BASE_URL at a running "
                "OpenAI-compatible endpoint."
            )

        created_at = datetime.now(timezone.utc)

        run = Investigation(
            investigation_id=(
                f"INV-{anomaly_id}-{created_at.strftime('%H%M%S')}"
            ),
            anomaly=anomaly,
            created_at=created_at,
            evidence_cutoff=session_close(anomaly.observed_on),
            model=self._model,
            provider=self._provider,
            stages=[
                InvestigationStage(key=key, label=label)
                for key, label in STAGES
            ],
        )

        self._investigations.save(run)

        if self._run_inline:
            self._run(run, event)
        else:
            self._executor.submit(self._run, run, event)

        return self.get(run.investigation_id)

    # -------------------------------------------------
    # Pipeline
    # -------------------------------------------------

    def _run(self, run: Investigation, event: AnomalyEvent) -> None:
        run.status = InvestigationStatus.RUNNING
        self._investigations.save(run)

        try:
            self._pipeline(run, event)
            run.status = InvestigationStatus.COMPLETED

        except Exception as exc:
            run.status = InvestigationStatus.FAILED
            run.error = str(exc) or type(exc).__name__

            for stage in run.stages:
                if stage.status == StageStatus.PENDING:
                    stage.status = StageStatus.SKIPPED

        run.finished_at = datetime.now(timezone.utc)
        self._investigations.save(run)

    def _pipeline(self, run: Investigation, event: AnomalyEvent) -> None:
        llm = self._llm_factory()
        cutoff = run.evidence_cutoff

        with self._stage(run, "news") as stage:
            articles = self._news.around(run.anomaly).admissible
            run.documents_considered = len(articles)

            stage.detail = (
                f"{len(articles)} articles published by "
                f"{cutoff:%Y-%m-%d %H:%M} UTC"
            )

            if not articles:
                raise RuntimeError(
                    "No news was published before the anomaly."
                )

        with self._stage(run, "documents") as stage:
            documents = self._read_documents(articles, event, cutoff)
            run.documents_used = len(documents)

            stage.detail = f"{len(documents)} documents admitted as evidence"

            if not documents:
                raise RuntimeError("No article could be read.")

        with self._stage(run, "claims") as stage:
            claim_runs, claims, failures = self._extract_claims(documents, llm)

            stage.detail = (
                f"{len(claims)} claims, each with its source quote, from "
                f"{len(claim_runs)} of {len(documents)} articles"
            )

            if failures:
                stage.detail += f". Not read: {'; '.join(failures)}"

            if not claims:
                raise RuntimeError(
                    "No source-grounded claim could be extracted."
                )

        with self._stage(run, "hypotheses") as stage:
            hypothesis_run, hypotheses = generate_hypotheses(
                event, claims, llm
            )

            # The dedicated audit stage owns assumptions.
            hypotheses = tuple(
                hypothesis.model_copy(update={"assumptions": ()})
                for hypothesis in hypotheses
            )

            stage.detail = f"{len(hypotheses)} competing explanations"

        with self._stage(run, "audit") as stage:
            audit_run, audits = audit_hypotheses(
                event, claims, hypotheses, llm
            )

            stage.detail = f"{len(audits)} explanations audited"

        with self._stage(run, "relations") as stage:
            relation_runs, assessments = assess_relationships(
                claims,
                hypotheses,
                llm,
                max_workers=self._llm_workers,
            )

            stage.detail = f"{len(assessments)} claim-to-explanation links"

        with self._stage(run, "graph") as stage:
            state = InvestigationState(
                investigation_id=run.investigation_id,
                anomaly=event,
                documents=documents,
                model_runs=(
                    *claim_runs,
                    hypothesis_run,
                    audit_run,
                    *relation_runs,
                ),
                claims=claims,
                hypotheses=hypotheses,
                hypothesis_audits=audits,
                relationship_assessments=assessments,
            )

            graph = build_investigation_graph(state)
            run.graph = graph.model_dump(mode="json")

            stage.detail = (
                f"{len(graph.nodes)} nodes, {len(graph.edges)} edges"
            )

        audits_by_hypothesis = {
            audit.hypothesis_id: audit for audit in audits
        }

        run.hypotheses = sorted(
            (
                self._verdict(
                    hypothesis,
                    assessments,
                    audits_by_hypothesis.get(hypothesis.hypothesis_id),
                )
                for hypothesis in hypotheses
            ),
            key=lambda verdict: verdict.score,
            reverse=True,
        )

        documents_by_id = {d.document_id: d for d in documents}

        run.claims = [
            EvidenceClaim(
                claim_id=claim.claim_id,
                text=claim.text,
                claim_type=claim.claim_type.value,
                source_quote=claim.source_quote,
                document_id=claim.document_id,
                document_title=documents_by_id[claim.document_id].title,
                publisher=documents_by_id[claim.document_id].publisher,
                url=str(documents_by_id[claim.document_id].url),
                published_at=documents_by_id[claim.document_id].published_at,
            )
            for claim in claims
        ]

    # -------------------------------------------------
    # Stages
    # -------------------------------------------------

    @contextmanager
    def _stage(self, run: Investigation, key: str):
        stage = next(s for s in run.stages if s.key == key)

        stage.status = StageStatus.RUNNING
        self._investigations.save(run)

        started = time.perf_counter()

        try:
            yield stage
            stage.status = StageStatus.DONE

        except Exception as exc:
            stage.status = StageStatus.FAILED
            stage.detail = str(exc) or type(exc).__name__
            raise

        finally:
            stage.seconds = round(time.perf_counter() - started, 2)
            self._investigations.save(run)

    def _read_documents(
        self,
        articles: list[NewsItem],
        event: AnomalyEvent,
        cutoff: datetime,
    ) -> tuple[SourceDocument, ...]:
        """
        Turn the freshest admissible headlines into full
        documents, optionally widened by a web search.
        """

        retrieved_at = datetime.now(timezone.utc)
        candidates = articles[: self._max_documents * 2]

        with ThreadPoolExecutor(max_workers=6) as pool:
            fetched = pool.map(
                lambda item: self._read_article(item, retrieved_at),
                candidates,
            )

        documents = [d for d in fetched if d is not None]

        if self._search is not None:
            try:
                bundle = execute_research_plan(
                    plan_research(event),
                    search_provider=self._search,
                    document_fetcher=self._fetcher,
                    retrieved_at=retrieved_at,
                    per_task_limit=2,
                )

                documents.extend(bundle.documents)

            except Exception:
                # Web search widens the evidence; the news
                # feed alone is still a valid corpus.
                pass

        unique: dict[str, SourceDocument] = {}

        for document in documents:
            if is_published_by(document, cutoff):
                unique.setdefault(
                    document.lineage_id or document.document_id,
                    document,
                )

        return tuple(unique.values())[: self._max_documents]

    def _read_article(
        self,
        item: NewsItem,
        retrieved_at: datetime,
    ) -> SourceDocument | None:
        hit = SearchHit(
            hit_id=f"{item.news_id}:{item.provider}",
            task_id=f"NEWS-{item.ticker}",
            provider=item.provider,
            query=item.ticker,
            rank=1,
            title=item.title,
            url=item.url,
            snippet=item.summary,
            publisher=item.publisher,
            published_at=item.published_at,
        )

        try:
            document = self._fetcher.fetch(hit, retrieved_at=retrieved_at)

            if not matches_headline(document.text, item.title):
                raise ValueError("Fetched page is not the article.")

            # The feed's timestamp is precise to the
            # minute; page metadata is often date-only.
            return document.model_copy(
                update={
                    "published_at": item.published_at,
                    "published_date_only": False,
                }
            )

        except Exception:
            pass

        # Paywalled or blocked: the publisher's own summary
        # is still a citable, timestamped statement.
        if len(item.summary) < MIN_SUMMARY_CHARS:
            return None

        lineage = sha1(item.url.encode("utf-8")).hexdigest()[:12]

        return SourceDocument(
            document_id=f"DOC-{lineage}-summary",
            title=item.title,
            publisher=item.publisher,
            url=item.url,
            published_at=item.published_at,
            retrieved_at=retrieved_at,
            text=f"{item.title}\n\n{item.summary}",
            lineage_id=f"LIN-{lineage}",
        )

    def _extract_claims(
        self,
        documents: tuple[SourceDocument, ...],
        llm: StructuredLLM,
    ):
        """
        Extraction is independent per document, so the
        calls run concurrently and the server batches
        them.
        """

        def extract_one(document: SourceDocument):
            try:
                return extract_claims(
                    document,
                    llm,
                    max_document_chars=MAX_DOCUMENT_CHARS,
                )
            except LLMTransportError:
                return "the model did not answer"
            except Exception as error:
                # The model answered, but a quote it gave could
                # not be found verbatim in the article.
                return f"{type(error).__name__}"

        with ThreadPoolExecutor(
            max_workers=min(self._llm_workers, len(documents)),
        ) as pool:
            results = list(pool.map(extract_one, documents))

        runs = []
        claims: list[ExtractedClaim] = []
        seen: set[str] = set()
        failures: Counter[str] = Counter()

        for result in results:
            if isinstance(result, str):
                failures[result] += 1
                continue

            run, extracted = result
            runs.append(run)

            kept = 0

            for claim in extracted:
                normalised = " ".join(claim.text.lower().split())

                if normalised in seen or len(claims) >= self._max_claims:
                    continue

                seen.add(normalised)
                claims.append(claim)
                kept += 1

                if kept >= CLAIMS_PER_DOCUMENT:
                    break

        return (
            tuple(runs),
            tuple(claims),
            [f"{count} ({reason})" for reason, count in failures.items()],
        )

    @staticmethod
    def _verdict(hypothesis, assessments, audit) -> HypothesisVerdict:
        related: list[RelationshipAssessment] = [
            a for a in assessments if a.target_id == hypothesis.hypothesis_id
        ]

        def count(kind: RelationKind) -> int:
            return sum(1 for a in related if a.relation == kind)

        score = sum(
            RELATION_WEIGHTS.get(a.relation, 0.0)
            * (a.strength if a.strength is not None else DEFAULT_STRENGTH)
            for a in related
        )

        return HypothesisVerdict(
            hypothesis_id=hypothesis.hypothesis_id,
            text=hypothesis.text,
            supporting=count(RelationKind.SUPPORTS),
            contradicting=count(RelationKind.CONTRADICTS),
            weakening=count(RelationKind.WEAKENS),
            context=count(RelationKind.CONTEXT_FOR),
            score=round(score, 3),
            assumptions=audit.assumptions if audit else (),
            missing_information=audit.missing_information if audit else (),
        )
