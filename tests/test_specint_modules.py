"""
Unit tests for SPECINT modules:
- WHO disease severity estimation
- ProMED disease extraction
- VIIRS fire record parsing
- Nightlight anomaly detection logic
- NOAA severity mapping
"""
import pytest


class TestWHO:
    def test_severity_ebola(self):
        from ingestion.who import estimate_severity
        assert estimate_severity("Ebola outbreak in Congo", "") >= 85

    def test_severity_dengue(self):
        from ingestion.who import estimate_severity
        assert estimate_severity("Dengue fever alert", "") >= 50

    def test_severity_unknown(self):
        from ingestion.who import estimate_severity
        assert estimate_severity("Unknown illness cluster", "") == 50

    def test_extract_disease_ebola(self):
        from ingestion.who import extract_disease
        assert extract_disease("Ebola virus disease - Democratic Republic of Congo").lower() == "ebola"

    def test_extract_disease_avian(self):
        from ingestion.who import extract_disease
        assert "avian" in extract_disease("Avian influenza A(H5N1) - Cambodia").lower()

    def test_extract_disease_dash_fallback(self):
        from ingestion.who import extract_disease
        result = extract_disease("Mystery illness - Brazil")
        assert result == "Mystery illness"


class TestProMED:
    def test_severity_nipah(self):
        from ingestion.promed import estimate_severity
        assert estimate_severity("Nipah virus - India: (Kerala)", "") >= 80

    def test_extract_disease_cholera(self):
        from ingestion.promed import extract_disease
        assert extract_disease("Cholera - Mozambique: update").lower() == "cholera"

    def test_extract_undiagnosed(self):
        from ingestion.promed import extract_disease
        result = extract_disease("Undiagnosed illness - China: (Hubei)")
        assert "undiagnosed" in result.lower()


class TestVIIRS:
    def test_parse_fire_record_valid(self):
        from ingestion.viirs import parse_fire_record
        row = {
            "latitude": "34.052", "longitude": "-118.243",
            "bright_ti4": "330.5", "bright_ti5": "290.1",
            "frp": "12.5", "confidence": "high",
            "daynight": "D", "acq_date": "2025-01-15", "acq_time": "1430",
            "satellite": "NOAA-20",
        }
        result = parse_fire_record(row)
        assert result is not None
        assert result["lat"] == pytest.approx(34.052)
        assert result["lng"] == pytest.approx(-118.243)
        assert result["confidence"] == "high"
        assert "2025-01-15T14:30" in result["capture_date"]

    def test_parse_fire_record_zero_coords(self):
        from ingestion.viirs import parse_fire_record
        row = {"latitude": "0", "longitude": "0", "acq_date": "2025-01-15"}
        assert parse_fire_record(row) is None

    def test_parse_fire_record_missing_fields(self):
        from ingestion.viirs import parse_fire_record
        row = {"latitude": "10", "longitude": "20", "acq_date": "2025-01-15", "acq_time": "0800"}
        result = parse_fire_record(row)
        assert result is not None
        assert result["lat"] == 10.0


class TestNightlights:
    def test_compute_change_positive(self):
        from detection.nightlights import compute_change
        assert compute_change(130, 100) == pytest.approx(30.0)

    def test_compute_change_negative(self):
        from detection.nightlights import compute_change
        assert compute_change(60, 100) == pytest.approx(-40.0)

    def test_compute_change_zero_baseline(self):
        from detection.nightlights import compute_change
        assert compute_change(50, 0) == 0.0

    def test_severity_large_drop(self):
        from detection.nightlights import severity_from_change
        assert severity_from_change(-50) >= 85

    def test_severity_moderate_drop(self):
        from detection.nightlights import severity_from_change
        assert severity_from_change(-25) >= 50

    def test_severity_small_change(self):
        from detection.nightlights import severity_from_change
        assert severity_from_change(-5) <= 30

    def test_classify_critical_decline(self):
        from detection.nightlights import classify_change
        assert classify_change(-45) == "critical_decline"

    def test_classify_significant_decline(self):
        from detection.nightlights import classify_change
        assert classify_change(-25) == "significant_decline"

    def test_classify_significant_surge(self):
        from detection.nightlights import classify_change
        assert classify_change(35) == "significant_surge"

    def test_classify_normal(self):
        from detection.nightlights import classify_change
        assert classify_change(-5) == "normal"

    def test_classify_normal_positive(self):
        from detection.nightlights import classify_change
        assert classify_change(15) == "normal"


class TestNOAA:
    def test_severity_map(self):
        from ingestion.noaa import SEVERITY_MAP
        assert SEVERITY_MAP["Extreme"] >= 90
        assert SEVERITY_MAP["Severe"] >= 75
        assert SEVERITY_MAP["Minor"] <= 35

    def test_extract_coords_point(self):
        from ingestion.noaa import extract_coords
        feature = {"geometry": {"type": "Point", "coordinates": [-95.5, 35.2]}}
        lat, lng = extract_coords(feature)
        assert lat == pytest.approx(35.2)
        assert lng == pytest.approx(-95.5)

    def test_extract_coords_polygon(self):
        from ingestion.noaa import extract_coords
        feature = {
            "geometry": {
                "type": "Polygon",
                "coordinates": [[[-96, 34], [-94, 34], [-94, 36], [-96, 36], [-96, 34]]],
            }
        }
        lat, lng = extract_coords(feature)
        assert lat == pytest.approx(35.0, abs=0.5)
        assert lng == pytest.approx(-95.0, abs=0.5)

    def test_extract_coords_none_geometry(self):
        from ingestion.noaa import extract_coords
        lat, lng = extract_coords({"geometry": None})
        assert lat is None
        assert lng is None
