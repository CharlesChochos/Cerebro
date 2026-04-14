"""
Analysis of Competing Hypotheses (ACH) — structured analytic technique.

Based on Richards Heuer's methodology from the CIA:
1. Generate hypotheses for an intelligence question
2. Collect evidence from all sources
3. Build C/I/N matrix (Consistent, Inconsistent, Neutral)
4. The hypothesis with fewest Inconsistent ratings wins

Claude fills the matrix automatically; analysts can override.
"""
import json
import logging
import uuid

import anthropic

from config.settings import CLAUDE_API_KEY

logger = logging.getLogger(__name__)

MODEL = "claude-sonnet-4-20250514"

ACH_PROMPT = """You are a senior intelligence analyst performing an Analysis of Competing Hypotheses (ACH).

QUESTION: {question}

HYPOTHESES:
{hypotheses_text}

EVIDENCE:
{evidence_text}

For each piece of evidence, rate its consistency with each hypothesis:
- "C" = Consistent (evidence supports this hypothesis)
- "I" = Inconsistent (evidence contradicts this hypothesis)
- "N" = Neutral (evidence neither supports nor contradicts)
- "NA" = Not Applicable

Return a JSON object with:
1. "matrix": A 2D array where matrix[evidence_index][hypothesis_index] = "C"/"I"/"N"/"NA"
2. "conclusion": 1-2 paragraphs analyzing which hypothesis is best supported (fewest I ratings)
3. "confidence": 0.0-1.0 confidence in the conclusion

CRITICAL: Be rigorous. Focus on INCONSISTENT evidence — the hypothesis with fewest "I" ratings is most likely correct. Do not let confirmation bias affect ratings.

Respond ONLY with the JSON object.
"""

HYPOTHESIS_GEN_PROMPT = """You are a senior intelligence analyst. Given the following intelligence question and context, generate 3-5 competing hypotheses that could explain the situation.

QUESTION: {question}

CONTEXT:
{context}

Return a JSON object with:
1. "hypotheses": Array of hypothesis strings (each 1-2 sentences)
2. "evidence": Array of evidence items extracted from the context (each 1-2 sentences, with source attribution)

Respond ONLY with the JSON object.
"""


def create_ach_framework(
    conn,
    title: str,
    question: str,
    hypotheses: list[str],
    evidence: list[str],
    workspace_id: str | None = None,
) -> dict:
    """
    Create an ACH framework and optionally auto-fill the matrix with Claude.
    """
    framework_id = str(uuid.uuid4())

    # Initialize empty matrix
    matrix = [["N"] * len(hypotheses) for _ in range(len(evidence))]

    # Try to fill with Claude
    model_used = None
    conclusion = None

    if CLAUDE_API_KEY and hypotheses and evidence:
        try:
            filled = fill_ach_matrix(question, hypotheses, evidence)
            if filled and "matrix" in filled:
                matrix = filled["matrix"]
                conclusion = filled.get("conclusion")
                model_used = MODEL
        except Exception as e:
            logger.error("ACH matrix fill error: %s", e)

    conn.execute(
        """INSERT INTO ach_frameworks
           (id, workspace_id, title, description, hypotheses, evidence,
            matrix, conclusion, model_used)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            framework_id, workspace_id, title, question,
            json.dumps(hypotheses), json.dumps(evidence),
            json.dumps(matrix), conclusion, model_used,
        ),
    )
    conn.commit()

    return {
        "framework_id": framework_id,
        "title": title,
        "hypotheses": hypotheses,
        "evidence": evidence,
        "matrix": matrix,
        "conclusion": conclusion,
        "model_used": model_used,
    }


def fill_ach_matrix(
    question: str,
    hypotheses: list[str],
    evidence: list[str],
) -> dict | None:
    """
    Use Claude to fill the ACH matrix with C/I/N ratings.
    """
    if not CLAUDE_API_KEY:
        return None

    hypotheses_text = "\n".join(f"  H{i+1}: {h}" for i, h in enumerate(hypotheses))
    evidence_text = "\n".join(f"  E{i+1}: {e}" for i, e in enumerate(evidence))

    prompt = ACH_PROMPT.format(
        question=question,
        hypotheses_text=hypotheses_text,
        evidence_text=evidence_text,
    )

    client = anthropic.Anthropic(api_key=CLAUDE_API_KEY)

    try:
        message = client.messages.create(
            model=MODEL,
            max_tokens=2000,
            messages=[{"role": "user", "content": prompt}],
        )
        content = message.content[0].text.strip()

        if "```json" in content:
            content = content.split("```json")[1].split("```")[0].strip()
        elif "```" in content:
            content = content.split("```")[1].split("```")[0].strip()

        result = json.loads(content)

        # Validate matrix dimensions
        matrix = result.get("matrix", [])
        if len(matrix) != len(evidence):
            logger.warning("Matrix row count mismatch: %d vs %d evidence", len(matrix), len(evidence))
            return None
        for row in matrix:
            if len(row) != len(hypotheses):
                logger.warning("Matrix column count mismatch")
                return None

        # Validate cell values
        valid_values = {"C", "I", "N", "NA"}
        for i, row in enumerate(matrix):
            for j, cell in enumerate(row):
                if cell not in valid_values:
                    matrix[i][j] = "N"

        return {
            "matrix": matrix,
            "conclusion": result.get("conclusion"),
            "confidence": result.get("confidence", 0.5),
        }

    except (json.JSONDecodeError, anthropic.APIError) as e:
        logger.error("ACH fill error: %s", e)
        return None


def generate_hypotheses_from_context(conn, question: str, event_ids: list[str] = None) -> dict:
    """
    Auto-generate hypotheses and evidence from a question and context.
    """
    if not CLAUDE_API_KEY:
        return {"error": "no_api_key"}

    # Build context from events
    context_lines = []
    if event_ids:
        placeholders = ",".join(["?"] * len(event_ids))
        rows = conn.execute(
            f"""SELECT source, title, summary, category, severity, country_code, timestamp
                FROM events WHERE id IN ({placeholders})
                ORDER BY timestamp DESC""",
            event_ids,
        ).fetchall()
        for r in rows:
            e = dict(r)
            context_lines.append(
                f"[{e['source']}] {e['timestamp'][:10]} | {e['title']} (sev={e['severity']})"
            )
            if e.get("summary"):
                context_lines.append(f"  {e['summary'][:200]}")
    else:
        # Use recent high-severity events as context
        rows = conn.execute(
            """SELECT source, title, summary, category, severity, country_code, timestamp
               FROM events WHERE severity >= 50
               ORDER BY timestamp DESC LIMIT 20"""
        ).fetchall()
        for r in rows:
            e = dict(r)
            context_lines.append(
                f"[{e['source']}] {e['timestamp'][:10]} | {e['title']} (sev={e['severity']})"
            )

    context = "\n".join(context_lines) if context_lines else "No context available."

    prompt = HYPOTHESIS_GEN_PROMPT.format(question=question, context=context)
    client = anthropic.Anthropic(api_key=CLAUDE_API_KEY)

    try:
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

        return json.loads(content)

    except (json.JSONDecodeError, anthropic.APIError) as e:
        logger.error("Hypothesis generation error: %s", e)
        return {"error": str(e)}


def update_ach_cell(conn, framework_id: str, evidence_idx: int, hypothesis_idx: int, value: str) -> dict:
    """
    Update a single cell in the ACH matrix (analyst override).
    """
    if value not in ("C", "I", "N", "NA"):
        return {"error": f"Invalid value: {value}. Must be C, I, N, or NA."}

    row = conn.execute(
        "SELECT matrix FROM ach_frameworks WHERE id = ?", (framework_id,)
    ).fetchone()
    if not row:
        return {"error": "framework_not_found"}

    matrix = json.loads(row["matrix"])

    if evidence_idx < 0 or evidence_idx >= len(matrix):
        return {"error": "evidence_idx out of range"}
    if hypothesis_idx < 0 or hypothesis_idx >= len(matrix[0]):
        return {"error": "hypothesis_idx out of range"}

    matrix[evidence_idx][hypothesis_idx] = value

    conn.execute(
        """UPDATE ach_frameworks SET matrix = ?, updated_at = strftime('%Y-%m-%dT%H:%M:%SZ', 'now')
           WHERE id = ?""",
        (json.dumps(matrix), framework_id),
    )
    conn.commit()

    return {"updated": True, "matrix": matrix}


def score_ach_matrix(matrix: list[list[str]], hypotheses: list[str]) -> list[dict]:
    """
    Score hypotheses based on ACH methodology.
    The hypothesis with the fewest Inconsistent ratings is most likely.
    """
    scores = []
    for h_idx, hypothesis in enumerate(hypotheses):
        consistent = sum(1 for row in matrix if row[h_idx] == "C")
        inconsistent = sum(1 for row in matrix if row[h_idx] == "I")
        neutral = sum(1 for row in matrix if row[h_idx] == "N")

        # Lower inconsistency score = better hypothesis
        total_rated = consistent + inconsistent + neutral
        inconsistency_ratio = inconsistent / total_rated if total_rated > 0 else 0

        scores.append({
            "hypothesis": hypothesis,
            "index": h_idx,
            "consistent": consistent,
            "inconsistent": inconsistent,
            "neutral": neutral,
            "inconsistency_ratio": round(inconsistency_ratio, 3),
        })

    # Sort by fewest inconsistent ratings (best hypothesis first)
    scores.sort(key=lambda x: x["inconsistency_ratio"])
    return scores
