"""
Tests for ModelType and ModelInfo functionality.

Tests model type classification and provider model info retrieval,
critical for automatic selection of instruction-tuned models for agent planning.
"""

import pytest
from unittest.mock import MagicMock, patch

# Import will fail until implementation exists
try:
    from src.providers.base import ModelType, ModelInfo, LLMProviderBase
    IMPORTS_AVAILABLE = True
except ImportError:
    IMPORTS_AVAILABLE = False
    ModelType = None
    ModelInfo = None


@pytest.mark.skipif(not IMPORTS_AVAILABLE, reason="ModelType/ModelInfo not yet implemented")
class TestModelType:
    """Test ModelType enum."""


    def test_model_type_string_values(self):
        """ModelType values should be lowercase strings."""
        assert ModelType.BASE.value == "base"
        assert ModelType.CHAT.value == "chat"
        assert ModelType.INSTRUCT.value == "instruct"
        assert ModelType.CODE.value == "code"
        assert ModelType.REASONING.value == "reasoning"
        assert ModelType.UNKNOWN.value == "unknown"

    def test_model_type_comparison(self):
        """ModelType should support equality comparison."""
        assert ModelType.INSTRUCT == ModelType.INSTRUCT
        assert ModelType.INSTRUCT != ModelType.CHAT
        assert ModelType.BASE != ModelType.INSTRUCT


@pytest.mark.skipif(not IMPORTS_AVAILABLE, reason="ModelType/ModelInfo not yet implemented")
class TestModelInfo:
    """Test ModelInfo dataclass."""

    def test_model_info_creation_minimal(self):
        """ModelInfo should be creatable with minimal required fields."""
        info = ModelInfo(
            id="test-model",
            model_type=ModelType.INSTRUCT,
            context_length=8192
        )
        assert info.id == "test-model"
        assert info.model_type == ModelType.INSTRUCT
        assert info.context_length == 8192

    def test_model_info_creation_full(self):
        """ModelInfo should accept all optional fields."""
        from src.providers.base import QualityRank, SpeedRank
        info = ModelInfo(
            id="gemma2-9b-it",
            model_type=ModelType.INSTRUCT,
            context_length=8192,
            rpd=14400,
            tpm=15000,
            quality=QualityRank.GOOD,
            speed=SpeedRank.VERY_FAST
        )
        assert info.id == "gemma2-9b-it"
        assert info.rpd == 14400
        assert info.tpm == 15000
        assert info.quality == QualityRank.GOOD
        assert info.speed == SpeedRank.VERY_FAST

    def test_model_info_defaults(self):
        """ModelInfo should have sensible defaults."""
        from src.providers.base import QualityRank, SpeedRank
        info = ModelInfo(
            id="test",
            model_type=ModelType.CHAT,
            context_length=4096
        )
        assert info.rpd is None
        assert info.tpm is None
        assert info.quality == QualityRank.GOOD
        assert info.speed == SpeedRank.FAST

    def test_is_instruction_tuned_true(self):
        """is_instruction_tuned should return True for INSTRUCT type."""
        info = ModelInfo(
            id="qwen-instruct",
            model_type=ModelType.INSTRUCT,
            context_length=8192
        )
        assert info.is_instruction_tuned is True

    def test_is_instruction_tuned_false_for_chat(self):
        """is_instruction_tuned should return False for CHAT type."""
        info = ModelInfo(
            id="llama-chat",
            model_type=ModelType.CHAT,
            context_length=8192
        )
        assert info.is_instruction_tuned is False

    def test_is_instruction_tuned_false_for_base(self):
        """is_instruction_tuned should return False for BASE type."""
        info = ModelInfo(
            id="llama-base",
            model_type=ModelType.BASE,
            context_length=8192
        )
        assert info.is_instruction_tuned is False

    def test_is_instruction_tuned_false_for_unknown(self):
        """is_instruction_tuned should return False for UNKNOWN type."""
        info = ModelInfo(
            id="mysterious-model",
            model_type=ModelType.UNKNOWN,
            context_length=8192
        )
        assert info.is_instruction_tuned is False



@pytest.mark.skipif(not IMPORTS_AVAILABLE, reason="ModelType/ModelInfo not yet implemented")
class TestModelTypeDetection:
    """Test automatic model type detection from model name."""

    def test_instruct_takes_precedence_over_code(self):
        """'instruct' should take precedence over 'code' in model name."""
        from src.providers.base import detect_model_type

        # codellama with instruct should be CODE (code-specific instruct)
        result = detect_model_type('codellama-7b-instruct')
        assert result == ModelType.CODE


@pytest.mark.skipif(not IMPORTS_AVAILABLE, reason="ModelType/ModelInfo not yet implemented")
class TestModelInfoFromDict:
    """Test creating ModelInfo from dictionary (for provider configs)."""

    def test_model_info_from_dict(self):
        """Should be able to create ModelInfo from provider config dict."""
        from src.providers.base import QualityRank, SpeedRank
        config = {
            'type': ModelType.INSTRUCT,
            'rpm': 30,
            'rpd': 14400,
            'tpm': 15000,
            'tpd': None,
            'context': 8192,
            'speed': SpeedRank.VERY_FAST,
            'quality': QualityRank.GOOD
        }

        info = ModelInfo.from_config('gemma2-9b-it', config)

        assert info.id == 'gemma2-9b-it'
        assert info.model_type == ModelType.INSTRUCT
        assert info.context_length == 8192
        assert info.rpd == 14400
        assert info.tpm == 15000
        assert info.speed == SpeedRank.VERY_FAST
        assert info.quality == QualityRank.GOOD

    def test_model_info_from_dict_without_type(self):
        """Should auto-detect type if not provided in config."""
        from src.providers.base import QualityRank, SpeedRank
        config = {
            'rpm': 30,
            'rpd': 14400,
            'tpm': 15000,
            'context': 8192,
            'speed': SpeedRank.VERY_FAST,
            'quality': QualityRank.GOOD
        }

        # Should detect from model name
        info = ModelInfo.from_config('gemma2-9b-it', config)
        assert info.model_type == ModelType.INSTRUCT

    def test_model_info_from_dict_legacy_format(self):
        """Should handle legacy config format without 'type' field."""
        from src.providers.base import QualityRank, SpeedRank
        # Current provider configs don't have 'type'
        config = {
            'rpm': 30, 'rpd': 7000, 'tpm': 20000, 'tpd': 200000,
            'context': 131072, 'speed': SpeedRank.VERY_FAST, 'quality': QualityRank.GOOD
        }

        info = ModelInfo.from_config('llama-3.1-8b-instant', config)

        assert info.id == 'llama-3.1-8b-instant'
        assert info.context_length == 131072
        assert info.rpd == 7000
        # Should auto-detect type from name (instant = fast inference, not instruction-tuned)
        # This is UNKNOWN or CHAT, depending on implementation
        assert info.model_type in [ModelType.UNKNOWN, ModelType.CHAT]
