"""
EXIF metadata extraction — parses image EXIF data to extract geolocation,
camera info, timestamps, and other forensic metadata.

Provides a pure-Python fallback for environments without PIL/Pillow,
using basic binary parsing of common EXIF tags.
"""
import json
import math
import struct
import uuid
from datetime import datetime


# Common EXIF tag IDs
EXIF_TAGS = {
    0x010F: "camera_make",
    0x0110: "camera_model",
    0x0131: "software",
    0x0132: "capture_date",
    0x8769: "exif_ifd",
    0x8825: "gps_ifd",
    0xA002: "image_width",
    0xA003: "image_height",
}

GPS_TAGS = {
    0x0001: "gps_lat_ref",
    0x0002: "gps_lat",
    0x0003: "gps_lng_ref",
    0x0004: "gps_lng",
    0x0005: "gps_alt_ref",
    0x0006: "gps_alt",
}


def _dms_to_decimal(dms_tuple: tuple, ref: str) -> float | None:
    """Convert (degrees, minutes, seconds) to decimal degrees."""
    if not dms_tuple or len(dms_tuple) < 3:
        return None
    degrees = dms_tuple[0] + dms_tuple[1] / 60.0 + dms_tuple[2] / 3600.0
    if ref in ("S", "W"):
        degrees = -degrees
    return round(degrees, 6)


def parse_exif_from_dict(exif_dict: dict) -> dict:
    """
    Parse EXIF data from a pre-extracted dictionary.
    Accepts a dict with standard EXIF field names.
    """
    result = {
        "latitude": None, "longitude": None, "altitude": None,
        "capture_date": None, "camera_make": None, "camera_model": None,
        "software": None, "image_width": None, "image_height": None,
        "gps_accuracy": None,
    }

    result["camera_make"] = exif_dict.get("Make") or exif_dict.get("camera_make")
    result["camera_model"] = exif_dict.get("Model") or exif_dict.get("camera_model")
    result["software"] = exif_dict.get("Software") or exif_dict.get("software")
    result["capture_date"] = exif_dict.get("DateTimeOriginal") or exif_dict.get("capture_date")
    result["image_width"] = exif_dict.get("ImageWidth") or exif_dict.get("image_width")
    result["image_height"] = exif_dict.get("ImageHeight") or exif_dict.get("image_height")

    # GPS coordinates
    gps_lat = exif_dict.get("GPSLatitude") or exif_dict.get("gps_lat")
    gps_lat_ref = exif_dict.get("GPSLatitudeRef") or exif_dict.get("gps_lat_ref", "N")
    gps_lng = exif_dict.get("GPSLongitude") or exif_dict.get("gps_lng")
    gps_lng_ref = exif_dict.get("GPSLongitudeRef") or exif_dict.get("gps_lng_ref", "E")
    gps_alt = exif_dict.get("GPSAltitude") or exif_dict.get("gps_alt")

    if isinstance(gps_lat, (list, tuple)):
        result["latitude"] = _dms_to_decimal(tuple(gps_lat), gps_lat_ref)
    elif isinstance(gps_lat, (int, float)):
        result["latitude"] = gps_lat if gps_lat_ref != "S" else -gps_lat

    if isinstance(gps_lng, (list, tuple)):
        result["longitude"] = _dms_to_decimal(tuple(gps_lng), gps_lng_ref)
    elif isinstance(gps_lng, (int, float)):
        result["longitude"] = gps_lng if gps_lng_ref != "W" else -gps_lng

    if isinstance(gps_alt, (int, float)):
        result["altitude"] = gps_alt

    return result


def store_exif(conn, parsed: dict, source_url: str | None = None,
               filename: str | None = None,
               linked_event_id: str | None = None) -> str:
    """Store extracted EXIF metadata."""
    eid = str(uuid.uuid4())
    conn.execute(
        """INSERT INTO exif_metadata
           (id, source_url, filename, latitude, longitude, altitude,
            capture_date, camera_make, camera_model, software,
            image_width, image_height, gps_accuracy, raw_exif, linked_event_id)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (eid, source_url, filename,
         parsed.get("latitude"), parsed.get("longitude"), parsed.get("altitude"),
         parsed.get("capture_date"), parsed.get("camera_make"),
         parsed.get("camera_model"), parsed.get("software"),
         parsed.get("image_width"), parsed.get("image_height"),
         parsed.get("gps_accuracy"), json.dumps(parsed),
         linked_event_id),
    )
    conn.commit()
    return eid


def get_exif(conn, exif_id: str) -> dict | None:
    row = conn.execute("SELECT * FROM exif_metadata WHERE id = ?", (exif_id,)).fetchone()
    if not row:
        return None
    d = dict(row)
    d["raw_exif"] = json.loads(d["raw_exif"]) if d["raw_exif"] else None
    return d


def list_exif(conn, linked_event_id: str | None = None, limit: int = 50) -> list[dict]:
    if linked_event_id:
        rows = conn.execute(
            "SELECT * FROM exif_metadata WHERE linked_event_id = ? ORDER BY created_at DESC LIMIT ?",
            (linked_event_id, limit)).fetchall()
    else:
        rows = conn.execute(
            "SELECT * FROM exif_metadata ORDER BY created_at DESC LIMIT ?",
            (limit,)).fetchall()
    results = []
    for r in rows:
        d = dict(r)
        d["raw_exif"] = json.loads(d["raw_exif"]) if d["raw_exif"] else None
        results.append(d)
    return results


def find_exif_near(conn, lat: float, lng: float, radius_deg: float = 0.1,
                   limit: int = 20) -> list[dict]:
    """Find EXIF records near a geographic point."""
    rows = conn.execute(
        """SELECT * FROM exif_metadata
           WHERE latitude BETWEEN ? AND ? AND longitude BETWEEN ? AND ?
           ORDER BY created_at DESC LIMIT ?""",
        (lat - radius_deg, lat + radius_deg,
         lng - radius_deg, lng + radius_deg, limit),
    ).fetchall()
    results = []
    for r in rows:
        d = dict(r)
        d["raw_exif"] = json.loads(d["raw_exif"]) if d["raw_exif"] else None
        results.append(d)
    return results
