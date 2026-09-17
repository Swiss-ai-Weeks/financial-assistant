from __future__ import annotations

from datetime import (
    datetime,
    timezone,
)

from hashlib import sha1

from pydantic import (
    BaseModel,
    ConfigDict,
)

from financial_assistant.domain import (
    ClaimType,
    ExtractedClaim,
    ModelOperation,
    ModelRun,
    SourceDocument,
)

from .provider import (
    StructuredLLM,
)


PROMPT_VERSION = "claim-extraction-v1"


class _ClaimCandidate(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )

    text: str
    claim_type: ClaimType
    source_quote: str


class _ClaimExtractionResponse(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )

    claims: tuple[
        _ClaimCandidate,
        ...
    ]


SYSTEM_PROMPT = """
Extract atomic analytical claims from the supplied
source document.

Allowed claim_type values ONLY:

- reported_fact
- attributed_claim
- forecast
- interpretation

Rules:

1. Each claim must express one independently
   assessable proposition.

2. Do not invent materiality, causality, importance,
   sentiment, probability, or financial impact.

3. source_quote must be copied verbatim from the
   supplied document.

4. Do not return any claim_type other than the four
   explicitly allowed values.

5. Do not output trading signals.

Return JSON only in this structure:

{
  "claims": [
    {
      "text": "...",
      "claim_type": "reported_fact",
      "source_quote": "..."
    }
  ]
}
""".strip()


def extract_claims(
    document: SourceDocument,
    provider: StructuredLLM,
    *,
    max_document_chars: int = 16000,
) -> tuple[
    ModelRun,
    tuple[ExtractedClaim, ...],
]:
    source_text = (
        document.text[
            :max_document_chars
        ]
    )

    raw = provider.complete_json(
        system=SYSTEM_PROMPT,

        user=(
            "DOCUMENT TITLE:\n"
            f"{document.title}\n\n"

            "DOCUMENT SOURCE:\n"
            f"{document.publisher}\n\n"

            "DOCUMENT TEXT:\n"
            f"{source_text}"
        ),

        reasoning=False,
    )

    # This is where invalid values such as
    # "financial_performance" are rejected.
    parsed = (
        _ClaimExtractionResponse
        .model_validate(raw)
    )

    created_at = datetime.now(
        timezone.utc
    )

    run_digest = sha1(
        (
            f"{provider.provider_name}|"
            f"{provider.model_name}|"
            f"{document.document_id}|"
            f"{PROMPT_VERSION}|"
            f"{created_at.isoformat()}"
        ).encode("utf-8")
    ).hexdigest()[:12]

    run = ModelRun(
        run_id=(
            f"MR-CLAIMS-{run_digest}"
        ),

        provider=(
            provider.provider_name
        ),

        model=provider.model_name,

        operation=(
            ModelOperation.CLAIM_EXTRACTION
        ),

        prompt_version=PROMPT_VERSION,

        created_at=created_at,
    )

    claims: list[
        ExtractedClaim
    ] = []

    seen: set[
        tuple[str, str]
    ] = set()

    for candidate in parsed.claims:
        quote = (
            candidate.source_quote
            .strip()
        )

        if quote not in source_text:
            raise ValueError(
                "Model returned source_quote "
                "that does not occur verbatim "
                "in the source document:\n"
                f"{quote}"
            )

        key = (
            candidate.text.strip(),
            quote,
        )

        if key in seen:
            continue

        seen.add(key)

        digest = sha1(
            (
                f"{document.document_id}|"
                f"{candidate.text}|"
                f"{quote}"
            ).encode("utf-8")
        ).hexdigest()[:12]

        claims.append(
            ExtractedClaim(
                claim_id=f"C-{digest}",

                text=(
                    candidate.text.strip()
                ),

                claim_type=(
                    candidate.claim_type
                ),

                document_id=(
                    document.document_id
                ),

                source_quote=quote,

                model_run_id=run.run_id,
            )
        )

    return (
        run,
        tuple(claims),
    )
