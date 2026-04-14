"""
Reverse geocoding — converts latitude/longitude coordinates to
human-readable location names (country, state, city, district).

Uses a built-in country-level lookup table for fast offline resolution,
with a cache layer for higher-resolution results from external providers.
"""
import json
import math
import uuid

# Offline country centroid lookup (lat, lng, radius_deg, code, name)
# Covers major countries — enough for country-level reverse geocoding
COUNTRY_CENTROIDS = [
    (33.0, 44.0, 5, "IQ", "Iraq"),
    (32.0, 53.0, 6, "IR", "Iran"),
    (24.0, 45.0, 6, "SA", "Saudi Arabia"),
    (29.5, 47.5, 1.5, "KW", "Kuwait"),
    (25.3, 51.2, 0.5, "QA", "Qatar"),
    (24.0, 54.0, 1.5, "AE", "United Arab Emirates"),
    (23.0, 57.0, 3, "OM", "Oman"),
    (15.5, 48.0, 4, "YE", "Yemen"),
    (33.9, 35.5, 1, "LB", "Lebanon"),
    (31.8, 35.2, 1, "PS", "Palestine"),
    (31.5, 35.5, 1.5, "IL", "Israel"),
    (34.8, 39.0, 3, "SY", "Syria"),
    (33.3, 44.4, 4, "IQ", "Iraq"),
    (39.0, 35.0, 5, "TR", "Turkey"),
    (30.0, 31.0, 4, "EG", "Egypt"),
    (34.0, 9.0, 3, "TN", "Tunisia"),
    (28.0, 3.0, 8, "DZ", "Algeria"),
    (32.0, 13.0, 4, "LY", "Libya"),
    (31.8, -6.8, 4, "MA", "Morocco"),
    (48.9, 2.3, 4, "FR", "France"),
    (51.5, -0.1, 3, "GB", "United Kingdom"),
    (52.5, 13.4, 3, "DE", "Germany"),
    (41.9, 12.5, 3, "IT", "Italy"),
    (40.4, -3.7, 3, "ES", "Spain"),
    (50.8, 4.4, 1.5, "BE", "Belgium"),
    (52.4, 4.9, 1, "NL", "Netherlands"),
    (46.8, 8.2, 1.5, "CH", "Switzerland"),
    (48.2, 16.4, 2, "AT", "Austria"),
    (52.2, 21.0, 3, "PL", "Poland"),
    (50.1, 14.4, 2, "CZ", "Czech Republic"),
    (59.3, 18.1, 5, "SE", "Sweden"),
    (60.2, 25.0, 4, "FI", "Finland"),
    (59.9, 10.7, 4, "NO", "Norway"),
    (55.7, 12.6, 2, "DK", "Denmark"),
    (55.8, 37.6, 10, "RU", "Russia"),
    (50.4, 30.5, 4, "UA", "Ukraine"),
    (38.9, -77.0, 15, "US", "United States"),
    (45.4, -75.7, 10, "CA", "Canada"),
    (19.4, -99.1, 8, "MX", "Mexico"),
    (-23.6, -46.6, 10, "BR", "Brazil"),
    (-34.6, -58.4, 8, "AR", "Argentina"),
    (39.9, 116.4, 12, "CN", "China"),
    (35.7, 139.7, 5, "JP", "Japan"),
    (37.6, 127.0, 2, "KR", "South Korea"),
    (39.0, 125.8, 2, "KP", "North Korea"),
    (28.6, 77.2, 8, "IN", "India"),
    (33.7, 73.0, 5, "PK", "Pakistan"),
    (-6.2, 106.8, 8, "ID", "Indonesia"),
    (13.8, 100.5, 4, "TH", "Thailand"),
    (21.0, 105.8, 4, "VN", "Vietnam"),
    (14.6, 121.0, 4, "PH", "Philippines"),
    (3.1, 101.7, 3, "MY", "Malaysia"),
    (1.3, 103.8, 0.5, "SG", "Singapore"),
    (25.0, 121.5, 1.5, "TW", "Taiwan"),
    (-33.9, 151.2, 10, "AU", "Australia"),
    (-41.3, 174.8, 4, "NZ", "New Zealand"),
    (9.0, 8.0, 5, "NG", "Nigeria"),
    (-1.3, 36.8, 4, "KE", "Kenya"),
    (-26.2, 28.0, 5, "ZA", "South Africa"),
    (6.5, 3.4, 2, "NG", "Nigeria"),
    (5.6, -0.2, 3, "GH", "Ghana"),
    (9.0, 38.7, 4, "ET", "Ethiopia"),
]


def _haversine_approx(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    """Approximate distance in degrees (fast, no trig)."""
    dlat = abs(lat1 - lat2)
    dlng = abs(lng1 - lng2) * math.cos(math.radians((lat1 + lat2) / 2))
    return math.sqrt(dlat**2 + dlng**2)


def reverse_geocode_offline(lat: float, lng: float) -> dict:
    """
    Offline reverse geocoding using country centroid lookup.
    Returns best matching country based on distance.
    """
    best = None
    best_dist = float("inf")

    for clat, clng, radius, code, name in COUNTRY_CENTROIDS:
        dist = _haversine_approx(lat, lng, clat, clng)
        if dist < radius and dist < best_dist:
            best = {"country_code": code, "country_name": name}
            best_dist = dist

    if best:
        return {
            "latitude": lat, "longitude": lng,
            "country_code": best["country_code"],
            "country_name": best["country_name"],
            "resolution": "country_level",
            "provider": "internal",
        }

    # Ocean or unmapped area
    return {
        "latitude": lat, "longitude": lng,
        "country_code": None, "country_name": None,
        "resolution": "unknown", "provider": "internal",
    }


def reverse_geocode(conn, lat: float, lng: float, use_cache: bool = True) -> dict:
    """
    Reverse geocode with cache layer. Checks cache first, falls back to offline.
    """
    if use_cache:
        # Check cache (round to ~1km resolution)
        rlat = round(lat, 2)
        rlng = round(lng, 2)
        cached = conn.execute(
            """SELECT * FROM geocode_cache
               WHERE ABS(latitude - ?) < 0.02 AND ABS(longitude - ?) < 0.02
               LIMIT 1""",
            (rlat, rlng),
        ).fetchone()

        if cached:
            d = dict(cached)
            d["raw_response"] = json.loads(d["raw_response"]) if d["raw_response"] else None
            d["from_cache"] = True
            return d

    # Offline lookup
    result = reverse_geocode_offline(lat, lng)

    # Cache the result
    gid = str(uuid.uuid4())
    conn.execute(
        """INSERT INTO geocode_cache
           (id, latitude, longitude, country_code, country_name, resolution, provider)
           VALUES (?, ?, ?, ?, ?, ?, ?)""",
        (gid, lat, lng, result.get("country_code"),
         result.get("country_name"), result["resolution"], result["provider"]),
    )
    conn.commit()

    result["from_cache"] = False
    return result


def batch_reverse_geocode(conn, coords: list[tuple[float, float]]) -> list[dict]:
    """Reverse geocode multiple coordinates."""
    return [reverse_geocode(conn, lat, lng) for lat, lng in coords]


def get_geocode_stats(conn) -> dict:
    """Cache statistics."""
    total = conn.execute("SELECT COUNT(*) as c FROM geocode_cache").fetchone()["c"]
    by_country = {}
    rows = conn.execute(
        "SELECT country_code, COUNT(*) as c FROM geocode_cache WHERE country_code IS NOT NULL GROUP BY country_code"
    ).fetchall()
    for r in rows:
        by_country[r["country_code"]] = r["c"]
    return {"total_cached": total, "by_country": by_country}
