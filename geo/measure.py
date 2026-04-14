"""
Geospatial measurement tools — distance, area, bearing, elevation profiles.

Pure-Python implementations of Turf.js equivalents:
- Haversine distance (great-circle)
- Shoelace polygon area (with equirectangular projection)
- Initial bearing between two points
- Range ring generation (circle polygon from center + radius)
- Ballistic trajectory arc approximation
"""
import math
import json
import uuid

EARTH_RADIUS_KM = 6371.0


def haversine_distance(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    """
    Haversine great-circle distance between two points in kilometers.
    """
    lat1_r, lat2_r = math.radians(lat1), math.radians(lat2)
    dlat = math.radians(lat2 - lat1)
    dlng = math.radians(lng2 - lng1)

    a = math.sin(dlat / 2) ** 2 + math.cos(lat1_r) * math.cos(lat2_r) * math.sin(dlng / 2) ** 2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return EARTH_RADIUS_KM * c


def initial_bearing(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    """
    Initial bearing (forward azimuth) from point 1 to point 2 in degrees.
    Returns value in [0, 360).
    """
    lat1_r, lat2_r = math.radians(lat1), math.radians(lat2)
    dlng = math.radians(lng2 - lng1)

    x = math.sin(dlng) * math.cos(lat2_r)
    y = math.cos(lat1_r) * math.sin(lat2_r) - math.sin(lat1_r) * math.cos(lat2_r) * math.cos(dlng)

    bearing = math.degrees(math.atan2(x, y))
    return (bearing + 360) % 360


def polyline_distance(points: list[list[float]]) -> float:
    """
    Total distance along a polyline in kilometers.
    points: list of [lat, lng] pairs.
    """
    total = 0.0
    for i in range(len(points) - 1):
        total += haversine_distance(points[i][0], points[i][1], points[i + 1][0], points[i + 1][1])
    return total


def polygon_area_km2(points: list[list[float]]) -> float:
    """
    Approximate area of a polygon in square kilometers.
    Uses equirectangular projection with shoelace formula.
    points: list of [lat, lng] pairs (or [lng, lat] GeoJSON order — auto-detected).
    """
    if len(points) < 3:
        return 0.0

    # Close polygon if not closed
    pts = list(points)
    if pts[0] != pts[-1]:
        pts.append(pts[0])

    # Detect if GeoJSON order (lng, lat) vs (lat, lng)
    # Heuristic: if first coord > 90, it's likely longitude-first
    if abs(pts[0][0]) > 90:
        # GeoJSON order: [lng, lat] → swap to [lat, lng]
        pts = [[p[1], p[0]] for p in pts]

    # Convert to projected coordinates (equirectangular)
    avg_lat = sum(p[0] for p in pts) / len(pts)
    cos_lat = math.cos(math.radians(avg_lat))

    # Project to km
    projected = []
    for p in pts:
        x = math.radians(p[1]) * EARTH_RADIUS_KM * cos_lat
        y = math.radians(p[0]) * EARTH_RADIUS_KM
        projected.append((x, y))

    # Shoelace formula
    area = 0.0
    n = len(projected)
    for i in range(n - 1):
        area += projected[i][0] * projected[i + 1][1]
        area -= projected[i + 1][0] * projected[i][1]

    return abs(area) / 2.0


def generate_circle_polygon(center_lat: float, center_lng: float, radius_km: float, num_points: int = 64) -> list[list[float]]:
    """
    Generate a circle polygon (approximation) for range ring visualization.
    Returns list of [lng, lat] pairs (GeoJSON order).
    """
    coords = []
    for i in range(num_points + 1):
        angle = 2 * math.pi * i / num_points
        # Destination point given bearing and distance
        bearing_rad = angle
        lat1_r = math.radians(center_lat)
        lng1_r = math.radians(center_lng)

        angular_dist = radius_km / EARTH_RADIUS_KM

        lat2 = math.asin(
            math.sin(lat1_r) * math.cos(angular_dist) +
            math.cos(lat1_r) * math.sin(angular_dist) * math.cos(bearing_rad)
        )
        lng2 = lng1_r + math.atan2(
            math.sin(bearing_rad) * math.sin(angular_dist) * math.cos(lat1_r),
            math.cos(angular_dist) - math.sin(lat1_r) * math.sin(lat2)
        )

        coords.append([math.degrees(lng2), math.degrees(lat2)])

    return coords


def generate_range_rings(center_lat: float, center_lng: float, ranges_km: list[float]) -> list[dict]:
    """
    Generate multiple range ring polygons for weapons system visualization.
    Returns GeoJSON features for each ring.
    """
    features = []
    for r in sorted(ranges_km):
        coords = generate_circle_polygon(center_lat, center_lng, r)
        features.append({
            "type": "Feature",
            "geometry": {
                "type": "Polygon",
                "coordinates": [coords],
            },
            "properties": {
                "range_km": r,
                "center": [center_lng, center_lat],
            },
        })
    return features


def ballistic_trajectory_arc(
    launch_lat: float, launch_lng: float,
    target_lat: float, target_lng: float,
    max_altitude_km: float = 100,
    num_points: int = 50,
) -> list[dict]:
    """
    Generate a simplified ballistic trajectory arc between launch and target.
    Uses parabolic arc approximation for altitude profile.
    Returns list of {lat, lng, altitude_km, t} points.
    """
    points = []
    for i in range(num_points + 1):
        t = i / num_points  # 0.0 to 1.0

        # Linear interpolation for lat/lng
        lat = launch_lat + (target_lat - launch_lat) * t
        lng = launch_lng + (target_lng - launch_lng) * t

        # Parabolic altitude: peaks at t=0.5
        altitude = max_altitude_km * 4 * t * (1 - t)

        points.append({
            "lat": round(lat, 6),
            "lng": round(lng, 6),
            "altitude_km": round(altitude, 2),
            "t": round(t, 3),
        })

    return points


def cruise_missile_trajectory(
    launch_lat: float, launch_lng: float,
    target_lat: float, target_lng: float,
    cruise_altitude_km: float = 0.05,
    num_points: int = 50,
) -> list[dict]:
    """
    Generate a cruise missile trajectory (low-altitude, terrain-following).
    Returns list of {lat, lng, altitude_km, t} points.
    """
    points = []
    for i in range(num_points + 1):
        t = i / num_points

        lat = launch_lat + (target_lat - launch_lat) * t
        lng = launch_lng + (target_lng - launch_lng) * t

        # Cruise profile: climb, cruise, terminal dive
        if t < 0.1:
            altitude = cruise_altitude_km * (t / 0.1)
        elif t > 0.95:
            altitude = cruise_altitude_km * (1 - t) / 0.05
        else:
            altitude = cruise_altitude_km

        points.append({
            "lat": round(lat, 6),
            "lng": round(lng, 6),
            "altitude_km": round(altitude, 4),
            "t": round(t, 3),
        })

    return points


def save_measurement(conn, name: str, profile_type: str, points: list[list[float]]) -> dict:
    """Save a measurement profile to the database."""
    mid = str(uuid.uuid4())

    total_distance = polyline_distance(points) if len(points) >= 2 else 0
    total_area = polygon_area_km2(points) if profile_type == "area" and len(points) >= 3 else None

    conn.execute(
        """INSERT INTO measurement_profiles
           (id, name, profile_type, points_json, total_distance_km, total_area_km2)
           VALUES (?, ?, ?, ?, ?, ?)""",
        (mid, name, profile_type, json.dumps(points), total_distance, total_area),
    )
    conn.commit()

    return {
        "measurement_id": mid,
        "profile_type": profile_type,
        "total_distance_km": round(total_distance, 3),
        "total_area_km2": round(total_area, 3) if total_area else None,
    }
