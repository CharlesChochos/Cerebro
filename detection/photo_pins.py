"""
Photo pins — geolocated photos extracted from news articles and pinned
to the intelligence map. Supports EXIF cross-referencing to flag
location mismatches (potential misinformation).
"""
import uuid
from detection.exif_extraction import extract_exif, check_location_mismatch


def add_photo_pin(conn, source_url: str, latitude: float, longitude: float,
                  title: str | None = None, caption: str | None = None,
                  event_id: str | None = None, country_code: str | None = None,
                  image_url: str | None = None,
                  image_bytes: bytes | None = None) -> dict:
    """
    Add a geolocated photo pin. If image_bytes are provided,
    extracts EXIF and checks for location mismatch.
    """
    pid = str(uuid.uuid4())
    exif_lat = None
    exif_lng = None
    exif_timestamp = None
    exif_camera = None
    exif_mismatch = 0
    mismatch_km = None

    # Extract EXIF if image data provided
    if image_bytes:
        exif = extract_exif(image_bytes)
        if exif.get("has_gps"):
            exif_lat = exif["latitude"]
            exif_lng = exif["longitude"]
            exif_camera = exif.get("camera_model")
            exif_timestamp = exif.get("timestamp")

            # Check location mismatch
            check = check_location_mismatch(latitude, longitude, exif_lat, exif_lng)
            if check["mismatch"]:
                exif_mismatch = 1
                mismatch_km = check["distance_km"]
        elif exif.get("camera_model"):
            exif_camera = exif["camera_model"]
        if exif.get("timestamp"):
            exif_timestamp = exif["timestamp"]

    conn.execute(
        """INSERT INTO photo_pins
           (id, event_id, source_url, image_url, latitude, longitude,
            title, caption, country_code,
            exif_lat, exif_lng, exif_timestamp, exif_camera,
            exif_mismatch, mismatch_km)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (pid, event_id, source_url, image_url, latitude, longitude,
         title, caption, country_code,
         exif_lat, exif_lng, exif_timestamp, exif_camera,
         exif_mismatch, mismatch_km),
    )
    conn.commit()

    return {
        "id": pid,
        "exif_mismatch": bool(exif_mismatch),
        "mismatch_km": mismatch_km,
    }


def get_photo_pin(conn, pin_id: str) -> dict | None:
    row = conn.execute("SELECT * FROM photo_pins WHERE id = ?",
                       (pin_id,)).fetchone()
    return dict(row) if row else None


def list_photo_pins(conn, event_id: str | None = None,
                    country_code: str | None = None,
                    mismatch_only: bool = False,
                    limit: int = 100) -> list[dict]:
    conditions, params = [], []
    if event_id:
        conditions.append("event_id = ?"); params.append(event_id)
    if country_code:
        conditions.append("country_code = ?"); params.append(country_code)
    if mismatch_only:
        conditions.append("exif_mismatch = 1")

    where = (" WHERE " + " AND ".join(conditions)) if conditions else ""
    rows = conn.execute(
        f"SELECT * FROM photo_pins{where} ORDER BY created_at DESC LIMIT ?",
        params + [limit]).fetchall()
    return [dict(r) for r in rows]


def get_photo_pin_geojson(conn, mismatch_only: bool = False) -> dict:
    """Generate GeoJSON for photo pin markers on the map."""
    pins = list_photo_pins(conn, mismatch_only=mismatch_only, limit=500)
    features = []

    for pin in pins:
        props = {
            "id": pin["id"],
            "title": pin["title"],
            "caption": pin["caption"],
            "source_url": pin["source_url"],
            "image_url": pin["image_url"],
            "country_code": pin["country_code"],
            "exif_mismatch": bool(pin["exif_mismatch"]),
            "mismatch_km": pin["mismatch_km"],
            "color": "#ef4444" if pin["exif_mismatch"] else "#a78bfa",
        }

        features.append({
            "type": "Feature",
            "geometry": {
                "type": "Point",
                "coordinates": [pin["longitude"], pin["latitude"]],
            },
            "properties": props,
        })

        # If EXIF mismatch, also add a line showing the discrepancy
        if pin["exif_mismatch"] and pin["exif_lat"] and pin["exif_lng"]:
            features.append({
                "type": "Feature",
                "geometry": {
                    "type": "LineString",
                    "coordinates": [
                        [pin["longitude"], pin["latitude"]],
                        [pin["exif_lng"], pin["exif_lat"]],
                    ],
                },
                "properties": {
                    "type": "mismatch_line",
                    "distance_km": pin["mismatch_km"],
                    "color": "#ef4444",
                },
            })

    return {"type": "FeatureCollection", "features": features}


def find_mismatches(conn, limit: int = 50) -> list[dict]:
    """Return all photo pins where EXIF GPS doesn't match claimed location."""
    rows = conn.execute(
        """SELECT * FROM photo_pins
           WHERE exif_mismatch = 1
           ORDER BY mismatch_km DESC
           LIMIT ?""",
        (limit,)).fetchall()
    return [dict(r) for r in rows]
