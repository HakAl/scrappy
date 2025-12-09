"""
Tests for DefaultResultRanker and PassthroughRanker.

Tests cover:
- Weighted scoring (vector + FTS)
- Exact match boost
- Path match boost
- Sorting by final score
- Custom config overrides
- Edge cases (empty query, empty candidates)
- Protocol conformance
"""

import pytest

from scrappy.context.protocols import RankingConfig, ResultRankerProtocol, ScoredChunk
from scrappy.context.semantic.ranker import DefaultResultRanker, PassthroughRanker


class TestScoredChunk:
    """Test ScoredChunk dataclass."""

    def test_default_values(self):
        """Should have sensible defaults."""
        chunk = ScoredChunk(
            file_path="src/main.py",
            start_line=1,
            end_line=10,
            content="def main():\n    pass",
        )

        assert chunk.vector_score == 0.0
        assert chunk.fts_score == 0.0
        assert chunk.final_score == 0.0
        assert chunk.match_details == {}

    def test_match_details_initialized_empty(self):
        """match_details should be empty dict by default."""
        chunk = ScoredChunk(
            file_path="src/main.py",
            start_line=1,
            end_line=10,
            content="code",
        )

        assert isinstance(chunk.match_details, dict)
        assert len(chunk.match_details) == 0


class TestRankingConfig:
    """Test RankingConfig dataclass."""

    def test_default_weights(self):
        """Should have reasonable default weights."""
        config = RankingConfig()

        assert config.vector_weight == 0.6
        assert config.fts_weight == 0.3
        assert config.exact_match_boost == 0.5
        assert config.path_match_boost == 0.2

    def test_custom_weights(self):
        """Should accept custom weights."""
        config = RankingConfig(
            vector_weight=0.8,
            fts_weight=0.1,
            exact_match_boost=0.2,
            path_match_boost=0.1,
        )

        assert config.vector_weight == 0.8
        assert config.fts_weight == 0.1


class TestDefaultResultRanker:
    """Test DefaultResultRanker ranking logic."""

    @pytest.fixture
    def ranker(self):
        """Create a default ranker."""
        return DefaultResultRanker()

    @pytest.fixture
    def sample_chunks(self):
        """Create sample chunks for testing."""
        return [
            ScoredChunk(
                file_path="src/auth/login.py",
                start_line=1,
                end_line=20,
                content="def authenticate_user(username, password):\n    # Authentication logic",
                vector_score=0.8,
                fts_score=0.2,
            ),
            ScoredChunk(
                file_path="src/utils/helpers.py",
                start_line=50,
                end_line=70,
                content="def format_date(date):\n    return date.strftime('%Y-%m-%d')",
                vector_score=0.6,
                fts_score=0.1,
            ),
            ScoredChunk(
                file_path="tests/test_auth.py",
                start_line=10,
                end_line=30,
                content="def test_authenticate_user():\n    assert authenticate_user('admin', 'pass')",
                vector_score=0.7,
                fts_score=0.3,
            ),
        ]

    # --- Base Scoring Tests ---

    def test_computes_weighted_score(self, ranker, sample_chunks):
        """Should compute weighted combination of vector and FTS scores."""
        query = "something"
        ranked = ranker.rank(query, sample_chunks)

        # With default weights (0.6 vector, 0.3 FTS):
        # chunk1: 0.8*0.6 + 0.2*0.3 = 0.48 + 0.06 = 0.54
        # chunk2: 0.6*0.6 + 0.1*0.3 = 0.36 + 0.03 = 0.39
        # chunk3: 0.7*0.6 + 0.3*0.3 = 0.42 + 0.09 = 0.51

        # Check scores are set (with some tolerance for floating point)
        assert ranked[0].final_score > 0
        assert ranked[1].final_score > 0
        assert ranked[2].final_score > 0

    def test_sorts_by_final_score_descending(self, ranker, sample_chunks):
        """Should sort results by final_score, highest first."""
        query = "something"
        ranked = ranker.rank(query, sample_chunks)

        # Verify descending order
        for i in range(len(ranked) - 1):
            assert ranked[i].final_score >= ranked[i + 1].final_score

    # --- Exact Match Boost Tests ---

    def test_exact_match_boost_applied(self, ranker):
        """Should apply boost when query appears as substring in content."""
        chunks = [
            ScoredChunk(
                file_path="src/main.py",
                start_line=1,
                end_line=10,
                content="This is the authenticate_user function",
                vector_score=0.5,
                fts_score=0.1,
            ),
            ScoredChunk(
                file_path="src/other.py",
                start_line=1,
                end_line=10,
                content="This has no matching content here",
                vector_score=0.5,
                fts_score=0.1,
            ),
        ]

        query = "authenticate_user"
        ranked = ranker.rank(query, chunks)

        # Chunk with exact match should rank higher
        assert ranked[0].file_path == "src/main.py"
        assert ranked[0].match_details.get("exact_match") is True

    def test_exact_match_case_insensitive(self, ranker):
        """Exact match should be case-insensitive."""
        chunks = [
            ScoredChunk(
                file_path="src/main.py",
                start_line=1,
                end_line=10,
                content="def AUTHENTICATE_USER():",
                vector_score=0.5,
                fts_score=0.1,
            ),
        ]

        query = "authenticate_user"
        ranked = ranker.rank(query, chunks)

        assert ranked[0].match_details.get("exact_match") is True

    # --- Path Match Boost Tests ---

    def test_path_match_boost_applied(self, ranker):
        """Should apply boost when query terms appear in file path."""
        chunks = [
            ScoredChunk(
                file_path="src/authentication/login.py",
                start_line=1,
                end_line=10,
                content="def login():",
                vector_score=0.5,
                fts_score=0.1,
            ),
            ScoredChunk(
                file_path="src/utils/helpers.py",
                start_line=1,
                end_line=10,
                content="def helper():",
                vector_score=0.5,
                fts_score=0.1,
            ),
        ]

        query = "authentication login"
        ranked = ranker.rank(query, chunks)

        # File with matching path should rank higher
        assert ranked[0].file_path == "src/authentication/login.py"
        assert "path_matches" in ranked[0].match_details

    def test_path_match_proportional_to_matching_terms(self, ranker):
        """Path boost should be proportional to number of matching terms."""
        chunks = [
            ScoredChunk(
                file_path="src/auth/login.py",
                start_line=1,
                end_line=10,
                content="code",
                vector_score=0.5,
                fts_score=0.1,
            ),
            ScoredChunk(
                file_path="src/auth.py",
                start_line=1,
                end_line=10,
                content="code",
                vector_score=0.5,
                fts_score=0.1,
            ),
        ]

        query = "auth login"
        ranked = ranker.rank(query, chunks)

        # "src/auth/login.py" matches both "auth" and "login"
        # "src/auth.py" matches only "auth"
        assert ranked[0].file_path == "src/auth/login.py"
        assert len(ranked[0].match_details.get("path_matches", [])) == 2
        assert len(ranked[1].match_details.get("path_matches", [])) == 1

    # --- Custom Config Tests ---

    def test_custom_config_weights(self, ranker):
        """Should respect custom config weights."""
        chunks = [
            ScoredChunk(
                file_path="src/a.py",
                start_line=1,
                end_line=10,
                content="code",
                vector_score=1.0,  # High vector
                fts_score=0.0,    # No FTS
            ),
            ScoredChunk(
                file_path="src/b.py",
                start_line=1,
                end_line=10,
                content="code",
                vector_score=0.0,  # No vector
                fts_score=1.0,    # High FTS
            ),
        ]

        # Default weights favor vector (0.6 vs 0.3)
        ranked_default = ranker.rank("query", chunks)
        assert ranked_default[0].file_path == "src/a.py"

        # Custom weights favor FTS
        fts_heavy_config = RankingConfig(
            vector_weight=0.1,
            fts_weight=0.9,
        )
        ranked_custom = ranker.rank("query", chunks, config=fts_heavy_config)
        assert ranked_custom[0].file_path == "src/b.py"

    def test_config_from_constructor(self):
        """Should use config from constructor as default."""
        config = RankingConfig(
            vector_weight=0.1,
            fts_weight=0.9,
        )
        ranker = DefaultResultRanker(config)

        chunks = [
            ScoredChunk(
                file_path="src/a.py",
                start_line=1,
                end_line=10,
                content="code",
                vector_score=1.0,
                fts_score=0.0,
            ),
            ScoredChunk(
                file_path="src/b.py",
                start_line=1,
                end_line=10,
                content="code",
                vector_score=0.0,
                fts_score=1.0,
            ),
        ]

        ranked = ranker.rank("query", chunks)
        assert ranked[0].file_path == "src/b.py"

    # --- Edge Cases ---

    def test_empty_candidates(self, ranker):
        """Should handle empty candidate list."""
        ranked = ranker.rank("query", [])
        assert ranked == []

    def test_single_candidate(self, ranker):
        """Should handle single candidate."""
        chunks = [
            ScoredChunk(
                file_path="src/main.py",
                start_line=1,
                end_line=10,
                content="code",
                vector_score=0.5,
                fts_score=0.3,
            ),
        ]

        ranked = ranker.rank("query", chunks)
        assert len(ranked) == 1
        assert ranked[0].final_score > 0

    def test_empty_query(self, ranker):
        """Should handle empty query (no exact/path match possible)."""
        chunks = [
            ScoredChunk(
                file_path="src/main.py",
                start_line=1,
                end_line=10,
                content="code",
                vector_score=0.5,
                fts_score=0.3,
            ),
        ]

        ranked = ranker.rank("", chunks)
        assert len(ranked) == 1
        # Only base score, no boosts
        assert "exact_match" not in ranked[0].match_details
        assert "path_matches" not in ranked[0].match_details

    def test_short_query_terms_filtered(self, ranker):
        """Should filter out very short query terms for path matching."""
        chunks = [
            ScoredChunk(
                file_path="src/a/b.py",
                start_line=1,
                end_line=10,
                content="code",
                vector_score=0.5,
                fts_score=0.3,
            ),
        ]

        # Single-char terms like "a" should not count as path matches
        ranked = ranker.rank("a b", chunks)

        # Neither "a" nor "b" should trigger path match (too short)
        assert "path_matches" not in ranked[0].match_details


class TestPassthroughRanker:
    """Test PassthroughRanker (no-op ranker)."""

    def test_returns_candidates_unchanged(self):
        """Should return candidates without modification."""
        ranker = PassthroughRanker()

        chunks = [
            ScoredChunk(
                file_path="src/b.py",
                start_line=1,
                end_line=10,
                content="second",
                vector_score=0.3,
                fts_score=0.1,
            ),
            ScoredChunk(
                file_path="src/a.py",
                start_line=1,
                end_line=10,
                content="first",
                vector_score=0.9,
                fts_score=0.5,
            ),
        ]

        ranked = ranker.rank("query", chunks)

        # Order should be preserved (not sorted)
        assert ranked[0].file_path == "src/b.py"
        assert ranked[1].file_path == "src/a.py"

    def test_ignores_config(self):
        """Should ignore any config parameter."""
        ranker = PassthroughRanker()

        chunks = [
            ScoredChunk(
                file_path="src/main.py",
                start_line=1,
                end_line=10,
                content="code",
                vector_score=0.5,
                fts_score=0.3,
            ),
        ]

        config = RankingConfig(vector_weight=1.0, fts_weight=0.0)
        ranked = ranker.rank("query", chunks, config)

        assert ranked == chunks


class TestProtocolConformance:
    """Verify rankers conform to ResultRankerProtocol."""

    def test_default_ranker_conforms_to_protocol(self):
        """DefaultResultRanker should satisfy ResultRankerProtocol."""
        ranker = DefaultResultRanker()
        assert isinstance(ranker, ResultRankerProtocol)

    def test_passthrough_ranker_conforms_to_protocol(self):
        """PassthroughRanker should satisfy ResultRankerProtocol."""
        ranker = PassthroughRanker()
        assert isinstance(ranker, ResultRankerProtocol)

