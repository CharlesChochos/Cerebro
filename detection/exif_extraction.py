"""
EXIF metadata extraction — extracts GPS coordinates, timestamps, and camera
info from images. Cross-references claimed location against EXIF GPS to
detect potential misinformation.

Uses Python Pillow (PIL) for zero-cost EXIF parsing.
"""
import math
from io import BytesIO
from typing import Any

try:
    from PIL import Image
    from PIL.ExifTags import TAGS, GPSTAGS
    HAS_PIL = True
except ImportError:
    HAS_PIL = False


def _dms_to_decimal(dms: tuple, ref: str) -> float | None:
    """Convert degrees/minutes/seconds to decimal degrees."""
    try:
        degrees = float(dms[0])
        minutes = float(dms[1])
        seconds = float(dms[2])
        decimal = degrees + minutes / 60 + seconds / 3600
        if ref in ("S", "W"):
            decimal = -decimal
        return round(decimal, 6)
    except (TypeError, ValueError, IndexError):
        return None


def _parse_gps_info(gps_data: dict) -> dict:
    """Parse GPS EXIF data into lat/lng."""
    result: dict[str, Any] = {}

    gps_lat = gps_data.get("GPSLatitude") or gps_data.get(2)
    gps_lat_ref = gps_data.get("GPSLatitudeRef") or gps_data.get(1, "N")
    gps_lng = gps_data.get("GPSLongitude") or gps_data.get(4)
    gps_lng_ref = gps_data.get("GPSLongitudeRef") or gps_data.get(3, "E")

    if gps_lat and gps_lng:
        lat = _dms_to_decimal(gps_lat, str(gps_lat_ref))
        lng = _dms_to_decimal(gps_lng, str(gps_lng_ref))
        if lat is not None and lng is not None:
            result["latitude"] = lat
            result["longitude"] = lng

    gps_alt = gps_data.get("GPSAltitude") or gps_data.get(6)
    if gps_alt is not None:
        try:
            result["altitude"] = float(gps_alt)
        except (TypeError, ValueError):
            pass

    return result


def extract_exif(image_bytes: bytes) -> dict:
    """
    Extract EXIF metadata from image bytes.

    Returns dict with keys:
        - latitude, longitude (if GPS present)
        - timestamp (original datetime)
        - camera_make, camera_model
        - software
        - has_gps (bool)
    """
    if not HAS_PIL:
        return {"error": "Pillow not installed", "has_gps": False}

    result: dict[str, Any] = {"has_gps": False}

    try:
        img = Image.open(BytesIO(image_bytes))
        exif_data = img._getexif()
        if not exif_data:
            return result

        # Parse standard EXIF tags
        decoded: dict[str, Any] = {}
        for tag_id, value in exif_data.items():
            tag_name = TAGS.get(tag_id, str(tag_id))
            decoded[tag_name] = value

        # Camera info
        if "Make" in decoded:
            result["camera_make"] = str(decoded["Make"]).strip()
        if "Model" in decoded:
            result["camera_model"] = str(decoded["Model"]).strip()
        if "Software" in decoded:
            result["software"] = str(decoded["Software"]).strip()

        # Timestamp
        for ts_key in ("DateTimeOriginal", "DateTimeDigitized", "DateTime"):
            if ts_key in decoded and decoded[ts_key]:
                # EXIF format: "2025:01:15 14:30:00"
                ts = str(decoded[ts_key]).replace(":", "-", 2)
                result["timestamp"] = ts
                break

        # GPS data
        if "GPSInfo" in decoded:
            gps_raw = decoded["GPSInfo"]
            # Decode GPS tag IDs to names
            gps_decoded = {}
            if isinstance(gps_raw, dict):
                for k, v in gps_raw.items():
                    gps_tag_name = GPSTAGS.get(k, k)
                    gps_decoded[gps_tag_name] = v
                    gps_decoded[k] = v  # Keep numeric key too

            gps_result = _parse_gps_info(gps_decoded)
            if "latitude" in gps_result and "longitude" in gps_result:
                result["latitude"] = gps_result["latitude"]
                result["longitude"] = gps_result["longitude"]
                result["has_gps"] = True
            if "altitude" in gps_result:
                result["altitude"] = gps_result["altitude"]

    except Exception as e:
        result["error"] = str(e)

    return result


def haversine_km(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    """Calculate distance in km between two points using Haversine formula."""
    R = 6371.0  # Earth's radius in km
    dlat = math.radians(lat2 - lat1)
    dlng = math.radians(lng2 - lng1)
    a = (math.sin(dlat / 2) ** 2 +
         math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) *
         math.sin(dlng / 2) ** 2)
    return R * 2 * math.asin(math.sqrt(a))


def check_location_mismatch(claimed_lat: float, claimed_lng: float,
                             exif_lat: float, exif_lng: float,
                             threshold_km: float = 50.0) -> dict:
    """
    Compare claimed event location against EXIF GPS coordinates.
    Returns mismatch info.
    """
    distance = haversine_km(claimed_lat, claimed_lng, exif_lat, exif_lng)
    return {
        "mismatch": distance > threshold_km,
        "distance_km": round(distance, 2),
        "threshold_km": threshold_km,
        "claimed": {"lat": claimed_lat, "lng": claimed_lng},
        "exif": {"lat": exif_lat, "lng": exif_lng},
    }
