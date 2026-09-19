import json

from financial_assistant.investigation_llm import (
    InvestigationGraphBuilder,
)


builder = InvestigationGraphBuilder()

graph = builder.build(
    target_id=
        "nim-nemotron-super",

    ticker_a="CHRD",
    ticker_b="REPX",

    signal_date=
        "2026-09-18",

    z_score=-3.33,

    correlation=0.72,

    cointegration_p=0.0252,
)


print(
    json.dumps(
        graph,
        indent=2,
    )
)
