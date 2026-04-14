"""
Leading indicator detection — cross-domain time-series correlation analysis.

Computes rolling correlations between event category pairs to find cases where
one domain leads another (e.g., wheat price spikes precede political instability
by 60-90 days, as seen in the Arab Spring).

Uses Pearson correlation on daily event counts, with configurable lag windows.
Claude evaluates whether detected correlations are causal or coincidental.
"""
import json
import logging
import math
import uuid
from datetime import datetime, timezone, timedelta

import anthropic

from config.settings import CLAUDE_API_KEY

logger = logging.getLogger(__name__)

MODEL = "claude-sonnet-4-20250514"

# Known historical leading indicator patterns
KNOWN_PATTERNS = [
    {
        "name": "food_price → political_instability",
        "leading": "economic",
        "lagging": "political",
        "typical_lag_days": 60,
        "description": "Food price spikes historically precede political unrest (Arab Spring 2011, Sri Lanka 2022).",
    },
    {
        "name": "military_buildup → conflict_escalation",
        "leading": "military",
        "lagging": "political",
        "typical_lag_days": 14,
        "description": "Military exercises and troop movements precede diplomatic crises and conflict escalation.",
    },
    {
        "name": "economic_crisis → health_degradation",
        "leading": "economic",
        "lagging": "health",
        "typical_lag_days": 90,
        "description": "Economic collapse degrades healthcare systems, leading to disease outbreaks (Venezuela, Lebanon).",
    },
    {
        "name": "environmental_disaster → economic_shock",
        "leading": "environmental",
        "lagging": "economic",
        "typical_lag_days": 30,
        "description": "Major environmental events (floods, droughts) cause supply chain disruptions and commodity spikes.",
    },
    {
        "name": "political_repression → military_response",
        "leading": "political",
        "lagging": "military",
        "typical_lag_days": 21,
        "description": "Political crackdowns escalate to military deployments and armed conflict.",
    },
]

INTERPRETATION_PROMPT = """You are a senior intelligence analyst evaluating a potential leading indicator signal.

INDICATOR: {indicator_name}
DESCRIPTION: {description}

DATA:
- Leading series ({leading}): {leading_data}
- Lagging series ({lagging}): {lagging_data}
- Computed correlation: {correlation:.3f} at {lag_days}-day lag
- Country/Region: {scope}

HISTORICAL CONTEXT:
{historical_context}

Evaluate this signal:
1. Is this correlation likely causal or coincidental in this specific context?
2. How does the current signal compare to historical precedents?
3. What is the probability that the lagging outcome materializes?
4. What should analysts watch for in the next {lag_days} days?

Respond with a JSON object:
{{
  "is_causal": true/false,
  "confidence": 0.0-1.0,
  "assessment": "2-3 sentence evaluation",
  "watch_items": ["what to monitor 1", "what to monitor 2"],
  "historical_accuracy": 0.0-1.0,
  "recommended_action": "what the analyst should do"
}}

Respond ONLY with the JSON object.
"""


def get_daily_event_counts(conn, category: str, country_code: str | None = None, days: int = 120) -> list[tuple[str, int]]:
    """Get daily event counts for a category, optionally filtered by country."""
    cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()

    query = """
        SELECT date(timestamp) as day, COUNT(*) as cnt
        FROM events
        WHERE category = ? AND timestamp >= ?
    """
    params = [category, cutoff]

    if country_code:
        query += " AND country_code = ?"
        params.append(country_code)

    query += " GROUP BY day ORDER BY day"
    rows = conn.execute(query, params).fetchall()
    return [(r["day"], r["cnt"]) for r in rows]


def fill_daily_series(data: list[tuple[str, int]], days: int = 120) -> list[int]:
    """Fill gaps in daily series with zeros, returning a contiguous array."""
    if not data:
        return [0] * days

    lookup = dict(data)
    start = datetime.now(timezone.utc) - timedelta(days=days)
    series = []
    for i in range(days):
        day = (start + timedelta(days=i)).strftime("%Y-%m-%d")
        series.append(lookup.get(day, 0))
    return series


def pearson_correlation(x: list[int | float], y: list[int | float]) -> float:
    """Compute Pearson correlation coefficient between two series."""
    n = len(x)
    if n < 5 or n != len(y):
        return 0.0

    mx = sum(x) / n
    my = sum(y) / n

    num = sum((xi - mx) * (yi - my) for xi, yi in zip(x, y))
    dx = math.sqrt(sum((xi - mx) ** 2 for xi in x))
    dy = math.sqrt(sum((yi - my) ** 2 for yi in y))

    if dx == 0 or dy == 0:
        return 0.0

    return num / (dx * dy)


def compute_lagged_correlation(
    leading: list[int],
    lagging: list[int],
    lag_days: int,
) -> float:
    """
    Compute correlation between leading series and lagging series offset by lag_days.

    If lag_days = 30, we correlate leading[:-30] with lagging[30:] —
    testing whether leading events 30 days ago predict lagging events today.
    """
    if lag_days <= 0 or lag_days >= len(leading):
        return 0.0

    x = leading[:len(leading) - lag_days]
    y = lagging[lag_days:]

    # Trim to same length
    min_len = min(len(x), len(y))
    if min_len < 10:
        return 0.0

    return pearson_correlation(x[:min_len], y[:min_len])


def find_best_lag(leading: list[int], lagging: list[int], max_lag: int = 90) -> tuple[int, float]:
    """Find the lag that maximizes correlation between two series."""
    best_lag = 0
    best_corr = 0.0

    for lag in range(7, min(max_lag + 1, len(leading) // 2)):
        corr = compute_lagged_correlation(leading, lagging, lag)
        if abs(corr) > abs(best_corr):
            best_corr = corr
            best_lag = lag

    return best_lag, best_corr


def scan_indicators(conn, country_code: str | None = None, days: int = 120) -> list[dict]:
    """
    Scan all known leading indicator patterns for a given scope.

    Returns list of detected signals with correlation strength.
    """
    results = []

    for pattern in KNOWN_PATTERNS:
        leading_data = get_daily_event_counts(conn, pattern["leading"], country_code, days)
        lagging_data = get_daily_event_counts(conn, pattern["lagging"], country_code, days)

        leading_series = fill_daily_series(leading_data, days)
        lagging_series = fill_daily_series(lagging_data, days)

        # Check if there's enough data
        if sum(leading_series) < 5 or sum(lagging_series) < 5:
            continue

        # Compute correlation at the typical lag
        corr = compute_lagged_correlation(
            leading_series, lagging_series, pattern["typical_lag_days"]
        )

        # Also find best lag
        best_lag, best_corr = find_best_lag(leading_series, lagging_series)

        # Is the leading indicator currently elevated?
        recent_window = 7
        recent_avg = sum(leading_series[-recent_window:]) / recent_window if recent_window <= len(leading_series) else 0
        baseline_avg = sum(leading_series[:-recent_window]) / max(len(leading_series) - recent_window, 1) if len(leading_series) > recent_window else 0
        is_elevated = recent_avg > baseline_avg * 1.5 if baseline_avg > 0 else False

        # Determine status
        if abs(corr) >= 0.3 and is_elevated:
            status = "firing"
        elif abs(corr) >= 0.3:
            status = "dormant"
        else:
            status = "weak"

        results.append({
            "pattern": pattern["name"],
            "leading": pattern["leading"],
            "lagging": pattern["lagging"],
            "description": pattern["description"],
            "correlation_at_typical_lag": round(corr, 3),
            "typical_lag_days": pattern["typical_lag_days"],
            "best_lag_days": best_lag,
            "best_correlation": round(best_corr, 3),
            "recent_leading_avg": round(recent_avg, 2),
            "baseline_leading_avg": round(baseline_avg, 2),
            "is_elevated": is_elevated,
            "status": status,
            "country_code": country_code,
        })

    return results


def store_indicator(conn, indicator: dict) -> str:
    """Store a detected leading indicator in the database."""
    ind_id = str(uuid.uuid4())
    conn.execute(
        """INSERT INTO leading_indicators
           (id, indicator_name, leading_series, lagging_series, correlation,
            lag_days, current_status, last_signal_value, threshold,
            description, historical_accuracy)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            ind_id,
            indicator["pattern"],
            indicator["leading"],
            indicator["lagging"],
            indicator["best_correlation"],
            indicator["best_lag_days"],
            indicator["status"],
            indicator["recent_leading_avg"],
            indicator["baseline_leading_avg"] * 1.5,  # 1.5x baseline as threshold
            indicator["description"],
            None,  # historical_accuracy filled by Claude
        ),
    )
    conn.commit()
    return ind_id


def evaluate_indicator(conn, indicator: dict) -> dict:
    """Use Claude to evaluate whether a detected correlation is meaningful."""
    if not CLAUDE_API_KEY:
        return {
            "is_causal": None,
            "confidence": 0.0,
            "assessment": "Evaluation requires Claude API key",
            "model_used": None,
        }

    scope = indicator.get("country_code", "Global")

    try:
        client = anthropic.Anthropic(api_key=CLAUDE_API_KEY)
        prompt = INTERPRETATION_PROMPT.format(
            indicator_name=indicator["pattern"],
            description=indicator["description"],
            leading=indicator["leading"],
            lagging=indicator["lagging"],
            leading_data=f"Recent avg: {indicator['recent_leading_avg']:.1f}/day, Baseline: {indicator['baseline_leading_avg']:.1f}/day",
            lagging_data=f"Correlation with {indicator['leading']}: {indicator['best_correlation']:.3f}",
            correlation=indicator["best_correlation"],
            lag_days=indicator["best_lag_days"],
            scope=scope,
            historical_context=indicator["description"],
        )

        message = client.messages.create(
            model=MODEL,
            max_tokens=800,
            messages=[{"role": "user", "content": prompt}],
        )
        content = message.content[0].text.strip()
        if "```json" in content:
            content = content.split("```json")[1].split("```")[0].strip()
        elif "```" in content:
            content = content.split("```")[1].split("```")[0].strip()

        result = json.loads(content)
        result["model_used"] = MODEL
        return result

    except (json.JSONDecodeError, anthropic.APIError) as e:
        logger.error("Leading indicator evaluation error: %s", e)
        return {
            "is_causal": None,
            "confidence": 0.0,
            "assessment": f"Evaluation failed: {e}",
            "model_used": None,
        }


def run_indicator_scan(conn, country_code: str | None = None) -> dict:
    """
    Run full leading indicator scan: detect patterns, store firing indicators,
    optionally evaluate with Claude.
    """
    indicators = scan_indicators(conn, country_code)

    firing = [i for i in indicators if i["status"] == "firing"]
    dormant = [i for i in indicators if i["status"] == "dormant"]

    # Store firing indicators
    stored_ids = []
    for ind in firing:
        ind_id = store_indicator(conn, ind)
        stored_ids.append(ind_id)

    return {
        "total_patterns_checked": len(indicators),
        "firing": len(firing),
        "dormant": len(dormant),
        "weak": len([i for i in indicators if i["status"] == "weak"]),
        "indicators": indicators,
        "stored_ids": stored_ids,
        "country_code": country_code,
    }


def list_indicators(conn, status: str | None = None, limit: int = 20) -> list[dict]:
    """List stored leading indicators."""
    query = "SELECT * FROM leading_indicators"
    params = []
    if status:
        query += " WHERE current_status = ?"
        params.append(status)
    query += " ORDER BY updated_at DESC LIMIT ?"
    params.append(limit)

    rows = conn.execute(query, params).fetchall()
    return [dict(r) for r in rows]
