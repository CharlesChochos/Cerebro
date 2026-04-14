"""
Unit tests for geospatial modules — measure, geofence, KML.
"""
import math
import json

import pytest


# ── Measurement Tests ──────────────────────────────────────────────────────


class TestHaversine:
    def test_zero_distance(self):
        from geo.measure import haversine_distance
        assert haversine_distance(0, 0, 0, 0) == 0.0

    def test_known_distance_london_paris(self):
        """London (51.5074, -0.1278) to Paris (48.8566, 2.3522) ≈ 343 km."""
        from geo.measure import haversine_distance
        d = haversine_distance(51.5074, -0.1278, 48.8566, 2.3522)
        assert 340 < d < 350

    def test_known_distance_nyc_la(self):
        """NYC (40.7128, -74.0060) to LA (34.0522, -118.2437) ≈ 3944 km."""
        from geo.measure import haversine_distance
        d = haversine_distance(40.7128, -74.0060, 34.0522, -118.2437)
        assert 3930 < d < 3960

    def test_symmetry(self):
        from geo.measure import haversine_distance
        d1 = haversine_distance(10, 20, 30, 40)
        d2 = haversine_distance(30, 40, 10, 20)
        assert abs(d1 - d2) < 0.001

    def test_antipodal(self):
        """Distance between antipodal points ≈ half circumference ≈ 20015 km."""
        from geo.measure import haversine_distance
        d = haversine_distance(0, 0, 0, 180)
        assert 20000 < d < 20100


class TestBearing:
    def test_due_north(self):
        from geo.measure import initial_bearing
        b = initial_bearing(0, 0, 10, 0)
        assert abs(b - 0) < 1  # ~0 degrees

    def test_due_east(self):
        from geo.measure import initial_bearing
        b = initial_bearing(0, 0, 0, 10)
        assert abs(b - 90) < 1

    def test_due_south(self):
        from geo.measure import initial_bearing
        b = initial_bearing(10, 0, 0, 0)
        assert abs(b - 180) < 1

    def test_due_west(self):
        from geo.measure import initial_bearing
        b = initial_bearing(0, 10, 0, 0)
        assert abs(b - 270) < 1


class TestPolyline:
    def test_two_points(self):
        from geo.measure import polyline_distance
        d = polyline_distance([[0, 0], [0, 1]])
        assert 110 < d < 115  # ~111 km per degree at equator

    def test_closed_triangle(self):
        from geo.measure import polyline_distance
        d = polyline_distance([[0, 0], [0, 1], [1, 0], [0, 0]])
        assert d > 0


class TestPolygonArea:
    def test_small_square(self):
        """1 degree × 1 degree square near equator ≈ 12,308 km²."""
        from geo.measure import polygon_area_km2
        area = polygon_area_km2([[0, 0], [0, 1], [1, 1], [1, 0]])
        assert 12000 < area < 13000

    def test_zero_area(self):
        from geo.measure import polygon_area_km2
        assert polygon_area_km2([[0, 0], [0, 0]]) == 0.0

    def test_triangle(self):
        from geo.measure import polygon_area_km2
        area = polygon_area_km2([[0, 0], [0, 1], [1, 0]])
        assert area > 0


class TestCircleGeneration:
    def test_circle_has_correct_points(self):
        from geo.measure import generate_circle_polygon
        coords = generate_circle_polygon(0, 0, 100, num_points=36)
        assert len(coords) == 37  # 36 + 1 (closed)

    def test_circle_closes(self):
        from geo.measure import generate_circle_polygon
        coords = generate_circle_polygon(45, 10, 50)
        # First and last should be very close
        assert abs(coords[0][0] - coords[-1][0]) < 0.001
        assert abs(coords[0][1] - coords[-1][1]) < 0.001

    def test_range_rings(self):
        from geo.measure import generate_range_rings
        rings = generate_range_rings(34.0, 35.0, [50, 100, 200])
        assert len(rings) == 3
        assert rings[0]["properties"]["range_km"] == 50
        assert rings[2]["properties"]["range_km"] == 200


class TestTrajectory:
    def test_ballistic_arc(self):
        from geo.measure import ballistic_trajectory_arc
        points = ballistic_trajectory_arc(34, 35, 50, 10, max_altitude_km=100, num_points=10)
        assert len(points) == 11
        # Start at ground level
        assert points[0]["altitude_km"] == 0
        # End at ground level
        assert points[-1]["altitude_km"] == 0
        # Peak in the middle
        peak = max(p["altitude_km"] for p in points)
        assert peak == 100  # max altitude at midpoint

    def test_cruise_trajectory(self):
        from geo.measure import cruise_missile_trajectory
        points = cruise_missile_trajectory(34, 35, 50, 10, num_points=20)
        assert len(points) == 21
        # Cruise altitude should be very low
        assert all(p["altitude_km"] <= 0.06 for p in points)


# ── Geofence Tests ─────────────────────────────────────────────────────────


class TestPointInPolygon:
    def test_inside_square(self):
        from detection.geofence import point_in_polygon
        # Square: [0,0] to [10,10] in [lng, lat] order
        polygon = [[0, 0], [10, 0], [10, 10], [0, 10], [0, 0]]
        assert point_in_polygon(5, 5, polygon) is True

    def test_outside_square(self):
        from detection.geofence import point_in_polygon
        polygon = [[0, 0], [10, 0], [10, 10], [0, 10], [0, 0]]
        assert point_in_polygon(15, 5, polygon) is False

    def test_on_edge(self):
        """Points exactly on edges may return True or False — implementation-dependent."""
        from detection.geofence import point_in_polygon
        polygon = [[0, 0], [10, 0], [10, 10], [0, 10], [0, 0]]
        # Just test it doesn't crash
        result = point_in_polygon(0, 5, polygon)
        assert isinstance(result, bool)

    def test_triangle(self):
        from detection.geofence import point_in_polygon
        polygon = [[0, 0], [10, 0], [5, 10], [0, 0]]
        assert point_in_polygon(3, 5, polygon) is True
        assert point_in_polygon(9, 9, polygon) is False

    def test_complex_polygon(self):
        from detection.geofence import point_in_polygon
        # L-shaped polygon
        polygon = [[0, 0], [5, 0], [5, 5], [10, 5], [10, 10], [0, 10], [0, 0]]
        assert point_in_polygon(2, 2, polygon) is True  # In the bottom-left
        assert point_in_polygon(7, 7, polygon) is True   # In the top-right


class TestBoundingBox:
    def test_compute_bbox(self):
        from detection.geofence import compute_bbox
        polygon = [[10, 20], [30, 40], [50, 60]]
        west, south, east, north = compute_bbox(polygon)
        assert west == 10
        assert south == 20
        assert east == 50
        assert north == 60

    def test_point_in_bbox(self):
        from detection.geofence import point_in_bbox
        assert point_in_bbox(5, 5, 0, 0, 10, 10) is True
        assert point_in_bbox(15, 5, 0, 0, 10, 10) is False


# ── KML Tests ──────────────────────────────────────────────────────────────


class TestKMLParsing:
    def test_parse_point_placemark(self):
        from geo.kml import parse_kml
        kml = """<?xml version="1.0" encoding="UTF-8"?>
        <kml xmlns="http://www.opengis.net/kml/2.2">
        <Document>
          <Placemark>
            <name>Test Point</name>
            <description>A test</description>
            <Point><coordinates>35.5,31.5,0</coordinates></Point>
          </Placemark>
        </Document>
        </kml>"""
        result = parse_kml(kml)
        assert len(result) == 1
        assert result[0]["name"] == "Test Point"
        assert result[0]["geometry_type"] == "Point"
        assert result[0]["coordinates"][0] == 35.5  # lng
        assert result[0]["coordinates"][1] == 31.5  # lat

    def test_parse_polygon_placemark(self):
        from geo.kml import parse_kml
        kml = """<?xml version="1.0" encoding="UTF-8"?>
        <kml xmlns="http://www.opengis.net/kml/2.2">
        <Document>
          <Placemark>
            <name>Test Polygon</name>
            <Polygon><outerBoundaryIs><LinearRing>
              <coordinates>0,0,0 10,0,0 10,10,0 0,10,0 0,0,0</coordinates>
            </LinearRing></outerBoundaryIs></Polygon>
          </Placemark>
        </Document>
        </kml>"""
        result = parse_kml(kml)
        assert len(result) == 1
        assert result[0]["geometry_type"] == "Polygon"
        assert len(result[0]["coordinates"]) == 5

    def test_parse_empty_kml(self):
        from geo.kml import parse_kml
        kml = """<?xml version="1.0"?><kml xmlns="http://www.opengis.net/kml/2.2"><Document></Document></kml>"""
        assert parse_kml(kml) == []

    def test_parse_invalid_xml(self):
        from geo.kml import parse_kml
        assert parse_kml("not xml") == []

    def test_coordinate_parsing(self):
        from geo.kml import parse_kml_coordinates
        coords = parse_kml_coordinates("10.5,20.3,100 30.1,40.2,0")
        assert len(coords) == 2
        assert coords[0] == [10.5, 20.3, 100.0]
        assert coords[1] == [30.1, 40.2, 0.0]


class TestKMLExport:
    def test_escape_xml(self):
        from geo.kml import _escape_xml
        assert _escape_xml("A & B") == "A &amp; B"
        assert _escape_xml("<tag>") == "&lt;tag&gt;"
        assert _escape_xml("") == ""

    def test_generate_kmz(self):
        from geo.kml import generate_kmz, parse_kmz
        kml = """<?xml version="1.0"?><kml xmlns="http://www.opengis.net/kml/2.2">
        <Document><Placemark><name>Test</name>
        <Point><coordinates>0,0,0</coordinates></Point></Placemark></Document></kml>"""

        kmz_bytes = generate_kmz(kml)
        assert len(kmz_bytes) > 0

        # Round-trip test
        placemarks = parse_kmz(kmz_bytes)
        assert len(placemarks) == 1
        assert placemarks[0]["name"] == "Test"
