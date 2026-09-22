import json
from utils.report_validator import validate_report, print_validation
from langchain_core.messages import SystemMessage, HumanMessage
from model import llm, llm_with_tools, tool_registry

DEBUG = False
def debug_print(*args, **kwargs):
    if DEBUG:
        print(*args, **kwargs)

# ============================================================
# AGENT
# ============================================================

def run_agent(query: str):

    # STEP 1: Initial conversation

    messages = [
        SystemMessage(
            content="""
You are a financial market anomaly analysis agent.

Use tools when market analysis is required.

Report anomaly dates, return percentages,
and volume z-scores.

Never invent financial data.
"""
        ),
        HumanMessage(content=query),
    ]

    # STEP 2: Let the LLM choose a tool

    response = llm_with_tools.invoke(messages)

    if not response.tool_calls:
        print("\nAgent:")
        print(response.content or "No response generated.")
        return

    # STEP 3: Execute tools

    results = []

    for call in response.tool_calls[:1]:

        tool_name = call["name"]

        debug_print(f"\nCalling tool: {tool_name}")
        debug_print(f"Arguments: {call['args']}")

        if tool_name not in tool_registry:
            result = {
                "error": f"Unknown tool: {tool_name}"
            }
        else:
            try:
                result = tool_registry[tool_name].invoke(
                    call["args"]
                )
            except Exception as e:
                result = {
                    "error": str(e)
                }

        results.append(result)

        # Save anomaly data
        if (
            tool_name == "analyze_ticker"
            and "error" not in result
        ):
            with open("anomalies.json", "w") as f:
                json.dump(result, f, indent=4)

    # STEP 4: Generate final report
    # Fresh conversation without tool calling history

    report_messages = [
        SystemMessage(
            content="""
            You are a financial market anomaly analyst.

            Your task is to produce an insightful and concise
            financial report using the provided JSON.

            The Python analysis is the source of truth.

            REPORT STRUCTURE:

            1. Key Findings

            Use exactly these three separate labels and populate
            their values from the source JSON:

            - Total anomalies detected: <total_anomalies>
            - Positive anomalies: <positive_anomalies>
            - Negative anomalies: <negative_anomalies>

            Then explain the detection methodology.

            Do not combine the three counts into one sentence.

            2. Most Extreme Events
            - Highlight 3 to 5 important events.
            - Include dates, returns, and volume z-scores.
            - Explain why each event meets the detection rule.

            3. Key Observations
            - Discuss verified patterns only.
            - Distinguish statistical observations from
                possible explanations.

            STRICT RULES:
            - Never invent numerical values.
            - Never modify the anomaly count.
            - Use the provided summary statistics.
            - Never invent historical events or news.
            - Do not claim causation from correlation.
            - Do not claim that volume preceded a price
            movement using daily observations alone.
            - Do not claim temporal clustering unless
            clustering statistics are provided.
            - Do not claim market peaks or bullish trends
            unless supported by the data.
            - Do not calculate new statistics yourself.
            - If evidence is missing, say it is unknown.
            - Do not mention the phrases "selling pressure" or "buying pressure",
            even in negated statements. Instead, state that daily price and
            volume data cannot establish causation.

            - Do not use superlatives such as "largest", "highest", or "strongest"
            unless the ranking is explicitly provided in the source JSON.
            Otherwise, describe the event using its numeric values only.

            Write a natural, professional financial report.
            Avoid unnecessarily long tables.

            INTERPRETATION RULES:
            - High trading volume does not prove selling pressure.
            - Negative returns with high volume indicate
            co-occurrence, not causation.
            - Do not describe temporal clustering unless
            clustering metrics are explicitly provided.
            - Do not infer market sentiment from price
            and volume alone.
            - Do not claim that all observations are verified
            unless they are supported by the JSON.
            """
        ),
        HumanMessage(
            content=(
                f"Original question:\n{query}\n\n"
                f"Market analysis results:\n"
                f"{json.dumps(results, default=str)}"
            )
        ),
    ]

    debug_print("\nGenerating final response...")

    final_response = llm.invoke(report_messages)

    answer = final_response.content

    if not answer:
        print("\nERROR: LLM returned an empty response.")
        print("Metadata:", final_response.response_metadata)
        return

    # Load source data
    with open("anomalies.json", "r", encoding="utf-8") as f:
        data = json.load(f)

    # Maximum one revision
    MAX_REVISIONS = 1

    for attempt in range(MAX_REVISIONS + 1):

        validation = validate_report(answer, data)

        if DEBUG:
            print(f"\nValidation attempt {attempt + 1}")
            print_validation(validation)

        # Publish only if all implemented checks pass
        if not validation["errors"] and not validation["warnings"]:

            with open("report.txt", "w", encoding="utf-8") as f:
                f.write(answer)
            
            if DEBUG:
                print("\nAgent:")
                print(answer)
                print("\nReport passed the implemented checks.")
            return

        # Stop after maximum revisions
        if attempt == MAX_REVISIONS:
            break

        debug_print("\nRevising report...")

        revision_messages = [
            SystemMessage(
                content="""
    You are revising a financial analysis report.

    The provided JSON is the only source of truth.

    Fix all validation errors and warnings.

    Do not introduce new facts, dates, numbers,
    historical explanations, or market narratives.

    Replace unsupported interpretations with
    strictly descriptive observations.

    Specifically:
    - Replace selling-pressure claims with statements
    about negative returns coinciding with high volume.
    - Remove all temporal-clustering claims.
    - Remove claims that events are marked as verified.
    - Preserve the correct numerical values.
    - Preserve the report structure.

    Return only the revised report.
    """
            ),
            HumanMessage(
                content=(
                    f"ORIGINAL QUESTION:\n{query}\n\n"
                    f"SOURCE DATA:\n"
                    f"{json.dumps(data, default=str)}\n\n"
                    f"CURRENT REPORT:\n{answer}\n\n"
                    f"VALIDATION ERRORS:\n"
                    f"{json.dumps(validation['errors'])}\n\n"
                    f"VALIDATION WARNINGS:\n"
                    f"{json.dumps(validation['warnings'])}"
                )
            ),
        ]

        revised_response = llm.invoke(revision_messages)

        if not revised_response.content:
            print("\nRevision failed: LLM returned empty content.")
            break
        
        answer = revised_response.content
        # Remove unsupported interpretation lines.
        # These lines are optional commentary, not required statistics.

        blocked_labels = (
            "**Temporal distribution:**",
            "- **Temporal distribution:**",
            "**Verification status:**",
            "- **Verification status:**",
            "**Volume-driven signals:**",
            "- **Volume-driven signals:**",
        )

        answer = "\n".join(
            line
            for line in answer.splitlines()
            if not any(
                line.strip().startswith(label)
                for label in blocked_labels
            )
            and not (
                "clustering metrics" in line.lower()
                and "speculative" in line.lower()
            )
        )

        # Replace the unsupported report summary with a
        # deterministic summary built from Python results.

        summary = data["summary"]

        safe_summary = (
            "\n---\n"
            "**Report Summary**\n"
            f"The analysis identified "
            f"{summary['total_anomalies']} anomalies: "
            f"{summary['negative_anomalies']} with negative returns "
            f"and {summary['positive_anomalies']} with positive returns. "
            "Each event satisfies the specified volume and "
            "absolute-return thresholds."
        )

        # Remove the LLM-generated Report Summary.
        answer = answer.split("**Report Summary**")[0].rstrip()

        # Append the deterministic summary.
        answer += safe_summary
        debug_print("\nDEBUG: POST-FILTER REPORT")
        print(answer)

    # Save the latest draft if validation still fails
    with open("report_draft.txt", "w", encoding="utf-8") as f:
        f.write(answer)

    print("\nReport requires review before publication.")
    print("Draft saved to report_draft.txt")


