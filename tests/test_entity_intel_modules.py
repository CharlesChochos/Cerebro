"""
Unit tests for entity intelligence modules — dossier, ACH, sanctions.
"""
import json

import pytest


# ── Dossier Tests ──────────────────────────────────────────────────────────


class TestOmnisearchHelpers:
    def test_dossier_module_imports(self):
        from intelligence.dossier import omnisearch, generate_dossier, get_link_graph, find_shortest_path
        assert callable(omnisearch)
        assert callable(generate_dossier)
        assert callable(get_link_graph)
        assert callable(find_shortest_path)

    def test_format_intel_for_prompt_with_events(self):
        from intelligence.dossier import format_intel_for_prompt
        intel = {
            "events": [
                {"source": "gdelt", "timestamp": "2026-04-10T12:00:00Z",
                 "title": "Test Event", "severity": 75, "country_code": "US"},
            ],
            "fusion_signals": [],
            "sanctions_matches": [],
        }
        result = format_intel_for_prompt(intel)
        assert "EVENTS" in result
        assert "Test Event" in result
        assert "gdelt" in result

    def test_format_intel_for_prompt_empty(self):
        from intelligence.dossier import format_intel_for_prompt
        result = format_intel_for_prompt({})
        assert "No intelligence" in result

    def test_format_relations_empty(self):
        from intelligence.dossier import format_relations_for_prompt
        result = format_relations_for_prompt([])
        assert "No known" in result

    def test_format_relations_with_data(self):
        from intelligence.dossier import format_relations_for_prompt
        rels = [{"related_name": "NATO", "related_type": "organization",
                 "relation_type": "co_occurs", "confidence": 0.8}]
        result = format_relations_for_prompt(rels)
        assert "NATO" in result
        assert "co_occurs" in result


# ── ACH Tests ──────────────────────────────────────────────────────────────


class TestACHScoring:
    def test_score_matrix_basic(self):
        from intelligence.ach import score_ach_matrix
        matrix = [
            ["C", "I"],  # Evidence 1: supports H1, contradicts H2
            ["C", "N"],  # Evidence 2: supports H1, neutral for H2
            ["I", "C"],  # Evidence 3: contradicts H1, supports H2
        ]
        hypotheses = ["Hypothesis A", "Hypothesis B"]
        scores = score_ach_matrix(matrix, hypotheses)

        # H1 has 1 inconsistent, H2 has 1 inconsistent
        assert len(scores) == 2

    def test_score_favors_fewer_inconsistencies(self):
        from intelligence.ach import score_ach_matrix
        matrix = [
            ["C", "I"],
            ["C", "I"],
            ["N", "C"],
        ]
        hypotheses = ["H1", "H2"]
        scores = score_ach_matrix(matrix, hypotheses)

        # H1 has 0 inconsistent, H2 has 2 — H1 should rank first
        assert scores[0]["hypothesis"] == "H1"
        assert scores[0]["inconsistent"] == 0
        assert scores[1]["inconsistent"] == 2

    def test_score_empty_matrix(self):
        from intelligence.ach import score_ach_matrix
        scores = score_ach_matrix([], ["H1", "H2"])
        assert len(scores) == 2
        assert all(s["consistent"] == 0 for s in scores)

    def test_score_all_neutral(self):
        from intelligence.ach import score_ach_matrix
        matrix = [["N", "N"], ["N", "N"]]
        scores = score_ach_matrix(matrix, ["H1", "H2"])
        # All neutral — tied, both should have 0 inconsistency
        assert all(s["inconsistency_ratio"] == 0 for s in scores)

    def test_module_imports(self):
        from intelligence.ach import (
            create_ach_framework, fill_ach_matrix,
            update_ach_cell, score_ach_matrix,
        )
        assert callable(create_ach_framework)
        assert callable(fill_ach_matrix)
        assert callable(update_ach_cell)
        assert callable(score_ach_matrix)


# ── Sanctions Tests ────────────────────────────────────────────────────────


class TestSanctionsHelpers:
    def test_normalize_name(self):
        from detection.sanctions import normalize_name
        assert normalize_name("Test Corp.") == "test corp"
        assert normalize_name("  Foo, Inc.  ") == "foo inc"
        assert normalize_name("NATO") == "nato"

    def test_normalize_preserves_content(self):
        from detection.sanctions import normalize_name
        assert normalize_name("Bank of Russia") == "bank of russia"

    def test_module_imports(self):
        from detection.sanctions import (
            check_direct_matches, check_multi_hop_matches,
            run_sanctions_scan, get_sanctions_hits,
        )
        assert callable(check_direct_matches)
        assert callable(check_multi_hop_matches)
        assert callable(run_sanctions_scan)
        assert callable(get_sanctions_hits)

    def test_max_hops_constant(self):
        from detection.sanctions import MAX_HOPS
        assert MAX_HOPS == 3

    def test_alias_confidence_threshold(self):
        from detection.sanctions import ALIAS_CONFIDENCE
        assert 0.5 <= ALIAS_CONFIDENCE <= 0.8


# ── Link Analysis Tests ───────────────────────────────────────────────────


class TestShortestPath:
    def test_same_node_path(self):
        """Path from node to itself is trivial."""
        from intelligence.dossier import find_shortest_path
        from db.connection import get_connection
        from db.migrate import run_migrations

        conn = get_connection(":memory:")
        run_migrations(conn)

        conn.execute(
            "INSERT INTO entities (id, name, entity_type) VALUES ('e1', 'Test', 'org')"
        )
        conn.commit()

        result = find_shortest_path(conn, "e1", "e1")
        assert result["hops"] == 0
        assert result["path"] == ["e1"]
        conn.close()

    def test_direct_connection(self):
        """Two entities directly connected should have 1-hop path."""
        from intelligence.dossier import find_shortest_path
        from db.connection import get_connection
        from db.migrate import run_migrations
        import uuid

        conn = get_connection(":memory:")
        run_migrations(conn)

        conn.execute("INSERT INTO entities (id, name, entity_type) VALUES ('e1', 'A', 'org')")
        conn.execute("INSERT INTO entities (id, name, entity_type) VALUES ('e2', 'B', 'org')")
        conn.execute(
            """INSERT INTO entity_relations (id, source_entity_id, target_entity_id, relation_type)
               VALUES (?, 'e1', 'e2', 'co_occurs')""",
            (str(uuid.uuid4()),),
        )
        conn.commit()

        result = find_shortest_path(conn, "e1", "e2")
        assert result["hops"] == 1
        assert result["path"] == ["e1", "e2"]
        assert result["relations"] == ["co_occurs"]
        conn.close()

    def test_no_path(self):
        """Disconnected entities should return no_path_found."""
        from intelligence.dossier import find_shortest_path
        from db.connection import get_connection
        from db.migrate import run_migrations

        conn = get_connection(":memory:")
        run_migrations(conn)

        conn.execute("INSERT INTO entities (id, name, entity_type) VALUES ('e1', 'A', 'org')")
        conn.execute("INSERT INTO entities (id, name, entity_type) VALUES ('e2', 'B', 'org')")
        conn.commit()

        result = find_shortest_path(conn, "e1", "e2")
        assert result["hops"] == -1
        assert result["path"] == []
        conn.close()


class TestLinkGraph:
    def test_single_node_graph(self):
        from intelligence.dossier import get_link_graph
        from db.connection import get_connection
        from db.migrate import run_migrations

        conn = get_connection(":memory:")
        run_migrations(conn)

        conn.execute(
            "INSERT INTO entities (id, name, entity_type, event_count) VALUES ('e1', 'Test', 'org', 5)"
        )
        conn.commit()

        graph = get_link_graph(conn, "e1")
        assert graph["node_count"] == 1
        assert graph["edge_count"] == 0
        assert graph["nodes"][0]["name"] == "Test"
        conn.close()

    def test_graph_with_connections(self):
        from intelligence.dossier import get_link_graph
        from db.connection import get_connection
        from db.migrate import run_migrations
        import uuid

        conn = get_connection(":memory:")
        run_migrations(conn)

        for eid, name in [("e1", "Center"), ("e2", "Neighbor1"), ("e3", "Neighbor2")]:
            conn.execute(
                "INSERT INTO entities (id, name, entity_type, event_count) VALUES (?, ?, 'org', 3)",
                (eid, name),
            )
        for src, tgt in [("e1", "e2"), ("e1", "e3")]:
            conn.execute(
                """INSERT INTO entity_relations (id, source_entity_id, target_entity_id, relation_type, confidence)
                   VALUES (?, ?, ?, 'co_occurs', 0.7)""",
                (str(uuid.uuid4()), src, tgt),
            )
        conn.commit()

        graph = get_link_graph(conn, "e1", max_depth=1)
        assert graph["node_count"] == 3
        # Each relation is found when expanding from center AND from neighbors
        assert graph["edge_count"] >= 2
        conn.close()
