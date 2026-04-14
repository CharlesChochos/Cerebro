"""
Copernicus Sentinel-2 satellite imagery ingestion connector.

Fetches imagery metadata and thumbnails from the Copernicus Data Space.
Free registration required: https://dataspace.copernicus.eu/
Claude Vision can then analyze the imagery for change detection.

Note: Full image download requires authentication; we cache metadata
and thumbnails for browse, with on-demand full resolution fetch.
"""
import json
import logging
import os
import uuid
from datetime import datetime, timezone, timedelta

import httpx

logger = logging.getLogger(__name__)

COPERNICUS_API = "https://catalogue.dataspace.copernicus.eu/odata/v1"
COPERNICUS_TOKEN_URL = "https://identity.dataspace.copernicus.eu/auth/realms/CDSE/protocol/openid-connect/token"

COPERNICUS_CLIENT_ID = os.getenv("COPERNICUS_CLIENT_ID", "")
COPERNICUS_CLIENT_SECRET = os.getenv("COPERNICUS_CLIENT_SECRET", "")

# Areas of interest for satellite monitoring (same as OSM)
AREAS_OF_INTEREST = [
    {"name": "South China Sea", "bbox": [105, 5, 125, 25]},
    {"name": "Crimea/Black Sea", "bbox": [32, 43, 37, 47]},
    {"name": "Korean DMZ", "bbox": [126, 37.5, 127.5, 38.5]},
    {"name": "Taiwan Strait", "bbox": [117, 22, 122, 26]},
    {"name": "Persian Gulf", "bbox": [50, 24, 56, 30]},
    {"name": "Horn of Africa", "bbox": [41, 8, 52, 15]},
]


def search_products(
    bbox: list[float],
    days_back: int = 7,
    max_cloud: float = 30.0,
    limit: int = 5,
) -> list[dict]:
    """
    Search Copernicus for Sentinel-2 products in a bounding box.
    Returns product metadata (no authentication needed for search).
    """
    start_date = (datetime.now(timezone.utc) - timedelta(days=days_back)).strftime("%Y-%m-%dT00:00:00Z")
    end_date = datetime.now(timezone.utc).strftime("%Y-%m-%dT23:59:59Z")

    west, south, east, north = bbox
    footprint = f"OData.CSC.Intersects(area=geography'SRID=4326;POLYGON(({west} {south},{east} {south},{east} {north},{west} {north},{west} {south}))')"

    url = f"{COPERNICUS_API}/Products"
    params = {
        "$filter": (
            f"Collection/Name eq 'SENTINEL-2' "
            f"and ContentDate/Start ge {start_date} "
            f"and ContentDate/Start le {end_date} "
            f"and Attributes/OData.CSC.DoubleAttribute/any(att:att/Name eq 'cloudCover' and att/Value le {max_cloud}) "
            f"and {footprint}"
        ),
        "$top": str(limit),
        "$orderby": "ContentDate/Start desc",
    }

    try:
        resp = httpx.get(url, params=params, timeout=20.0)
        resp.raise_for_status()
        data = resp.json()
        return data.get("value", [])
    except (httpx.HTTPStatusError, httpx.RequestError) as e:
        logger.error("Copernicus API error: %s", e)
        return []


def extract_product_metadata(product: dict) -> dict:
    """Extract useful metadata from a Copernicus product."""
    name = product.get("Name", "")
    product_id = product.get("Id", "")
    content_date = product.get("ContentDate", {})
    start = content_date.get("Start", "")

    # Extract cloud cover from attributes
    cloud_cover = None
    for attr in product.get("Attributes", []):
        if attr.get("Name") == "cloudCover":
            cloud_cover = attr.get("Value")
            break

    # Extract footprint center (approximate)
    footprint = product.get("GeoFootprint", {})
    coords = footprint.get("coordinates", [[[0, 0]]])
    if coords and coords[0]:
        flat = coords[0] if isinstance(coords[0][0], (int, float)) else coords[0]
        if flat:
            lats = [c[1] for c in flat if isinstance(c, (list, tuple)) and len(c) >= 2]
            lngs = [c[0] for c in flat if isinstance(c, (list, tuple)) and len(c) >= 2]
            center_lat = sum(lats) / len(lats) if lats else 0
            center_lng = sum(lngs) / len(lngs) if lngs else 0
        else:
            center_lat, center_lng = 0, 0
    else:
        center_lat, center_lng = 0, 0

    # Quicklook thumbnail URL
    thumbnail_url = f"{COPERNICUS_API}/Products({product_id})/Nodes({name})/Nodes(GRANULE)/Nodes"

    return {
        "product_id": product_id,
        "name": name,
        "capture_date": start[:10] if start else "",
        "cloud_cover": cloud_cover,
        "center_lat": center_lat,
        "center_lng": center_lng,
        "resolution_m": 10.0,
        "thumbnail_url": thumbnail_url,
        "footprint": json.dumps(footprint) if footprint else None,
    }


def ingest(conn) -> dict:
    """Search and cache Sentinel-2 product metadata for areas of interest."""
    inserted = 0
    skipped = 0
    errors = 0
    fetched = 0

    for area in AREAS_OF_INTEREST:
        products = search_products(area["bbox"], days_back=7, limit=3)
        fetched += len(products)

        for product in products:
            meta = extract_product_metadata(product)
            if not meta["capture_date"]:
                continue

            cache_id = str(uuid.uuid4())
            source_id = f"sentinel2-{meta['product_id']}"

            try:
                cursor = conn.execute(
                    """INSERT OR IGNORE INTO satellite_cache
                       (id, source, lat, lng, bbox_json, capture_date, cloud_cover,
                        image_url, thumbnail_url, resolution_m, metadata)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (
                        cache_id, "sentinel2",
                        meta["center_lat"], meta["center_lng"],
                        json.dumps(area["bbox"]),
                        meta["capture_date"], meta["cloud_cover"],
                        None,  # Full image URL requires auth
                        meta["thumbnail_url"],
                        meta["resolution_m"],
                        json.dumps({
                            "product_id": meta["product_id"],
                            "name": meta["name"],
                            "area": area["name"],
                            "footprint": meta["footprint"],
                        }),
                    ),
                )
                if cursor.rowcount > 0:
                    inserted += 1
                else:
                    skipped += 1
            except Exception as e:
                logger.error("Error caching Sentinel-2 product: %s", e)
                errors += 1

    conn.commit()
    stats = {"source": "sentinel2", "fetched": fetched, "inserted": inserted, "skipped": skipped, "errors": errors}
    logger.info("Sentinel-2 ingestion: %s", stats)
    return stats
