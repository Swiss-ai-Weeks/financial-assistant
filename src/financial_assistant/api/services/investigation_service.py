from __future__ import annotations

import re
import time
from collections import Counter
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from datetime import datetime, timezone
from hashlib import sha1
from uuid import uuid4

from financial_assistant.api.errors import (
    Conflict,
    NotFound,
    UpstreamUnavailable,
)
from financial_assistant.api.models import (
    EvidenceClaim,
    FollowUp,
    FundamentalsSummary,
    HypothesisVerdict,
    Investigation,
    InvestigationStage,
    InvestigationStatus,
    ModelUsage,
    NewsItem,
    StageStatus,
)
from financial_assistant.api.repositories import InvestigationRepository
from financial_assistant.api.schemas import ModelList, ModelView, ServiceStatus
from financial_assistant.api.services.followup import (
    FOLLOWUP_STAGES,
    graph_cutoff,
    run_followup,
)
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
from financial_assistant.fundamentals.service import (
    domain_evidence,
    model_context,
)
from financial_assistant.llm import (
    LLMTransportError,
    StructuredLLM,
    assess_relationships,
    audit_hypotheses,
    extract_claims,
    generate_hypotheses,
)
from financial_assistant.llm.model_registry import (
    ModelRegistry,
    ModelSpec,
    RoutingError,
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
    ("fundamentals", "Read SEC filings, point in time"),
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

# The quarterly record of two companies is thousands of
# tokens. What the hypothesis stages read is bounded; the
# graph keeps everything.
FINANCIAL_CONTEXT_CHARS = 12000

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
        registry: ModelRegistry | None = None,
        fundamentals_loader: Callable[
            [tuple[str, ...], datetime], tuple
        ] | None = None,
    ):
        self._investigations = investigations
        self._anomalies = anomalies
        self._news = news

        # A desk wired to one model (the historical
        # constructor, and every test) becomes a registry of
        # one, served by the factory it was given.
        self._registry = registry or ModelRegistry(
            (
                ModelSpec(
                    id="default",
                    provider=provider,
                    model=model,
                    base_url=llm_base_url,
                    api_key_env="LLM_API_KEY",
                ),
            ),
            environ={"LLM_API_KEY": llm_api_key or ""},
            factories={"default": llm_factory},
        )

        self._llm_factory = llm_factory
        self._fundamentals = fundamentals_loader

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

        self._recover_interrupted()

    def _recover_interrupted(self) -> None:
        """
        A run is carried by a thread of this process. If the
        process restarted, nobody is working on the runs it left
        "running": they would stay that way forever, and since
        an active run is handed back instead of starting a new
        one, that anomaly could never be explained again.
        """

        active = (InvestigationStatus.QUEUED, InvestigationStatus.RUNNING)

        for run in self._investigations.list():
            stalled = [f for f in run.followups if f.status in active]

            for followup in stalled:
                followup.status = InvestigationStatus.FAILED
                followup.error = "Interrupted by a restart of the desk."
                followup.finished_at = datetime.now(timezone.utc)

            if stalled and run.status not in active:
                self._investigations.save(run)

            if run.status not in active:
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

    def llm_status(self, model_id: str | None = None) -> ServiceStatus:
        try:
            spec = self._registry.get(model_id)
        except RoutingError as error:
            return ServiceStatus(name="llm", online=False, detail=str(error))

        health = self._registry.health(spec.id)

        return ServiceStatus(
            name=spec.provider,
            online=health.online,
            detail=health.detail,
        )

    def models(self) -> ModelList:
        """
        Every configured model and whether it answers. Probed
        concurrently: a list of five must not take five
        timeouts to draw.
        """

        specs = self._registry.list()

        with ThreadPoolExecutor(max_workers=max(1, len(specs))) as pool:
            healths = list(
                pool.map(lambda spec: self._registry.health(spec.id), specs)
            )

        return ModelList(
            default_id=self._registry.default_id,
            egress_policy=self._registry.egress_policy,
            models=[
                ModelView(
                    id=spec.id,
                    label=spec.display_name,
                    origin=spec.origin,
                    provider=spec.provider,
                    model=spec.model,
                    local=spec.is_local,
                    roles=list(spec.roles),
                    default=spec.id == self._registry.default_id,
                    online=health.online,
                    detail=health.detail,
                )
                for spec, health in zip(specs, healths)
            ],
        )

    # -------------------------------------------------
    # Commands
    # -------------------------------------------------

    def start(
        self,
        anomaly_id: str,
        *,
        ticker: str | None,
        model_id: str | None = None,
    ) -> Investigation:
        anomaly, event = self._anomalies.find(anomaly_id, ticker=ticker)
        spec = self._spec(model_id)

        # The same anomaly may be running on another model:
        # that is a comparison, not a duplicate.
        for run in self._investigations.list():
            if (
                run.anomaly.anomaly_id == anomaly_id
                and (run.model_id or self._registry.default_id) == spec.id
                and run.status
                in (InvestigationStatus.QUEUED, InvestigationStatus.RUNNING)
            ):
                return run

        self._require_online(spec)

        created_at = datetime.now(timezone.utc)

        run = Investigation(
            investigation_id=(
                f"INV-{anomaly_id}-{created_at.strftime('%H%M%S')}"
                f"-{uuid4().hex[:4]}"
            ),
            anomaly=anomaly,
            created_at=created_at,
            evidence_cutoff=session_close(anomaly.observed_on),
            model=spec.model,
            provider=spec.provider,
            model_id=spec.id,
            model_label=spec.display_name,
            model_local=spec.is_local,
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

    def follow_up(
        self,
        investigation_id: str,
        requirement_id: str,
        *,
        model_id: str | None = None,
    ) -> Investigation:
        """
        Research one open question of a finished
        investigation. One cycle per investigation at a time:
        two would merge into the same graph.
        """

        run = self.get(investigation_id)

        if run.graph is None:
            raise Conflict("This investigation has no ClaimGraph yet.")

        if any(
            item.status
            in (InvestigationStatus.QUEUED, InvestigationStatus.RUNNING)
            for item in run.followups
        ):
            raise Conflict("A follow-up is already running on this graph.")

        node = next(
            (n for n in run.graph["nodes"] if n["node_id"] == requirement_id),
            None,
        )

        if node is None or node["kind"] not in (
            "missing_evidence",
            "evidence_requirement",
        ):
            raise NotFound(
                "Select a Missing Evidence or Evidence Requirement node."
            )

        spec = self._spec(model_id or run.model_id)
        self._require_online(spec)

        followup = FollowUp(
            run_id=f"FU-{uuid4().hex[:10]}",
            requirement_id=requirement_id,
            question=node["label"],
            created_at=datetime.now(timezone.utc),
            model_id=spec.id,
            model=spec.model,
            stages=[
                InvestigationStage(key=key, label=label)
                for key, label in FOLLOWUP_STAGES
            ],
        )

        run.followups.append(followup)
        self._investigations.save(run)

        if self._run_inline:
            self._run_followup(run, followup, spec)
        else:
            self._executor.submit(self._run_followup, run, followup, spec)

        return self.get(investigation_id)

    def _spec(self, model_id: str | None) -> ModelSpec:
        try:
            spec = self._registry.get(model_id)
        except RoutingError as error:
            raise NotFound(str(error)) from error

        if "analysis" not in spec.roles:
            raise Conflict(f"{spec.display_name} is not an analysis model.")

        return spec

    def _require_online(self, spec: ModelSpec) -> None:
        if self._run_inline:
            return

        health = self._registry.health(spec.id)

        if not health.online:
            raise UpstreamUnavailable(
                f"{spec.display_name} is offline ({health.detail}). "
                "Start it with `make llm` / `make apertus`, or point "
                "its base URL at a running OpenAI-compatible endpoint."
            )

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
        llm = self._registry.provider(run.model_id)
        workers = self._workers(run.model_id)
        cutoff = run.evidence_cutoff

        # The graph records when the anomaly became observable,
        # which is what every temporal view of it is cut at.
        event = event.model_copy(
            update={
                "metadata": {
                    **event.metadata,
                    "observed_at": cutoff.isoformat(),
                }
            }
        )

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

        with self._stage(run, "fundamentals") as stage:
            bundles = self._load_fundamentals(run, cutoff)
            run.fundamentals = [self._summary(bundle) for bundle in bundles]

            stage.detail = (
                "; ".join(
                    f"{item.ticker}: {item.quarters} quarters, "
                    f"{item.calculations} metrics"
                    if item.status == "available"
                    else f"{item.ticker}: unavailable"
                    for item in run.fundamentals
                )
                or "SEC enrichment is not configured (set SEC_USER_AGENT)"
            )

        financial_documents, observations, calculations = domain_evidence(
            bundles
        )

        financial_context = (
            model_context(bundles)[:FINANCIAL_CONTEXT_CHARS]
            if any(bundle.status == "available" for bundle in bundles)
            else ""
        )

        with self._stage(run, "claims") as stage:
            claim_runs, claims, failures = self._extract_claims(
                documents, llm, workers=workers
            )

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

            # Shown as soon as they exist, and kept even if a
            # later stage fails: the evidence is the product.
            run.claims = self._evidence(claims, documents)

        with self._stage(run, "hypotheses") as stage:
            hypothesis_run, hypotheses = generate_hypotheses(
                event,
                claims,
                llm,
                financial_context=financial_context,
            )

            # The dedicated audit stage owns assumptions.
            hypotheses = tuple(
                hypothesis.model_copy(update={"assumptions": ()})
                for hypothesis in hypotheses
            )

            stage.detail = f"{len(hypotheses)} competing explanations"

            run.hypotheses = [
                self._verdict(hypothesis, (), None)
                for hypothesis in hypotheses
            ]

        with self._stage(run, "audit") as stage:
            audit_run, audits = audit_hypotheses(
                event,
                claims,
                hypotheses,
                llm,
                financial_context=financial_context,
            )

            stage.detail = f"{len(audits)} explanations audited"

        with self._stage(run, "relations") as stage:
            # SEC figures are judged like any other evidence:
            # a calculation can support or weaken an
            # explanation, it is never attached as context by
            # default.
            relation_runs, assessments = assess_relationships(
                claims,
                hypotheses,
                llm,
                calculations=calculations,
                observations=observations,
                max_workers=workers,
            )

            stage.detail = (
                f"{len(assessments)} evidence-to-explanation links"
            )

        model_runs = (
            *claim_runs,
            hypothesis_run,
            audit_run,
            *relation_runs,
        )

        with self._stage(run, "graph") as stage:
            state = InvestigationState(
                investigation_id=run.investigation_id,
                anomaly=event,
                documents=(*documents, *financial_documents),
                fundamentals=bundles,
                observations=observations,
                calculations=calculations,
                model_runs=model_runs,
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

        run.usage = self._usage(model_runs)

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

    def _run_followup(
        self,
        run: Investigation,
        followup: FollowUp,
        spec: ModelSpec,
    ) -> None:
        followup.status = InvestigationStatus.RUNNING
        self._investigations.save(run)

        @contextmanager
        def stage(key: str):
            current = next(s for s in followup.stages if s.key == key)
            current.status = StageStatus.RUNNING
            self._investigations.save(run)

            started = time.perf_counter()

            try:
                yield current
                current.status = StageStatus.DONE
            except Exception as exc:
                current.status = StageStatus.FAILED
                current.detail = str(exc) or type(exc).__name__
                raise
            finally:
                current.seconds = round(time.perf_counter() - started, 2)
                self._investigations.save(run)

        try:
            llm = self._registry.provider(spec.id)
            workers = self._workers(spec.id)
            before = (len(run.graph["nodes"]), len(run.graph["edges"]))

            graph, resolution = run_followup(
                run.graph,
                followup.requirement_id,
                llm,
                run_id=followup.run_id,
                candidates=self._followup_candidates,
                search=self._followup_search if self._search else None,
                read=self._read_article,
                extract=lambda documents, provider: self._extract_claims(
                    documents, provider, workers=workers
                ),
                fundamentals=(
                    (lambda tickers, cutoff: self._fundamentals(tickers, cutoff))
                    if self._fundamentals
                    else None
                ),
                stage=stage,
                workers=workers,
            )

            run.graph = graph

            followup.resolution = resolution.status
            followup.summary = resolution.summary
            followup.added_nodes = len(graph["nodes"]) - before[0]
            followup.added_edges = len(graph["edges"]) - before[1]
            followup.status = InvestigationStatus.COMPLETED

        except Exception as exc:
            followup.status = InvestigationStatus.FAILED
            followup.error = str(exc) or type(exc).__name__

            for item in followup.stages:
                if item.status == StageStatus.PENDING:
                    item.status = StageStatus.SKIPPED

        followup.finished_at = datetime.now(timezone.utc)
        self._investigations.save(run)

    # -------------------------------------------------
    # Models, fundamentals, follow-up retrieval
    # -------------------------------------------------

    def _workers(self, model_id: str | None) -> int:
        """
        Parallelism is a property of the endpoint: a hosted
        free tier gets slower with every concurrent request,
        our own GPUs get faster.
        """

        try:
            spec = self._registry.get(model_id)
        except RoutingError:
            return self._llm_workers

        if spec.id == "default":
            return self._llm_workers

        return spec.workers

    def _load_fundamentals(self, run: Investigation, cutoff: datetime) -> tuple:
        """
        SEC figures that had been FILED by the cutoff, for each
        leg. Never fatal: without them the investigation is the
        news-only one it always was, and the graph records the
        gap as missing evidence.
        """

        if self._fundamentals is None:
            return ()

        tickers = (run.anomaly.ticker, *run.anomaly.related_tickers)

        try:
            return tuple(self._fundamentals(tickers, cutoff))
        except Exception:
            return ()

    @staticmethod
    def _summary(bundle) -> FundamentalsSummary:
        return FundamentalsSummary(
            ticker=bundle.ticker,
            status=bundle.status,
            issuer=bundle.issuer or "",
            quarters=len(bundle.snapshots),
            facts=len(bundle.facts),
            calculations=sum(
                1 for c in bundle.calculations if c.status == "available"
            ),
            latest_period=max(bundle.periods) if bundle.periods else None,
            warnings=tuple(bundle.warnings),
        )

    @staticmethod
    def _usage(model_runs) -> ModelUsage:
        def total(field: str) -> int:
            return sum(getattr(run, field, None) or 0 for run in model_runs)

        return ModelUsage(
            calls=len(model_runs),
            latency_ms=total("latency_ms"),
            prompt_tokens=total("prompt_tokens"),
            completion_tokens=total("completion_tokens"),
        )

    def _followup_candidates(
        self,
        tickers: tuple[str, ...],
        cutoff: datetime,
    ) -> list[NewsItem]:
        """
        Everything the news cache holds on the legs of the
        anomaly that was public by the cutoff. The follow-up
        ranks it against the open question.
        """

        unique: dict[str, NewsItem] = {}

        for ticker in tickers:
            for item in self._news.feed(ticker, limit=300):
                if item.published_at <= cutoff:
                    unique.setdefault(item.news_id, item)

        return list(unique.values())

    def _followup_search(self, query: str, task_id: str) -> tuple[NewsItem, ...]:
        hits = self._search.search(query, task_id=task_id, limit=6)

        return tuple(
            NewsItem(
                news_id="NEWS-" + sha1(str(hit.url).encode()).hexdigest()[:12],
                ticker=task_id,
                title=hit.title,
                url=str(hit.url),
                publisher=hit.publisher,
                published_at=hit.published_at,
                summary=hit.snippet or "",
                provider=hit.provider,
            )
            for hit in hits
            # An undated page cannot be shown to precede the
            # anomaly, so it cannot be evidence about it.
            if hit.published_at is not None and not hit.published_date_only
        )

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
        *,
        workers: int | None = None,
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
                    max_claims=CLAIMS_PER_DOCUMENT,
                )
            except LLMTransportError:
                return "the model did not answer"
            except Exception as error:
                # The model answered, but a quote it gave could
                # not be found verbatim in the article.
                return f"{type(error).__name__}"

        with ThreadPoolExecutor(
            max_workers=max(
                1, min(workers or self._llm_workers, len(documents))
            ),
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
    def _evidence(claims, documents) -> list[EvidenceClaim]:
        documents_by_id = {d.document_id: d for d in documents}

        return [
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
