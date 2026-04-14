"""
Phase 4 Tests — SIGINT connectors and dark pattern detection.
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from ingestion.aisstream import (
    classify_vessel_type,
    parse_position_report,
    parse_static_report,
    NAV_STATUS,
)
from ingestion.opensky import classify_flight_type
from detection.ais_gaps import get_region_for_position


class TestAISParsing:
    def test_classify_cargo(self):
        assert classify_vessel_type(70) == "cargo"
        assert classify_vessel_type(79) == "cargo"

    def test_classify_tanker(self):
        assert classify_vessel_type(80) == "tanker"
        assert classify_vessel_type(89) == "tanker"

    def test_classify_fishing(self):
        assert classify_vessel_type(30) == "fishing"

    def test_classify_passenger(self):
        assert classify_vessel_type(60) == "passenger"

    def test_classify_military_by_name(self):
        result = classify_vessel_type(0, mmsi="338123456", name="USS NIMITZ")
        assert result == "military"

    def test_classify_unknown(self):
        assert classify_vessel_type(0) == "other"

    def test_parse_position_report(self):
        msg = {
            "MessageType": "PositionReport",
            "MetaData": {
                "MMSI": 211000001,
                "ShipName": "HAMBURG EXPRESS",
                "ShipType": 70,
                "time_utc": "2026-04-09T12:00:00Z",
            },
            "Message": {
                "PositionReport": {
                    "Latitude": 53.55,
                    "Longitude": 9.99,
                    "Sog": 12.5,
                    "Cog": 180.0,
                    "TrueHeading": 179,
                    "NavigationalStatus": 0,
                }
            },
        }
        data = parse_position_report(msg)
        assert data is not None
        assert data["mmsi"] == "211000001"
        assert data["latitude"] == 53.55
        assert data["vessel_type"] == "cargo"
        assert data["nav_status"] == "under_way_engine"

    def test_parse_position_rejects_zero_coords(self):
        msg = {
            "MetaData": {"MMSI": 123456789, "time_utc": "2026-04-09T12:00:00Z"},
            "Message": {"PositionReport": {"Latitude": 0, "Longitude": 0, "Sog": 0, "Cog": 0}},
        }
        assert parse_position_report(msg) is None

    def test_parse_static_report(self):
        msg = {
            "MetaData": {"MMSI": 211000001},
            "Message": {
                "ShipStaticData": {
                    "Name": "HAMBURG EXPRESS",
                    "ImoNumber": 9501332,
                    "CallSign": "DABC",
                    "Destination": "ROTTERDAM",
                    "Type": 70,
                    "Dimension": {"A": 200, "B": 100, "C": 20, "D": 20},
                    "MaximumStaticDraught": 14.5,
                }
            },
        }
        data = parse_static_report(msg)
        assert data is not None
        assert data["name"] == "HAMBURG EXPRESS"
        assert data["imo"] == "9501332"
        assert data["length"] == 300  # A + B
        assert data["width"] == 40   # C + D
        assert data["draught"] == 14.5


class TestFlightClassification:
    def test_civilian(self):
        assert classify_flight_type("DLH123") == "civilian"

    def test_military_reach(self):
        assert classify_flight_type("REACH01") == "military"

    def test_military_rch(self):
        assert classify_flight_type("RCH1234") == "military"

    def test_military_nato(self):
        assert classify_flight_type("NATO01") == "military"

    def test_cargo_fedex(self):
        assert classify_flight_type("FDX892") == "cargo"

    def test_cargo_ups(self):
        assert classify_flight_type("UPS456") == "cargo"

    def test_unknown_empty(self):
        assert classify_flight_type("") == "unknown"


class TestDarkPatternDetection:
    def test_strait_of_hormuz(self):
        region, boost = get_region_for_position(26.5, 56.0)
        assert region == "Strait of Hormuz"
        assert boost == 30

    def test_south_china_sea(self):
        region, boost = get_region_for_position(15.0, 115.0)
        assert region == "South China Sea"
        assert boost > 0

    def test_black_sea(self):
        region, boost = get_region_for_position(43.0, 35.0)
        assert region == "Black Sea"
        assert boost == 25

    def test_open_ocean_no_region(self):
        # Mid-Atlantic, far from any sensitive region
        region, boost = get_region_for_position(-30.0, -20.0)
        assert region is None
        assert boost == 0

    def test_none_coords(self):
        region, boost = get_region_for_position(None, None)
        assert region is None
        assert boost == 0
