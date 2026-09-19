from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

import os

from financial_assistant.llm.openai_compatible import (
    OpenAICompatibleProvider,
)

from financial_assistant.llm.registry import (
    get_target,
)

# ---------------------------------------------------------
# STRUCTURED OUTPUT FROM THE LLM
#
# Notice what is deliberately NOT here:
# - evidence
# - sources
# - conclusions
#
# Those require retrieval.
# ---------------------------------------------------------


class HypothesisSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str

    text: str

    rationale: str

    evidence_requirements: list[str] = Field(
        min_length=1,
        max_length=5,
    )


class InvestigationPlan(BaseModel):
    model_config = ConfigDict(extra="forbid")

    hypotheses: list[HypothesisSpec] = Field(
        min_length=2,
        max_length=6,
    )

    assumptions: list[str] = Field(
        default_factory=list,
        max_length=5,
    )


SYSTEM_PROMPT = """
You are the decomposition component of ClaimGraph.

ClaimGraph makes analytical claims auditable.

Your task is NOT to explain an anomaly and NOT to decide its cause.

Given an observed statistical market anomaly, propose a small set of
plausible hypotheses that should be investigated.

Maintain strict epistemic distinctions:

OBSERVATION
Something directly supplied in the input.

CALCULATION
A deterministic result supplied in the input.

HYPOTHESIS
A possible explanation that has not yet been established.

EVIDENCE REQUIREMENT
Information that would be needed to support or weaken a hypothesis.

ASSUMPTION
Something being provisionally assumed.

Rules:

1. Never create evidence.
2. Never claim that a hypothesis is true.
3. Never invent news events, filings, earnings releases, management
   statements or market events.
4. Do not infer causality from correlation or cointegration.
5. Keep hypotheses meaningfully distinct.
6. Evidence requirements should be phrased so that a retrieval system
   could search for them.
7. Prefer company-specific, sector, market and technical explanations
   where appropriate.
8. Return JSON only.

Return this structure:

{
  "hypotheses": [
    {
      "id": "H1",
      "text": "...",
      "rationale": "...",
      "evidence_requirements": [
        "...",
        "..."
      ]
    }
  ],
  "assumptions": [
    "..."
  ]
}
""".strip()


class InvestigationGraphBuilder:
    def build(
        self,
        *,
        target_id: str,
        ticker_a: str,
        ticker_b: str,
        signal_date: str,
        z_score: float,
        correlation: float,
        cointegration_p: float,
    ) -> dict:

        # Resolve provider/model configuration.
        target = get_target(
            target_id
        )


        # Secrets stay on the backend.
        api_key = None

        if target.api_key_env:
            api_key = os.getenv(
                target.api_key_env
            )

            if not api_key:
                raise RuntimeError(
                    "Missing API key environment "
                    f"variable: {target.api_key_env}"
                )


        # Build a provider-independent LLM client.
        llm = OpenAICompatibleProvider(
            provider_name=
                target.provider,

            model_name=
                target.model_name,

            base_url=
                target.base_url,

            api_key=
                api_key,

            prepend_no_think=
                target.prepend_no_think,

            use_json_response_format=
                target.use_json_response_format,

            token_limit_field=
                target.token_limit_field,

            temperature=
                target.temperature,
        )


        pair = (
            f"{ticker_a}/{ticker_b}"
        )


        # This prompt contains only observations and
        # calculations already known by ClaimGraph.
        #
        # The model may propose hypotheses and evidence
        # requirements, but not evidence.
        user_prompt = f"""
Observed market anomaly:

Pair: {pair}
Observation date: {signal_date}

Calculated statistics:
- spread z-score: {z_score:.4f}
- return correlation: {correlation:.4f}
- Engle-Granger p-value: {cointegration_p:.6f}

Generate an investigation plan.

These statistics justify investigation.
They do not establish an economic explanation.
""".strip()


        raw = llm.complete_json(
            system=SYSTEM_PROMPT,
            user=user_prompt,
            reasoning=False,
        )


        # Model output does not become ClaimGraph state
        # until it satisfies our schema.
        plan = (
            InvestigationPlan
            .model_validate(raw)
        )


        return self._to_graph(
            pair=pair,

            signal_date=
                signal_date,

            z_score=
                z_score,

            correlation=
                correlation,

            cointegration_p=
                cointegration_p,

            provider_name=
                target.provider,

            model_name=
                target.model_name,

            target_id=
                target.id,

            plan=plan,
        )


    @staticmethod
    def _to_graph(
        *,
        pair: str,
        signal_date: str,
        z_score: float,
        correlation: float,
        cointegration_p: float,
        provider_name: str,
        model_name: str,
        target_id: str,
        plan: InvestigationPlan,



    ) -> dict:

        anomaly_id = f"ANOMALY-{pair}"

        nodes: list[dict] = [
            {
                "node_id": anomaly_id,
                "kind": "anomaly",
                "label": f"{pair} statistical anomaly",
                "observed_at": signal_date,
            },

            {
                "node_id": "OBS-Z",
                "kind": "calculation",
                "label": f"Spread z-score {z_score:.2f}",
                "value": z_score,
            },

            {
                "node_id": "OBS-CORR",
                "kind": "calculation",
                "label": f"Correlation {correlation:.2f}",
                "value": correlation,
            },

            {
                "node_id": "OBS-COINT",
                "kind": "calculation",
                "label": f"Cointegration p {cointegration_p:.4f}",
                "value": cointegration_p,
            },
        ]

        edges: list[dict] = []


        # -------------------------------------------------
        # Deterministic provenance:
        # these statistics produced the anomaly.
        # -------------------------------------------------

        for metric_id in (
            "OBS-Z",
            "OBS-CORR",
            "OBS-COINT",
        ):
            edges.append(
                {
                    "edge_id":
                        f"E-{metric_id}-{anomaly_id}",

                    "source":
                        metric_id,

                    "target":
                        anomaly_id,

                    "kind":
                        "supports_observation",

                    "data": {},
                }
            )


        # -------------------------------------------------
        # LLM-generated hypotheses.
        # -------------------------------------------------

        for hypothesis in plan.hypotheses:

            hypothesis_id = (
                f"HYP-{hypothesis.id}"
            )

            nodes.append(
                {
                    "node_id":
                        hypothesis_id,

                    "kind":
                        "hypothesis",

                    "label":
                        hypothesis.text,

                    "rationale":
                        hypothesis.rationale,

                    "epistemic_status":
                        "unverified",

                    "generated_by":
                        "llm",
                }
            )

            edges.append(
                {
                    "edge_id":
                        f"E-{anomaly_id}-{hypothesis_id}",

                    "source":
                        anomaly_id,

                    "target":
                        hypothesis_id,

                    "kind":
                        "motivates",

                    "data": {},
                }
            )


            for index, requirement in enumerate(
                hypothesis.evidence_requirements,
                start=1,
            ):
                requirement_id = (
                    f"REQ-{hypothesis.id}-{index}"
                )

                nodes.append(
                    {
                        "node_id":
                            requirement_id,

                        "kind":
                            "evidence_requirement",

                        "label":
                            requirement,

                        "status":
                            "unresolved",
                    }
                )

                edges.append(
                    {
                        "edge_id":
                            f"E-{hypothesis_id}-{requirement_id}",

                        "source":
                            hypothesis_id,

                        "target":
                            requirement_id,

                        "kind":
                            "requires_evidence",

                        "data": {},
                    }
                )


        # -------------------------------------------------
        # Explicit assumptions are separate nodes.
        # -------------------------------------------------

        for index, assumption in enumerate(
            plan.assumptions,
            start=1,
        ):
            assumption_id = (
                f"ASSUMPTION-{index}"
            )

            nodes.append(
                {
                    "node_id":
                        assumption_id,

                    "kind":
                        "assumption",

                    "label":
                        assumption,
                }
            )

            edges.append(
                {
                    "edge_id":
                        f"E-{assumption_id}-{anomaly_id}",

                    "source":
                        assumption_id,

                    "target":
                        anomaly_id,

                    "kind":
                        "contextualizes",

                    "data": {},
                }
            )


        # -------------------------------------------------
        # Execution provenance.
        # -------------------------------------------------

        model_node = "MODEL-DECOMPOSITION"

        nodes.append(
            {
                "node_id":
                    model_node,

                "kind":
                    "model_run",

                "label":
                    "LLM hypothesis decomposition",

                "provider":
                    provider_name,

                "model":
                    model_name,

                "target_id":
                    target_id,

                "role":
                    "graph decomposition",
            }
        )

        for hypothesis in plan.hypotheses:
            edges.append(
                {
                    "edge_id":
                        f"E-{model_node}-HYP-{hypothesis.id}",

                    "source":
                        model_node,

                    "target":
                        f"HYP-{hypothesis.id}",

                    "kind":
                        "generated",

                    "data": {},
                }
            )


        return {
            "schema_version":
                "claimgraph-investigation-v1",

            "pair":
                pair,

            "as_of":
                signal_date,

            "nodes":
                nodes,

            "edges":
                edges,
        }
