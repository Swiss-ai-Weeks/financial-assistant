from pathlib import Path

from financial_assistant.claimgraph.builder_v2 import (
    build_investigation_graph,
)

from financial_assistant.demo import (
    make_demo_state,
)


def main() -> None:
    state = make_demo_state()

    graph = build_investigation_graph(
        state
    )

    payload = (
        graph.model_dump_json(
            indent=2
        )
        + "\n"
    )

    outputs = [
        Path(
            "data/fixtures/"
            "investigation_demo.json"
        ),
        Path(
            "frontend/public/"
            "investigation_demo.json"
        ),
    ]

    for output in outputs:
        output.parent.mkdir(
            parents=True,
            exist_ok=True,
        )

        output.write_text(
            payload
        )

        print(
            f"wrote {output}"
        )


if __name__ == "__main__":
    main()
