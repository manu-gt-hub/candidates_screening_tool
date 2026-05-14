"""Unit tests for shared pure-Python utility functions.

Covers functions that are mode-agnostic (no Spark, no LLM calls).
Run with:  pytest tests/test_utils.py -v
"""
import pytest

# ── topic_pools ──────────────────────────────────────────────────────

from utils.topic_pools import (
    get_topics,
    _resolve_pool,
    TOPIC_POOLS,
    DEFAULT_POOL,
    SCENARIOS_PER_TEST,
)


class TestResolvePool:
    def test_none_returns_default(self):
        assert _resolve_pool(None) is DEFAULT_POOL

    def test_empty_string_returns_default(self):
        assert _resolve_pool("") is DEFAULT_POOL

    def test_exact_match_data_engineer(self):
        assert _resolve_pool("data_engineer") is TOPIC_POOLS["data_engineer"]

    def test_exact_match_data_scientist(self):
        assert _resolve_pool("data_scientist") is TOPIC_POOLS["data_scientist"]

    def test_case_insensitive(self):
        assert _resolve_pool("Data_Engineer") is TOPIC_POOLS["data_engineer"]

    def test_natural_language_role(self):
        assert _resolve_pool("Senior Data Engineer") is TOPIC_POOLS["data_engineer"]

    def test_partial_match_engineer(self):
        assert _resolve_pool("Lead Engineer") is TOPIC_POOLS["data_engineer"]

    def test_partial_match_scientist(self):
        assert _resolve_pool("Applied Scientist") is TOPIC_POOLS["data_scientist"]

    def test_unknown_role_returns_default(self):
        assert _resolve_pool("Product Manager") is DEFAULT_POOL


class TestGetTopics:
    def test_returns_correct_count(self):
        assert len(get_topics(1, "data_engineer")) == SCENARIOS_PER_TEST

    def test_custom_n(self):
        assert len(get_topics(1, "data_engineer", n=5)) == 5

    def test_variant_1_and_2_differ(self):
        t1 = get_topics(1, "data_engineer")
        t2 = get_topics(2, "data_engineer")
        assert t1 != t2

    def test_all_topics_from_pool(self):
        pool = TOPIC_POOLS["data_scientist"]
        topics = get_topics(1, "data_scientist")
        for t in topics:
            assert t in pool

    def test_rotation_wraps_around(self):
        pool = TOPIC_POOLS["data_engineer"]
        # variant 4: start = (4-1)*3 % 10 = 9 → wraps around
        topics = get_topics(4, "data_engineer")
        assert len(topics) == 3
        assert topics[0] == pool[9]
        assert topics[1] == pool[0]

    def test_no_role_uses_default_pool(self):
        topics = get_topics(1)
        for t in topics:
            assert t in DEFAULT_POOL


# ── prompts ──────────────────────────────────────────────────────────

from utils.prompts import (
    sql_esc,
    build_ranking_prompt,
    build_ranking_prompt_parts,
    build_test_prompt,
    build_test_prompt_parts,
    build_evaluation_prompt,
    build_evaluation_prompt_parts,
)


class TestSqlEsc:
    def test_no_quotes(self):
        assert sql_esc("hello") == "hello"

    def test_single_quote(self):
        assert sql_esc("it's") == "it''s"

    def test_multiple_quotes(self):
        assert sql_esc("a'b'c") == "a''b''c"

    def test_empty_string(self):
        assert sql_esc("") == ""


class TestRankingPrompt:
    def test_contains_jd_and_cv(self):
        prompt = build_ranking_prompt("cv text", "jd text")
        assert "cv text" in prompt
        assert "jd text" in prompt

    def test_contains_json_instruction(self):
        prompt = build_ranking_prompt("cv", "jd")
        assert "JSON" in prompt

    def test_tech_context_included(self):
        prompt = build_ranking_prompt("cv", "jd", tech_context="fintech")
        assert "fintech" in prompt

    def test_no_tech_context(self):
        prompt = build_ranking_prompt("cv", "jd")
        assert "BUSINESS CONTEXT" not in prompt

    def test_parts_compose_to_full_prompt(self):
        prefix, sep, suffix = build_ranking_prompt_parts(tech_context="retail")
        composed = f"{prefix}JD{sep}CV{suffix}"
        full = build_ranking_prompt("CV", "JD", tech_context="retail")
        assert composed == full


class TestTestPrompt:
    def test_contains_jd(self):
        prompt = build_test_prompt("jd text")
        assert "jd text" in prompt

    def test_topics_included(self):
        topics = ["Topic A", "Topic B", "Topic C"]
        prompt = build_test_prompt("jd", topics=topics)
        for t in topics:
            assert t in prompt

    def test_tech_context_included(self):
        prompt = build_test_prompt("jd", tech_context="healthcare")
        assert "healthcare" in prompt

    def test_parts_compose_to_full_prompt(self):
        topics = ["A", "B"]
        prefix, suffix = build_test_prompt_parts(topics=topics, tech_context="gaming")
        composed = f"{prefix}JD{suffix}"
        full = build_test_prompt("JD", topics=topics, tech_context="gaming")
        assert composed == full


class TestEvaluationPrompt:
    def test_contains_response_and_jd(self):
        prompt = build_evaluation_prompt("response text", "jd text")
        assert "response text" in prompt
        assert "jd text" in prompt

    def test_parts_compose_to_full_prompt(self):
        prefix, sep, suffix = build_evaluation_prompt_parts()
        composed = f"{prefix}JD{sep}RESP{suffix}"
        full = build_evaluation_prompt("RESP", "JD")
        assert composed == full


# ── llm_client helpers ───────────────────────────────────────────────

from utils.llm_client import _strip_fences


class TestStripFences:
    def test_no_fences(self):
        assert _strip_fences('{"key": "value"}') == '{"key": "value"}'

    def test_json_fences(self):
        text = '```json\n{"key": "value"}\n```'
        assert _strip_fences(text) == '{"key": "value"}'

    def test_plain_fences(self):
        text = '```\n{"key": "value"}\n```'
        assert _strip_fences(text) == '{"key": "value"}'

    def test_fences_without_closing(self):
        text = '```json\n{"key": "value"}'
        assert _strip_fences(text) == '{"key": "value"}'

    def test_multiline_content(self):
        text = '```json\n{\n  "a": 1,\n  "b": 2\n}\n```'
        result = _strip_fences(text)
        assert '"a": 1' in result
        assert '"b": 2' in result


# ── pdf_reports helpers ──────────────────────────────────────────────

from utils.pdf_reports import _esc, _safe_name, _score_color


class TestEsc:
    def test_none(self):
        assert _esc(None) == ""

    def test_empty(self):
        assert _esc("") == ""

    def test_html_entities(self):
        assert "&lt;" in _esc("<script>")
        assert "&amp;" in _esc("A & B")

    def test_plain_text_unchanged(self):
        assert _esc("hello world") == "hello world"


class TestSafeName:
    def test_simple_name(self):
        assert _safe_name("John Doe") == "John_Doe"

    def test_special_characters_removed(self):
        assert _safe_name("José García!@#") == "José_García"

    def test_truncation(self):
        long_name = "A" * 100
        assert len(_safe_name(long_name)) == 80

    def test_hyphens_preserved(self):
        assert _safe_name("Jean-Pierre") == "Jean-Pierre"

    def test_underscores_preserved(self):
        assert _safe_name("first_last") == "first_last"


class TestScoreColor:
    def test_high_score_green(self):
        assert _score_color(85) == "#2E7D32"

    def test_threshold_boundary_green(self):
        assert _score_color(70) == "#2E7D32"

    def test_mid_score_amber(self):
        assert _score_color(60) == "#F57F17"

    def test_boundary_50_amber(self):
        assert _score_color(50) == "#F57F17"

    def test_low_score_red(self):
        assert _score_color(30) == "#C62828"

    def test_custom_threshold(self):
        assert _score_color(60, green_threshold=60) == "#2E7D32"
        assert _score_color(59, green_threshold=60) == "#F57F17"


# ── pdf_parser helpers ───────────────────────────────────────────────

from utils.pdf_parser import _validate_identifier


class TestValidateIdentifier:
    def test_valid_simple(self):
        _validate_identifier("cv_texts")  # should not raise

    def test_valid_with_numbers(self):
        _validate_identifier("view_123")  # should not raise

    def test_valid_underscore_start(self):
        _validate_identifier("_binary_view")  # should not raise

    def test_invalid_starts_with_number(self):
        with pytest.raises(ValueError):
            _validate_identifier("123abc")

    def test_invalid_special_chars(self):
        with pytest.raises(ValueError):
            _validate_identifier("drop; --")

    def test_invalid_empty(self):
        with pytest.raises(ValueError):
            _validate_identifier("")

    def test_invalid_spaces(self):
        with pytest.raises(ValueError):
            _validate_identifier("my view")
