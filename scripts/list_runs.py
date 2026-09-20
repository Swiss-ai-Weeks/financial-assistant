"""
Which model produced each saved explanation.

Saved investigations and triage readings are replayed without
calling a model. Before a final recording on the local GPUs,
anything listed here under another provider would be replayed
as if it were local, so it should be forgotten and re-run.
"""

from __future__ import annotations

import json
from collections import Counter

from financial_assistant.api.config import get_settings


def main() -> None:
    settings = get_settings()
    state = settings.state_dir

    print(
        f"active profile: {settings.llm_provider_name} "
        f"({'local' if settings.llm_is_local else 'NOT local'}) "
        f"{settings.llm_model}\n"
    )

    produced_by: Counter[str] = Counter()

    for path in sorted((state / "investigations").glob("*.json")):
        run = json.loads(path.read_text())
        produced_by[run["model"]] += 1

        print(
            f"investigation  {run['status']:10} {run['provider']:12} "
            f"{run['model']:52} {run['anomaly']['anomaly_id']}"
        )

    for path in sorted((state / "triage").glob("*.json")):
        reading = json.loads(path.read_text())
        produced_by[reading["model"]] += 1

        print(
            f"triage         {reading['verdict']:16} "
            f"{reading['model']:52} {reading['anomaly_id']}"
        )

    if not produced_by:
        print("No saved runs.")
        return

    foreign = {m: n for m, n in produced_by.items() if m != settings.llm_model}

    if foreign:
        print(
            f"\n{sum(foreign.values())} saved runs were NOT produced by the "
            "active model and would be replayed as-is:"
        )

        for model, count in foreign.items():
            print(f"  {count:3}  {model}")

        print("\nRun `make forget-runs` to re-run them on the active profile.")
    else:
        print("\nEvery saved run was produced by the active model.")


if __name__ == "__main__":
    main()
