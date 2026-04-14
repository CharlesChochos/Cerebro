"""
Historical analog matching — find past situations that resemble current events.

Intelligence analysts routinely compare emerging crises to historical precedents:
"Is this more like 1914 Sarajevo or 1962 Cuba?" This module automates that process
by matching event patterns (category, severity trajectory, regional context) against
a curated set of known historical analogs, then optionally uses Claude to assess
the quality of the match.
"""
import json
import logging
import uuid
from datetime import datetime, timezone, timedelta

import anthropic

from config.settings import CLAUDE_API_KEY

logger = logging.getLogger(__name__)

MODEL = "claude-sonnet-4-20250514"

# Curated historical analogs — each has a signature pattern of event characteristics
HISTORICAL_ANALOGS = [
    {
        "title": "Arab Spring (2011)",
        "year": 2011,
        "region": "Middle East & North Africa",
        "signature": {"categories": ["political", "economic"], "severity_range": [60, 100]},
        "description": "Economic grievances and food price spikes led to mass protests across MENA, "
                       "toppling governments in Tunisia, Egypt, Libya, and triggering civil war in Syria.",
        "outcome": "Regime changes, civil wars, prolonged regional instability, refugee crises.",
        "triggers": ["food_price_spike", "youth_unemployment", "political_repression"],
    },
    {
        "title": "Cuban Missile Crisis (1962)",
        "year": 1962,
        "region": "Caribbean",
        "signature": {"categories": ["military", "political"], "severity_range": [80, 100]},
        "description": "Soviet nuclear missile deployment in Cuba brought the US and USSR to the brink "
                       "of nuclear war. Resolved through back-channel diplomacy.",
        "outcome": "Negotiated withdrawal, hotline established, détente period followed.",
        "triggers": ["military_buildup", "nuclear_threat", "superpower_confrontation"],
    },
    {
        "title": "Asian Financial Crisis (1997)",
        "year": 1997,
        "region": "Southeast Asia",
        "signature": {"categories": ["economic"], "severity_range": [50, 90]},
        "description": "Currency collapses cascaded from Thailand across Southeast Asia, triggering "
                       "IMF bailouts and political upheaval.",
        "outcome": "Economic recession, political instability, IMF structural adjustments.",
        "triggers": ["currency_crisis", "capital_flight", "debt_default"],
    },
    {
        "title": "Crimea Annexation (2014)",
        "year": 2014,
        "region": "Eastern Europe",
        "signature": {"categories": ["military", "political"], "severity_range": [70, 100]},
        "description": "Russia annexed Crimea following Ukraine's Euromaidan revolution, "
                       "using hybrid warfare tactics and 'little green men'.",
        "outcome": "Territorial change, Western sanctions, frozen conflict in Donbas, 2022 escalation.",
        "triggers": ["political_transition", "military_buildup", "ethnic_tension"],
    },
    {
        "title": "Ebola Outbreak (2014)",
        "year": 2014,
        "region": "West Africa",
        "signature": {"categories": ["health", "economic"], "severity_range": [60, 100]},
        "description": "Ebola epidemic in Guinea, Liberia, Sierra Leone overwhelmed health systems "
                       "and devastated local economies.",
        "outcome": "11,000+ deaths, economic collapse in affected regions, international mobilization.",
        "triggers": ["disease_outbreak", "health_system_collapse", "border_closures"],
    },
    {
        "title": "Fukushima Disaster (2011)",
        "year": 2011,
        "region": "East Asia",
        "signature": {"categories": ["environmental", "economic"], "severity_range": [70, 100]},
        "description": "Earthquake and tsunami caused nuclear meltdown at Fukushima Daiichi, "
                       "triggering evacuation and global nuclear policy shifts.",
        "outcome": "Nuclear phase-out debate, long-term contamination, energy policy shifts worldwide.",
        "triggers": ["natural_disaster", "infrastructure_failure", "nuclear_incident"],
    },
    {
        "title": "Rwanda Genocide (1994)",
        "year": 1994,
        "region": "Central Africa",
        "signature": {"categories": ["military", "political"], "severity_range": [90, 100]},
        "description": "Systematic genocide of Tutsi population following assassination of President "
                       "Habyarimana. International community failed to intervene.",
        "outcome": "800,000+ killed in 100 days, refugee crisis, regional destabilization.",
        "triggers": ["ethnic_tension", "political_assassination", "hate_media"],
    },
    {
        "title": "Venezuelan Collapse (2014-present)",
        "year": 2014,
        "region": "South America",
        "signature": {"categories": ["economic", "political", "health"], "severity_range": [50, 90]},
        "description": "Oil price collapse combined with economic mismanagement led to hyperinflation, "
                       "healthcare collapse, and mass emigration.",
        "outcome": "Hyperinflation, 7M+ refugees, healthcare collapse, political crisis.",
        "triggers": ["commodity_crash", "economic_mismanagement", "political_crisis"],
    },
    {
        "title": "Suez Canal Blockage (2021)",
        "year": 2021,
        "region": "Middle East",
        "signature": {"categories": ["economic", "environmental"], "severity_range": [40, 70]},
        "description": "Ever Given container ship blocked the Suez Canal for 6 days, "
                       "disrupting $9.6B/day in global trade.",
        "outcome": "Supply chain disruptions, shipping rerouting, infrastructure vulnerability exposed.",
        "triggers": ["infrastructure_disruption", "supply_chain_shock", "trade_route_closure"],
    },
    {
        "title": "Color Revolutions (2003-2005)",
        "year": 2003,
        "region": "Eastern Europe / Central Asia",
        "signature": {"categories": ["political"], "severity_range": [50, 80]},
        "description": "Wave of pro-democracy movements in Georgia (2003), Ukraine (2004), "
                       "Kyrgyzstan (2005) challenged post-Soviet authoritarian regimes.",
        "outcome": "Democratic transitions (some reversed), Russian counter-measures, geopolitical realignment.",
        "triggers": ["election_fraud", "mass_protests", "democratic_demand"],
    },
]

MATCHING_PROMPT = """You are a senior intelligence analyst specializing in historical pattern analysis.

CURRENT SITUATION:
Region: {region}
Category: {category}
Average Severity: {avg_severity:.0f}/100
Event Count (30 days): {event_count}
Recent Events:
{events_summary}

CANDIDATE HISTORICAL ANALOG:
{analog_title} ({analog_year})
Description: {analog_description}
Outcome: {analog_outcome}

Assess how closely this historical analog matches the current situation.
Consider: geographic parallels, escalation dynamics, actor profiles, economic conditions,
and structural similarities (NOT superficial topic overlap).

Respond with a JSON object:
{{
  "similarity_score": 0.0 to 1.0,
  "key_similarities": ["similarity 1", "similarity 2", "similarity 3"],
  "key_differences": ["difference 1", "difference 2"],
  "risk_factors": ["risk if pattern repeats 1", "risk 2"],
  "outcome_likelihood": "1-2 sentence assessment of whether the historical outcome could repeat",
  "confidence": 0.0 to 1.0
}}

Respond ONLY with the JSON object.
"""


def compute_signature_match(event_profile: dict, analog: dict) -> float:
    """
    Compute a simple signature-based similarity score without Claude.

    Considers: category overlap, severity range overlap, and trigger keyword matches.
    """
    sig = analog["signature"]
    score = 0.0
    weights_total = 0.0

    # Category overlap (weight: 0.4)
    cat_overlap = len(set(event_profile.get("categories", [])) & set(sig["categories"]))
    cat_max = max(len(sig["categories"]), 1)
    score += 0.4 * (cat_overlap / cat_max)
    weights_total += 0.4

    # Severity range overlap (weight: 0.3)
    avg_sev = event_profile.get("avg_severity", 50)
    sev_min, sev_max = sig["severity_range"]
    if sev_min <= avg_sev <= sev_max:
        score += 0.3
    elif avg_sev < sev_min:
        score += 0.3 * max(0, 1 - (sev_min - avg_sev) / 30)
    else:
        score += 0.3 * max(0, 1 - (avg_sev - sev_max) / 30)
    weights_total += 0.3

    # Trigger keyword match (weight: 0.3) — match against event titles/summaries
    trigger_words = set()
    for t in analog.get("triggers", []):
        trigger_words.update(t.lower().split("_"))

    event_text = " ".join(event_profile.get("titles", [])).lower()
    if trigger_words and event_text:
        matched = sum(1 for w in trigger_words if w in event_text)
        score += 0.3 * min(matched / max(len(trigger_words), 1), 1.0)
    weights_total += 0.3

    return round(score / weights_total if weights_total > 0 else 0.0, 3)


def build_event_profile(conn, event_id: str | None = None,
                         region: str | None = None,
                         category: str | None = None) -> dict:
    """Build a profile of current events for analog matching."""
    conditions = []
    params = []

    if event_id:
        row = conn.execute("SELECT * FROM events WHERE id = ?", (event_id,)).fetchone()
        if row:
            if row["region"]:
                conditions.append("region = ?")
                params.append(row["region"])
            if row["category"]:
                conditions.append("category = ?")
                params.append(row["category"])
            region = row.get("region", region)
            category = row.get("category", category)

    if region and "region = ?" not in conditions:
        conditions.append("region = ?")
        params.append(region)

    if category and "category = ?" not in conditions:
        conditions.append("category = ?")
        params.append(category)

    if not conditions:
        conditions.append("1=1")

    where = " AND ".join(conditions)
    cutoff = (datetime.now(timezone.utc) - timedelta(days=30)).isoformat()

    events = conn.execute(
        f"""SELECT id, title, category, severity, summary
            FROM events WHERE {where} AND timestamp >= ?
            ORDER BY severity DESC LIMIT 30""",
        params + [cutoff],
    ).fetchall()

    categories = list(set(e["category"] for e in events if e["category"]))
    avg_severity = sum(e["severity"] for e in events) / max(len(events), 1) if events else 0
    titles = [e["title"] for e in events]

    return {
        "region": region or "Global",
        "category": category,
        "categories": categories,
        "avg_severity": avg_severity,
        "event_count": len(events),
        "titles": titles,
        "events": events,
    }


def find_analogs(conn, event_id: str | None = None,
                  region: str | None = None,
                  category: str | None = None,
                  top_n: int = 5) -> list[dict]:
    """
    Find the top-N historical analogs matching the current situation.

    Uses signature-based scoring, optionally enhanced by Claude for the top matches.
    """
    profile = build_event_profile(conn, event_id, region, category)

    if profile["event_count"] == 0:
        return []

    # Score all analogs
    scored = []
    for analog in HISTORICAL_ANALOGS:
        score = compute_signature_match(profile, analog)
        scored.append((score, analog))

    scored.sort(key=lambda x: x[0], reverse=True)
    top = scored[:top_n]

    results = []
    events_summary = "\n".join(
        f"  - [{e['id']}] sev={e['severity']} {e['title']}"
        for e in profile["events"][:10]
    )

    for score, analog in top:
        result = {
            "analog_title": analog["title"],
            "analog_year": analog["year"],
            "analog_region": analog["region"],
            "analog_description": analog["description"],
            "outcome_description": analog["outcome"],
            "similarity_score": score,
            "key_similarities": [],
            "key_differences": [],
            "risk_factors": [],
            "model_used": None,
        }

        # Use Claude for top matches with decent scores
        if CLAUDE_API_KEY and score >= 0.2:
            try:
                client = anthropic.Anthropic(api_key=CLAUDE_API_KEY)
                prompt = MATCHING_PROMPT.format(
                    region=profile["region"],
                    category=", ".join(profile["categories"]),
                    avg_severity=profile["avg_severity"],
                    event_count=profile["event_count"],
                    events_summary=events_summary,
                    analog_title=analog["title"],
                    analog_year=analog["year"],
                    analog_description=analog["description"],
                    analog_outcome=analog["outcome"],
                )
                message = client.messages.create(
                    model=MODEL,
                    max_tokens=600,
                    messages=[{"role": "user", "content": prompt}],
                )
                content = message.content[0].text.strip()
                if "```json" in content:
                    content = content.split("```json")[1].split("```")[0].strip()
                elif "```" in content:
                    content = content.split("```")[1].split("```")[0].strip()

                claude_result = json.loads(content)
                result["similarity_score"] = claude_result.get("similarity_score", score)
                result["key_similarities"] = claude_result.get("key_similarities", [])
                result["key_differences"] = claude_result.get("key_differences", [])
                result["risk_factors"] = claude_result.get("risk_factors", [])
                result["model_used"] = MODEL
            except (json.JSONDecodeError, anthropic.APIError) as e:
                logger.warning("Claude analog matching failed: %s", e)

        results.append(result)

    # Re-sort by final score
    results.sort(key=lambda x: x["similarity_score"], reverse=True)
    return results


def store_analog_match(conn, event_id: str | None, region: str | None,
                        category: str | None, analog: dict) -> str:
    """Store a matched historical analog in the database."""
    aid = str(uuid.uuid4())
    conn.execute(
        """INSERT INTO historical_analogs
           (id, source_event_id, source_region, source_category,
            analog_title, analog_description, analog_year, analog_region,
            similarity_score, outcome_description,
            key_differences, key_similarities, risk_factors, model_used)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            aid, event_id, region, category,
            analog["analog_title"], analog["analog_description"],
            analog["analog_year"], analog["analog_region"],
            analog["similarity_score"], analog["outcome_description"],
            json.dumps(analog.get("key_differences", [])),
            json.dumps(analog.get("key_similarities", [])),
            json.dumps(analog.get("risk_factors", [])),
            analog.get("model_used"),
        ),
    )
    conn.commit()
    return aid


def run_analog_search(conn, event_id: str | None = None,
                       region: str | None = None,
                       category: str | None = None,
                       top_n: int = 5) -> dict:
    """Full analog search: find matches and store the top ones."""
    analogs = find_analogs(conn, event_id, region, category, top_n)

    stored_ids = []
    for a in analogs:
        if a["similarity_score"] >= 0.1:
            aid = store_analog_match(conn, event_id, region, category, a)
            stored_ids.append(aid)

    return {
        "total_analogs_checked": len(HISTORICAL_ANALOGS),
        "matches_found": len(analogs),
        "stored": len(stored_ids),
        "analogs": analogs,
    }


def list_analog_matches(conn, category: str | None = None, limit: int = 20) -> list[dict]:
    """List stored historical analog matches."""
    query = "SELECT * FROM historical_analogs"
    params = []
    if category:
        query += " WHERE source_category = ?"
        params.append(category)
    query += " ORDER BY created_at DESC LIMIT ?"
    params.append(limit)

    rows = conn.execute(query, params).fetchall()
    results = []
    for r in rows:
        d = dict(r)
        for field in ("key_differences", "key_similarities", "risk_factors"):
            d[field] = json.loads(d[field]) if d[field] else []
        results.append(d)
    return results


def get_analog_match(conn, analog_id: str) -> dict | None:
    """Get a single stored analog match."""
    row = conn.execute(
        "SELECT * FROM historical_analogs WHERE id = ?", (analog_id,)
    ).fetchone()
    if not row:
        return None
    d = dict(row)
    for field in ("key_differences", "key_similarities", "risk_factors"):
        d[field] = json.loads(d[field]) if d[field] else []
    return d
