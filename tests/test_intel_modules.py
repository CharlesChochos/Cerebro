"""
Unit tests for intelligence module functions:
- brief.py: metadata extraction, grounding scores, formatting
- worldstate.py: formatting, region computation
- redteam.py: formatting functions
- fuse.py: grounding score computation, formatting
"""
import pytest


# ── Brief module tests ──────────────────────────────────────────────────────


class TestBriefMetadataExtraction:
    def test_extract_metadata_valid(self):
        from intelligence.brief import extract_metadata_block

        content = """## Executive Summary
Some analysis here.

## Critical Developments
More content.

```json
{"event_ids_referenced": ["evt-1", "evt-2"], "entity_ids_referenced": ["ent-1"], "predictions": [{"prediction": "X", "confidence": 0.7, "timeframe": "24h", "category": "military"}]}
```"""
        brief_text, metadata = extract_metadata_block(content)
        assert "## Executive Summary" in brief_text
        assert "```json" not in brief_text
        assert metadata["event_ids_referenced"] == ["evt-1", "evt-2"]
        assert metadata["entity_ids_referenced"] == ["ent-1"]
        assert len(metadata["predictions"]) == 1
        assert metadata["predictions"][0]["confidence"] == 0.7

    def test_extract_metadata_no_json_block(self):
        from intelligence.brief import extract_metadata_block

        content = "## Brief\nJust a brief with no metadata block."
        brief_text, metadata = extract_metadata_block(content)
        assert brief_text == content
        assert metadata["event_ids_referenced"] == []
        assert metadata["predictions"] == []

    def test_extract_metadata_malformed_json(self):
        from intelligence.brief import extract_metadata_block

        content = "## Brief\nContent\n```json\n{bad json here\n```"
        brief_text, metadata = extract_metadata_block(content)
        assert "## Brief" in brief_text
        assert metadata["event_ids_referenced"] == []


class TestBriefGrounding:
    def test_grounding_all_valid(self):
        from intelligence.brief import compute_grounding_score

        valid = {"a", "b", "c"}
        assert compute_grounding_score(["a", "b", "c"], valid) == 1.0

    def test_grounding_partial(self):
        from intelligence.brief import compute_grounding_score

        valid = {"a", "b"}
        assert compute_grounding_score(["a", "b", "c", "d"], valid) == 0.5

    def test_grounding_none_valid(self):
        from intelligence.brief import compute_grounding_score

        assert compute_grounding_score(["x", "y"], {"a", "b"}) == 0.0

    def test_grounding_empty_refs(self):
        from intelligence.brief import compute_grounding_score

        assert compute_grounding_score([], {"a", "b"}) == 0.0


class TestBriefFormatting:
    def test_format_events(self):
        from intelligence.brief import format_events

        events = [
            {"id": "e1", "source": "gdelt", "category": "military", "severity": 80,
             "country_code": "US", "title": "Test Event", "summary": "Summary text"},
        ]
        result = format_events(events)
        assert "[e1]" in result
        assert "(gdelt)" in result
        assert "sev=80" in result

    def test_format_events_empty(self):
        from intelligence.brief import format_events

        assert format_events([]) == "(no events)"

    def test_format_entities(self):
        from intelligence.brief import format_entities

        entities = [{"id": "ent1", "name": "NATO", "entity_type": "organization", "event_count": 15}]
        result = format_entities(entities)
        assert "NATO" in result
        assert "(organization)" in result

    def test_format_entities_empty(self):
        from intelligence.brief import format_entities

        assert format_entities([]) == "(no entities)"

    def test_format_fusion_empty(self):
        from intelligence.brief import format_fusion

        assert format_fusion([]) == "(no fusion signals detected)"


# ── World State module tests ────────────────────────────────────────────────


class TestWorldStateFormatting:
    def test_format_events(self):
        from intelligence.worldstate import format_events

        events = [
            {"source": "gdelt", "category": "economic", "severity": 60,
             "country_code": "DE", "title": "Market Drop"},
        ]
        result = format_events(events)
        assert "(gdelt)" in result
        assert "sev=60" in result
        assert "Market Drop" in result

    def test_format_events_empty(self):
        from intelligence.worldstate import format_events

        assert format_events([]) == "(no events)"

    def test_format_fusion(self):
        from intelligence.worldstate import format_fusion

        signals = [{"signal_type": "economic_crisis", "severity": 75, "title": "EU debt spike"}]
        result = format_fusion(signals)
        assert "economic_crisis" in result
        assert "EU debt spike" in result

    def test_format_fusion_empty(self):
        from intelligence.worldstate import format_fusion

        assert format_fusion([]) == "(none)"


class TestTopRegions:
    def test_compute_top_regions(self):
        from intelligence.worldstate import compute_top_regions

        events = [
            {"region": "Europe", "country_code": "DE"},
            {"region": "Europe", "country_code": "FR"},
            {"region": "Asia", "country_code": "CN"},
            {"region": "Europe", "country_code": "UK"},
            {"region": "Asia", "country_code": "JP"},
        ]
        result = compute_top_regions(events)
        assert "Europe (3)" in result
        assert "Asia (2)" in result

    def test_top_regions_missing_data(self):
        from intelligence.worldstate import compute_top_regions

        events = [{"region": None, "country_code": None}]
        result = compute_top_regions(events)
        assert "unknown" in result


# ── Fusion module tests ─────────────────────────────────────────────────────


class TestFusionGrounding:
    def test_grounding_perfect(self):
        from intelligence.fuse import compute_grounding_score

        signal = {"event_ids": ["a", "b", "c"]}
        assert compute_grounding_score(signal, {"a", "b", "c"}) == 1.0

    def test_grounding_partial(self):
        from intelligence.fuse import compute_grounding_score

        signal = {"event_ids": ["a", "b", "c", "d"]}
        assert compute_grounding_score(signal, {"a", "c"}) == 0.5

    def test_grounding_empty(self):
        from intelligence.fuse import compute_grounding_score

        signal = {"event_ids": []}
        assert compute_grounding_score(signal, {"a"}) == 0.0

    def test_grounding_no_key(self):
        from intelligence.fuse import compute_grounding_score

        signal = {}
        assert compute_grounding_score(signal, {"a"}) == 0.0


class TestFusionFormatting:
    def test_format_events(self):
        from intelligence.fuse import format_events_for_prompt

        events = [
            {"id": "e1", "source": "gdelt", "category": "military", "severity": 90,
             "country_code": "UA", "title": "Conflict Update", "summary": "Details here"},
        ]
        result = format_events_for_prompt(events)
        assert "[e1]" in result
        assert "sev=90" in result
        assert "Summary: Details here" in result

    def test_format_entities(self):
        from intelligence.fuse import format_entities_for_prompt

        entities = [{"id": "ent1", "name": "Russia", "entity_type": "location", "event_count": 30}]
        result = format_entities_for_prompt(entities)
        assert "Russia" in result
        assert "(location)" in result
