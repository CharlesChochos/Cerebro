"""
Phase 0 Validation Tests — FastAPI health endpoint.
"""
import os
import sys
import tempfile

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

# Override DB path before importing the app
_fd, _test_db_path = tempfile.mkstemp(suffix=".db")
os.close(_fd)
os.environ["CEREBRO_DB_PATH"] = _test_db_path

from api.main import app


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        yield c
    os.unlink(_test_db_path)


class TestHealthEndpoint:
    def test_returns_200(self, client):
        response = client.get("/health")
        assert response.status_code == 200

    def test_status_healthy(self, client):
        data = client.get("/health").json()
        assert data["status"] == "healthy"

    def test_database_connected(self, client):
        data = client.get("/health").json()
        assert data["database"] == "connected"

    def test_fts5_ok(self, client):
        data = client.get("/health").json()
        assert data["fts5"] == "ok"

    def test_spatialite_loaded(self, client):
        data = client.get("/health").json()
        assert data["spatialite"] == "loaded"

    def test_counts_present(self, client):
        data = client.get("/health").json()
        assert "counts" in data
        assert "events" in data["counts"]
        assert "entities" in data["counts"]
        assert "alerts" in data["counts"]

    def test_initial_counts(self, client):
        data = client.get("/health").json()
        assert data["counts"]["events"] >= 0
        assert data["counts"]["entities"] >= 0
        assert data["counts"]["alerts"] >= 0
