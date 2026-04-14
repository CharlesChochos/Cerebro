"""
Radar/sensor coverage visualization — generates coverage polygons
for known radar installations and sensor systems.
"""
import uuid
import math
import json


def _offset_coords(lat: float, lng: float, bearing_deg: float, dist_km: float):
    R = 6371.0
    d = dist_km / R
    br = math.radians(bearing_deg)
    lat1 = math.radians(lat)
    lng1 = math.radians(lng)
    lat2 = math.asin(math.sin(lat1) * math.cos(d) +
                      math.cos(lat1) * math.sin(d) * math.cos(br))
    lng2 = lng1 + math.atan2(math.sin(br) * math.sin(d) * math.cos(lat1),
                              math.cos(d) - math.sin(lat1) * math.sin(lat2))
    return math.degrees(lat2), math.degrees(lng2)


def _generate_sector(lat: float, lng: float, radius_km: float,
                     start_bearing: float, end_bearing: float,
                     num_points: int = 32) -> list:
    """Generate a sector polygon (pie slice) from center."""
    coords = [[lng, lat]]  # center
    bearing_range = end_bearing - start_bearing
    if bearing_range < 0:
        bearing_range += 360
    for i in range(num_points + 1):
        b = start_bearing + (bearing_range * i / num_points)
        plat, plng = _offset_coords(lat, lng, b % 360, radius_km)
        coords.append([plng, plat])
    coords.append([lng, lat])  # close to center
    return coords


def _generate_circle(lat: float, lng: float, radius_km: float,
                     num_points: int = 48) -> list:
    """Generate a circle polygon."""
    coords = []
    for i in range(num_points + 1):
        angle = (i % num_points) * (360 / num_points)
        plat, plng = _offset_coords(lat, lng, angle, radius_km)
        coords.append([plng, plat])
    return coords


# Sample radar installations with known parameters
RADAR_INSTALLATIONS = [
    {
        "name": "Voronezh-M (Lekhtusi)",
        "type": "early_warning",
        "lat": 60.29, "lng": 30.54,
        "range_km": 6000, "sector_start": 270, "sector_end": 90,
        "country": "RU", "color": "#ef4444",
    },
    {
        "name": "AN/TPY-2 (Turkey)",
        "type": "missile_defense",
        "lat": 37.95, "lng": 40.21,
        "range_km": 1000, "sector_start": 30, "sector_end": 150,
        "country": "US", "color": "#3b82f6",
    },
    {
        "name": "Green Pine (Israel)",
        "type": "missile_defense",
        "lat": 30.98, "lng": 34.75,
        "range_km": 500, "sector_start": 0, "sector_end": 360,
        "country": "IL", "color": "#22c55e",
    },
    {
        "name": "THAAD (Guam)",
        "type": "missile_defense",
        "lat": 13.45, "lng": 144.79,
        "range_km": 200, "sector_start": 0, "sector_end": 360,
        "country": "US", "color": "#3b82f6",
    },
    {
        "name": "Aegis Ashore (Romania)",
        "type": "missile_defense",
        "lat": 43.92, "lng": 24.28,
        "range_km": 500, "sector_start": 0, "sector_end": 360,
        "country": "US", "color": "#3b82f6",
    },
    {
        "name": "S-400 Khmeimim",
        "type": "air_defense",
        "lat": 35.41, "lng": 35.95,
        "range_km": 400, "sector_start": 0, "sector_end": 360,
        "country": "RU", "color": "#ef4444",
    },
    {
        "name": "Patriot (South Korea)",
        "type": "air_defense",
        "lat": 36.96, "lng": 127.03,
        "range_km": 160, "sector_start": 0, "sector_end": 360,
        "country": "US", "color": "#3b82f6",
    },
    {
        "name": "Iron Dome (Tel Aviv)",
        "type": "point_defense",
        "lat": 32.06, "lng": 34.79,
        "range_km": 70, "sector_start": 0, "sector_end": 360,
        "country": "IL", "color": "#22c55e",
    },
]


def get_radar_coverage_geojson(radar_type: str | None = None) -> dict:
    """Generate GeoJSON for all radar/sensor coverage areas."""
    installations = RADAR_INSTALLATIONS
    if radar_type:
        installations = [r for r in installations if r["type"] == radar_type]

    features = []
    for r in installations:
        # Coverage polygon
        if r["sector_start"] == 0 and r["sector_end"] == 360:
            coords = _generate_circle(r["lat"], r["lng"], r["range_km"])
        else:
            coords = _generate_sector(r["lat"], r["lng"], r["range_km"],
                                      r["sector_start"], r["sector_end"])

        features.append({
            "type": "Feature",
            "geometry": {"type": "Polygon", "coordinates": [coords]},
            "properties": {
                "name": r["name"],
                "radar_type": r["type"],
                "range_km": r["range_km"],
                "country": r["country"],
                "color": r["color"],
                "type": "coverage",
            },
        })

        # Center point marker
        features.append({
            "type": "Feature",
            "geometry": {"type": "Point", "coordinates": [r["lng"], r["lat"]]},
            "properties": {
                "name": r["name"],
                "radar_type": r["type"],
                "range_km": r["range_km"],
                "country": r["country"],
                "color": r["color"],
                "type": "station",
            },
        })

    return {"type": "FeatureCollection", "features": features}


def list_radar_types() -> list[str]:
    return sorted(set(r["type"] for r in RADAR_INSTALLATIONS))
