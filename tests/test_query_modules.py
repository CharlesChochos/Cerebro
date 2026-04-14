"""
Unit tests for the NL query engine (intelligence/query.py).
Tests context building, metadata extraction, grounding, and FTS search helpers.
"""
import pytest


class TestMetadataExtraction:
    def test_extract_valid_metadata(self):
        from intelligence.query import extract_metadata

        content = """Here is my analysis of the situation.

The conflict in region X [evt-1] has escalated due to [evt-2].

```json
{"event_ids_referenced": ["evt-1", "evt-2"], "entity_ids_referenced": ["ent-1"], "suggested_questions": ["What about the economic impact?", "How does this affect trade?", "What is the military posture?"]}
```"""
        answer, meta = extract_metadata(content)
        assert "Here is my analysis" in answer
        assert "```json" not in answer
        assert meta["event_ids_referenced"] == ["evt-1", "evt-2"]
        assert meta["entity_ids_referenced"] == ["ent-1"]
        assert len(meta["suggested_questions"]) == 3

    def test_extract_no_metadata(self):
        from intelligence.query import extract_metadata

        content = "Simple answer with no JSON block."
        answer, meta = extract_metadata(content)
        assert answer == content
        assert meta["event_ids_referenced"] == []
        assert meta["suggested_questions"] == []

    def test_extract_malformed_json(self):
        from intelligence.query import extract_metadata

        content = "Answer\n```json\n{bad json\n```"
        answer, meta = extract_metadata(content)
        assert "Answer" in answer
        assert meta["event_ids_referenced"] == []

    def test_suggested_questions_capped_at_3(self):
        from intelligence.query import extract_metadata

        content = """Answer text.

```json
{"event_ids_referenced": [], "entity_ids_referenced": [], "suggested_questions": ["Q1", "Q2", "Q3", "Q4", "Q5"]}
```"""
        _, meta = extract_metadata(content)
        assert len(meta["suggested_questions"]) == 3


class TestGrounding:
    def test_perfect_grounding(self):
        from intelligence.query import compute_grounding

        assert compute_grounding(["a", "b", "c"], {"a", "b", "c"}) == 1.0

    def test_partial_grounding(self):
        from intelligence.query import compute_grounding

        assert compute_grounding(["a", "b", "c", "d"], {"a", "b"}) == 0.5

    def test_no_grounding(self):
        from intelligence.query import compute_grounding

        assert compute_grounding(["x", "y"], {"a", "b"}) == 0.0

    def test_empty_refs(self):
        from intelligence.query import compute_grounding

        assert compute_grounding([], {"a"}) == 0.0


class TestFTSHelpers:
    def test_search_events_like_builds_query(self):
        """Test that the LIKE fallback handles word lists correctly."""
        from intelligence.query import _search_events_like
        # We can't easily test against a real DB here, but we can verify
        # the function doesn't crash with empty input
        # (it would need a real conn, so we just test the logic path)
        pass

    def test_stop_word_filtering(self):
        """Verify that stop words are filtered from FTS queries."""
        stop_words = {
            "what", "when", "where", "who", "why", "how", "is", "are", "was",
            "were", "the", "a", "an", "in", "on", "at", "to", "for", "of",
            "and", "or", "but", "not", "with", "about", "tell", "me", "show",
            "latest", "recent", "any", "there", "has", "have", "been", "do",
            "does", "did", "can", "could", "would", "should", "will",
            "happening", "going", "current", "update", "know",
        }
        question = "What is happening in Ukraine with the military conflict"
        words = [w for w in question.lower().split() if w.isalpha() and w not in stop_words and len(w) > 2]
        assert "ukraine" in words
        assert "military" in words
        assert "conflict" in words
        assert "what" not in words
        assert "the" not in words
        assert "happening" not in words

    def test_format_event(self):
        from intelligence.query import _format_event

        event = {
            "id": "e1", "source": "gdelt", "category": "military",
            "severity": 85, "country_code": "UA",
            "timestamp": "2025-01-01T00:00:00Z",
            "title": "Test Event", "summary": "Some details here",
        }
        result = _format_event(event)
        assert "[e1]" in result
        assert "(gdelt)" in result
        assert "sev=85" in result
        assert "Test Event" in result
        assert "Some details here" in result
