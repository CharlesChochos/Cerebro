"""
Module-level tests — Phase 13: webcam feeds, trade flows, conflict frontlines,
map annotations, street imagery, animation export.
"""
import os
import sys
import json
import tempfile

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from db.connection import get_connection
from db.migrate import run_migrations


@pytest.fixture(scope="module")
def conn():
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    os.environ["CEREBRO_DB_PATH"] = path
    c = get_connection()
    run_migrations(c)
    yield c
    os.unlink(path)


# ─── Webcam Feeds ──────────────────────────────────────────

from detection.webcam_feeds import (
    seed_webcams, add_webcam, get_webcam, list_webcams,
    find_webcams_near, get_webcam_geojson,
)


class TestWebcamFeeds:
    _wid = None

    def test_seed_webcams(self, conn):
        count = seed_webcams(conn)
        cams = list_webcams(conn, limit=200)
        assert len(cams) >= 10

    def test_seed_idempotent(self, conn):
        seed_webcams(conn)
        cams = list_webcams(conn, limit=200)
        assert len(cams) >= 10

    def test_add_webcam(self, conn):
        wid = add_webcam(conn, "Test Cam", 40.7, -74.0,
                         country_code="US", category="traffic",
                         stream_url="https://example.com/stream")
        assert wid
        TestWebcamFeeds._wid = wid

    def test_get_webcam(self, conn):
        item = get_webcam(conn, self._wid)
        assert item is not None
        assert item["title"] == "Test Cam"
        assert item["category"] == "traffic"

    def test_list_webcams(self, conn):
        items = list_webcams(conn)
        assert len(items) >= 11

    def test_list_by_category(self, conn):
        items = list_webcams(conn, category="port")
        assert len(items) >= 1

    def test_list_by_country(self, conn):
        items = list_webcams(conn, country_code="TR")
        assert len(items) >= 1

    def test_find_near(self, conn):
        items = find_webcams_near(conn, 41.0, 29.0, radius_deg=1.0)
        assert len(items) >= 1

    def test_find_near_no_results(self, conn):
        items = find_webcams_near(conn, -60.0, -60.0, radius_deg=0.5)
        assert len(items) == 0

    def test_geojson(self, conn):
        geo = get_webcam_geojson(conn)
        assert geo["type"] == "FeatureCollection"
        assert len(geo["features"]) >= 10
        assert geo["features"][0]["geometry"]["type"] == "Point"

    def test_get_nonexistent(self, conn):
        item = get_webcam(conn, "nonexistent")
        assert item is None


# ─── Trade Flows ───────────────────────────────────────────

from detection.trade_flows import (
    seed_trade_flows, add_trade_flow, get_trade_flow,
    list_trade_flows, get_trade_flow_arcs,
)


class TestTradeFlows:
    _tid = None

    def test_seed_flows(self, conn):
        seed_trade_flows(conn)
        flows = list_trade_flows(conn, limit=200)
        assert len(flows) >= 10

    def test_add_trade_flow(self, conn):
        tid = add_trade_flow(conn, "JP", "US", commodity="automobiles",
                             volume_usd=50e9, flow_type="trade",
                             year=2025, origin_lat=35.7, origin_lng=139.7,
                             dest_lat=40.7, dest_lng=-74.0)
        assert tid
        TestTradeFlows._tid = tid

    def test_get_trade_flow(self, conn):
        item = get_trade_flow(conn, self._tid)
        assert item is not None
        assert item["origin_country"] == "JP"
        assert item["commodity"] == "automobiles"

    def test_list_by_origin(self, conn):
        items = list_trade_flows(conn, origin_country="CN")
        assert len(items) >= 1

    def test_list_by_type(self, conn):
        items = list_trade_flows(conn, flow_type="arms")
        assert len(items) >= 1

    def test_list_by_commodity(self, conn):
        items = list_trade_flows(conn, commodity="crude_oil")
        assert len(items) >= 1

    def test_arcs(self, conn):
        arcs = get_trade_flow_arcs(conn)
        assert arcs["total"] >= 10
        assert len(arcs["flows"]) >= 10
        arc = arcs["flows"][0]
        assert "origin" in arc
        assert "destination" in arc
        assert "color" in arc
        assert "width" in arc

    def test_arcs_filtered(self, conn):
        arcs = get_trade_flow_arcs(conn, flow_type="energy")
        assert arcs["total"] >= 1
        for a in arcs["flows"]:
            assert a["flow_type"] == "energy"

    def test_get_nonexistent(self, conn):
        item = get_trade_flow(conn, "nonexistent")
        assert item is None


# ─── Conflict Frontlines ──────────────────────────────────

from detection.conflict_frontlines import (
    add_frontline, get_frontline, list_frontlines,
    get_frontline_animation, get_frontlines_geojson,
)


class TestConflictFrontlines:
    _fid = None

    def test_add_frontline(self, conn):
        geometry = {
            "type": "LineString",
            "coordinates": [[36.0, 49.0], [37.0, 48.5], [38.0, 48.0]]
        }
        fid = add_frontline(conn, "Ukraine-Russia", "2025-06-15",
                            geometry, country_code="UA",
                            side_a="Ukraine", side_b="Russia",
                            status="active", source="osint")
        assert fid
        TestConflictFrontlines._fid = fid

    def test_get_frontline(self, conn):
        item = get_frontline(conn, self._fid)
        assert item is not None
        assert item["conflict_name"] == "Ukraine-Russia"
        assert item["geometry"]["type"] == "LineString"
        assert len(item["geometry"]["coordinates"]) == 3

    def test_add_multiple_dates(self, conn):
        """Add frontlines at different dates for animation."""
        for i in range(5):
            geo = {
                "type": "LineString",
                "coordinates": [[36.0 + i * 0.1, 49.0], [37.0 + i * 0.1, 48.5]]
            }
            add_frontline(conn, "Ukraine-Russia", f"2025-06-{16 + i:02d}",
                          geo, country_code="UA",
                          side_a="Ukraine", side_b="Russia")

    def test_list_frontlines(self, conn):
        items = list_frontlines(conn, conflict_name="Ukraine-Russia")
        assert len(items) >= 6

    def test_list_by_status(self, conn):
        items = list_frontlines(conn, status="active")
        assert len(items) >= 1

    def test_animation(self, conn):
        anim = get_frontline_animation(conn, "Ukraine-Russia")
        assert anim["conflict_name"] == "Ukraine-Russia"
        assert anim["frame_count"] >= 6
        assert len(anim["frames"]) >= 6
        # Frames should be chronologically ordered
        dates = [f["date"] for f in anim["frames"]]
        assert dates == sorted(dates)

    def test_geojson(self, conn):
        geo = get_frontlines_geojson(conn)
        assert geo["type"] == "FeatureCollection"
        assert len(geo["features"]) >= 1

    def test_geojson_by_conflict(self, conn):
        geo = get_frontlines_geojson(conn, conflict_name="Ukraine-Russia")
        assert len(geo["features"]) >= 1
        for f in geo["features"]:
            assert f["properties"]["conflict_name"] == "Ukraine-Russia"

    def test_get_nonexistent(self, conn):
        item = get_frontline(conn, "nonexistent")
        assert item is None


# ─── Map Annotations ──────────────────────────────────────

from detection.map_annotations import (
    create_annotation, get_annotation, list_annotations,
    update_annotation, delete_annotation,
    get_annotations_geojson, list_layers,
)


class TestMapAnnotations:
    _aid = None

    def test_create_marker(self, conn):
        geo = {"type": "Point", "coordinates": [44.0, 33.0]}
        aid = create_annotation(conn, "marker", geo,
                                properties_json={"color": "#ef4444", "icon": "alert"},
                                title="Baghdad Checkpoint",
                                description="Military checkpoint observed",
                                created_by="analyst1", layer_name="ops")
        assert aid
        TestMapAnnotations._aid = aid

    def test_create_polygon(self, conn):
        geo = {
            "type": "Polygon",
            "coordinates": [[[44.0, 33.0], [44.5, 33.0], [44.5, 33.5], [44.0, 33.5], [44.0, 33.0]]]
        }
        aid = create_annotation(conn, "polygon", geo,
                                properties_json={"fill": "#3b82f6", "fill_opacity": 0.3},
                                title="Control Zone Alpha",
                                layer_name="ops")
        assert aid

    def test_create_freehand(self, conn):
        geo = {
            "type": "LineString",
            "coordinates": [[44.0, 33.0], [44.1, 33.1], [44.2, 33.15], [44.3, 33.1]]
        }
        aid = create_annotation(conn, "freehand", geo,
                                title="Supply route sketch",
                                layer_name="intel")
        assert aid

    def test_get_annotation(self, conn):
        item = get_annotation(conn, self._aid)
        assert item is not None
        assert item["annotation_type"] == "marker"
        assert item["title"] == "Baghdad Checkpoint"
        assert item["geometry"]["type"] == "Point"
        assert item["properties"]["color"] == "#ef4444"

    def test_list_annotations(self, conn):
        items = list_annotations(conn)
        assert len(items) >= 3

    def test_list_by_layer(self, conn):
        items = list_annotations(conn, layer_name="ops")
        assert len(items) >= 2

    def test_list_by_type(self, conn):
        items = list_annotations(conn, annotation_type="marker")
        assert len(items) >= 1

    def test_update_annotation(self, conn):
        ok = update_annotation(conn, self._aid,
                               title="Updated Checkpoint",
                               description="Checkpoint removed")
        assert ok
        item = get_annotation(conn, self._aid)
        assert item["title"] == "Updated Checkpoint"

    def test_update_visibility(self, conn):
        ok = update_annotation(conn, self._aid, visible=False)
        assert ok
        # Should not appear in default list
        items = list_annotations(conn, layer_name="ops")
        ids = [a["id"] for a in items]
        assert self._aid not in ids

        # Restore
        update_annotation(conn, self._aid, visible=True)

    def test_geojson(self, conn):
        geo = get_annotations_geojson(conn)
        assert geo["type"] == "FeatureCollection"
        assert len(geo["features"]) >= 3

    def test_geojson_by_layer(self, conn):
        geo = get_annotations_geojson(conn, layer_name="ops")
        for f in geo["features"]:
            assert f["properties"]["layer_name"] == "ops"

    def test_list_layers(self, conn):
        layers = list_layers(conn)
        assert len(layers) >= 2
        names = [l["layer_name"] for l in layers]
        assert "ops" in names
        assert "intel" in names

    def test_delete_annotation(self, conn):
        geo = {"type": "Point", "coordinates": [0, 0]}
        aid = create_annotation(conn, "marker", geo, title="To Delete")
        ok = delete_annotation(conn, aid)
        assert ok
        assert get_annotation(conn, aid) is None

    def test_delete_nonexistent(self, conn):
        ok = delete_annotation(conn, "nonexistent")
        assert not ok

    def test_get_nonexistent(self, conn):
        item = get_annotation(conn, "nonexistent")
        assert item is None


# ─── Street Imagery ────────────────────────────────────────

from detection.street_imagery import (
    store_image, get_image, list_images,
    find_images_near, get_imagery_geojson,
)


class TestStreetImagery:
    _sid = None

    def test_store_image(self, conn):
        sid = store_image(conn, "mapillary_12345", 33.34, 44.39,
                          compass_angle=180.5, captured_at="2025-03-15T10:30:00Z",
                          sequence_id="seq_001",
                          thumbnail_url="https://mapillary.com/thumb/12345",
                          full_url="https://mapillary.com/full/12345")
        assert sid
        TestStreetImagery._sid = sid

    def test_get_image(self, conn):
        item = get_image(conn, self._sid)
        assert item is not None
        assert item["image_id"] == "mapillary_12345"
        assert item["compass_angle"] == 180.5
        assert item["provider"] == "mapillary"

    def test_store_multiple(self, conn):
        for i in range(5):
            store_image(conn, f"mapillary_{20000 + i}",
                        33.34 + i * 0.001, 44.39 + i * 0.001,
                        captured_at=f"2025-03-15T{10 + i}:00:00Z")

    def test_list_images(self, conn):
        items = list_images(conn)
        assert len(items) >= 6

    def test_find_near(self, conn):
        items = find_images_near(conn, 33.34, 44.39, radius_deg=0.01)
        assert len(items) >= 1

    def test_find_near_no_results(self, conn):
        items = find_images_near(conn, -50.0, -70.0, radius_deg=0.01)
        assert len(items) == 0

    def test_geojson(self, conn):
        geo = get_imagery_geojson(conn, lat=33.34, lng=44.39, radius_deg=0.1)
        assert geo["type"] == "FeatureCollection"
        assert len(geo["features"]) >= 1

    def test_get_nonexistent(self, conn):
        item = get_image(conn, "nonexistent")
        assert item is None


# ─── Animation Export ──────────────────────────────────────

from detection.animation_export import (
    create_export_job, get_export_job, list_export_jobs,
    update_export_status,
)


class TestAnimationExport:
    _eid = None

    def test_create_job(self, conn):
        eid = create_export_job(conn, "gif",
                                parameters={"center": [44, 33], "zoom": 5,
                                            "fps": 10, "duration": 10},
                                duration_secs=10.0, frame_count=100)
        assert eid
        TestAnimationExport._eid = eid

    def test_get_job(self, conn):
        item = get_export_job(conn, self._eid)
        assert item is not None
        assert item["export_type"] == "gif"
        assert item["status"] == "pending"
        assert item["parameters"]["fps"] == 10

    def test_list_jobs(self, conn):
        items = list_export_jobs(conn)
        assert len(items) >= 1

    def test_list_by_status(self, conn):
        items = list_export_jobs(conn, status="pending")
        assert len(items) >= 1

    def test_update_rendering(self, conn):
        ok = update_export_status(conn, self._eid, "rendering")
        assert ok
        item = get_export_job(conn, self._eid)
        assert item["status"] == "rendering"

    def test_update_completed(self, conn):
        ok = update_export_status(conn, self._eid, "completed",
                                  output_path="/exports/anim_001.gif",
                                  file_size=2500000)
        assert ok
        item = get_export_job(conn, self._eid)
        assert item["status"] == "completed"
        assert item["output_path"] == "/exports/anim_001.gif"
        assert item["file_size"] == 2500000
        assert item["completed_at"] is not None

    def test_update_invalid_status(self, conn):
        ok = update_export_status(conn, self._eid, "invalid")
        assert not ok

    def test_create_failed_job(self, conn):
        eid = create_export_job(conn, "mp4")
        ok = update_export_status(conn, eid, "failed",
                                  error_message="Out of memory")
        assert ok
        item = get_export_job(conn, eid)
        assert item["status"] == "failed"
        assert item["error_message"] == "Out of memory"

    def test_get_nonexistent(self, conn):
        item = get_export_job(conn, "nonexistent")
        assert item is None
