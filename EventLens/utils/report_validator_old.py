import json
import re
from pathlib import Path


RISKY_CLAIMS = {
    "selling pressure": "Price and volume alone do not establish selling pressure.",
    "buying pressure": "Price and volume alone do not establish buying pressure.",
    "market stress": "Market stress needs a defined metric or external evidence.",
    "cluster": "Temporal clustering requires an explicit calculation.",
    "verified": "The source JSON does not contain a verification field.",
    "volume-driven": "This interpretation requires a defined comparison.",
}


def load_data(path="anomalies.json"):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def validate_report(report: str, data: dict) -> dict:
    """
    Check explicit anomaly counts and event values.

    This is a partial validator, not a guarantee that
    every statement in the report is correct.
    """

    errors = []
    warnings = []
    # Remove Markdown formatting before parsing counts
    clean_report = report.replace("**", "")

    summary = data["summary"]
    events = data["events"]

    expected_total = len(events)
    expected_positive = sum(
        event["return_pct"] > 0 for event in events
    )
    expected_negative = sum(
        event["return_pct"] < 0 for event in events
    )

    # 1. Check JSON internal consistency

    if data["anomaly_count"] != expected_total:
        errors.append(
            "JSON inconsistency: anomaly_count does not match events."
        )

    if summary["total_anomalies"] != expected_total:
        errors.append(
            "JSON inconsistency: total_anomalies does not match events."
        )

    if summary["positive_anomalies"] != expected_positive:
        errors.append(
            "JSON inconsistency: positive_anomalies is incorrect."
        )

    if summary["negative_anomalies"] != expected_negative:
        errors.append(
            "JSON inconsistency: negative_anomalies is incorrect."
        )

    # 2. Check explicit report counts

    count_patterns = {
        "total": (
            r"total anomalies(?: detected)?\s*:\s*\*{0,2}(\d+)",
            expected_total,
        ),
        "positive": (
            r"positive anomalies(?:\s*\([^)]*\))?\s*:\s*\*{0,2}(\d+)",
            expected_positive,
        ),
        "negative": (
            r"negative anomalies(?:\s*\([^)]*\))?\s*:\s*\*{0,2}(\d+)",
            expected_negative,
        ),
    }

    for label, (pattern, expected) in count_patterns.items():
        match = re.search(pattern, clean_report, re.IGNORECASE)

        if not match:
            errors.append(
                f"Could not validate {label} anomaly count."
            )
            continue

        actual = int(match.group(1))

        if actual != expected:
            errors.append(
                f"{label} count: report={actual}, JSON={expected}"
            )

    # 3. Check event dates and numeric values in Markdown tables

    events_by_date = {
        event["date"]: event for event in events
    }

    date_pattern = r"\b\d{4}-\d{2}-\d{2}\b"

    for line in report.splitlines():

        if not line.strip().startswith("|"):
            continue

        date_match = re.search(date_pattern, line)

        if not date_match:
            continue

        date = date_match.group(0)

        if date not in events_by_date:
            errors.append(
                f"Report contains an unknown anomaly date: {date}"
            )
            continue

        event = events_by_date[date]

        # Expected table layout:
        # Date | Close | Volume Z-Score | Return | Explanation

        cells = [
            cell.strip().replace("**", "")
            for cell in line.strip().strip("|").split("|")
        ]

        if len(cells) < 4:
            warnings.append(
                f"Could not parse table row for {date}."
            )
            continue

        def parse_number(value):
            value = value.replace("−", "-").replace("–", "-")
            value = value.replace(",", "").replace("%", "")
            match = re.search(r"[-+]?\d+(?:\.\d+)?", value)

            if not match:
                return None

            return float(match.group(0))

        fields = [
            ("close", cells[1]),
            ("volume_zscore", cells[2]),
            ("return_pct", cells[3]),
        ]

        for field, cell in fields:
            actual = parse_number(cell)
            expected = event[field]

            if actual is None:
                warnings.append(
                    f"Could not parse {field} for {date}."
                )
                continue

            if abs(actual - expected) > 0.011:
                errors.append(
                    f"{date} {field}: "
                    f"report={actual}, JSON={expected}"
                )

    # 4. Flag interpretations requiring additional evidence

    lower_report = report.lower()

    for phrase, explanation in RISKY_CLAIMS.items():
        for line in report.splitlines():
            lower_line = line.lower()

            # Explicit disclaimers are not clustering claims.
            if phrase == "cluster" and re.search(
                r"\bno\s+(?:temporal\s+)?clustering\s+claims?\b",
                lower_line,
            ):
                continue

            if phrase in lower_line:
                warnings.append(
                    f"Review '{phrase}': {explanation}\n"
                    f"  Text: {line.strip()}"
                )

    return {
        "passed_numeric_checks": len(errors) == 0,
        "errors": errors,
        "warnings": warnings,
    }


def print_validation(result: dict):

    print("\n" + "=" * 55)
    print("REPORT VALIDATION")
    print("=" * 55)

    if result["passed_numeric_checks"]:
        print("\nPASS: Implemented numeric checks passed.")
    else:
        print("\nFAIL: Numeric inconsistencies detected.")

    if result["errors"]:
        print("\nERRORS:")
        for error in result["errors"]:
            print(f"  - {error}")

    if result["warnings"]:
        print("\nWARNINGS:")
        for warning in result["warnings"]:
            print(f"  - {warning}")

    print("\nNote: Passing does not prove the entire report is correct.")


if __name__ == "__main__":

    data = load_data("anomalies.json")

    report_path = Path("report.txt")

    if not report_path.exists():
        raise FileNotFoundError(
            "Save the agent's report to report.txt first."
        )

    report = report_path.read_text(encoding="utf-8")

    result = validate_report(report, data)

    print_validation(result)