"""
Phase 2 Tests — Entity extraction module.
"""
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from intelligence.extract import extract_entities_regex


class TestRegexExtraction:
    def test_extracts_organizations(self):
        entities = extract_entities_regex("NATO forces deployed to eastern border")
        names = [e["name"] for e in entities]
        assert "NATO" in names
        nato = next(e for e in entities if e["name"] == "NATO")
        assert nato["entity_type"] == "organization"
        assert nato["confidence"] >= 0.8

    def test_extracts_country_names(self):
        entities = extract_entities_regex("Tensions between Russia and Ukraine escalate")
        names = [e["name"] for e in entities]
        assert "Russia" in names
        assert "Ukraine" in names
        russia = next(e for e in entities if e["name"] == "Russia")
        assert russia["entity_type"] == "location"
        assert russia["metadata"]["country_code"] == "RU"

    def test_extracts_from_entities_json(self):
        ej = json.dumps([{"name": "John Smith", "type": "person", "role": "leader"}])
        entities = extract_entities_regex("Summit meeting today", entities_json=ej)
        names = [e["name"] for e in entities]
        assert "John Smith" in names

    def test_ignores_short_names_in_json(self):
        ej = json.dumps([{"name": "UK", "type": "actor"}])
        entities = extract_entities_regex("Meeting at UK", entities_json=ej)
        # "UK" is 2 chars — should be filtered out from entities_json
        actor_entities = [e for e in entities if e["entity_type"] == "actor"]
        assert len(actor_entities) == 0

    def test_ignores_unknown_names(self):
        ej = json.dumps([{"name": "Unknown", "type": "actor"}])
        entities = extract_entities_regex("Something happened", entities_json=ej)
        names = [e["name"] for e in entities]
        assert "Unknown" not in names

    def test_deduplicates_entities(self):
        entities = extract_entities_regex(
            "NATO held talks with NATO allies about the United Nations and NATO"
        )
        nato_count = sum(1 for e in entities if e["name"] == "NATO")
        assert nato_count == 1

    def test_empty_input(self):
        entities = extract_entities_regex("", "")
        assert isinstance(entities, list)

    def test_multiple_org_types(self):
        entities = extract_entities_regex(
            "WHO and IMF issued joint statement on World Bank policy"
        )
        names = [e["name"] for e in entities]
        assert "WHO" in names
        assert "IMF" in names
        assert "World Bank" in names

    def test_handles_bad_json(self):
        entities = extract_entities_regex("Test event", entities_json="not valid json")
        assert isinstance(entities, list)

    def test_mixed_extraction(self):
        """Test extracting orgs, countries, and actors from same text."""
        ej = json.dumps([{"name": "Sergey Lavrov", "type": "person"}])
        entities = extract_entities_regex(
            "UN Security Council discusses Iran nuclear deal",
            summary="Russia and China block resolution",
            entities_json=ej,
        )
        names = [e["name"] for e in entities]
        assert "Iran" in names
        assert "Russia" in names
        assert "China" in names
        assert "Sergey Lavrov" in names
