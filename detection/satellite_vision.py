"""
Satellite change detection using Claude Vision.

Compares pairs of satellite images (or their metadata) to detect and
annotate changes: new construction, vehicle concentrations, flooding,
fire damage, deforestation, military deployments, etc.

Workflow:
  1.  Find image pairs for a location (before / after).
  2.  If actual image files exist on disk, send them to Claude Vision.
  3.  If only metadata exists, use a text-based comparison mode.
  4.  Store structured annotations back onto the satellite_cache record.
"""
import base64
import json
import logging
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path

import anthropic

from config.settings import CLAUDE_API_KEY, PROJECT_ROOT

logger = logging.getLogger(__name__)

MODEL = "claude-sonnet-4-20250514"

VISION_SYSTEM = """You are a satellite imagery analyst specializing in change detection.
You are comparing two satellite images of the same geographic location taken on
different dates.  Analyze both images carefully and report all detected changes.

For each change, provide:
- type: new_construction | demolition | vehicle_concentration | military_deployment |
        flooding | fire_damage | deforestation | agricultural_change | infrastructure |
        vessel_activity | other
- description: What changed between the two dates
- severity: low | medium | high
- confidence: 0.0-1.0

Respond ONLY with valid JSON:
{
  "changes_detected": true/false,
  "change_count": N,
  "changes": [
    {"type": "...", "description": "...", "severity": "...", "confidence": 0.0-1.0}
  ],
  "overall_assessment": "one paragraph summary of what changed",
  "strategic_significance": "low | medium | high | critical"
}"""

TEXT_COMPARISON_SYSTEM = """You are a satellite imagery analyst.  You don't have the actual
images but you have metadata for two satellite captures of the same area on
different dates.  Based on the metadata, contextual events in the area, and your
knowledge of the region, assess what changes are LIKELY.

Respond ONLY with valid JSON:
{
  "changes_detected": true/false,
  "change_count": N,
  "changes": [
    {"type": "...", "description": "...", "severity": "...", "confidence": 0.0-1.0}
  ],
  "overall_assessment": "one paragraph assessment based on available metadata",
  "strategic_significance": "low | medium | high | critical"
}"""


def _load_image_as_base64(file_path: str) -> tuple[str, str] | None:
    """Load an image file and return (base64_data, media_type)."""
    path = Path(file_path)
    if not path.exists():
        return None

    ext = path.suffix.lower()
    media_types = {
        ".png": "image/png",
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".gif": "image/gif",
        ".webp": "image/webp",
        ".tif": "image/tiff",
        ".tiff": "image/tiff",
    }
    media_type = media_types.get(ext)
    if not media_type:
        return None

    with open(path, "rb") as f:
        data = base64.standard_b64encode(f.read()).decode("utf-8")
    return data, media_type


def _find_image_pair(conn, lat: float, lng: float,
                     radius_km: float = 50) -> tuple[dict | None, dict | None]:
    """
    Find the two most recent satellite images near a location
    for before/after comparison.
    """
    delta = radius_km / 111.0

    rows = conn.execute(
        """SELECT id, source, capture_date, image_url, cloud_cover,
                  resolution_m, bbox_json, annotations, thumbnail_url
           FROM satellite_cache
           WHERE CAST(json_extract(bbox_json, '$[0]') AS REAL) <= ?
             AND CAST(json_extract(bbox_json, '$[2]') AS REAL) >= ?
             AND CAST(json_extract(bbox_json, '$[1]') AS REAL) <= ?
             AND CAST(json_extract(bbox_json, '$[3]') AS REAL) >= ?
           ORDER BY capture_date DESC LIMIT 2""",
        (lng + delta, lng - delta, lat + delta, lat - delta),
    ).fetchall()

    if len(rows) < 2:
        return (dict(rows[0]) if rows else None, None)
    return dict(rows[0]), dict(rows[1])


def compare_images_vision(conn, image_before_id: str,
                           image_after_id: str) -> dict:
    """
    Compare two satellite images using Claude Vision.

    Args:
        image_before_id: satellite_cache ID for the earlier image
        image_after_id:  satellite_cache ID for the later image

    Returns:
        Change detection results.
    """
    if not CLAUDE_API_KEY:
        return {"error": "no_api_key"}

    before = conn.execute(
        "SELECT * FROM satellite_cache WHERE id = ?", (image_before_id,)
    ).fetchone()
    after = conn.execute(
        "SELECT * FROM satellite_cache WHERE id = ?", (image_after_id,)
    ).fetchone()

    if not before or not after:
        return {"error": "Image(s) not found"}

    before_d = dict(before)
    after_d = dict(after)

    # Try to load actual image files
    before_img = _load_image_as_base64(before_d.get("image_url", "")) if before_d.get("image_url") else None
    after_img = _load_image_as_base64(after_d.get("image_url", "")) if after_d.get("image_url") else None

    client = anthropic.Anthropic(api_key=CLAUDE_API_KEY)

    if before_img and after_img:
        # Vision mode — send actual images
        content = [
            {"type": "text", "text": f"BEFORE image (captured {before_d['capture_date']}):"},
            {
                "type": "image",
                "source": {
                    "type": "base64",
                    "media_type": before_img[1],
                    "data": before_img[0],
                },
            },
            {"type": "text", "text": f"AFTER image (captured {after_d['capture_date']}):"},
            {
                "type": "image",
                "source": {
                    "type": "base64",
                    "media_type": after_img[1],
                    "data": after_img[0],
                },
            },
            {"type": "text", "text": "Analyze what changed between these two satellite images."},
        ]
        system = VISION_SYSTEM
    else:
        # Text metadata mode — no actual images available
        before_meta = {
            "capture_date": before_d.get("capture_date"),
            "source": before_d.get("source"),
            "cloud_cover": before_d.get("cloud_cover"),
            "resolution_m": before_d.get("resolution_m"),
            "bbox": before_d.get("bbox_json"),
            "existing_annotations": before_d.get("annotations"),
        }
        after_meta = {
            "capture_date": after_d.get("capture_date"),
            "source": after_d.get("source"),
            "cloud_cover": after_d.get("cloud_cover"),
            "resolution_m": after_d.get("resolution_m"),
            "bbox": after_d.get("bbox_json"),
            "existing_annotations": after_d.get("annotations"),
        }

        # Also fetch nearby events between the two dates
        events_between = []
        if before_d.get("bbox_json") and after_d.get("capture_date"):
            try:
                bbox = json.loads(before_d["bbox_json"]) if isinstance(before_d["bbox_json"], str) else before_d["bbox_json"]
                center_lat = (bbox[1] + bbox[3]) / 2
                center_lng = (bbox[0] + bbox[2]) / 2
                delta = 1.0  # ~111 km
                rows = conn.execute(
                    """SELECT title, category, severity, timestamp
                       FROM events
                       WHERE latitude BETWEEN ? AND ?
                         AND longitude BETWEEN ? AND ?
                         AND timestamp BETWEEN ? AND ?
                       ORDER BY severity DESC LIMIT 10""",
                    (center_lat - delta, center_lat + delta,
                     center_lng - delta, center_lng + delta,
                     before_d["capture_date"], after_d["capture_date"]),
                ).fetchall()
                events_between = [dict(r) for r in rows]
            except (json.JSONDecodeError, TypeError, KeyError):
                pass

        content = [
            {
                "type": "text",
                "text": (
                    f"BEFORE metadata:\n{json.dumps(before_meta, indent=2, default=str)}\n\n"
                    f"AFTER metadata:\n{json.dumps(after_meta, indent=2, default=str)}\n\n"
                    f"Events in the area between captures:\n"
                    f"{json.dumps(events_between, indent=2, default=str)}\n\n"
                    "Based on this metadata and regional context, assess likely changes."
                ),
            }
        ]
        system = TEXT_COMPARISON_SYSTEM

    try:
        response = client.messages.create(
            model=MODEL,
            max_tokens=2000,
            system=system,
            messages=[{"role": "user", "content": content}],
        )
        text = response.content[0].text.strip()
        # Strip markdown fences
        if text.startswith("```"):
            text = text.split("\n", 1)[1] if "\n" in text else text[3:]
        if text.endswith("```"):
            text = text[:-3]
        text = text.strip()
        if text.startswith("json"):
            text = text[4:].strip()

        result = json.loads(text)
    except json.JSONDecodeError:
        result = {
            "changes_detected": False,
            "change_count": 0,
            "changes": [],
            "overall_assessment": text[:1000] if text else "Parse error",
            "strategic_significance": "low",
        }
    except anthropic.APIError as e:
        logger.error("Vision API error: %s", e)
        return {"error": str(e)}

    # Store annotations on the AFTER image
    annotations = json.dumps({
        "compared_with": image_before_id,
        "detection_result": result,
        "detected_at": datetime.now(timezone.utc).isoformat(),
        "model": MODEL,
        "mode": "vision" if (before_img and after_img) else "metadata",
    })
    conn.execute(
        "UPDATE satellite_cache SET annotations = ? WHERE id = ?",
        (annotations, image_after_id),
    )
    conn.commit()

    # Also store in change_detections table
    detection_id = str(uuid.uuid4())
    conn.execute(
        """INSERT INTO satellite_change_detections
           (id, before_image_id, after_image_id, changes_json,
            strategic_significance, model_used, mode, created_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            detection_id,
            image_before_id,
            image_after_id,
            json.dumps(result),
            result.get("strategic_significance", "low"),
            MODEL,
            "vision" if (before_img and after_img) else "metadata",
            datetime.now(timezone.utc).isoformat(),
        ),
    )
    conn.commit()

    return {
        "detection_id": detection_id,
        "before_image": image_before_id,
        "after_image": image_after_id,
        "mode": "vision" if (before_img and after_img) else "metadata",
        "result": result,
        "input_tokens": response.usage.input_tokens,
        "output_tokens": response.usage.output_tokens,
    }


def detect_changes_at_location(conn, lat: float, lng: float,
                                radius_km: float = 50) -> dict:
    """
    Auto-detect satellite changes near a location.
    Finds the two most recent images and compares them.
    """
    after_img, before_img = _find_image_pair(conn, lat, lng, radius_km)

    if not after_img or not before_img:
        return {
            "error": "insufficient_imagery",
            "images_found": 1 if after_img else 0,
            "message": "Need at least 2 satellite images for change detection",
        }

    return compare_images_vision(conn, before_img["id"], after_img["id"])


def get_change_detection(conn, detection_id: str) -> dict | None:
    """Retrieve a stored change detection result."""
    row = conn.execute(
        "SELECT * FROM satellite_change_detections WHERE id = ?",
        (detection_id,),
    ).fetchone()
    if not row:
        return None
    d = dict(row)
    if d.get("changes_json"):
        try:
            d["changes"] = json.loads(d["changes_json"])
        except (json.JSONDecodeError, TypeError):
            pass
    return d


def list_change_detections(conn, limit: int = 20) -> list[dict]:
    """List recent satellite change detections."""
    rows = conn.execute(
        """SELECT id, before_image_id, after_image_id,
                  strategic_significance, mode, created_at
           FROM satellite_change_detections
           ORDER BY created_at DESC LIMIT ?""",
        (limit,),
    ).fetchall()
    return [dict(r) for r in rows]


def auto_detect_changes(conn, max_locations: int = 5) -> list[dict]:
    """
    Auto-scan locations with multiple satellite images for changes.
    Targets locations that haven't been analyzed yet.
    """
    # Find image pairs that haven't been compared
    rows = conn.execute(
        """SELECT DISTINCT s1.id as after_id, s2.id as before_id
           FROM satellite_cache s1
           JOIN satellite_cache s2
             ON s1.source = s2.source
             AND s1.capture_date > s2.capture_date
             AND s1.id != s2.id
           LEFT JOIN satellite_change_detections d
             ON d.before_image_id = s2.id AND d.after_image_id = s1.id
           WHERE d.id IS NULL
           ORDER BY s1.capture_date DESC
           LIMIT ?""",
        (max_locations,),
    ).fetchall()

    results = []
    for row in rows:
        result = compare_images_vision(conn, row["before_id"], row["after_id"])
        results.append(result)
    return results
