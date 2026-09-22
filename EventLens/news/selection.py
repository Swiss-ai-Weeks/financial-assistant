"""One shared, deterministic anomaly selector for ingestion and investigation."""
import json
import random
from datetime import date, timedelta


def select_events(payload, *, demo=True, today=None, count=3, seed=42):
    """Demo: choose up to count events from the last 365 days, including today.

    Keep the source payload unchanged. Production: use all original events.
    """
    if not demo:
        return payload
    today = today or date.today()
    cutoff = today - timedelta(days=365)
    eligible = [event for event in payload['events']
                if cutoff <= date.fromisoformat(event['date'][:10]) <= today]
    eligible.sort(key=lambda event: (event['date'], json.dumps(event, sort_keys=True)))
    chosen = random.Random(seed).sample(eligible, min(count, len(eligible)))
    chosen.sort(key=lambda event: event['date'])
    return {**payload, 'events': chosen}
