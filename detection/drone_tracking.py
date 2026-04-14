"""
Drone/UAV activity visualization — generates drone patrol markers
with patrol radius circles and activity status indicators.
"""
import uuid
import math


def _generate_circle(lat: float, lng: float, radius_km: float,
                     num_points: int = 48) -> list:
    R = 6371.0
    coords = []
    for i in range(num_points + 1):
        angle = math.radians((i % num_points) * (360 / num_points))
        d = radius_km / R
        lat1 = math.radians(lat)
        lng1 = math.radians(lng)
        lat2 = math.asin(math.sin(lat1) * math.cos(d) +
                          math.cos(lat1) * math.sin(d) * math.cos(angle))
        lng2 = lng1 + math.atan2(math.sin(angle) * math.sin(d) * math.cos(lat1),
                                  math.cos(d) - math.sin(lat1) * math.sin(lat2))
        coords.append([math.degrees(lng2), math.degrees(lat2)])
    return coords


# Known drone activity zones (sample data)
DRONE_ZONES = [
    {
        "name": "MQ-9 Reaper Patrol",
        "drone_type": "MQ-9 Reaper",
        "category": "reconnaissance",
        "lat": 33.5, "lng": 44.4,
        "patrol_radius_km": 150,
        "altitude_m": 15000,
        "status": "active",
        "operator": "USAF",
        "color": "#3b82f6",
    },
    {
        "name": "Bayraktar TB2 Zone",
        "drone_type": "Bayraktar TB2",
        "category": "combat",
        "lat": 48.5, "lng": 37.0,
        "patrol_radius_km": 80,
        "altitude_m": 7000,
        "status": "active",
        "operator": "Ukraine",
        "color": "#eab308",
    },
    {
        "name": "Shahed-136 Swarm Zone",
        "drone_type": "Shahed-136",
        "category": "attack",
        "lat": 50.4, "lng": 30.5,
        "patrol_radius_km": 50,
        "altitude_m": 1000,
        "status": "detected",
        "operator": "Iran/Russia",
        "color": "#ef4444",
    },
    {
        "name": "Heron TP Surveillance",
        "drone_type": "Heron TP",
        "category": "reconnaissance",
        "lat": 31.5, "lng": 34.8,
        "patrol_radius_km": 120,
        "altitude_m": 14000,
        "status": "active",
        "operator": "IAF",
        "color": "#22c55e",
    },
    {
        "name": "Wing Loong II Patrol",
        "drone_type": "Wing Loong II",
        "category": "multi_role",
        "lat": 24.5, "lng": 54.6,
        "patrol_radius_km": 100,
        "altitude_m": 9000,
        "status": "active",
        "operator": "UAE",
        "color": "#a78bfa",
    },
    {
        "name": "RQ-4 Global Hawk ELINT",
        "drone_type": "RQ-4 Global Hawk",
        "category": "elint",
        "lat": 36.0, "lng": 127.5,
        "patrol_radius_km": 200,
        "altitude_m": 18000,
        "status": "active",
        "operator": "USAF",
        "color": "#3b82f6",
    },
    {
        "name": "CH-5 Rainbow Patrol",
        "drone_type": "CH-5 Rainbow",
        "category": "combat",
        "lat": 15.5, "lng": 44.0,
        "patrol_radius_km": 90,
        "altitude_m": 8000,
        "status": "active",
        "operator": "PLAAF",
        "color": "#f97316",
    },
]

CATEGORY_COLORS = {
    "reconnaissance": "#3b82f6",
    "combat": "#ef4444",
    "attack": "#ef4444",
    "multi_role": "#a78bfa",
    "elint": "#22c55e",
}


def get_drone_activity_geojson(category: str | None = None,
                                status: str | None = None) -> dict:
    """Generate GeoJSON for drone activity zones."""
    zones = DRONE_ZONES
    if category:
        zones = [z for z in zones if z["category"] == category]
    if status:
        zones = [z for z in zones if z["status"] == status]

    features = []
    for z in zones:
        # Patrol radius circle
        coords = _generate_circle(z["lat"], z["lng"], z["patrol_radius_km"])
        features.append({
            "type": "Feature",
            "geometry": {"type": "Polygon", "coordinates": [coords]},
            "properties": {
                "name": z["name"],
                "drone_type": z["drone_type"],
                "category": z["category"],
                "patrol_radius_km": z["patrol_radius_km"],
                "status": z["status"],
                "operator": z["operator"],
                "color": z["color"],
                "type": "patrol_radius",
            },
        })

        # Diamond center marker (represented as a rotated square polygon)
        size_km = 5  # marker size in km
        diamond_coords = [
            _offset_point(z["lat"], z["lng"], 0, size_km),     # top
            _offset_point(z["lat"], z["lng"], 90, size_km),    # right
            _offset_point(z["lat"], z["lng"], 180, size_km),   # bottom
            _offset_point(z["lat"], z["lng"], 270, size_km),   # left
        ]
        diamond_coords.append(diamond_coords[0])  # close polygon

        features.append({
            "type": "Feature",
            "geometry": {"type": "Polygon", "coordinates": [diamond_coords]},
            "properties": {
                "name": z["name"],
                "drone_type": z["drone_type"],
                "category": z["category"],
                "altitude_m": z["altitude_m"],
                "status": z["status"],
                "operator": z["operator"],
                "color": z["color"],
                "type": "drone_marker",
            },
        })

        # Center point for label
        features.append({
            "type": "Feature",
            "geometry": {"type": "Point", "coordinates": [z["lng"], z["lat"]]},
            "properties": {
                "name": z["name"],
                "drone_type": z["drone_type"],
                "category": z["category"],
                "status": z["status"],
                "operator": z["operator"],
                "color": z["color"],
                "type": "drone_label",
            },
        })

    return {"type": "FeatureCollection", "features": features}


def _offset_point(lat, lng, bearing, dist_km):
    R = 6371.0
    d = dist_km / R
    br = math.radians(bearing)
    lat1 = math.radians(lat)
    lng1 = math.radians(lng)
    lat2 = math.asin(math.sin(lat1) * math.cos(d) +
                      math.cos(lat1) * math.sin(d) * math.cos(br))
    lng2 = lng1 + math.atan2(math.sin(br) * math.sin(d) * math.cos(lat1),
                              math.cos(d) - math.sin(lat1) * math.sin(lat2))
    return [math.degrees(lng2), math.degrees(lat2)]


def list_drone_categories() -> list[str]:
    return sorted(set(z["category"] for z in DRONE_ZONES))


def list_drone_operators() -> list[str]:
    return sorted(set(z["operator"] for z in DRONE_ZONES))
