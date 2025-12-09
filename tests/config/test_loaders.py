"""
Tests for configuration loaders.

These tests verify:
- FileConfigLoader handles missing files correctly
- FileConfigLoader parses YAML and JSON
- FileConfigLoader raises errors for invalid content
- ChainedConfigLoader merges configs correctly
"""

from pathlib import Path

import pytest

from scrappy.config.loaders import (
    ChainedConfigLoader,
    FileConfigLoader,
    FileSystemProtocol,
)
from scrappy.config.protocols import ConfigLoadError


class FakeFileSystem:
    """
    Fake file system for testing without real I/O.

    This test double implements FileSystemProtocol.
    """

    def __init__(self) -> None:
        self.files: dict[Path, str] = {}

    def exists(self, path: Path) -> bool:
        return path in self.files

    def read_text(self, path: Path) -> str:
        if path not in self.files:
            raise FileNotFoundError(f"No such file: {path}")
        return self.files[path]

    def add_file(self, path: Path, content: str) -> None:
        """Add a file to the fake file system."""
        self.files[path] = content


class TestFileConfigLoaderMissingFile:
    """Tests for FileConfigLoader behavior when file is missing."""

    @pytest.mark.unit
    def test_returns_empty_dict_when_file_missing(self):
        """Should return empty dict when config file does not exist."""
        fs = FakeFileSystem()
        loader = FileConfigLoader(Path(".scrappy.yaml"), file_system=fs)

        result = loader.load()

        assert result == {}



class TestFileConfigLoaderYAML:
    """Tests for FileConfigLoader YAML parsing."""

    @pytest.mark.unit
    def test_parses_yaml_file(self):
        """Should parse valid YAML content."""
        fs = FakeFileSystem()
        fs.add_file(
            Path(".scrappy.yaml"),
            """
clarification:
  confidence_threshold: 0.6
  high_confidence_bypass: 0.85
""",
        )
        loader = FileConfigLoader(Path(".scrappy.yaml"), file_system=fs)

        result = loader.load()

        assert result == {
            "clarification": {
                "confidence_threshold": 0.6,
                "high_confidence_bypass": 0.85,
            }
        }

    @pytest.mark.unit
    def test_parses_yml_extension(self):
        """Should parse .yml files same as .yaml."""
        fs = FakeFileSystem()
        fs.add_file(Path("config.yml"), "key: value")
        loader = FileConfigLoader(Path("config.yml"), file_system=fs)

        result = loader.load()

        assert result == {"key": "value"}

    @pytest.mark.unit
    def test_returns_empty_dict_for_empty_yaml(self):
        """Should return empty dict for empty YAML file."""
        fs = FakeFileSystem()
        fs.add_file(Path("empty.yaml"), "")
        loader = FileConfigLoader(Path("empty.yaml"), file_system=fs)

        result = loader.load()

        assert result == {}

    @pytest.mark.unit
    def test_raises_for_invalid_yaml(self):
        """Should raise ConfigLoadError for invalid YAML syntax."""
        fs = FakeFileSystem()
        fs.add_file(Path("bad.yaml"), "key: [unclosed bracket")
        loader = FileConfigLoader(Path("bad.yaml"), file_system=fs)

        with pytest.raises(ConfigLoadError) as exc_info:
            loader.load()

        assert "Invalid YAML" in str(exc_info.value)

    @pytest.mark.unit
    def test_raises_for_non_mapping_yaml(self):
        """Should raise ConfigLoadError when YAML is not a mapping."""
        fs = FakeFileSystem()
        fs.add_file(Path("list.yaml"), "- item1\n- item2")
        loader = FileConfigLoader(Path("list.yaml"), file_system=fs)

        with pytest.raises(ConfigLoadError) as exc_info:
            loader.load()

        assert "mapping" in str(exc_info.value).lower()


class TestFileConfigLoaderJSON:
    """Tests for FileConfigLoader JSON parsing."""

    @pytest.mark.unit
    def test_parses_json_file(self):
        """Should parse valid JSON content."""
        fs = FakeFileSystem()
        fs.add_file(
            Path(".scrappy.json"),
            '{"clarification": {"confidence_threshold": 0.6}}',
        )
        loader = FileConfigLoader(Path(".scrappy.json"), file_system=fs)

        result = loader.load()

        assert result == {"clarification": {"confidence_threshold": 0.6}}

    @pytest.mark.unit
    def test_raises_for_invalid_json(self):
        """Should raise ConfigLoadError for invalid JSON syntax."""
        fs = FakeFileSystem()
        fs.add_file(Path("bad.json"), "{invalid json}")
        loader = FileConfigLoader(Path("bad.json"), file_system=fs)

        with pytest.raises(ConfigLoadError) as exc_info:
            loader.load()

        assert "Invalid JSON" in str(exc_info.value)

    @pytest.mark.unit
    def test_raises_for_non_object_json(self):
        """Should raise ConfigLoadError when JSON is not an object."""
        fs = FakeFileSystem()
        fs.add_file(Path("array.json"), "[1, 2, 3]")
        loader = FileConfigLoader(Path("array.json"), file_system=fs)

        with pytest.raises(ConfigLoadError) as exc_info:
            loader.load()

        assert "object" in str(exc_info.value).lower()


class TestFileConfigLoaderFormat:
    """Tests for FileConfigLoader format handling."""

    @pytest.mark.unit
    def test_raises_for_unsupported_format(self):
        """Should raise ConfigLoadError for unsupported file format."""
        fs = FakeFileSystem()
        fs.add_file(Path("config.toml"), "[section]\nkey = 'value'")
        loader = FileConfigLoader(Path("config.toml"), file_system=fs)

        with pytest.raises(ConfigLoadError) as exc_info:
            loader.load()

        assert "Unsupported" in str(exc_info.value)
        assert ".toml" in str(exc_info.value)


class TestChainedConfigLoader:
    """Tests for ChainedConfigLoader merging behavior."""

    @pytest.mark.unit
    def test_merges_configs_from_multiple_loaders(self):
        """Should merge configs from multiple sources."""
        fs = FakeFileSystem()
        fs.add_file(Path("defaults.yaml"), "a: 1\nb: 2")
        fs.add_file(Path("user.yaml"), "b: 3\nc: 4")

        loader = ChainedConfigLoader(
            [
                FileConfigLoader(Path("defaults.yaml"), file_system=fs),
                FileConfigLoader(Path("user.yaml"), file_system=fs),
            ]
        )

        result = loader.load()

        assert result == {"a": 1, "b": 3, "c": 4}

    @pytest.mark.unit
    def test_later_loader_overrides_earlier(self):
        """Later loaders should override earlier ones."""
        fs = FakeFileSystem()
        fs.add_file(Path("first.yaml"), "key: first")
        fs.add_file(Path("second.yaml"), "key: second")

        loader = ChainedConfigLoader(
            [
                FileConfigLoader(Path("first.yaml"), file_system=fs),
                FileConfigLoader(Path("second.yaml"), file_system=fs),
            ]
        )

        result = loader.load()

        assert result["key"] == "second"

    @pytest.mark.unit
    def test_deep_merges_nested_dicts(self):
        """Should deep merge nested dictionaries."""
        fs = FakeFileSystem()
        fs.add_file(
            Path("defaults.yaml"),
            """
clarification:
  confidence_threshold: 0.7
  high_confidence_bypass: 0.9
""",
        )
        fs.add_file(
            Path("user.yaml"),
            """
clarification:
  confidence_threshold: 0.6
""",
        )

        loader = ChainedConfigLoader(
            [
                FileConfigLoader(Path("defaults.yaml"), file_system=fs),
                FileConfigLoader(Path("user.yaml"), file_system=fs),
            ]
        )

        result = loader.load()

        # confidence_threshold overridden, high_confidence_bypass preserved
        assert result["clarification"]["confidence_threshold"] == 0.6
        assert result["clarification"]["high_confidence_bypass"] == 0.9

    @pytest.mark.unit
    def test_handles_missing_files_in_chain(self):
        """Should handle missing files gracefully in chain."""
        fs = FakeFileSystem()
        fs.add_file(Path("defaults.yaml"), "a: 1")
        # user.yaml does not exist

        loader = ChainedConfigLoader(
            [
                FileConfigLoader(Path("defaults.yaml"), file_system=fs),
                FileConfigLoader(Path("user.yaml"), file_system=fs),
            ]
        )

        result = loader.load()

        assert result == {"a": 1}

    @pytest.mark.unit
    def test_returns_empty_dict_when_all_missing(self):
        """Should return empty dict when all loaders return empty."""
        fs = FakeFileSystem()

        loader = ChainedConfigLoader(
            [
                FileConfigLoader(Path("a.yaml"), file_system=fs),
                FileConfigLoader(Path("b.yaml"), file_system=fs),
            ]
        )

        result = loader.load()

        assert result == {}


class TestConfigLoaderProtocol:
    """Tests for ConfigLoaderProtocol compliance."""




class TestConfigIntegration:
    """Integration tests for config loading with ClarificationConfig."""

    @pytest.mark.unit
    def test_loads_clarification_config_from_yaml(self):
        """Should load ClarificationConfig from YAML file."""
        from scrappy.task_router.config import ClarificationConfig

        fs = FakeFileSystem()
        fs.add_file(
            Path(".scrappy.yaml"),
            """
clarification:
  confidence_threshold: 0.65
  high_confidence_bypass: 0.88
""",
        )

        loader = FileConfigLoader(Path(".scrappy.yaml"), file_system=fs)
        config_data = loader.load()

        clarification = ClarificationConfig.from_dict(
            config_data.get("clarification", {})
        )

        assert clarification.confidence_threshold == 0.65
        assert clarification.high_confidence_bypass == 0.88

    @pytest.mark.unit
    def test_uses_defaults_when_section_missing(self):
        """Should use defaults when clarification section is missing."""
        from scrappy.task_router.config import ClarificationConfig

        fs = FakeFileSystem()
        fs.add_file(Path(".scrappy.yaml"), "other_section: value")

        loader = FileConfigLoader(Path(".scrappy.yaml"), file_system=fs)
        config_data = loader.load()

        clarification = ClarificationConfig.from_dict(
            config_data.get("clarification", {})
        )

        assert clarification.confidence_threshold == 0.7  # default
        assert clarification.high_confidence_bypass == 0.9  # default
