"""
Multi-perspective simulation — parallel actor interpretations of events.

For events involving multiple state actors, generates each actor's likely
interpretation. Divergence between perspectives signals miscalculation risk —
the most dangerous kind of intelligence failure.

Uses Claude Sonnet for each perspective, then computes a divergence score.
"""
import json
import logging
import uuid
from datetime import datetime, timezone

import anthropic

from config.settings import CLAUDE_API_KEY

logger = logging.getLogger(__name__)

MODEL = "claude-sonnet-4-20250514"

PERSPECTIVE_PROMPT = """You are simulating the worldview and decision calculus of {actor}.

SITUATION:
{scenario}

RECENT EVENTS:
{events_text}

Adopt the perspective of {actor}'s leadership and intelligence apparatus.
Consider their:
- Strategic objectives and red lines
- Domestic political pressures
- Historical patterns of behavior
- Information environment (what they likely know vs. don't know)
- Cultural and ideological framing

Respond with a JSON object:
{{
  "actor": "{actor}",
  "interpretation": "How {actor} likely interprets this situation (2-3 sentences)",
  "perceived_threats": ["threat 1", "threat 2"],
  "strategic_goals": ["goal 1", "goal 2"],
  "likely_response": "Most probable course of action (1-2 sentences)",
  "escalation_risk": 0.0 to 1.0,
  "miscalculation_factors": ["factor that could cause {actor} to miscalculate"],
  "information_gaps": ["what {actor} probably doesn't know that matters"]
}}

Respond ONLY with the JSON object.
"""

DIVERGENCE_PROMPT = """You are a senior intelligence analyst assessing miscalculation risk.

SCENARIO: {scenario}

ACTOR PERSPECTIVES:
{perspectives_text}

Analyze the divergence between these perspectives. Focus on:
1. Where do actors fundamentally misunderstand each other's intentions?
2. What actions by one actor could be misinterpreted by another?
3. Where are the escalation tripwires that actors might not realize they're approaching?

Respond with a JSON object:
{{
  "divergence_score": 0.0 to 1.0 (higher = more dangerous divergence),
  "critical_misperceptions": ["misperception 1", "misperception 2"],
  "escalation_tripwires": ["tripwire 1", "tripwire 2"],
  "miscalculation_risk": "overall assessment paragraph",
  "de_escalation_options": ["option 1", "option 2"]
}}

Respond ONLY with the JSON object.
"""


def identify_actors(conn, event_id: str | None = None, region: str | None = None) -> list[str]:
    """Identify relevant state actors from event data."""
    conditions = []
    params = []

    if event_id:
        # Get the event's region and country
        row = conn.execute(
            "SELECT country_code, region, entities_json FROM events WHERE id = ?",
            (event_id,),
        ).fetchone()
        if row:
            if row["country_code"]:
                conditions.append("country_code = ?")
                params.append(row["country_code"])
            if row["region"]:
                conditions.append("region = ?")
                params.append(row["region"])

    if region:
        conditions.append("region = ?")
        params.append(region)

    if not conditions:
        conditions.append("1=1")

    # Find countries with most events in the area
    where = " OR ".join(conditions)
    rows = conn.execute(
        f"""SELECT country_code, COUNT(*) as cnt
            FROM events
            WHERE ({where}) AND country_code IS NOT NULL
            AND julianday('now') - julianday(timestamp) <= 30
            GROUP BY country_code
            ORDER BY cnt DESC LIMIT 5""",
        params,
    ).fetchall()

    # Map country codes to actor names
    ACTOR_NAMES = {
        "US": "United States", "CN": "China", "RU": "Russia", "GB": "United Kingdom",
        "FR": "France", "DE": "Germany", "IN": "India", "JP": "Japan",
        "KR": "South Korea", "KP": "North Korea", "IR": "Iran", "SA": "Saudi Arabia",
        "IL": "Israel", "TR": "Turkey", "UA": "Ukraine", "TW": "Taiwan",
        "PK": "Pakistan", "BR": "Brazil", "AU": "Australia", "EG": "Egypt",
    }

    actors = []
    for r in rows:
        cc = r["country_code"]
        name = ACTOR_NAMES.get(cc, cc)
        actors.append(name)

    # Ensure at least 2 actors for meaningful simulation
    if len(actors) < 2:
        actors = ["United States", "China", "Russia"][:3 - len(actors)] + actors

    return actors[:5]


def gather_scenario_context(conn, event_id: str | None = None, region: str | None = None) -> tuple[str, str]:
    """Gather scenario description and events text."""
    conditions = []
    params = []

    if event_id:
        row = conn.execute("SELECT * FROM events WHERE id = ?", (event_id,)).fetchone()
        if row:
            scenario = f"Event: {row['title']}\nRegion: {row.get('region', 'Unknown')}\nCountry: {row.get('country_code', '?')}\nSummary: {row.get('summary', 'N/A')}"
            conditions.append("(region = ? OR country_code = ?)")
            params.extend([row.get("region"), row.get("country_code")])
        else:
            return "", ""
    elif region:
        scenario = f"Situation in {region}"
        conditions.append("region = ?")
        params.append(region)
    else:
        return "", ""

    where = " AND ".join(conditions) if conditions else "1=1"
    events = conn.execute(
        f"""SELECT id, source, title, severity, category, country_code, timestamp
            FROM events WHERE {where}
            AND julianday('now') - julianday(timestamp) <= 7
            ORDER BY severity DESC LIMIT 15""",
        params,
    ).fetchall()

    events_text = "\n".join(
        f"  [{e['id']}] ({e['source']}) {e['category'] or '?'} sev={e['severity']} — {e['title']}"
        for e in events
    ) or "No recent events."

    return scenario, events_text


def generate_perspective(
    client: anthropic.Anthropic,
    actor: str,
    scenario: str,
    events_text: str,
) -> dict:
    """Generate a single actor's perspective using Claude."""
    prompt = PERSPECTIVE_PROMPT.format(
        actor=actor,
        scenario=scenario,
        events_text=events_text,
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

    return json.loads(content)


def compute_divergence(
    client: anthropic.Anthropic,
    scenario: str,
    perspectives: list[dict],
) -> dict:
    """Compute divergence score and miscalculation risk across perspectives."""
    perspectives_text = "\n\n".join(
        f"--- {p['actor']} ---\n"
        f"Interpretation: {p['interpretation']}\n"
        f"Likely response: {p['likely_response']}\n"
        f"Escalation risk: {p['escalation_risk']}"
        for p in perspectives
    )

    prompt = DIVERGENCE_PROMPT.format(
        scenario=scenario,
        perspectives_text=perspectives_text,
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

    return json.loads(content)


def compute_divergence_simple(perspectives: list[dict]) -> float:
    """
    Compute divergence without Claude — uses escalation risk variance.
    High variance in how different actors perceive escalation risk = high divergence.
    """
    risks = [p.get("escalation_risk", 0.5) for p in perspectives]
    if len(risks) < 2:
        return 0.0
    mean = sum(risks) / len(risks)
    variance = sum((r - mean) ** 2 for r in risks) / len(risks)
    # Normalize: variance of [0,1] range maxes at 0.25
    return min(variance / 0.25, 1.0)


def run_multi_perspective(
    conn,
    event_id: str | None = None,
    region: str | None = None,
    actors: list[str] | None = None,
) -> dict:
    """
    Run multi-perspective simulation on an event or region.

    Returns stored simulation with all perspectives and divergence assessment.
    """
    scenario, events_text = gather_scenario_context(conn, event_id, region)
    if not scenario:
        return {"error": "no_scenario_context"}

    if not actors:
        actors = identify_actors(conn, event_id, region)

    sim_id = str(uuid.uuid4())
    perspectives = []
    model_used = None

    if CLAUDE_API_KEY and len(actors) >= 2:
        try:
            client = anthropic.Anthropic(api_key=CLAUDE_API_KEY)

            # Generate each actor's perspective
            for actor in actors:
                try:
                    persp = generate_perspective(client, actor, scenario, events_text)
                    perspectives.append(persp)
                except (json.JSONDecodeError, anthropic.APIError) as e:
                    logger.warning("Failed perspective for %s: %s", actor, e)
                    perspectives.append({
                        "actor": actor,
                        "interpretation": f"Perspective generation failed for {actor}",
                        "escalation_risk": 0.5,
                        "likely_response": "Unknown",
                        "perceived_threats": [],
                        "strategic_goals": [],
                        "miscalculation_factors": [],
                        "information_gaps": [],
                    })

            # Compute divergence
            try:
                divergence_result = compute_divergence(client, scenario, perspectives)
                divergence_score = divergence_result.get("divergence_score", 0.5)
                miscalculation_risk = divergence_result.get("miscalculation_risk", "")
            except (json.JSONDecodeError, anthropic.APIError):
                divergence_score = compute_divergence_simple(perspectives)
                miscalculation_risk = f"Divergence computed from escalation risk variance: {divergence_score:.2f}"

            model_used = MODEL

        except anthropic.APIError as e:
            logger.error("Multi-perspective API error: %s", e)
            return {"error": str(e)}
    else:
        # Fallback: generate stub perspectives without Claude
        for actor in actors:
            perspectives.append({
                "actor": actor,
                "interpretation": f"{actor} perspective not available (no API key)",
                "escalation_risk": 0.5,
                "likely_response": "Assessment requires Claude API",
                "perceived_threats": [],
                "strategic_goals": [],
                "miscalculation_factors": [],
                "information_gaps": [],
            })
        divergence_score = 0.0
        miscalculation_risk = "Multi-perspective analysis requires Claude API key"

    scenario_title = scenario.split("\n")[0][:100]

    # Store
    conn.execute(
        """INSERT INTO multi_perspective
           (id, event_id, region, scenario_title, actors, perspectives,
            divergence_score, miscalculation_risk, model_used)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            sim_id, event_id, region, scenario_title,
            json.dumps(actors), json.dumps(perspectives),
            divergence_score, miscalculation_risk, model_used,
        ),
    )
    conn.commit()

    return {
        "simulation_id": sim_id,
        "scenario": scenario_title,
        "actors": actors,
        "perspectives": perspectives,
        "divergence_score": divergence_score,
        "miscalculation_risk": miscalculation_risk,
        "model_used": model_used,
    }


def list_simulations(conn, limit: int = 20) -> list[dict]:
    """List multi-perspective simulations."""
    rows = conn.execute(
        "SELECT * FROM multi_perspective ORDER BY created_at DESC LIMIT ?",
        (limit,),
    ).fetchall()
    result = []
    for r in rows:
        d = dict(r)
        d["actors"] = json.loads(d["actors"]) if d["actors"] else []
        d["perspectives"] = json.loads(d["perspectives"]) if d["perspectives"] else []
        result.append(d)
    return result


def get_simulation(conn, sim_id: str) -> dict | None:
    """Get a single simulation by ID."""
    row = conn.execute(
        "SELECT * FROM multi_perspective WHERE id = ?", (sim_id,)
    ).fetchone()
    if not row:
        return None
    d = dict(row)
    d["actors"] = json.loads(d["actors"]) if d["actors"] else []
    d["perspectives"] = json.loads(d["perspectives"]) if d["perspectives"] else []
    return d
