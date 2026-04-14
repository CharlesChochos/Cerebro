"""
Country extrusions — stores per-country metric values used for 3D
extrusion visualization on the globe (height-mapped country polygons,
bar charts, heatmap volumes).
"""
import uuid
from datetime import datetime, timezone

# Seed: sample metrics for notable countries
SEED_EXTRUSIONS = [
    ("US", "event_count", 1250, 0.85, "current"),
    ("US", "risk_score", 45, 0.45, "current"),
    ("CN", "event_count", 980, 0.67, "current"),
    ("CN", "risk_score", 62, 0.62, "current"),
    ("RU", "event_count", 870, 0.59, "current"),
    ("RU", "risk_score", 78, 0.78, "current"),
    ("UA", "event_count", 1450, 0.99, "current"),
    ("UA", "risk_score", 92, 0.92, "current"),
    ("IR", "event_count", 520, 0.35, "current"),
    ("IR", "risk_score", 85, 0.85, "current"),
    ("SY", "event_count", 680, 0.46, "current"),
    ("SY", "risk_score", 88, 0.88, "current"),
    ("KP", "event_count", 190, 0.13, "current"),
    ("KP", "risk_score", 95, 0.95, "current"),
    ("IL", "event_count", 890, 0.61, "current"),
    ("IL", "risk_score", 72, 0.72, "current"),
    ("GB", "event_count", 320, 0.22, "current"),
    ("GB", "risk_score", 25, 0.25, "current"),
    ("DE", "event_count", 280, 0.19, "current"),
    ("DE", "risk_score", 20, 0.20, "current"),
]


def seed_extrusions(conn) -> int:
    count = 0
    for cc, metric, value, norm, period in SEED_EXTRUSIONS:
        eid = str(uuid.uuid4())
        try:
            conn.execute(
                """INSERT OR IGNORE INTO country_extrusions
                   (id, country_code, metric_name, metric_value, normalized, period)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (eid, cc, metric, value, norm, period),
            )
            count += 1
        except Exception:
            pass
    conn.commit()
    return count


def upsert_metric(conn, country_code: str, metric_name: str,
                  metric_value: float, normalized: float | None = None,
                  period: str = "current") -> str:
    """Insert or update a country metric. Returns the record ID."""
    valid_metrics = {"event_count", "risk_score", "gdp", "population",
                     "threat_level", "military_spending", "cyber_incidents"}

    if metric_name not in valid_metrics:
        raise ValueError(f"Invalid metric_name: {metric_name}")

    # Check if exists
    existing = conn.execute(
        """SELECT id FROM country_extrusions
           WHERE country_code = ? AND metric_name = ? AND period = ?""",
        (country_code, metric_name, period),
    ).fetchone()

    if existing:
        conn.execute(
            """UPDATE country_extrusions
               SET metric_value = ?, normalized = ?, updated_at = datetime('now')
               WHERE id = ?""",
            (metric_value, normalized, existing["id"]),
        )
        conn.commit()
        return existing["id"]

    eid = str(uuid.uuid4())
    conn.execute(
        """INSERT INTO country_extrusions
           (id, country_code, metric_name, metric_value, normalized, period)
           VALUES (?, ?, ?, ?, ?, ?)""",
        (eid, country_code, metric_name, metric_value, normalized, period),
    )
    conn.commit()
    return eid


def get_metric(conn, country_code: str, metric_name: str,
               period: str = "current") -> dict | None:
    row = conn.execute(
        """SELECT * FROM country_extrusions
           WHERE country_code = ? AND metric_name = ? AND period = ?""",
        (country_code, metric_name, period),
    ).fetchone()
    return dict(row) if row else None


def list_metrics(conn, metric_name: str | None = None,
                 country_code: str | None = None,
                 period: str = "current",
                 limit: int = 200) -> list[dict]:
    conditions, params = ["period = ?"], [period]
    if metric_name:
        conditions.append("metric_name = ?"); params.append(metric_name)
    if country_code:
        conditions.append("country_code = ?"); params.append(country_code)

    where = " WHERE " + " AND ".join(conditions)
    rows = conn.execute(
        f"SELECT * FROM country_extrusions{where} ORDER BY metric_value DESC LIMIT ?",
        params + [limit]).fetchall()
    return [dict(r) for r in rows]


def get_extrusion_data(conn, metric_name: str,
                       period: str = "current") -> list[dict]:
    """Get extrusion-ready data: country_code → normalized height."""
    rows = conn.execute(
        """SELECT country_code, metric_value, normalized
           FROM country_extrusions
           WHERE metric_name = ? AND period = ?
           ORDER BY metric_value DESC""",
        (metric_name, period),
    ).fetchall()
    return [dict(r) for r in rows]


def get_rankings(conn, metric_name: str, period: str = "current",
                 top_n: int = 20) -> list[dict]:
    """Get top-N countries ranked by a metric."""
    rows = conn.execute(
        """SELECT country_code, metric_value, normalized
           FROM country_extrusions
           WHERE metric_name = ? AND period = ?
           ORDER BY metric_value DESC
           LIMIT ?""",
        (metric_name, period, top_n),
    ).fetchall()

    ranked = []
    for i, r in enumerate(rows, 1):
        d = dict(r)
        d["rank"] = i
        ranked.append(d)
    return ranked


def compute_normalized(conn, metric_name: str,
                       period: str = "current") -> int:
    """Recompute normalized values (0-1) for all entries of a metric."""
    rows = conn.execute(
        """SELECT id, metric_value FROM country_extrusions
           WHERE metric_name = ? AND period = ?""",
        (metric_name, period),
    ).fetchall()

    if not rows:
        return 0

    max_val = max(r["metric_value"] for r in rows)
    if max_val == 0:
        return 0

    for r in rows:
        norm = r["metric_value"] / max_val
        conn.execute(
            "UPDATE country_extrusions SET normalized = ? WHERE id = ?",
            (round(norm, 4), r["id"]),
        )

    conn.commit()
    return len(rows)
