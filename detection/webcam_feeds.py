"""
Public webcam feed management — tracks live camera feeds from Windy.com,
traffic cameras, and other public sources for real-time visual intelligence.
"""
import json
import uuid

# Seed: notable public webcam locations (ports, borders, capitals)
SEED_WEBCAMS = [
    ("Istanbul Bosphorus", 41.04, 29.00, "TR", "port",
     "https://www.windy.com/webcams/1234567890"),
    ("Suez Canal", 30.58, 32.27, "EG", "port",
     "https://www.windy.com/webcams/suez"),
    ("Strait of Hormuz", 26.59, 56.27, "OM", "port",
     "https://www.windy.com/webcams/hormuz"),
    ("Kyiv Maidan", 50.45, 30.52, "UA", "landscape",
     "https://www.windy.com/webcams/kyiv-maidan"),
    ("US-Mexico Border Tijuana", 32.54, -117.04, "MX", "border",
     "https://www.windy.com/webcams/tijuana"),
    ("Gaza Border", 31.34, 34.38, "PS", "border",
     "https://www.windy.com/webcams/gaza"),
    ("South China Sea", 16.05, 112.33, "CN", "landscape",
     "https://www.windy.com/webcams/scs"),
    ("Singapore Strait", 1.26, 103.85, "SG", "port",
     "https://www.windy.com/webcams/singapore"),
    ("London Westminster", 51.50, -0.12, "GB", "landscape",
     "https://www.windy.com/webcams/westminster"),
    ("Tokyo Shibuya", 35.66, 139.70, "JP", "landscape",
     "https://www.windy.com/webcams/shibuya"),
    ("Panama Canal", 9.08, -79.68, "PA", "port",
     "https://www.windy.com/webcams/panama"),
    ("Rafah Crossing", 31.28, 34.24, "EG", "border",
     "https://www.windy.com/webcams/rafah"),
]


def seed_webcams(conn) -> int:
    """Seed initial webcam feeds."""
    count = 0
    for title, lat, lng, cc, cat, url in SEED_WEBCAMS:
        wid = str(uuid.uuid4())
        try:
            conn.execute(
                """INSERT OR IGNORE INTO webcam_feeds
                   (id, provider, title, latitude, longitude, country_code,
                    category, stream_url, thumbnail_url, status)
                   VALUES (?, 'windy', ?, ?, ?, ?, ?, ?, ?, 'active')""",
                (wid, title, lat, lng, cc, cat, url,
                 url.replace("webcams/", "webcams/thumbnail/")),
            )
            count += 1
        except Exception:
            pass
    conn.commit()
    return count


def add_webcam(conn, title: str, lat: float, lng: float,
               country_code: str | None = None, category: str = "weather",
               stream_url: str | None = None, thumbnail_url: str | None = None,
               provider: str = "windy") -> str:
    wid = str(uuid.uuid4())
    conn.execute(
        """INSERT INTO webcam_feeds
           (id, provider, title, latitude, longitude, country_code,
            category, stream_url, thumbnail_url)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (wid, provider, title, lat, lng, country_code,
         category, stream_url, thumbnail_url),
    )
    conn.commit()
    return wid


def get_webcam(conn, webcam_id: str) -> dict | None:
    row = conn.execute("SELECT * FROM webcam_feeds WHERE id = ?",
                       (webcam_id,)).fetchone()
    return dict(row) if row else None


def list_webcams(conn, category: str | None = None,
                 country_code: str | None = None,
                 status: str = "active",
                 limit: int = 100) -> list[dict]:
    conditions, params = ["status = ?"], [status]
    if category:
        conditions.append("category = ?"); params.append(category)
    if country_code:
        conditions.append("country_code = ?"); params.append(country_code)

    where = " WHERE " + " AND ".join(conditions)
    rows = conn.execute(
        f"SELECT * FROM webcam_feeds{where} ORDER BY title LIMIT ?",
        params + [limit]).fetchall()
    return [dict(r) for r in rows]


def find_webcams_near(conn, lat: float, lng: float,
                      radius_deg: float = 2.0,
                      limit: int = 20) -> list[dict]:
    rows = conn.execute(
        """SELECT * FROM webcam_feeds
           WHERE latitude BETWEEN ? AND ?
           AND longitude BETWEEN ? AND ?
           AND status = 'active'
           ORDER BY ABS(latitude - ?) + ABS(longitude - ?)
           LIMIT ?""",
        (lat - radius_deg, lat + radius_deg,
         lng - radius_deg, lng + radius_deg,
         lat, lng, limit),
    ).fetchall()
    return [dict(r) for r in rows]


def get_webcam_geojson(conn, category: str | None = None,
                       country_code: str | None = None) -> dict:
    """Return webcams as GeoJSON FeatureCollection."""
    cams = list_webcams(conn, category, country_code, limit=500)
    features = []
    for c in cams:
        features.append({
            "type": "Feature",
            "geometry": {"type": "Point",
                         "coordinates": [c["longitude"], c["latitude"]]},
            "properties": {
                "id": c["id"], "title": c["title"],
                "category": c["category"],
                "country_code": c["country_code"],
                "stream_url": c["stream_url"],
                "thumbnail_url": c["thumbnail_url"],
                "provider": c["provider"],
            },
        })
    return {"type": "FeatureCollection", "features": features}
