"""
Street-level imagery — caches Mapillary image references for ground-level
visual intelligence, linking geo-located street photos to events.
"""
import json
import uuid


def store_image(conn, image_id: str, lat: float, lng: float,
                compass_angle: float | None = None,
                captured_at: str | None = None,
                sequence_id: str | None = None,
                thumbnail_url: str | None = None,
                full_url: str | None = None,
                linked_event_id: str | None = None,
                provider: str = "mapillary") -> str:
    sid = str(uuid.uuid4())
    conn.execute(
        """INSERT OR IGNORE INTO street_imagery
           (id, provider, image_id, latitude, longitude, compass_angle,
            captured_at, sequence_id, thumbnail_url, full_url, linked_event_id)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (sid, provider, image_id, lat, lng, compass_angle,
         captured_at, sequence_id, thumbnail_url, full_url,
         linked_event_id),
    )
    conn.commit()
    return sid


def get_image(conn, record_id: str) -> dict | None:
    row = conn.execute("SELECT * FROM street_imagery WHERE id = ?",
                       (record_id,)).fetchone()
    return dict(row) if row else None


def list_images(conn, linked_event_id: str | None = None,
                provider: str | None = None,
                limit: int = 50) -> list[dict]:
    conditions, params = [], []
    if linked_event_id:
        conditions.append("linked_event_id = ?"); params.append(linked_event_id)
    if provider:
        conditions.append("provider = ?"); params.append(provider)

    where = (" WHERE " + " AND ".join(conditions)) if conditions else ""
    rows = conn.execute(
        f"SELECT * FROM street_imagery{where} ORDER BY created_at DESC LIMIT ?",
        params + [limit]).fetchall()
    return [dict(r) for r in rows]


def find_images_near(conn, lat: float, lng: float,
                     radius_deg: float = 0.05,
                     limit: int = 20) -> list[dict]:
    rows = conn.execute(
        """SELECT * FROM street_imagery
           WHERE latitude BETWEEN ? AND ?
           AND longitude BETWEEN ? AND ?
           ORDER BY ABS(latitude - ?) + ABS(longitude - ?) ASC
           LIMIT ?""",
        (lat - radius_deg, lat + radius_deg,
         lng - radius_deg, lng + radius_deg,
         lat, lng, limit),
    ).fetchall()
    return [dict(r) for r in rows]


def get_imagery_geojson(conn, lat: float | None = None,
                        lng: float | None = None,
                        radius_deg: float = 1.0,
                        limit: int = 200) -> dict:
    """Return street imagery as GeoJSON for map layer."""
    if lat is not None and lng is not None:
        images = find_images_near(conn, lat, lng, radius_deg, limit)
    else:
        images = list_images(conn, limit=limit)

    features = []
    for img in images:
        features.append({
            "type": "Feature",
            "geometry": {"type": "Point",
                         "coordinates": [img["longitude"], img["latitude"]]},
            "properties": {
                "id": img["id"],
                "image_id": img["image_id"],
                "compass_angle": img["compass_angle"],
                "captured_at": img["captured_at"],
                "thumbnail_url": img["thumbnail_url"],
                "full_url": img["full_url"],
                "provider": img["provider"],
            },
        })
    return {"type": "FeatureCollection", "features": features}
