"""
Hallucination firewall — ensures every factual claim maps to source evidence.

Two modes:
1. audit_text() — analyzes existing text, extracts claims, verifies each against DB
2. sanitize_text() — strips or flags ungrounded claims from text

Every brief, fusion signal, and dossier should pass through the firewall.
A grounding_score (0–1) indicates what fraction of claims are evidence-backed.
"""
import json
import logging
import re
import uuid
from datetime import datetime, timezone

import anthropic

from config.settings import CLAUDE_API_KEY

logger = logging.getLogger(__name__)

MODEL = "claude-sonnet-4-20250514"

CLAIM_EXTRACTION_PROMPT = """You are a fact-checking analyst. Extract every factual claim from the text below.

For each claim, identify:
1. The specific factual assertion
2. Any event IDs, entity IDs, or source references mentioned (e.g., [evt-123], (GDELT), etc.)
3. Whether the claim is: "factual" (verifiable statement), "analytical" (judgment/interpretation), or "predictive" (future-facing)

TEXT TO ANALYZE:
{text}

KNOWN VALID EVENT IDs:
{valid_ids}

Respond with a JSON object:
{{
  "claims": [
    {{
      "claim": "the specific assertion",
      "type": "factual|analytical|predictive",
      "referenced_ids": ["id1", "id2"],
      "grounded": true/false,
      "reason": "why grounded or not — reference exists in valid IDs or not"
    }}
  ],
  "total_claims": N,
  "grounded_claims": N,
  "ungrounded_claims": N,
  "grounding_score": 0.0-1.0
}}

Mark a claim as grounded if:
- It references a valid event/entity ID from the known list
- It's an analytical judgment clearly derived from referenced events
- It's a prediction explicitly framed as uncertain

Mark a claim as ungrounded if:
- It references IDs not in the valid list
- It states facts not traceable to any referenced source
- It presents speculation as established fact
"""

SANITIZE_PROMPT = """You are a fact-checking editor. Your job is to sanitize this intelligence text
by flagging or removing ungrounded claims.

ORIGINAL TEXT:
{text}

UNGROUNDED CLAIMS IDENTIFIED:
{flagged_claims}

Rules:
1. For each ungrounded factual claim, either:
   a. Add "[UNVERIFIED]" before the claim if it's plausible but not sourced
   b. Remove the claim entirely if it's fabricated or contradicts known data
2. Keep all grounded claims exactly as written
3. Keep analytical judgments that are clearly framed as interpretation
4. Keep predictions that are clearly framed as uncertain

Return the sanitized text. Preserve formatting (markdown, headers, etc.).
"""


def extract_referenced_ids(text: str) -> set[str]:
    """Extract event/entity IDs referenced in text using common patterns."""
    # Match patterns like [evt-123], (evt-123), evt-123
    patterns = [
        r'\[([a-zA-Z0-9_-]+)\]',  # [id]
        r'\(([a-zA-Z0-9_-]{8,})\)',  # (uuid-like)
    ]
    ids = set()
    for pattern in patterns:
        ids.update(re.findall(pattern, text))
    return ids


def get_valid_event_ids(conn, ids_to_check: set[str] | None = None) -> set[str]:
    """Get set of valid event IDs from the database."""
    if ids_to_check:
        placeholders = ",".join("?" * len(ids_to_check))
        rows = conn.execute(
            f"SELECT id FROM events WHERE id IN ({placeholders})",
            list(ids_to_check),
        ).fetchall()
        return {r["id"] for r in rows}
    else:
        # Get recent event IDs for context
        rows = conn.execute(
            "SELECT id FROM events ORDER BY timestamp DESC LIMIT 200"
        ).fetchall()
        return {r["id"] for r in rows}


def compute_grounding_score_simple(text: str, valid_ids: set[str]) -> dict:
    """
    Fast grounding check without Claude — count how many referenced IDs are valid.
    This is the minimum viable firewall that runs on every output.
    """
    referenced = extract_referenced_ids(text)

    if not referenced:
        # No IDs referenced at all — can't verify
        return {
            "total_references": 0,
            "valid_references": 0,
            "invalid_references": 0,
            "grounding_score": 0.0,
            "invalid_ids": [],
            "method": "simple",
        }

    valid = referenced & valid_ids
    invalid = referenced - valid_ids

    score = len(valid) / len(referenced) if referenced else 0.0

    return {
        "total_references": len(referenced),
        "valid_references": len(valid),
        "invalid_references": len(invalid),
        "grounding_score": round(score, 2),
        "invalid_ids": list(invalid),
        "method": "simple",
    }


def audit_text(conn, text: str, target_type: str = "unknown", target_id: str = "") -> dict:
    """
    Full grounding audit using Claude for claim extraction + DB verification.

    Returns audit results with per-claim grounding status and overall score.
    """
    # Get valid IDs from DB
    referenced = extract_referenced_ids(text)
    valid_ids = get_valid_event_ids(conn, referenced if referenced else None)

    # Simple check first
    simple = compute_grounding_score_simple(text, valid_ids)

    audit_id = str(uuid.uuid4())
    model_used = None

    if CLAUDE_API_KEY and len(text.strip()) > 50:
        try:
            client = anthropic.Anthropic(api_key=CLAUDE_API_KEY)
            prompt = CLAIM_EXTRACTION_PROMPT.format(
                text=text[:3000],  # cap to avoid token overflow
                valid_ids=", ".join(list(valid_ids)[:50]),
            )

            message = client.messages.create(
                model=MODEL,
                max_tokens=1500,
                messages=[{"role": "user", "content": prompt}],
            )
            content = message.content[0].text.strip()
            if "```json" in content:
                content = content.split("```json")[1].split("```")[0].strip()
            elif "```" in content:
                content = content.split("```")[1].split("```")[0].strip()

            result = json.loads(content)
            model_used = MODEL

            total = result.get("total_claims", 0)
            grounded = result.get("grounded_claims", 0)
            ungrounded = result.get("ungrounded_claims", 0)
            score = result.get("grounding_score", simple["grounding_score"])

            flagged = [
                c for c in result.get("claims", [])
                if not c.get("grounded", True)
            ]

        except (json.JSONDecodeError, anthropic.APIError) as e:
            logger.error("Grounding audit Claude error: %s", e)
            # Fall back to simple check
            total = simple["total_references"]
            grounded = simple["valid_references"]
            ungrounded = simple["invalid_references"]
            score = simple["grounding_score"]
            flagged = [{"claim": f"Referenced invalid ID: {iid}", "reason": "ID not found in database"} for iid in simple["invalid_ids"]]
    else:
        # No API key — use simple check
        total = simple["total_references"]
        grounded = simple["valid_references"]
        ungrounded = simple["invalid_references"]
        score = simple["grounding_score"]
        flagged = [{"claim": f"Referenced invalid ID: {iid}", "reason": "ID not found in database"} for iid in simple["invalid_ids"]]

    # Store audit
    conn.execute(
        """INSERT INTO grounding_audits
           (id, target_type, target_id, total_claims, grounded_claims,
            ungrounded_claims, grounding_score, flagged_claims, model_used)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            audit_id, target_type, target_id,
            total, grounded, ungrounded, score,
            json.dumps(flagged), model_used,
        ),
    )
    conn.commit()

    return {
        "audit_id": audit_id,
        "target_type": target_type,
        "target_id": target_id,
        "total_claims": total,
        "grounded_claims": grounded,
        "ungrounded_claims": ungrounded,
        "grounding_score": score,
        "flagged_claims": flagged,
        "model_used": model_used,
    }


def sanitize_text(conn, text: str) -> dict:
    """
    Run hallucination firewall and return sanitized text with ungrounded claims flagged.

    Without Claude: flags invalid ID references with [UNVERIFIED].
    With Claude: full claim-level analysis and surgical editing.
    """
    referenced = extract_referenced_ids(text)
    valid_ids = get_valid_event_ids(conn, referenced if referenced else None)
    invalid_ids = referenced - valid_ids

    sanitized = text
    model_used = None
    flagged = []

    if CLAUDE_API_KEY and invalid_ids:
        try:
            # First do the audit to identify ungrounded claims
            audit = audit_text(conn, text)
            flagged = audit.get("flagged_claims", [])

            if flagged:
                client = anthropic.Anthropic(api_key=CLAUDE_API_KEY)
                prompt = SANITIZE_PROMPT.format(
                    text=text[:3000],
                    flagged_claims=json.dumps(flagged, indent=2),
                )
                message = client.messages.create(
                    model=MODEL,
                    max_tokens=2000,
                    messages=[{"role": "user", "content": prompt}],
                )
                sanitized = message.content[0].text.strip()
                model_used = MODEL

        except anthropic.APIError as e:
            logger.error("Sanitize API error: %s", e)
            # Fall through to simple replacement

    if not model_used:
        # Simple mode: flag invalid references
        for iid in invalid_ids:
            sanitized = sanitized.replace(f"[{iid}]", f"[UNVERIFIED: {iid}]")
            flagged.append({"claim": f"Reference to {iid}", "reason": "ID not found in database"})

    score = compute_grounding_score_simple(text, valid_ids)["grounding_score"]

    return {
        "original_length": len(text),
        "sanitized_length": len(sanitized),
        "sanitized_text": sanitized,
        "grounding_score": score,
        "flagged_count": len(flagged),
        "flagged_claims": flagged,
        "model_used": model_used,
    }


def audit_brief(conn, brief_id: str) -> dict:
    """Audit a specific brief for grounding."""
    row = conn.execute("SELECT * FROM briefs WHERE id = ?", (brief_id,)).fetchone()
    if not row:
        return {"error": "brief_not_found"}

    result = audit_text(conn, row["content"] or "", "brief", brief_id)

    # Update the brief's grounding_score
    conn.execute(
        "UPDATE briefs SET grounding_score = ? WHERE id = ?",
        (result["grounding_score"], brief_id),
    )
    conn.commit()

    return result


def audit_fusion_signal(conn, signal_id: str) -> dict:
    """Audit a specific fusion signal for grounding."""
    row = conn.execute("SELECT * FROM fusion_signals WHERE id = ?", (signal_id,)).fetchone()
    if not row:
        return {"error": "signal_not_found"}

    text = f"{row['title']}\n{row['description']}"
    result = audit_text(conn, text, "fusion_signal", signal_id)

    conn.execute(
        "UPDATE fusion_signals SET grounding_score = ? WHERE id = ?",
        (result["grounding_score"], signal_id),
    )
    conn.commit()

    return result


def get_audit(conn, audit_id: str) -> dict | None:
    """Get a grounding audit by ID."""
    row = conn.execute("SELECT * FROM grounding_audits WHERE id = ?", (audit_id,)).fetchone()
    if not row:
        return None
    d = dict(row)
    d["flagged_claims"] = json.loads(d["flagged_claims"]) if d["flagged_claims"] else []
    return d


def list_audits(conn, target_type: str | None = None, limit: int = 20) -> list[dict]:
    """List grounding audits."""
    query = "SELECT * FROM grounding_audits"
    params = []
    if target_type:
        query += " WHERE target_type = ?"
        params.append(target_type)
    query += " ORDER BY created_at DESC LIMIT ?"
    params.append(limit)

    rows = conn.execute(query, params).fetchall()
    result = []
    for r in rows:
        d = dict(r)
        d["flagged_claims"] = json.loads(d["flagged_claims"]) if d["flagged_claims"] else []
        result.append(d)
    return result
