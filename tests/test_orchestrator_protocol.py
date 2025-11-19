"""
Tests for Orchestrator Protocol.

Tests verify that AgentOrchestrator implements the Orchestrator Protocol,
enabling loose coupling and better testability throughout the codebase.
"""

import pytest
from typing import Dict, Optional, runtime_checkable
from unittest.mock import Mock, AsyncMock

from src.providers.base import LLMResponse
from tests.helpers import ConfigurableTestOrchestrator, make_response


class TestOrchestratorProtocolDefinition:
    """Tests for the Protocol definition itself."""

    def test_protocol_is_importable(self):
        """Protocol can be imported from orchestrator.protocols."""
        from src.orchestrator.protocols import Orchestrator
        assert Orchestrator is not None

    def test_protocol_is_runtime_checkable(self):
        """Protocol is decorated with @runtime_checkable for isinstance checks."""
        from src.orchestrator.protocols import Orchestrator

        # Should be able to use isinstance with Protocol
        # This works because Protocol is decorated with @runtime_checkable
        assert hasattr(Orchestrator, '__protocol_attrs__') or hasattr(Orchestrator, '_is_runtime_protocol')

    def test_protocol_defines_delegate_method(self):
        """Protocol defines delegate method signature."""
        from src.orchestrator.protocols import Orchestrator

        # Check method exists in protocol
        assert hasattr(Orchestrator, 'delegate')

    def test_protocol_defines_delegate_async_method(self):
        """Protocol defines delegate_async method signature."""
        from src.orchestrator.protocols import Orchestrator

        assert hasattr(Orchestrator, 'delegate_async')

    def test_protocol_defines_get_usage_report_method(self):
        """Protocol defines get_usage_report method signature."""
        from src.orchestrator.protocols import Orchestrator

        assert hasattr(Orchestrator, 'get_usage_report')


class TestAgentOrchestratorImplementsProtocol:
    """Tests verifying AgentOrchestrator implements the Orchestrator Protocol."""

    def test_agent_orchestrator_is_instance_of_protocol(self, tmp_path):
        """AgentOrchestrator passes runtime isinstance check for Protocol."""
        from src.orchestrator.protocols import Orchestrator
        from src.orchestrator.core import AgentOrchestrator
        from src.orchestrator.output import NullOutput

        orch = AgentOrchestrator(
            auto_register=False,
            project_path=str(tmp_path),
            output=NullOutput()
        )

        # Runtime check that AgentOrchestrator implements the Protocol
        assert isinstance(orch, Orchestrator)

    def test_agent_orchestrator_has_delegate_method(self, tmp_path):
        """AgentOrchestrator has delegate method with correct signature."""
        from src.orchestrator.core import AgentOrchestrator
        from src.orchestrator.output import NullOutput

        orch = AgentOrchestrator(
            auto_register=False,
            project_path=str(tmp_path),
            output=NullOutput()
        )

        # Verify method exists and is callable
        assert hasattr(orch, 'delegate')
        assert callable(orch.delegate)

    def test_agent_orchestrator_has_delegate_async_method(self, tmp_path):
        """AgentOrchestrator has delegate_async method."""
        from src.orchestrator.core import AgentOrchestrator
        from src.orchestrator.output import NullOutput

        orch = AgentOrchestrator(
            auto_register=False,
            project_path=str(tmp_path),
            output=NullOutput()
        )

        assert hasattr(orch, 'delegate_async')
        assert callable(orch.delegate_async)

    def test_agent_orchestrator_has_get_usage_report_method(self, tmp_path):
        """AgentOrchestrator has get_usage_report method returning dict."""
        from src.orchestrator.core import AgentOrchestrator
        from src.orchestrator.output import NullOutput

        orch = AgentOrchestrator(
            auto_register=False,
            project_path=str(tmp_path),
            output=NullOutput()
        )

        assert hasattr(orch, 'get_usage_report')
        assert callable(orch.get_usage_report)

        # Verify return type
        report = orch.get_usage_report()
        assert isinstance(report, dict)


class TestConfigurableTestOrchestratorImplementsProtocol:
    """Tests verifying ConfigurableTestOrchestrator implements Protocol for testing."""

    def test_configurable_test_orchestrator_is_instance_of_protocol(self):
        """ConfigurableTestOrchestrator passes isinstance check for Protocol."""
        from src.orchestrator.protocols import Orchestrator

        orch = ConfigurableTestOrchestrator()

        assert isinstance(orch, Orchestrator)

    def test_configurable_test_orchestrator_has_required_methods(self):
        """ConfigurableTestOrchestrator has all Protocol-required methods."""
        orch = ConfigurableTestOrchestrator()

        # All required methods exist and are callable
        assert callable(orch.delegate)
        assert callable(orch.get_usage_report)

        # delegate returns LLMResponse
        response = orch.delegate(prompt="test")
        assert isinstance(response, LLMResponse)

        # get_usage_report returns dict
        report = orch.get_usage_report()
        assert isinstance(report, dict)


class TestProtocolAsTypeHint:
    """Tests verifying Protocol can be used as type hint."""

    def test_function_accepts_protocol_type(self):
        """Function with Protocol type hint accepts AgentOrchestrator."""
        from src.orchestrator.protocols import Orchestrator
        from src.orchestrator.core import AgentOrchestrator
        from src.orchestrator.output import NullOutput
        import tempfile

        def use_orchestrator(orch: Orchestrator) -> Dict:
            """Function that uses Orchestrator protocol."""
            return orch.get_usage_report()

        with tempfile.TemporaryDirectory() as tmp:
            orch = AgentOrchestrator(
                auto_register=False,
                project_path=tmp,
                output=NullOutput()
            )

            # Should not raise any errors
            result = use_orchestrator(orch)
            assert isinstance(result, dict)

    def test_function_accepts_test_orchestrator(self):
        """Function with Protocol type hint accepts ConfigurableTestOrchestrator."""
        from src.orchestrator.protocols import Orchestrator

        def use_orchestrator(orch: Orchestrator) -> Dict:
            """Function that uses Orchestrator protocol."""
            return orch.get_usage_report()

        test_orch = ConfigurableTestOrchestrator()

        result = use_orchestrator(test_orch)
        assert isinstance(result, dict)


class TestProtocolMethodSignatures:
    """Tests verifying method signatures match expectations."""

    def test_delegate_accepts_minimal_parameters(self):
        """delegate works with just prompt parameter."""
        orch = ConfigurableTestOrchestrator()

        # Should work with just prompt
        response = orch.delegate(prompt="Hello")
        assert isinstance(response, LLMResponse)

    def test_delegate_accepts_provider_and_prompt(self):
        """delegate works with provider and prompt."""
        orch = ConfigurableTestOrchestrator()

        response = orch.delegate(provider_name="test", prompt="Hello")
        assert isinstance(response, LLMResponse)
        assert response.provider == "test"

    def test_delegate_accepts_common_parameters(self):
        """delegate accepts common parameters like max_tokens, temperature."""
        orch = ConfigurableTestOrchestrator()

        response = orch.delegate(
            prompt="Hello",
            max_tokens=100,
            temperature=0.5
        )
        assert isinstance(response, LLMResponse)

    def test_get_usage_report_returns_expected_structure(self):
        """get_usage_report returns dict with expected keys."""
        orch = ConfigurableTestOrchestrator()

        # Make some calls first
        orch.delegate(prompt="test 1")
        orch.delegate(prompt="test 2")

        report = orch.get_usage_report()

        # Verify structure
        assert 'total_tasks' in report or 'api_calls' in report
        assert 'by_provider' in report


class TestProtocolEnablesPolymorphism:
    """Tests demonstrating Protocol enables polymorphic code."""

    def test_code_works_with_both_implementations(self):
        """Same code works with AgentOrchestrator and test mock."""
        from src.orchestrator.protocols import Orchestrator
        from src.orchestrator.core import AgentOrchestrator
        from src.orchestrator.output import NullOutput
        import tempfile

        def get_task_count(orch: Orchestrator) -> int:
            """Get task count from any Orchestrator implementation."""
            report = orch.get_usage_report()
            return report.get('total_tasks', report.get('api_calls', 0))

        # Works with test orchestrator
        test_orch = ConfigurableTestOrchestrator()
        test_orch.delegate(prompt="test")
        assert get_task_count(test_orch) >= 0

        # Works with real orchestrator
        with tempfile.TemporaryDirectory() as tmp:
            real_orch = AgentOrchestrator(
                auto_register=False,
                project_path=tmp,
                output=NullOutput()
            )
            assert get_task_count(real_orch) >= 0


class TestProtocolWithAsyncMethods:
    """Tests for async method support in Protocol."""

    @pytest.mark.asyncio
    async def test_delegate_async_returns_llm_response(self, tmp_path):
        """delegate_async returns LLMResponse."""
        from src.orchestrator.core import AgentOrchestrator
        from src.orchestrator.output import NullOutput
        from unittest.mock import patch, AsyncMock

        orch = AgentOrchestrator(
            auto_register=False,
            project_path=str(tmp_path),
            output=NullOutput()
        )

        # Mock the actual provider call
        mock_response = make_response(content="async test", provider="test")
        mock_task_record = {}  # Task record returned alongside response

        with patch.object(orch.delegation_manager, 'delegate_async', new_callable=AsyncMock) as mock:
            mock.return_value = (mock_response, mock_task_record)

            response = await orch.delegate_async(
                provider_name="test",
                prompt="Hello async"
            )

            assert isinstance(response, LLMResponse)


class TestProtocolExportedFromModule:
    """Tests verifying Protocol is properly exported."""

    def test_protocol_in_orchestrator_init(self):
        """Protocol is exported from src.orchestrator package."""
        from src.orchestrator import Orchestrator
        assert Orchestrator is not None

    def test_protocol_importable_multiple_ways(self):
        """Protocol can be imported from protocols module or package."""
        from src.orchestrator.protocols import Orchestrator as P1
        from src.orchestrator import Orchestrator as P2

        # Both should be the same class
        assert P1 is P2
