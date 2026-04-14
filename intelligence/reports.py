"""
Report generation — country risk profiles and weekly trend reports.

Country profiles: per-country risk summaries with event analysis.
Weekly reports: "week in review" global trend analysis.
Both use Claude Sonnet when available, with graceful fallback to raw data.
"""
import json
import logging
import uuid
from datetime import datetime, timezone, timedelta

import anthropic

from config.settings import CLAUDE_API_KEY

logger = logging.getLogger(__name__)

MODEL = "claude-sonnet-4-20250514"

COUNTRY_PROFILE_PROMPT = """You are a senior intelligence analyst writing a weekly country risk profile.

COUNTRY: {country_name} ({country_code})
PERIOD: {period_start} to {period_end}

EVENTS THIS WEEK ({event_count} total):
{events_text}

RISK DATA:
- Current risk score: {risk_score}
- Event categories: {categories_text}

Write a concise risk profile. Provide a JSON object with:
1. "executive_summary": 2-3 paragraph summary of the country's risk situation this week
2. "key_events": Array of 3-5 most significant event summaries (strings)
3. "predictions": Array of 2-3 predictions for next week (strings)
4. "risk_trend": one of "rising", "stable", "falling"

Respond ONLY with the JSON object. Base everything on the provided data.
"""

WEEKLY_REPORT_PROMPT = """You are a senior intelligence analyst writing a weekly global trend report.

PERIOD: {week_start} to {week_end}

GLOBAL STATISTICS:
- Total events: {total_events}
- Average severity: {avg_severity}
- Top countries: {top_countries}
- Top categories: {top_categories}

KEY EVENTS THIS WEEK:
{events_text}

PREDICTION PERFORMANCE:
{prediction_text}

Write a "Week in Review" intelligence brief. Provide a JSON object with:
1. "title": Catchy title for this week's report (under 60 chars)
2. "executive_summary": 2-3 paragraph overview of the week's intelligence landscape
3. "trending_topics": Array of 3-5 trending topic strings
4. "outlook": 1-2 paragraph outlook for the coming week

Respond ONLY with the JSON object.
"""


def gather_country_data(conn, country_code: str, days: int = 7) -> dict:
    """Gather intelligence data for a country over a period."""
    cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()

    events = conn.execute(
        """SELECT id, source, title, category, severity, timestamp
           FROM events
           WHERE country_code = ? AND timestamp >= ?
           ORDER BY severity DESC LIMIT 50""",
        (country_code, cutoff),
    ).fetchall()

    # Category breakdown
    cats = conn.execute(
        """SELECT category, COUNT(*) as cnt
           FROM events
           WHERE country_code = ? AND timestamp >= ?
           GROUP BY category ORDER BY cnt DESC""",
        (country_code, cutoff),
    ).fetchall()

    # Risk score
    risk_row = conn.execute(
        """SELECT score, trend FROM risk_scores
           WHERE scope_type = 'country' AND scope_value = ?
           ORDER BY updated_at DESC LIMIT 1""",
        (country_code,),
    ).fetchone()

    return {
        "events": [dict(r) for r in events],
        "categories": [dict(r) for r in cats],
        "risk_score": risk_row["score"] if risk_row else 0,
        "risk_trend": risk_row["trend"] if risk_row else "stable",
        "event_count": len(events),
    }


def generate_country_profile(conn, country_code: str, country_name: str, days: int = 7) -> dict:
    """Generate a country risk profile for the given period."""
    now = datetime.now(timezone.utc)
    period_end = now.strftime("%Y-%m-%d")
    period_start = (now - timedelta(days=days)).strftime("%Y-%m-%d")

    data = gather_country_data(conn, country_code, days)

    events_text = "\n".join(
        f"  [{e['source']}] {e['timestamp'][:10]} | {e['title']} (sev={e['severity']})"
        for e in data["events"][:20]
    ) or "No events this period."

    categories_text = ", ".join(
        f"{c['category']}: {c['cnt']}" for c in data["categories"]
    ) or "None"

    profile_id = str(uuid.uuid4())

    # Try Claude synthesis
    executive_summary = f"Risk profile for {country_name} ({country_code}). {data['event_count']} events in the past {days} days."
    key_events = [e["title"] for e in data["events"][:5]]
    predictions = []
    risk_trend = data["risk_trend"]
    model_used = None

    if CLAUDE_API_KEY and data["event_count"] > 0:
        try:
            client = anthropic.Anthropic(api_key=CLAUDE_API_KEY)
            prompt = COUNTRY_PROFILE_PROMPT.format(
                country_name=country_name, country_code=country_code,
                period_start=period_start, period_end=period_end,
                event_count=data["event_count"],
                events_text=events_text,
                risk_score=data["risk_score"],
                categories_text=categories_text,
            )
            message = client.messages.create(
                model=MODEL, max_tokens=1500,
                messages=[{"role": "user", "content": prompt}],
            )
            content = message.content[0].text.strip()
            if "```json" in content:
                content = content.split("```json")[1].split("```")[0].strip()
            elif "```" in content:
                content = content.split("```")[1].split("```")[0].strip()

            result = json.loads(content)
            executive_summary = result.get("executive_summary", executive_summary)
            key_events = result.get("key_events", key_events)
            predictions = result.get("predictions", [])
            risk_trend = result.get("risk_trend", risk_trend)
            model_used = MODEL
        except (json.JSONDecodeError, anthropic.APIError) as e:
            logger.error("Country profile generation error: %s", e)

    # Store profile
    conn.execute(
        """INSERT INTO country_profiles
           (id, country_code, country_name, period_start, period_end,
            risk_score, risk_trend, event_count, top_categories,
            executive_summary, key_events, predictions, model_used)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            profile_id, country_code, country_name, period_start, period_end,
            data["risk_score"], risk_trend, data["event_count"],
            json.dumps(data["categories"]),
            executive_summary, json.dumps(key_events),
            json.dumps(predictions), model_used,
        ),
    )
    conn.commit()

    return {
        "profile_id": profile_id,
        "country_code": country_code,
        "country_name": country_name,
        "period": f"{period_start} to {period_end}",
        "risk_score": data["risk_score"],
        "risk_trend": risk_trend,
        "event_count": data["event_count"],
        "executive_summary": executive_summary,
        "key_events": key_events,
        "predictions": predictions,
        "model_used": model_used,
    }


def generate_weekly_report(conn) -> dict:
    """Generate a global weekly trend report."""
    now = datetime.now(timezone.utc)
    week_end = now.strftime("%Y-%m-%d")
    week_start = (now - timedelta(days=7)).strftime("%Y-%m-%d")
    cutoff = (now - timedelta(days=7)).isoformat()

    # Global stats
    stats = conn.execute(
        """SELECT COUNT(*) as total, AVG(severity) as avg_sev
           FROM events WHERE timestamp >= ?""",
        (cutoff,),
    ).fetchone()

    total_events = stats["total"] or 0
    avg_severity = round(stats["avg_sev"] or 0, 1)

    # Top countries
    top_countries_rows = conn.execute(
        """SELECT country_code, COUNT(*) as cnt
           FROM events WHERE timestamp >= ? AND country_code IS NOT NULL
           GROUP BY country_code ORDER BY cnt DESC LIMIT 5""",
        (cutoff,),
    ).fetchall()
    top_countries = [f"{r['country_code']}: {r['cnt']}" for r in top_countries_rows]

    # Top categories
    top_cats_rows = conn.execute(
        """SELECT category, COUNT(*) as cnt
           FROM events WHERE timestamp >= ? AND category IS NOT NULL
           GROUP BY category ORDER BY cnt DESC LIMIT 5""",
        (cutoff,),
    ).fetchall()
    top_categories = [f"{r['category']}: {r['cnt']}" for r in top_cats_rows]

    # Key events
    key_events = conn.execute(
        """SELECT source, title, severity, country_code, timestamp
           FROM events WHERE timestamp >= ?
           ORDER BY severity DESC LIMIT 15""",
        (cutoff,),
    ).fetchall()

    events_text = "\n".join(
        f"  [{e['source']}] {e['timestamp'][:10]} | {e['title']} (sev={e['severity']}, cc={e['country_code']})"
        for e in key_events
    ) or "No events this week."

    # Prediction performance
    pred_stats = conn.execute(
        """SELECT COUNT(*) as total,
                  SUM(CASE WHEN outcome = 'correct' THEN 1 ELSE 0 END) as correct,
                  SUM(CASE WHEN outcome = 'incorrect' THEN 1 ELSE 0 END) as incorrect
           FROM predictions WHERE created_at >= ?""",
        (cutoff,),
    ).fetchone()
    prediction_text = (
        f"Predictions made: {pred_stats['total'] or 0}, "
        f"Correct: {pred_stats['correct'] or 0}, "
        f"Incorrect: {pred_stats['incorrect'] or 0}"
    )

    report_id = str(uuid.uuid4())

    # Defaults
    title = f"Week in Review: {week_start} to {week_end}"
    executive_summary = f"Global intelligence summary for the week of {week_start}. {total_events} events processed with average severity {avg_severity}."
    trending_topics = [c.split(":")[0].strip() for c in top_categories[:3]]
    outlook = "Continued monitoring recommended across all domains."
    model_used = None
    global_risk = avg_severity

    if CLAUDE_API_KEY and total_events > 0:
        try:
            client = anthropic.Anthropic(api_key=CLAUDE_API_KEY)
            prompt = WEEKLY_REPORT_PROMPT.format(
                week_start=week_start, week_end=week_end,
                total_events=total_events, avg_severity=avg_severity,
                top_countries=", ".join(top_countries),
                top_categories=", ".join(top_categories),
                events_text=events_text,
                prediction_text=prediction_text,
            )
            message = client.messages.create(
                model=MODEL, max_tokens=1500,
                messages=[{"role": "user", "content": prompt}],
            )
            content = message.content[0].text.strip()
            if "```json" in content:
                content = content.split("```json")[1].split("```")[0].strip()
            elif "```" in content:
                content = content.split("```")[1].split("```")[0].strip()

            result = json.loads(content)
            title = result.get("title", title)
            executive_summary = result.get("executive_summary", executive_summary)
            trending_topics = result.get("trending_topics", trending_topics)
            outlook = result.get("outlook", outlook)
            model_used = MODEL
        except (json.JSONDecodeError, anthropic.APIError) as e:
            logger.error("Weekly report generation error: %s", e)

    conn.execute(
        """INSERT INTO weekly_reports
           (id, week_start, week_end, title, executive_summary,
            global_risk_score, trending_topics, key_events,
            predictions_review, outlook, model_used)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            report_id, week_start, week_end, title, executive_summary,
            global_risk, json.dumps(trending_topics),
            json.dumps([dict(e) for e in key_events[:10]]),
            prediction_text, outlook, model_used,
        ),
    )
    conn.commit()

    return {
        "report_id": report_id,
        "title": title,
        "period": f"{week_start} to {week_end}",
        "total_events": total_events,
        "avg_severity": avg_severity,
        "executive_summary": executive_summary,
        "trending_topics": trending_topics,
        "outlook": outlook,
        "model_used": model_used,
    }
