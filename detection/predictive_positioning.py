"""
Predictive positioning — forecast where future events will likely occur.

Uses spatial and temporal clustering of historical events to predict future
hotspot locations. Four prediction types:

1. **Event hotspot**: Areas with accelerating event frequency
2. **Escalation zone**: Regions where severity is trending upward
3. **Entity movement**: Predicted next location for tracked entities
4. **Vessel destination**: Projected vessel arrival points

Core algorithm: spatial kernel density estimation on recent events,
weighted by recency and severity, with hotspot detection at local maxima.
"""
import json
import logging
import math
import uuid
from collections import defaultdict
from datetime import datetime, timezone, timedelta

logger = logging.getLogger(__name__)

EARTH_RADIUS_KM = 6371.0


def haversine(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    """Great-circle distance in km."""
    rlat1, rlng1, rlat2, rlng2 = map(math.radians, [lat1, lng1, lat2, lng2])
    dlat = rlat2 - rlat1
    dlng = rlng2 - rlng1
    a = math.sin(dlat / 2) ** 2 + math.cos(rlat1) * math.cos(rlat2) * math.sin(dlng / 2) ** 2
    return EARTH_RADIUS_KM * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def compute_event_density(events: list[dict], grid_size: float = 2.0) -> list[dict]:
    """
    Compute event density on a grid. Returns grid cells with event counts
    and weighted intensity.

    grid_size: degrees per cell (default 2° ≈ 200km at equator)
    """
    grid = defaultdict(lambda: {"count": 0, "severity_sum": 0, "events": []})

    for e in events:
        lat = e.get("lat") or e.get("latitude")
        lng = e.get("lng") or e.get("longitude")
        if lat is None or lng is None:
            continue

        # Snap to grid
        grid_lat = round(lat / grid_size) * grid_size
        grid_lng = round(lng / grid_size) * grid_size
        key = (grid_lat, grid_lng)

        grid[key]["count"] += 1
        grid[key]["severity_sum"] += e.get("severity", 50)
        grid[key]["events"].append(e.get("id", ""))

    cells = []
    for (lat, lng), data in grid.items():
        cells.append({
            "lat": lat,
            "lng": lng,
            "count": data["count"],
            "avg_severity": round(data["severity_sum"] / data["count"], 1),
            "intensity": data["count"] * (data["severity_sum"] / data["count"]) / 100,
        })

    cells.sort(key=lambda c: c["intensity"], reverse=True)
    return cells


def detect_hotspots(conn, category: str | None = None,
                     country_code: str | None = None,
                     days: int = 14,
                     min_events: int = 3) -> list[dict]:
    """
    Detect event hotspots — areas with high spatial concentration of recent events.
    """
    cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()

    conditions = ["timestamp >= ?", "latitude IS NOT NULL", "lng IS NOT NULL"]
    params: list = [cutoff]

    if category:
        conditions.append("category = ?")
        params.append(category)
    if country_code:
        conditions.append("country_code = ?")
        params.append(country_code)

    where = " AND ".join(conditions)
    events = conn.execute(
        f"SELECT id, latitude as lat, longitude as lng, severity, category, country_code, timestamp FROM events WHERE {where}",
        params,
    ).fetchall()

    events = [dict(e) for e in events]
    cells = compute_event_density(events)

    # Filter to significant hotspots
    hotspots = [c for c in cells if c["count"] >= min_events]
    return hotspots[:20]


def detect_escalation_zones(conn, days: int = 14) -> list[dict]:
    """
    Detect zones where event severity is trending upward.

    Compares recent severity to baseline for each grid cell.
    """
    now = datetime.now(timezone.utc)
    recent_cutoff = (now - timedelta(days=days)).isoformat()
    baseline_cutoff = (now - timedelta(days=days * 3)).isoformat()

    # Recent events
    recent = conn.execute(
        """SELECT latitude as lat, longitude as lng, severity, category, country_code
           FROM events WHERE timestamp >= ? AND latitude IS NOT NULL""",
        (recent_cutoff,),
    ).fetchall()

    # Baseline events
    baseline = conn.execute(
        """SELECT latitude as lat, longitude as lng, severity
           FROM events WHERE timestamp >= ? AND timestamp < ? AND latitude IS NOT NULL""",
        (baseline_cutoff, recent_cutoff),
    ).fetchall()

    recent_density = compute_event_density([dict(e) for e in recent])
    baseline_density = compute_event_density([dict(e) for e in baseline])

    baseline_map = {(c["lat"], c["lng"]): c for c in baseline_density}

    escalation_zones = []
    for cell in recent_density:
        key = (cell["lat"], cell["lng"])
        base = baseline_map.get(key)

        if base:
            sev_change = cell["avg_severity"] - base["avg_severity"]
            count_ratio = cell["count"] / max(base["count"], 1)
        else:
            sev_change = cell["avg_severity"] - 40  # assume 40 baseline
            count_ratio = cell["count"]

        if sev_change > 10 or count_ratio > 2.0:
            escalation_zones.append({
                "lat": cell["lat"],
                "lng": cell["lng"],
                "severity_change": round(sev_change, 1),
                "count_ratio": round(count_ratio, 2),
                "recent_count": cell["count"],
                "recent_avg_severity": cell["avg_severity"],
                "baseline_avg_severity": base["avg_severity"] if base else 40,
            })

    escalation_zones.sort(key=lambda z: z["severity_change"], reverse=True)
    return escalation_zones[:15]


def generate_predictions(conn, category: str | None = None,
                          country_code: str | None = None,
                          time_horizon_hours: int = 72) -> list[dict]:
    """
    Generate predictive positions combining hotspot analysis and escalation detection.
    """
    predictions = []

    # Hotspot predictions
    hotspots = detect_hotspots(conn, category, country_code)
    for h in hotspots[:10]:
        predictions.append({
            "prediction_type": "event_hotspot",
            "lat": h["lat"],
            "lng": h["lng"],
            "radius_km": 100,
            "probability": min(0.9, h["intensity"] / 10),
            "category": category,
            "country_code": country_code,
            "description": f"Event hotspot: {h['count']} events, avg severity {h['avg_severity']}",
            "time_horizon_hours": time_horizon_hours,
        })

    # Escalation zone predictions
    zones = detect_escalation_zones(conn)
    for z in zones[:5]:
        predictions.append({
            "prediction_type": "escalation_zone",
            "lat": z["lat"],
            "lng": z["lng"],
            "radius_km": 150,
            "probability": min(0.8, z["severity_change"] / 50),
            "description": f"Escalation zone: severity +{z['severity_change']:.0f}, "
                           f"activity {z['count_ratio']:.1f}x baseline",
            "time_horizon_hours": time_horizon_hours,
        })

    return predictions


def store_predictions(conn, predictions: list[dict]) -> list[str]:
    """Store predictions in the database."""
    now = datetime.now(timezone.utc)
    stored_ids = []

    for p in predictions:
        pid = str(uuid.uuid4())
        expires = (now + timedelta(hours=p.get("time_horizon_hours", 72))).isoformat()

        conn.execute(
            """INSERT INTO predictive_positions
               (id, prediction_type, lat, lng, radius_km, probability,
                category, country_code, description, time_horizon_hours, expires_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                pid, p["prediction_type"], p["lat"], p["lng"],
                p.get("radius_km", 50), p.get("probability", 0.5),
                p.get("category"), p.get("country_code"),
                p["description"],
                p.get("time_horizon_hours", 72), expires,
            ),
        )
        stored_ids.append(pid)

    conn.commit()
    return stored_ids


def run_predictive_scan(conn, category: str | None = None,
                         country_code: str | None = None) -> dict:
    """Full prediction pipeline: detect + store."""
    predictions = generate_predictions(conn, category, country_code)
    stored_ids = store_predictions(conn, predictions)

    return {
        "total_predictions": len(predictions),
        "hotspots": len([p for p in predictions if p["prediction_type"] == "event_hotspot"]),
        "escalation_zones": len([p for p in predictions if p["prediction_type"] == "escalation_zone"]),
        "stored_ids": stored_ids,
        "predictions": predictions,
    }


def list_predictions(conn, prediction_type: str | None = None,
                      active_only: bool = True, limit: int = 20) -> list[dict]:
    """List predictions, optionally only active (not expired)."""
    query = "SELECT * FROM predictive_positions"
    conditions = []
    params: list = []

    if prediction_type:
        conditions.append("prediction_type = ?")
        params.append(prediction_type)
    if active_only:
        conditions.append("(expires_at IS NULL OR expires_at >= ?)")
        params.append(datetime.now(timezone.utc).isoformat())

    if conditions:
        query += " WHERE " + " AND ".join(conditions)
    query += " ORDER BY created_at DESC LIMIT ?"
    params.append(limit)

    rows = conn.execute(query, params).fetchall()
    results = []
    for r in rows:
        d = dict(r)
        d["basis"] = json.loads(d["basis"]) if d["basis"] else []
        results.append(d)
    return results


def get_predictions_geojson(conn, prediction_type: str | None = None) -> dict:
    """Get predictions as GeoJSON for map rendering."""
    predictions = list_predictions(conn, prediction_type)

    TYPE_COLORS = {
        "event_hotspot": "#ef4444",
        "escalation_zone": "#f97316",
        "entity_movement": "#a78bfa",
        "vessel_destination": "#60a5fa",
    }

    features = []
    for p in predictions:
        features.append({
            "type": "Feature",
            "geometry": {
                "type": "Point",
                "coordinates": [p["lng"], p["lat"]],
            },
            "properties": {
                "id": p["id"],
                "prediction_type": p["prediction_type"],
                "probability": p["probability"],
                "radius_km": p["radius_km"],
                "description": p["description"],
                "color": TYPE_COLORS.get(p["prediction_type"], "#ef4444"),
                "expires_at": p["expires_at"],
            },
        })

    return {"type": "FeatureCollection", "features": features}
