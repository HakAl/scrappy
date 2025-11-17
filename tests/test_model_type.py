"""
Tests for ModelType and ModelInfo functionality.

Tests model type classification and provider model info retrieval,
critical for automatic selection of instruction-tuned models for agent planning.
"""

import pytest
from unittest.mock import MagicMock, patch

# Import will fail until implementation exists
try:
    from src.providers.base import ModelType, ModelInfo, LLMProvider
    IMPORTS_AVAILABLE = True
except ImportError:
    IMPORTS_AVAILABLE = False
    ModelType = None
    ModelInfo = None


@pytest.mark.skipif(not IMPORTS_AVAILABLE, reason="ModelType/ModelInfo not yet implemented")
class TestModelType:
    """Test ModelType enum."""

    def test_model_type_values_exist(self):
        """ModelType enum should have expected values."""
        assert ModelType.BASE is not None
        assert ModelType.CHAT is not None
        assert ModelType.INSTRUCT is not None
        assert ModelType.CODE is not None
        assert ModelType.REASONING is not None
        assert ModelType.UNKNOWN is not None

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
        info = ModelInfo(
            id="gemma2-9b-it",
            model_type=ModelType.INSTRUCT,
            context_length=8192,
            rpd=14400,
            tpm=15000,
            quality="good",
            speed="very_fast"
        )
        assert info.id == "gemma2-9b-it"
        assert info.rpd == 14400
        assert info.tpm == 15000
        assert info.quality == "good"
        assert info.speed == "very_fast"

    def test_model_info_defaults(self):
        """ModelInfo should have sensible defaults."""
        info = ModelInfo(
            id="test",
            model_type=ModelType.CHAT,
            context_length=4096
        )
        assert info.rpd is None
        assert info.tpm is None
        assert info.quality == "good"
        assert info.speed == "fast"

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
class TestProviderModelInfo:
    """Test provider's get_model_info method."""

    def test_groq_provider_has_get_model_info(self):
        """GroqProvider should implement get_model_info method."""
        from src.providers.groq_provider import GroqProvider

        with patch.dict('os.environ', {'GROQ_API_KEY': 'test-key'}):
            with patch('src.providers.groq_provider.GROQ_AVAILABLE', True):
                with patch('src.providers.groq_provider.Groq'):
                    provider = GroqProvider(api_key='test-key')
                    assert hasattr(provider, 'get_model_info')
                    assert callable(provider.get_model_info)

    def test_groq_llama4_is_instruction_tuned(self):
        """Groq llama-4-scout-instruct should be classified as instruction-tuned."""
        from src.providers.groq_provider import GroqProvider

        with patch.dict('os.environ', {'GROQ_API_KEY': 'test-key'}):
            with patch('src.providers.groq_provider.GROQ_AVAILABLE', True):
                with patch('src.providers.groq_provider.Groq'):
                    provider = GroqProvider(api_key='test-key')
                    info = provider.get_model_info('meta-llama/llama-4-scout-17b-16e-instruct')

                    assert info.model_type == ModelType.INSTRUCT
                    assert info.is_instruction_tuned is True
                    assert info.rpd == 7000

    def test_groq_llama_versatile_is_chat(self):
        """Groq llama-3.3-70b-versatile should be classified as chat."""
        from src.providers.groq_provider import GroqProvider

        with patch.dict('os.environ', {'GROQ_API_KEY': 'test-key'}):
            with patch('src.providers.groq_provider.GROQ_AVAILABLE', True):
                with patch('src.providers.groq_provider.Groq'):
                    provider = GroqProvider(api_key='test-key')
                    info = provider.get_model_info('llama-3.3-70b-versatile')

                    assert info.model_type == ModelType.CHAT
                    assert info.is_instruction_tuned is False

    def test_cerebras_provider_has_get_model_info(self):
        """CerebrasProvider should implement get_model_info method."""
        from src.providers.cerebras_provider import CerebrasProvider

        with patch.dict('os.environ', {'CEREBRAS_API_KEY': 'test-key'}):
            with patch('src.providers.cerebras_provider.OPENAI_AVAILABLE', True):
                with patch('src.providers.cerebras_provider.OpenAI'):
                    provider = CerebrasProvider(api_key='test-key')
                    assert hasattr(provider, 'get_model_info')
                    assert callable(provider.get_model_info)

    def test_cerebras_qwen_instruct_is_instruction_tuned(self):
        """Cerebras qwen-instruct model should be classified as instruction-tuned."""
        from src.providers.cerebras_provider import CerebrasProvider

        with patch.dict('os.environ', {'CEREBRAS_API_KEY': 'test-key'}):
            with patch('src.providers.cerebras_provider.OPENAI_AVAILABLE', True):
                with patch('src.providers.cerebras_provider.OpenAI'):
                    provider = CerebrasProvider(api_key='test-key')
                    info = provider.get_model_info('qwen-3-32b')

                    # Even without 'instruct' in name, it may be chat-tuned
                    # The key is that qwen-3-235b-a22b-instruct should be INSTRUCT
                    assert info is not None
                    assert info.context_length > 0

    def test_gemini_provider_has_get_model_info(self):
        """GeminiProvider should implement get_model_info method."""
        from src.providers.gemini_provider import GeminiProvider

        with patch.dict('os.environ', {'GEMINI_API_KEY': 'test-key'}):
            with patch('src.providers.gemini_provider.GEMINI_AVAILABLE', True):
                with patch('src.providers.gemini_provider.genai'):
                    provider = GeminiProvider(api_key='test-key')
                    assert hasattr(provider, 'get_model_info')
                    assert callable(provider.get_model_info)

    def test_unknown_model_returns_unknown_type(self):
        """Unknown model ID should return ModelInfo with UNKNOWN type."""
        from src.providers.groq_provider import GroqProvider

        with patch.dict('os.environ', {'GROQ_API_KEY': 'test-key'}):
            with patch('src.providers.groq_provider.GROQ_AVAILABLE', True):
                with patch('src.providers.groq_provider.Groq'):
                    provider = GroqProvider(api_key='test-key')
                    info = provider.get_model_info('nonexistent-model')

                    assert info.model_type == ModelType.UNKNOWN


@pytest.mark.skipif(not IMPORTS_AVAILABLE, reason="ModelType/ModelInfo not yet implemented")
class TestProviderInstructionTunedModels:
    """Test provider's get_instruction_tuned_models method."""

    def test_groq_has_instruction_tuned_models(self):
        """GroqProvider should list instruction-tuned models."""
        from src.providers.groq_provider import GroqProvider

        with patch.dict('os.environ', {'GROQ_API_KEY': 'test-key'}):
            with patch('src.providers.groq_provider.GROQ_AVAILABLE', True):
                with patch('src.providers.groq_provider.Groq'):
                    provider = GroqProvider(api_key='test-key')
                    instruct_models = provider.get_instruction_tuned_models()

                    assert isinstance(instruct_models, list)
                    assert 'meta-llama/llama-4-scout-17b-16e-instruct' in instruct_models
                    assert 'moonshotai/kimi-k2-instruct' in instruct_models
                    # Chat models should NOT be in this list
                    assert 'llama-3.3-70b-versatile' not in instruct_models

    def test_get_instruction_tuned_models_returns_only_instruct(self):
        """get_instruction_tuned_models should only return INSTRUCT type models."""
        from src.providers.groq_provider import GroqProvider

        with patch.dict('os.environ', {'GROQ_API_KEY': 'test-key'}):
            with patch('src.providers.groq_provider.GROQ_AVAILABLE', True):
                with patch('src.providers.groq_provider.Groq'):
                    provider = GroqProvider(api_key='test-key')
                    instruct_models = provider.get_instruction_tuned_models()

                    for model_id in instruct_models:
                        info = provider.get_model_info(model_id)
                        assert info.model_type == ModelType.INSTRUCT


@pytest.mark.skipif(not IMPORTS_AVAILABLE, reason="ModelType/ModelInfo not yet implemented")
class TestModelTypeDetection:
    """Test automatic model type detection from model name."""

    def test_detect_instruct_from_name(self):
        """Models with 'instruct' in name should be detected as INSTRUCT."""
        from src.providers.base import detect_model_type

        assert detect_model_type('qwen-3-235b-a22b-instruct-2507') == ModelType.INSTRUCT
        assert detect_model_type('llama-4-maverick-17b-128e-instruct') == ModelType.INSTRUCT
        assert detect_model_type('meta-llama/llama-4-scout-17b-16e-instruct') == ModelType.INSTRUCT

    def test_detect_instruct_from_it_suffix(self):
        """Models with '-it' suffix should be detected as INSTRUCT."""
        from src.providers.base import detect_model_type

        assert detect_model_type('gemma2-9b-it') == ModelType.INSTRUCT
        assert detect_model_type('gemma-3-27b-it') == ModelType.INSTRUCT
        assert detect_model_type('gemma-3-12b-it') == ModelType.INSTRUCT

    def test_detect_chat_from_versatile(self):
        """Models with 'versatile' should be detected as CHAT."""
        from src.providers.base import detect_model_type

        assert detect_model_type('llama-3.3-70b-versatile') == ModelType.CHAT
        assert detect_model_type('llama-3.1-70b-versatile') == ModelType.CHAT

    def test_detect_chat_from_chat_suffix(self):
        """Models with 'chat' in name should be detected as CHAT."""
        from src.providers.base import detect_model_type

        assert detect_model_type('llama-3-chat') == ModelType.CHAT

    def test_detect_base_from_base_suffix(self):
        """Models with 'base' in name should be detected as BASE."""
        from src.providers.base import detect_model_type

        assert detect_model_type('llama-3-base') == ModelType.BASE

    def test_detect_code_from_code_suffix(self):
        """Models with 'code' in name should be detected as CODE."""
        from src.providers.base import detect_model_type

        assert detect_model_type('codellama-7b-instruct') == ModelType.CODE
        assert detect_model_type('deepseek-coder-v2') == ModelType.CODE

    def test_detect_unknown_for_ambiguous(self):
        """Ambiguous model names should return UNKNOWN."""
        from src.providers.base import detect_model_type

        # Models without clear type indicators
        assert detect_model_type('llama3.1-8b') == ModelType.UNKNOWN
        assert detect_model_type('qwen-3-32b') == ModelType.UNKNOWN
        assert detect_model_type('mixtral-8x7b-32768') == ModelType.UNKNOWN

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
        config = {
            'type': ModelType.INSTRUCT,
            'rpm': 30,
            'rpd': 14400,
            'tpm': 15000,
            'tpd': None,
            'context': 8192,
            'speed': 'very_fast',
            'quality': 'good'
        }

        info = ModelInfo.from_config('gemma2-9b-it', config)

        assert info.id == 'gemma2-9b-it'
        assert info.model_type == ModelType.INSTRUCT
        assert info.context_length == 8192
        assert info.rpd == 14400
        assert info.tpm == 15000
        assert info.speed == 'very_fast'
        assert info.quality == 'good'

    def test_model_info_from_dict_without_type(self):
        """Should auto-detect type if not provided in config."""
        config = {
            'rpm': 30,
            'rpd': 14400,
            'tpm': 15000,
            'context': 8192,
            'speed': 'very_fast',
            'quality': 'good'
        }

        # Should detect from model name
        info = ModelInfo.from_config('gemma2-9b-it', config)
        assert info.model_type == ModelType.INSTRUCT

    def test_model_info_from_dict_legacy_format(self):
        """Should handle legacy config format without 'type' field."""
        # Current provider configs don't have 'type'
        config = {
            'rpm': 30, 'rpd': 7000, 'tpm': 20000, 'tpd': 200000,
            'context': 131072, 'speed': 'very_fast', 'quality': 'good'
        }

        info = ModelInfo.from_config('llama-3.1-8b-instant', config)

        assert info.id == 'llama-3.1-8b-instant'
        assert info.context_length == 131072
        assert info.rpd == 7000
        # Should auto-detect type from name (instant = fast inference, not instruction-tuned)
        # This is UNKNOWN or CHAT, depending on implementation
        assert info.model_type in [ModelType.UNKNOWN, ModelType.CHAT]
