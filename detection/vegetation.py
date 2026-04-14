"""
Vegetation indices — NDVI monitoring for agricultural intelligence.

Vegetation stress is a leading indicator for food security crises, conflict
displacement, and economic shocks. This module processes NDVI (Normalized
Difference Vegetation Index) readings, classifies them, and detects anomalies
relative to historical baselines.

NDVI ranges:
  -1.0 to 0.0  → Water
  0.0 to 0.1   → Barren (rock, sand, snow)
  0.1 to 0.2   → Sparse vegetation / stressed
  0.2 to 0.5   → Normal / moderate vegetation
  0.5 to 1.0   → Dense / lush vegetation
"""
import json
import logging
import uuid
from datetime import datetime, timezone, timedelta

logger = logging.getLogger(__name__)


def classify_ndvi(ndvi: float) -> str:
    """Classify NDVI value into vegetation category."""
    if ndvi < 0:
        return "water"
    elif ndvi < 0.1:
        return "barren"
    elif ndvi < 0.2:
        return "stressed"
    elif ndvi < 0.5:
        return "normal"
    else:
        return "lush"


def compute_ndvi_change(current: float, baseline: float) -> float:
    """Compute percentage change from baseline."""
    if baseline == 0:
        return 0.0
    return round((current - baseline) / abs(baseline) * 100, 1)


def store_reading(conn, lat: float, lng: float, ndvi: float,
                   baseline_ndvi: float = 0.3,
                   capture_date: str | None = None,
                   country_code: str | None = None,
                   region: str | None = None,
                   source: str = "modis") -> str:
    """Store a vegetation reading."""
    rid = str(uuid.uuid4())
    classification = classify_ndvi(ndvi)
    change_pct = compute_ndvi_change(ndvi, baseline_ndvi)

    conn.execute(
        """INSERT INTO vegetation_readings
           (id, lat, lng, ndvi, baseline_ndvi, change_pct, classification,
            capture_date, country_code, region, source)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            rid, lat, lng, ndvi, baseline_ndvi, change_pct, classification,
            capture_date or datetime.now(timezone.utc).strftime("%Y-%m-%d"),
            country_code, region, source,
        ),
    )
    conn.commit()
    return rid


def get_readings(conn, country_code: str | None = None,
                  classification: str | None = None,
                  days: int = 30, limit: int = 100) -> list[dict]:
    """Get vegetation readings, optionally filtered."""
    cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).strftime("%Y-%m-%d")

    query = "SELECT * FROM vegetation_readings WHERE capture_date >= ?"
    params: list = [cutoff]

    if country_code:
        query += " AND country_code = ?"
        params.append(country_code)
    if classification:
        query += " AND classification = ?"
        params.append(classification)

    query += " ORDER BY capture_date DESC LIMIT ?"
    params.append(limit)

    rows = conn.execute(query, params).fetchall()
    return [dict(r) for r in rows]


def scan_vegetation_anomalies(conn, threshold_pct: float = -20.0,
                                days: int = 30) -> list[dict]:
    """
    Scan for significant vegetation anomalies (NDVI decline > threshold).

    Vegetation stress is a critical early warning for:
    - Drought → crop failure → food price spike → political instability
    - Deforestation → environmental monitoring
    - Conflict zones → scorched earth / agricultural destruction
    """
    cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).strftime("%Y-%m-%d")

    rows = conn.execute(
        """SELECT * FROM vegetation_readings
           WHERE capture_date >= ? AND change_pct <= ?
           ORDER BY change_pct ASC LIMIT 50""",
        (cutoff, threshold_pct),
    ).fetchall()

    anomalies = []
    for r in rows:
        d = dict(r)
        severity = min(100, abs(d["change_pct"]))
        d["severity"] = round(severity, 1)
        d["alert_level"] = (
            "critical" if d["change_pct"] <= -50 else
            "warning" if d["change_pct"] <= -30 else
            "watch"
        )
        anomalies.append(d)

    return anomalies


def get_vegetation_geojson(conn, country_code: str | None = None,
                            days: int = 30) -> dict:
    """Get vegetation readings as GeoJSON for map rendering."""
    readings = get_readings(conn, country_code, days=days)

    CLASSIFICATION_COLORS = {
        "lush": "#22c55e",
        "normal": "#86efac",
        "stressed": "#eab308",
        "barren": "#a16207",
        "water": "#3b82f6",
    }

    features = []
    for r in readings:
        features.append({
            "type": "Feature",
            "geometry": {
                "type": "Point",
                "coordinates": [r["lng"], r["lat"]],
            },
            "properties": {
                "id": r["id"],
                "ndvi": r["ndvi"],
                "baseline_ndvi": r["baseline_ndvi"],
                "change_pct": r["change_pct"],
                "classification": r["classification"],
                "color": CLASSIFICATION_COLORS.get(r["classification"], "#71717a"),
                "capture_date": r["capture_date"],
            },
        })

    return {"type": "FeatureCollection", "features": features}
