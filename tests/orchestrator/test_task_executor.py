"""
Tests for TaskExecutor.

Tests the task planning, reasoning, synthesis, and context summary functionality.
"""

import json
import pytest
from unittest.mock import Mock, MagicMock

from scrappy.orchestrator.task_executor import TaskExecutor
from scrappy.orchestrator.provider_types import LLMResponse
from tests.helpers import MockLLMService


class TestIsSimpleTask:
    """Tests for _is_simple_task method."""

    def setup_method(self):
        """Set up test fixtures."""
        self.llm_service = MockLLMService()
        self.recorded_tasks = []
        self.executor = TaskExecutor(
            llm_service=self.llm_service,
            record_task=lambda t: self.recorded_tasks.append(t),
        )

    def test_short_task_is_simple(self):
        """Short tasks without multi-step indicators are simple."""
        assert self.executor._is_simple_task("Fix the typo") is True
        assert self.executor._is_simple_task("Run tests") is True
        assert self.executor._is_simple_task("List files") is True

    def test_long_task_is_not_simple(self):
        """Tasks with many words are not simple."""
        long_task = "This is a very long task description that has many words and should not be considered simple"
        assert self.executor._is_simple_task(long_task) is False

    def test_task_with_and_is_not_simple(self):
        """Tasks with 'and' conjunction are not simple."""
        assert self.executor._is_simple_task("Fix the bug and run tests") is False

    def test_task_with_then_is_not_simple(self):
        """Tasks with 'then' conjunction are not simple."""
        assert self.executor._is_simple_task("Build then deploy") is False

    def test_task_with_numbered_steps_is_not_simple(self):
        """Tasks with numbered steps are not simple."""
        assert self.executor._is_simple_task("1. Do this 2. Do that") is False

    def test_task_with_first_second_is_not_simple(self):
        """Tasks with ordinal words are not simple."""
        assert self.executor._is_simple_task("First compile, second test") is False

    def test_task_with_multiple_indicator_is_not_simple(self):
        """Tasks mentioning 'multiple' are not simple."""
        assert self.executor._is_simple_task("Fix multiple bugs") is False

    def test_task_with_several_indicator_is_not_simple(self):
        """Tasks mentioning 'several' are not simple."""
        assert self.executor._is_simple_task("Update several files") is False

    def test_exactly_eight_words_is_simple(self):
        """Exactly 8 words without indicators is simple."""
        task = "Please fix the bug in this file now"  # 8 words
        assert self.executor._is_simple_task(task) is True

    def test_nine_words_is_not_simple(self):
        """More than 8 words is not simple."""
        task = "Please fix the bug in this file right now"  # 9 words
        assert self.executor._is_simple_task(task) is False

    def test_short_but_fifty_chars_is_not_simple(self):
        """Short word count but >= 50 chars is not simple."""
        task = "aaaaaaaaaa bbbbbbbbbb cccccccccc dddddddddd eeeeeeeeee"  # 5 words, 54 chars
        assert self.executor._is_simple_task(task) is False


class TestPlan:
    """Tests for plan method."""

    def setup_method(self):
        """Set up test fixtures."""
        self.recorded_tasks = []

    def test_plan_returns_steps_from_json_response(self):
        """Plan parses JSON array response into steps."""
        json_response = json.dumps([
            {"step": "analyze", "description": "Analyze the code", "provider_type": "quality"},
            {"step": "implement", "description": "Implement changes", "provider_type": "fast"},
        ])
        llm_service = MockLLMService(response_content=json_response)
        executor = TaskExecutor(
            llm_service=llm_service,
            record_task=lambda t: self.recorded_tasks.append(t),
        )

        steps = executor.plan("Refactor the authentication module")

        assert len(steps) == 2
        assert steps[0]["step"] == "analyze"
        assert steps[0]["provider_type"] == "quality"
        assert steps[1]["step"] == "implement"

    def test_plan_skips_for_low_complexity_score(self):
        """Plan returns single step for low complexity tasks."""
        llm_service = MockLLMService()
        executor = TaskExecutor(
            llm_service=llm_service,
            record_task=lambda t: self.recorded_tasks.append(t),
        )

        steps = executor.plan("Simple task", complexity_score=2)

        assert len(steps) == 1
        assert steps[0]["step"] == "execute_task"
        assert steps[0]["description"] == "Simple task"
        assert steps[0]["provider_type"] == "fast"
        # LLM should not be called for simple tasks
        assert llm_service.call_count == 0

    def test_plan_calls_llm_for_high_complexity(self):
        """Plan calls LLM for high complexity tasks."""
        json_response = json.dumps([
            {"step": "step1", "description": "Do something", "provider_type": "quality"},
        ])
        llm_service = MockLLMService(response_content=json_response)
        executor = TaskExecutor(
            llm_service=llm_service,
            record_task=lambda t: self.recorded_tasks.append(t),
        )

        executor.plan("Complex task", complexity_score=7)

        assert llm_service.call_count == 1
        assert llm_service.last_call_kwargs["model"] == "quality"

    def test_plan_includes_context_in_prompt(self):
        """Plan includes context in user prompt when provided."""
        json_response = json.dumps([
            {"step": "step1", "description": "Do it", "provider_type": "fast"},
        ])
        llm_service = MockLLMService(response_content=json_response)
        executor = TaskExecutor(
            llm_service=llm_service,
            record_task=lambda t: self.recorded_tasks.append(t),
        )

        executor.plan("Build feature", context="This is a Python project")

        messages = llm_service.last_call_kwargs["messages"]
        user_message = messages[1]["content"]
        assert "Context:" in user_message
        assert "This is a Python project" in user_message

    def test_plan_handles_markdown_code_block(self):
        """Plan extracts JSON from markdown code blocks."""
        json_content = [
            {"step": "step1", "description": "First step", "provider_type": "quality"},
        ]
        markdown_response = f"```json\n{json.dumps(json_content)}\n```"
        llm_service = MockLLMService(response_content=markdown_response)
        executor = TaskExecutor(
            llm_service=llm_service,
            record_task=lambda t: self.recorded_tasks.append(t),
        )

        steps = executor.plan("Task with markdown response")

        assert len(steps) == 1
        assert steps[0]["step"] == "step1"

    def test_plan_handles_embedded_json_in_text(self):
        """Plan extracts JSON array from surrounding text."""
        response = 'Here is the plan:\n[{"step": "do_it", "description": "Just do it", "provider_type": "fast"}]\nHope this helps!'
        llm_service = MockLLMService(response_content=response)
        executor = TaskExecutor(
            llm_service=llm_service,
            record_task=lambda t: self.recorded_tasks.append(t),
        )

        steps = executor.plan("Task")

        assert len(steps) == 1
        assert steps[0]["step"] == "do_it"

    def test_plan_handles_invalid_json(self):
        """Plan falls back to raw content on invalid JSON."""
        llm_service = MockLLMService(response_content="Not valid JSON at all")
        executor = TaskExecutor(
            llm_service=llm_service,
            record_task=lambda t: self.recorded_tasks.append(t),
        )

        steps = executor.plan("Task")

        assert len(steps) == 1
        assert steps[0]["step"] == "execute_task"
        assert steps[0]["description"] == "Not valid JSON at all"
        assert steps[0]["provider_type"] == "quality"

    def test_plan_records_task(self):
        """Plan records the task with correct type."""
        json_response = json.dumps([{"step": "s1", "description": "d1", "provider_type": "fast"}])
        llm_service = MockLLMService(response_content=json_response)
        executor = TaskExecutor(
            llm_service=llm_service,
            record_task=lambda t: self.recorded_tasks.append(t),
        )

        executor.plan("Task")

        assert len(self.recorded_tasks) == 1
        assert self.recorded_tasks[0]["task_type"] == "planning"

    def test_plan_handles_single_object_response(self):
        """Plan wraps single object in list."""
        json_response = json.dumps({"step": "single", "description": "Only one", "provider_type": "fast"})
        llm_service = MockLLMService(response_content=json_response)
        executor = TaskExecutor(
            llm_service=llm_service,
            record_task=lambda t: self.recorded_tasks.append(t),
        )

        steps = executor.plan("Task")

        assert len(steps) == 1
        assert steps[0]["step"] == "single"

    def test_plan_handles_none_content(self):
        """Plan handles None content from provider."""
        llm_service = MockLLMService(response_content=None)
        # Override to return None content
        original_completion = llm_service.completion_sync

        def completion_with_none(**kwargs):
            response, record = original_completion(**kwargs)
            response.content = None
            return response, record

        llm_service.completion_sync = completion_with_none
        executor = TaskExecutor(
            llm_service=llm_service,
            record_task=lambda t: self.recorded_tasks.append(t),
        )

        steps = executor.plan("Task")

        # Should fall back gracefully
        assert len(steps) == 1
        assert steps[0]["step"] == "execute_task"


class TestReason:
    """Tests for reason method."""

    def setup_method(self):
        """Set up test fixtures."""
        self.recorded_tasks = []

    def test_reason_parses_json_response(self):
        """Reason parses JSON response correctly."""
        json_response = json.dumps({
            "question": "Should we use X?",
            "analysis": "X has pros and cons...",
            "conclusion": "Use X",
            "confidence": "high",
        })
        llm_service = MockLLMService(response_content=json_response)
        executor = TaskExecutor(
            llm_service=llm_service,
            record_task=lambda t: self.recorded_tasks.append(t),
        )

        result = executor.reason("Should we use X?")

        assert result["question"] == "Should we use X?"
        assert result["analysis"] == "X has pros and cons..."
        assert result["conclusion"] == "Use X"
        assert result["confidence"] == "high"

    def test_reason_includes_context(self):
        """Reason includes context in prompt."""
        json_response = json.dumps({
            "question": "Q",
            "analysis": "A",
            "conclusion": "C",
            "confidence": "medium",
        })
        llm_service = MockLLMService(response_content=json_response)
        executor = TaskExecutor(
            llm_service=llm_service,
            record_task=lambda t: self.recorded_tasks.append(t),
        )

        executor.reason("Question?", context="Important context here")

        messages = llm_service.last_call_kwargs["messages"]
        user_message = messages[1]["content"]
        assert "Context: Important context here" in user_message

    def test_reason_includes_evidence(self):
        """Reason includes evidence in prompt."""
        json_response = json.dumps({
            "question": "Q",
            "analysis": "A",
            "conclusion": "C",
            "confidence": "high",
        })
        llm_service = MockLLMService(response_content=json_response)
        executor = TaskExecutor(
            llm_service=llm_service,
            record_task=lambda t: self.recorded_tasks.append(t),
        )

        executor.reason("Question?", evidence=["Fact 1", "Fact 2"])

        messages = llm_service.last_call_kwargs["messages"]
        user_message = messages[1]["content"]
        assert "Evidence to consider:" in user_message
        assert "- Fact 1" in user_message
        assert "- Fact 2" in user_message

    def test_reason_handles_markdown_code_block(self):
        """Reason extracts JSON from markdown code blocks."""
        json_content = {
            "question": "Q",
            "analysis": "A",
            "conclusion": "C",
            "confidence": "low",
        }
        markdown_response = f"```json\n{json.dumps(json_content)}\n```"
        llm_service = MockLLMService(response_content=markdown_response)
        executor = TaskExecutor(
            llm_service=llm_service,
            record_task=lambda t: self.recorded_tasks.append(t),
        )

        result = executor.reason("Question?")

        assert result["confidence"] == "low"

    def test_reason_handles_invalid_json(self):
        """Reason falls back gracefully on invalid JSON."""
        llm_service = MockLLMService(response_content="Just plain text analysis")
        executor = TaskExecutor(
            llm_service=llm_service,
            record_task=lambda t: self.recorded_tasks.append(t),
        )

        result = executor.reason("Question?")

        assert result["question"] == "Question?"
        assert result["analysis"] == "Just plain text analysis"
        assert result["conclusion"] == "See analysis above"
        assert result["confidence"] == "unknown"

    def test_reason_records_task(self):
        """Reason records the task with correct type."""
        json_response = json.dumps({
            "question": "Q",
            "analysis": "A",
            "conclusion": "C",
            "confidence": "high",
        })
        llm_service = MockLLMService(response_content=json_response)
        executor = TaskExecutor(
            llm_service=llm_service,
            record_task=lambda t: self.recorded_tasks.append(t),
        )

        executor.reason("Question?")

        assert len(self.recorded_tasks) == 1
        assert self.recorded_tasks[0]["task_type"] == "reasoning"

    def test_reason_uses_quality_model(self):
        """Reason uses quality model tier."""
        json_response = json.dumps({
            "question": "Q",
            "analysis": "A",
            "conclusion": "C",
            "confidence": "high",
        })
        llm_service = MockLLMService(response_content=json_response)
        executor = TaskExecutor(
            llm_service=llm_service,
            record_task=lambda t: self.recorded_tasks.append(t),
        )

        executor.reason("Question?")

        assert llm_service.last_call_kwargs["model"] == "quality"

    def test_reason_handles_non_dict_response(self):
        """Reason handles non-dict JSON response."""
        llm_service = MockLLMService(response_content='"just a string"')
        executor = TaskExecutor(
            llm_service=llm_service,
            record_task=lambda t: self.recorded_tasks.append(t),
        )

        result = executor.reason("Question?")

        # Should fall back to raw content
        assert result["question"] == "Question?"
        assert result["confidence"] == "unknown"


class TestSynthesize:
    """Tests for synthesize method."""

    def setup_method(self):
        """Set up test fixtures."""
        self.recorded_tasks = []

    def test_synthesize_combines_results(self):
        """Synthesize combines multiple LLM responses."""
        llm_service = MockLLMService(response_content="Combined summary of results")
        executor = TaskExecutor(
            llm_service=llm_service,
            record_task=lambda t: self.recorded_tasks.append(t),
        )

        results = [
            LLMResponse(content="First result", model="model1", provider="provider1", tokens_used=10),
            LLMResponse(content="Second result", model="model2", provider="provider2", tokens_used=20),
        ]

        summary = executor.synthesize(results)

        assert summary == "Combined summary of results"

    def test_synthesize_includes_all_results_in_prompt(self):
        """Synthesize includes all results in the prompt."""
        llm_service = MockLLMService(response_content="Summary")
        executor = TaskExecutor(
            llm_service=llm_service,
            record_task=lambda t: self.recorded_tasks.append(t),
        )

        results = [
            LLMResponse(content="Result A", model="m1", provider="p1", tokens_used=10),
            LLMResponse(content="Result B", model="m2", provider="p2", tokens_used=10),
        ]

        executor.synthesize(results)

        messages = llm_service.last_call_kwargs["messages"]
        user_message = messages[1]["content"]
        assert "Result A" in user_message
        assert "Result B" in user_message
        assert "p1/m1" in user_message
        assert "p2/m2" in user_message

    def test_synthesize_uses_custom_prompt(self):
        """Synthesize uses custom synthesis prompt."""
        llm_service = MockLLMService(response_content="Summary")
        executor = TaskExecutor(
            llm_service=llm_service,
            record_task=lambda t: self.recorded_tasks.append(t),
        )

        results = [
            LLMResponse(content="R1", model="m", provider="p", tokens_used=10),
        ]

        executor.synthesize(results, synthesis_prompt="Custom prompt:")

        messages = llm_service.last_call_kwargs["messages"]
        user_message = messages[1]["content"]
        assert "Custom prompt:" in user_message

    def test_synthesize_records_task(self):
        """Synthesize records the task with correct type."""
        llm_service = MockLLMService(response_content="Summary")
        executor = TaskExecutor(
            llm_service=llm_service,
            record_task=lambda t: self.recorded_tasks.append(t),
        )

        results = [
            LLMResponse(content="R", model="m", provider="p", tokens_used=10),
        ]

        executor.synthesize(results)

        assert len(self.recorded_tasks) == 1
        assert self.recorded_tasks[0]["task_type"] == "synthesis"

    def test_synthesize_uses_quality_model(self):
        """Synthesize uses quality model tier."""
        llm_service = MockLLMService(response_content="Summary")
        executor = TaskExecutor(
            llm_service=llm_service,
            record_task=lambda t: self.recorded_tasks.append(t),
        )

        results = [
            LLMResponse(content="R", model="m", provider="p", tokens_used=10),
        ]

        executor.synthesize(results)

        assert llm_service.last_call_kwargs["model"] == "quality"


class TestGenerateContextSummary:
    """Tests for generate_context_summary method."""

    def setup_method(self):
        """Set up test fixtures."""
        self.recorded_tasks = []

    def test_generate_context_summary_returns_content(self):
        """Generate context summary returns LLM response content."""
        llm_service = MockLLMService(response_content="This is a Python web application...")
        executor = TaskExecutor(
            llm_service=llm_service,
            record_task=lambda t: self.recorded_tasks.append(t),
        )

        summary = executor.generate_context_summary("File list: main.py, utils.py")

        assert summary == "This is a Python web application..."

    def test_generate_context_summary_passes_context_data(self):
        """Generate context summary passes context data to LLM."""
        llm_service = MockLLMService(response_content="Summary")
        executor = TaskExecutor(
            llm_service=llm_service,
            record_task=lambda t: self.recorded_tasks.append(t),
        )

        executor.generate_context_summary("Project files: src/, tests/, README.md")

        messages = llm_service.last_call_kwargs["messages"]
        user_message = messages[1]["content"]
        assert "Project files: src/, tests/, README.md" in user_message

    def test_generate_context_summary_records_task(self):
        """Generate context summary records the task with correct type."""
        llm_service = MockLLMService(response_content="Summary")
        executor = TaskExecutor(
            llm_service=llm_service,
            record_task=lambda t: self.recorded_tasks.append(t),
        )

        executor.generate_context_summary("Context data")

        assert len(self.recorded_tasks) == 1
        assert self.recorded_tasks[0]["task_type"] == "context_analysis"

    def test_generate_context_summary_uses_quality_model(self):
        """Generate context summary uses quality model tier."""
        llm_service = MockLLMService(response_content="Summary")
        executor = TaskExecutor(
            llm_service=llm_service,
            record_task=lambda t: self.recorded_tasks.append(t),
        )

        executor.generate_context_summary("Context data")

        assert llm_service.last_call_kwargs["model"] == "quality"

    def test_generate_context_summary_uses_low_temperature(self):
        """Generate context summary uses low temperature for consistency."""
        llm_service = MockLLMService(response_content="Summary")
        executor = TaskExecutor(
            llm_service=llm_service,
            record_task=lambda t: self.recorded_tasks.append(t),
        )

        executor.generate_context_summary("Context data")

        assert llm_service.last_call_kwargs["temperature"] == 0.3


class TestTaskExecutorInitialization:
    """Tests for TaskExecutor initialization."""

    def test_init_with_required_params(self):
        """TaskExecutor initializes with required parameters."""
        llm_service = MockLLMService()
        record_fn = lambda t: None

        executor = TaskExecutor(llm_service=llm_service, record_task=record_fn)

        assert executor._llm_service is llm_service
        assert executor._record_task is record_fn

    def test_init_ignores_legacy_params(self):
        """TaskExecutor ignores deprecated legacy parameters."""
        llm_service = MockLLMService()
        record_fn = lambda t: None

        # Should not raise even with legacy params
        executor = TaskExecutor(
            llm_service=llm_service,
            record_task=record_fn,
            get_brain_provider=lambda: "old_provider",
            get_brain_name=lambda: "old_name",
        )

        assert executor._llm_service is llm_service
