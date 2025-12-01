"""
Tests for SemanticIndexConfig.

Tests cover:
- Default values
- Factory methods
- Configuration validation
"""

import pytest

from scrappy.context.semantic.config import SemanticIndexConfig


class TestSemanticIndexConfigDefaults:
    """Test default configuration values."""

    def test_default_batch_size(self):
        """Default batch size should be 256 (optimal for BGE-small)."""
        config = SemanticIndexConfig()
        assert config.batch_size == 256

    def test_default_max_text_length(self):
        """Default max text length should be 512 (BGE-small context)."""
        config = SemanticIndexConfig()
        assert config.max_text_length == 512

    def test_default_min_chunk_size(self):
        """Default min chunk size should be 20."""
        config = SemanticIndexConfig()
        assert config.min_chunk_size == 20

    def test_default_super_batch_size(self):
        """Default super batch size should be 2048."""
        config = SemanticIndexConfig()
        assert config.super_batch_size == 2048

    def test_default_fts_rebuild_threshold(self):
        """Default FTS rebuild threshold should be 100."""
        config = SemanticIndexConfig()
        assert config.fts_rebuild_threshold == 100

    def test_default_db_dir_name(self):
        """Default db dir name should be .scrappy/lancedb."""
        config = SemanticIndexConfig()
        assert config.db_dir_name == ".scrappy/lancedb"

    def test_default_lock_timeout(self):
        """Default lock timeout should be 300 seconds."""
        config = SemanticIndexConfig()
        assert config.lock_timeout == 300


class TestSemanticIndexConfigCustomValues:
    """Test custom configuration values."""

    def test_custom_batch_size(self):
        """Should accept custom batch size."""
        config = SemanticIndexConfig(batch_size=128)
        assert config.batch_size == 128

    def test_custom_max_text_length(self):
        """Should accept custom max text length."""
        config = SemanticIndexConfig(max_text_length=1024)
        assert config.max_text_length == 1024

    def test_custom_super_batch_size(self):
        """Should accept custom super batch size."""
        config = SemanticIndexConfig(super_batch_size=4096)
        assert config.super_batch_size == 4096

    def test_custom_fts_rebuild_threshold(self):
        """Should accept custom FTS rebuild threshold."""
        config = SemanticIndexConfig(fts_rebuild_threshold=50)
        assert config.fts_rebuild_threshold == 50

    def test_custom_db_dir_name(self):
        """Should accept custom db directory name."""
        config = SemanticIndexConfig(db_dir_name=".custom_db")
        assert config.db_dir_name == ".custom_db"

    def test_multiple_custom_values(self):
        """Should accept multiple custom values at once."""
        config = SemanticIndexConfig(
            batch_size=512,
            max_text_length=256,
            super_batch_size=1024,
            fts_rebuild_threshold=200,
        )
        assert config.batch_size == 512
        assert config.max_text_length == 256
        assert config.super_batch_size == 1024
        assert config.fts_rebuild_threshold == 200


class TestSemanticIndexConfigFactoryMethods:
    """Test factory methods."""

    def test_from_memory_adaptive_returns_config(self):
        """from_memory_adaptive should return a SemanticIndexConfig."""
        config = SemanticIndexConfig.from_memory_adaptive()
        assert isinstance(config, SemanticIndexConfig)

    def test_from_memory_adaptive_has_valid_super_batch(self):
        """from_memory_adaptive should set reasonable super_batch_size."""
        config = SemanticIndexConfig.from_memory_adaptive()
        # Should be between 512 and 2048
        assert 512 <= config.super_batch_size <= 2048

    def test_from_memory_adaptive_preserves_other_defaults(self):
        """from_memory_adaptive should preserve other default values."""
        config = SemanticIndexConfig.from_memory_adaptive()
        assert config.batch_size == 256
        assert config.max_text_length == 512
        assert config.fts_rebuild_threshold == 100

    def test_for_testing_returns_config(self):
        """for_testing should return a SemanticIndexConfig."""
        config = SemanticIndexConfig.for_testing()
        assert isinstance(config, SemanticIndexConfig)

    def test_for_testing_has_small_batch_sizes(self):
        """for_testing should use smaller batch sizes for speed."""
        config = SemanticIndexConfig.for_testing()
        assert config.batch_size == 16
        assert config.super_batch_size == 64

    def test_for_testing_has_small_fts_threshold(self):
        """for_testing should use smaller FTS threshold."""
        config = SemanticIndexConfig.for_testing()
        assert config.fts_rebuild_threshold == 10


class TestSemanticIndexConfigDataclass:
    """Test dataclass behavior."""

    def test_is_immutable_by_default(self):
        """Config should be a dataclass (mutable by default)."""
        config = SemanticIndexConfig()
        # Dataclass is mutable, we can modify
        config.batch_size = 999
        assert config.batch_size == 999

    def test_equality(self):
        """Two configs with same values should be equal."""
        config1 = SemanticIndexConfig(batch_size=128)
        config2 = SemanticIndexConfig(batch_size=128)
        assert config1 == config2

    def test_inequality(self):
        """Two configs with different values should not be equal."""
        config1 = SemanticIndexConfig(batch_size=128)
        config2 = SemanticIndexConfig(batch_size=256)
        assert config1 != config2

    def test_repr(self):
        """Config should have readable repr."""
        config = SemanticIndexConfig(batch_size=128)
        repr_str = repr(config)
        assert "SemanticIndexConfig" in repr_str
        assert "batch_size=128" in repr_str
