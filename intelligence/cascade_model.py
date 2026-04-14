"""
Second-order cascade modeling — predict how events propagate through causal chains.

Real-world crises rarely stay contained. A drought causes food price spikes, which
trigger protests, which provoke military responses, which cause refugee flows. This
module models those cascading second-order (and third-order) effects using known
causal patterns from historical data, optionally enhanced by Claude reasoning.

Each cascade is a directed graph of predicted steps with probability estimates.
"""
import json
import logging
import uuid
from datetime import datetime, timezone, timedelta

import anthropic

from config.settings import CLAUDE_API_KEY

logger = logging.getLogger(__name__)

MODEL = "claude-sonnet-4-20250514"

# Known causal chains: category A → category B with typical delay and probability
CASCADE_RULES = [
    {
        "trigger": "environmental",
        "effect": "economic",
        "label": "Supply chain disruption",
        "probability": 0.7,
        "delay_days": 14,
        "severity_modifier": 0.8,
        "description": "Environmental disasters disrupt supply chains and spike commodity prices.",
    },
    {
        "trigger": "economic",
        "effect": "political",
        "label": "Popular unrest",
        "probability": 0.6,
        "delay_days": 30,
        "severity_modifier": 0.9,
        "description": "Economic hardship fuels protests, strikes, and political instability.",
    },
    {
        "trigger": "political",
        "effect": "military",
        "label": "Security crackdown",
        "probability": 0.5,
        "delay_days": 7,
        "severity_modifier": 1.1,
        "description": "Political crises escalate to military deployment or armed conflict.",
    },
    {
        "trigger": "military",
        "effect": "political",
        "label": "Diplomatic crisis",
        "probability": 0.7,
        "delay_days": 3,
        "severity_modifier": 0.9,
        "description": "Military actions trigger diplomatic fallout and sanctions threats.",
    },
    {
        "trigger": "military",
        "effect": "economic",
        "label": "Economic sanctions/disruption",
        "probability": 0.6,
        "delay_days": 14,
        "severity_modifier": 0.7,
        "description": "Military conflict disrupts trade routes and triggers sanctions.",
    },
    {
        "trigger": "health",
        "effect": "economic",
        "label": "Economic impact of health crisis",
        "probability": 0.8,
        "delay_days": 21,
        "severity_modifier": 0.7,
        "description": "Pandemics and epidemics cause workforce reduction and economic contraction.",
    },
    {
        "trigger": "health",
        "effect": "political",
        "label": "Governance pressure",
        "probability": 0.5,
        "delay_days": 30,
        "severity_modifier": 0.6,
        "description": "Public health failures erode trust in government and fuel opposition.",
    },
    {
        "trigger": "economic",
        "effect": "health",
        "label": "Healthcare degradation",
        "probability": 0.4,
        "delay_days": 60,
        "severity_modifier": 0.6,
        "description": "Economic collapse degrades healthcare access and public health outcomes.",
    },
    {
        "trigger": "environmental",
        "effect": "health",
        "label": "Health emergency",
        "probability": 0.5,
        "delay_days": 7,
        "severity_modifier": 0.8,
        "description": "Environmental disasters cause injuries, disease outbreaks, and contamination.",
    },
    {
        "trigger": "political",
        "effect": "economic",
        "label": "Capital flight / market shock",
        "probability": 0.6,
        "delay_days": 7,
        "severity_modifier": 0.7,
        "description": "Political instability causes capital flight, currency depreciation, and market drops.",
    },
]

CASCADE_PROMPT = """You are a senior intelligence analyst modeling second-order effects.

TRIGGER EVENT:
{trigger_description}
Category: {trigger_category}
Severity: {trigger_severity}/100
Region: {region}

Using your knowledge of geopolitical cascading effects, model the most likely
cascade chain starting from this trigger event. Consider:
- Direct second-order effects (what happens next?)
- Third-order effects (what do those effects cause?)
- Regional specifics and current context
- Historical precedents for similar cascades

Respond with a JSON object:
{{
  "cascade_steps": [
    {{
      "step": 1,
      "category": "economic|political|military|health|environmental",
      "label": "short label for this step",
      "description": "what happens and why (1-2 sentences)",
      "probability": 0.0 to 1.0,
      "delay_days": estimated days from trigger,
      "severity": 0-100,
      "indicators": ["what to watch for that this step is materializing"]
    }}
  ],
  "max_severity": 0-100,
  "time_horizon_days": total days the cascade might unfold over,
  "assessment": "1-2 sentence overall cascade risk assessment"
}}

Respond ONLY with the JSON object. Include 3-6 cascade steps.
"""


def get_cascade_rules_for(category: str) -> list[dict]:
    """Get all cascade rules triggered by a given category."""
    return [r for r in CASCADE_RULES if r["trigger"] == category]


def build_cascade_chain(trigger_category: str, trigger_severity: float,
                         max_depth: int = 4) -> list[dict]:
    """
    Build a deterministic cascade chain from known rules.

    Walks the rule graph breadth-first, propagating severity through each link.
    Stops at max_depth or when no further cascades are found.
    """
    steps = []
    visited = set()
    frontier = [(trigger_category, trigger_severity, 0)]  # (category, severity, cumulative_delay)

    depth = 0
    while frontier and depth < max_depth:
        next_frontier = []
        for cat, sev, delay_so_far in frontier:
            rules = get_cascade_rules_for(cat)
            for rule in rules:
                # Avoid infinite loops (A→B→A→B...)
                edge = (rule["trigger"], rule["effect"])
                if edge in visited:
                    continue
                visited.add(edge)

                step_severity = sev * rule["severity_modifier"]
                step_delay = delay_so_far + rule["delay_days"]

                step = {
                    "step": len(steps) + 1,
                    "category": rule["effect"],
                    "label": rule["label"],
                    "description": rule["description"],
                    "probability": rule["probability"],
                    "delay_days": step_delay,
                    "severity": round(min(step_severity, 100), 1),
                    "source_category": cat,
                }
                steps.append(step)
                next_frontier.append((rule["effect"], step_severity, step_delay))

        frontier = next_frontier
        depth += 1

    return steps


def model_cascade(conn, event_id: str | None = None,
                   trigger_description: str | None = None,
                   region: str | None = None,
                   category: str | None = None) -> dict:
    """
    Model the second-order cascade from a trigger event or description.

    Uses rule-based modeling, optionally enhanced by Claude for richer analysis.
    """
    trigger_severity = 50.0
    trigger_category = category or "political"
    country_code = None

    if event_id:
        row = conn.execute("SELECT * FROM events WHERE id = ?", (event_id,)).fetchone()
        if row:
            trigger_description = trigger_description or row["title"]
            region = region or row["region"]
            trigger_category = row["category"] or trigger_category
            trigger_severity = row["severity"] or 50
            country_code = row["country_code"]

    if not trigger_description:
        return {"error": "Provide event_id or trigger_description"}

    cascade_steps = []
    model_used = None

    if CLAUDE_API_KEY:
        try:
            client = anthropic.Anthropic(api_key=CLAUDE_API_KEY)
            prompt = CASCADE_PROMPT.format(
                trigger_description=trigger_description,
                trigger_category=trigger_category,
                trigger_severity=trigger_severity,
                region=region or "Global",
            )
            message = client.messages.create(
                model=MODEL,
                max_tokens=1000,
                messages=[{"role": "user", "content": prompt}],
            )
            content = message.content[0].text.strip()
            if "```json" in content:
                content = content.split("```json")[1].split("```")[0].strip()
            elif "```" in content:
                content = content.split("```")[1].split("```")[0].strip()

            claude_result = json.loads(content)
            cascade_steps = claude_result.get("cascade_steps", [])
            model_used = MODEL
        except (json.JSONDecodeError, anthropic.APIError) as e:
            logger.warning("Claude cascade modeling failed, using rules: %s", e)

    # Fall back to rule-based cascade
    if not cascade_steps:
        cascade_steps = build_cascade_chain(trigger_category, trigger_severity)

    max_severity = max((s.get("severity", 0) for s in cascade_steps), default=0)
    time_horizon = max((s.get("delay_days", 0) for s in cascade_steps), default=30)

    # Compute chain probability (product of step probabilities)
    prob_chain = 1.0
    for s in cascade_steps:
        prob_chain *= s.get("probability", 0.5)

    return {
        "trigger_event_id": event_id,
        "trigger_description": trigger_description,
        "region": region,
        "country_code": country_code,
        "trigger_category": trigger_category,
        "trigger_severity": trigger_severity,
        "cascade_steps": cascade_steps,
        "total_steps": len(cascade_steps),
        "max_severity": round(max_severity, 1),
        "probability_chain": round(prob_chain, 4),
        "time_horizon_days": time_horizon,
        "model_used": model_used,
    }


def store_cascade(conn, cascade: dict) -> str:
    """Store a cascade model in the database."""
    cid = str(uuid.uuid4())
    conn.execute(
        """INSERT INTO cascade_models
           (id, trigger_event_id, trigger_description, region, country_code,
            cascade_steps, total_steps, max_severity, probability_chain,
            time_horizon_days, model_used)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            cid, cascade.get("trigger_event_id"),
            cascade["trigger_description"], cascade.get("region"),
            cascade.get("country_code"),
            json.dumps(cascade["cascade_steps"]),
            cascade["total_steps"], cascade["max_severity"],
            cascade["probability_chain"], cascade["time_horizon_days"],
            cascade.get("model_used"),
        ),
    )
    conn.commit()
    return cid


def run_cascade_model(conn, event_id: str | None = None,
                       trigger_description: str | None = None,
                       region: str | None = None,
                       category: str | None = None) -> dict:
    """Full cascade pipeline: model + store."""
    cascade = model_cascade(conn, event_id, trigger_description, region, category)
    if "error" in cascade:
        return cascade

    cid = store_cascade(conn, cascade)
    cascade["cascade_id"] = cid
    return cascade


def list_cascades(conn, status: str | None = None, limit: int = 20) -> list[dict]:
    """List stored cascade models."""
    query = "SELECT * FROM cascade_models"
    params = []
    if status:
        query += " WHERE status = ?"
        params.append(status)
    query += " ORDER BY created_at DESC LIMIT ?"
    params.append(limit)

    rows = conn.execute(query, params).fetchall()
    results = []
    for r in rows:
        d = dict(r)
        d["cascade_steps"] = json.loads(d["cascade_steps"]) if d["cascade_steps"] else []
        results.append(d)
    return results


def get_cascade(conn, cascade_id: str) -> dict | None:
    """Get a single cascade model."""
    row = conn.execute(
        "SELECT * FROM cascade_models WHERE id = ?", (cascade_id,)
    ).fetchone()
    if not row:
        return None
    d = dict(row)
    d["cascade_steps"] = json.loads(d["cascade_steps"]) if d["cascade_steps"] else []
    return d
