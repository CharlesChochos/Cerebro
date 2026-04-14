"""
Cross-language narrative divergence — detect when different sources tell
different stories about the same events.

In OSINT, a key indicator of propaganda or information warfare is when domestic
media coverage of an event diverges significantly from international reporting.
This module groups events by topic, clusters them by source/narrative, and
computes a divergence score.

Without Claude: uses simple text overlap (Jaccard similarity) on event titles
and summaries to detect clustering.
With Claude: performs semantic narrative comparison for richer analysis.
"""
import json
import logging
import re
import uuid
from collections import defaultdict
from datetime import datetime, timezone, timedelta

import anthropic

from config.settings import CLAUDE_API_KEY

logger = logging.getLogger(__name__)

MODEL = "claude-sonnet-4-20250514"

DIVERGENCE_PROMPT = """You are an OSINT analyst specializing in cross-source narrative analysis.

TOPIC: {topic}
REGION: {region}

EVENTS FROM DIFFERENT SOURCES:
{events_text}

Analyze the narrative divergence across these sources. Look for:
1. Do all sources agree on basic facts?
2. Are there competing interpretations or framings?
3. Are any sources presenting a narrative that contradicts the majority?
4. Are there indicators of propaganda, spin, or information operations?

Respond with a JSON object:
{{
  "divergence_score": 0.0 to 1.0 (0 = full agreement, 1 = total contradiction),
  "dominant_narrative": "what most sources agree on (1-2 sentences)",
  "contrasting_narratives": [
    {{
      "source_group": "which sources share this narrative",
      "narrative": "what they claim (1-2 sentences)",
      "divergence_type": "framing|omission|contradiction|spin"
    }}
  ],
  "propaganda_indicators": ["indicator 1 if any"],
  "assessment": "1-2 sentence overall assessment"
}}

Respond ONLY with the JSON object.
"""


def tokenize(text: str) -> set[str]:
    """Simple word tokenization for Jaccard similarity."""
    if not text:
        return set()
    words = re.findall(r'\w+', text.lower())
    # Remove very common stopwords
    stopwords = {"the", "a", "an", "is", "are", "was", "were", "in", "on", "at",
                 "to", "for", "of", "and", "or", "but", "with", "by", "from", "as",
                 "that", "this", "it", "its", "has", "have", "had", "be", "been"}
    return set(words) - stopwords


def jaccard_similarity(a: set, b: set) -> float:
    """Jaccard similarity between two token sets."""
    if not a or not b:
        return 0.0
    intersection = len(a & b)
    union = len(a | b)
    return intersection / union if union > 0 else 0.0


def cluster_events_by_source(events: list[dict]) -> dict[str, list[dict]]:
    """Group events by their source."""
    clusters = defaultdict(list)
    for e in events:
        source = e.get("source", "unknown")
        clusters[source].append(e)
    return dict(clusters)


def compute_pairwise_divergence(clusters: dict[str, list[dict]]) -> float:
    """
    Compute narrative divergence across source clusters.

    Low divergence (near 0): sources agree (high Jaccard similarity).
    High divergence (near 1): sources disagree (low Jaccard similarity).
    """
    sources = list(clusters.keys())
    if len(sources) < 2:
        return 0.0

    # Build a combined text representation per source
    source_tokens = {}
    for source, events in clusters.items():
        combined = " ".join(
            f"{e.get('title', '')} {e.get('summary', '')}" for e in events
        )
        source_tokens[source] = tokenize(combined)

    # Compute average pairwise similarity
    similarities = []
    for i in range(len(sources)):
        for j in range(i + 1, len(sources)):
            sim = jaccard_similarity(source_tokens[sources[i]], source_tokens[sources[j]])
            similarities.append(sim)

    avg_similarity = sum(similarities) / len(similarities) if similarities else 1.0
    # Divergence = 1 - similarity
    return round(1.0 - avg_similarity, 3)


def extract_dominant_narrative(clusters: dict[str, list[dict]]) -> str:
    """Extract the dominant narrative from the largest source cluster."""
    if not clusters:
        return "No events to analyze."

    largest_source = max(clusters, key=lambda s: len(clusters[s]))
    events = clusters[largest_source]
    titles = [e.get("title", "") for e in events[:5]]
    return f"[{largest_source}] {'; '.join(titles)}"


def analyze_divergence(conn, topic: str,
                        region: str | None = None,
                        country_code: str | None = None,
                        days: int = 7) -> dict:
    """
    Analyze narrative divergence across sources for a given topic.

    Searches events matching the topic, clusters by source, and computes divergence.
    """
    cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()

    # Search events matching the topic
    conditions = ["timestamp >= ?"]
    params = [cutoff]

    if region:
        conditions.append("region = ?")
        params.append(region)
    if country_code:
        conditions.append("country_code = ?")
        params.append(country_code)

    where = " AND ".join(conditions)

    # Use FTS if available, fall back to LIKE
    try:
        events = conn.execute(
            f"""SELECT e.id, e.source, e.title, e.summary, e.category,
                       e.severity, e.country_code, e.timestamp
                FROM events e
                JOIN events_fts fts ON e.id = fts.rowid
                WHERE fts.events_fts MATCH ? AND {where}
                ORDER BY e.severity DESC LIMIT 50""",
            [topic] + params,
        ).fetchall()
    except Exception:
        # FTS might not match well, fall back to LIKE
        events = conn.execute(
            f"""SELECT id, source, title, summary, category, severity,
                       country_code, timestamp
                FROM events
                WHERE (title LIKE ? OR summary LIKE ?) AND {where}
                ORDER BY severity DESC LIMIT 50""",
            [f"%{topic}%", f"%{topic}%"] + params,
        ).fetchall()

    events = [dict(e) for e in events]

    if not events:
        return {
            "topic": topic,
            "region": region,
            "event_count": 0,
            "source_count": 0,
            "divergence_score": 0.0,
            "dominant_narrative": "No matching events found.",
            "contrasting_narratives": [],
            "propaganda_indicators": [],
            "model_used": None,
        }

    clusters = cluster_events_by_source(events)
    divergence_score = compute_pairwise_divergence(clusters)
    dominant = extract_dominant_narrative(clusters)
    event_ids = [e["id"] for e in events]

    contrasting = []
    propaganda_indicators = []
    model_used = None

    if CLAUDE_API_KEY and len(clusters) >= 2:
        try:
            client = anthropic.Anthropic(api_key=CLAUDE_API_KEY)
            events_text = "\n".join(
                f"  [{e['source']}] (sev={e['severity']}) {e['title']}: {e.get('summary', 'N/A')[:200]}"
                for e in events[:20]
            )
            prompt = DIVERGENCE_PROMPT.format(
                topic=topic,
                region=region or "Global",
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

            claude_result = json.loads(content)
            divergence_score = claude_result.get("divergence_score", divergence_score)
            dominant = claude_result.get("dominant_narrative", dominant)
            contrasting = claude_result.get("contrasting_narratives", [])
            propaganda_indicators = claude_result.get("propaganda_indicators", [])
            model_used = MODEL
        except (json.JSONDecodeError, anthropic.APIError) as e:
            logger.warning("Claude narrative divergence failed: %s", e)
    else:
        # Build simple contrasting narratives from non-dominant clusters
        largest_source = max(clusters, key=lambda s: len(clusters[s]))
        for source, evts in clusters.items():
            if source != largest_source and len(evts) >= 1:
                titles = "; ".join(e.get("title", "") for e in evts[:3])
                contrasting.append({
                    "source_group": source,
                    "narrative": titles,
                    "divergence_type": "framing",
                })

    return {
        "topic": topic,
        "region": region,
        "country_code": country_code,
        "event_count": len(events),
        "source_count": len(clusters),
        "sources": list(clusters.keys()),
        "divergence_score": divergence_score,
        "dominant_narrative": dominant,
        "contrasting_narratives": contrasting,
        "propaganda_indicators": propaganda_indicators,
        "event_ids": event_ids,
        "model_used": model_used,
    }


def store_divergence(conn, result: dict) -> str:
    """Store a narrative divergence analysis."""
    did = str(uuid.uuid4())
    conn.execute(
        """INSERT INTO narrative_divergence
           (id, topic, region, country_code, source_clusters, divergence_score,
            dominant_narrative, contrasting_narratives, event_ids,
            propaganda_indicators, model_used)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            did, result["topic"], result.get("region"), result.get("country_code"),
            json.dumps(result.get("sources", [])),
            result["divergence_score"],
            result["dominant_narrative"],
            json.dumps(result.get("contrasting_narratives", [])),
            json.dumps(result.get("event_ids", [])),
            json.dumps(result.get("propaganda_indicators", [])),
            result.get("model_used"),
        ),
    )
    conn.commit()
    return did


def run_divergence_analysis(conn, topic: str,
                             region: str | None = None,
                             country_code: str | None = None,
                             days: int = 7) -> dict:
    """Full pipeline: analyze + store."""
    result = analyze_divergence(conn, topic, region, country_code, days)
    if result["event_count"] > 0:
        did = store_divergence(conn, result)
        result["analysis_id"] = did
    return result


def list_divergence_analyses(conn, limit: int = 20) -> list[dict]:
    """List stored divergence analyses."""
    rows = conn.execute(
        "SELECT * FROM narrative_divergence ORDER BY analyzed_at DESC LIMIT ?",
        (limit,),
    ).fetchall()
    results = []
    for r in rows:
        d = dict(r)
        for field in ("source_clusters", "contrasting_narratives", "event_ids", "propaganda_indicators"):
            d[field] = json.loads(d[field]) if d[field] else []
        results.append(d)
    return results


def get_divergence_analysis(conn, analysis_id: str) -> dict | None:
    """Get a single divergence analysis."""
    row = conn.execute(
        "SELECT * FROM narrative_divergence WHERE id = ?", (analysis_id,)
    ).fetchone()
    if not row:
        return None
    d = dict(row)
    for field in ("source_clusters", "contrasting_narratives", "event_ids", "propaganda_indicators"):
        d[field] = json.loads(d[field]) if d[field] else []
    return d
