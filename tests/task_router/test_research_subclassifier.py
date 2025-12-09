"""
Tests for ResearchSubclassifier.

Tests verify that queries are correctly classified as codebase or general research.
"""

import pytest
from scrappy.task_router.strategies.research_subclassifier import ResearchSubclassifier
from scrappy.task_router.strategies.research_subtype import ResearchSubtype


class TestResearchSubclassifierGeneral:
    """Tests for general knowledge query classification."""

    def test_classifies_person_comparison_as_general(self):
        """Famous programmer comparison is general knowledge."""
        classifier = ResearchSubclassifier()
        result = classifier.classify("who is the best coder, Dijkstra or Turing?", file_index=None)
        assert result == ResearchSubtype.GENERAL

    def test_classifies_invention_question_as_general(self):
        """Questions about who invented something are general."""
        classifier = ResearchSubclassifier()
        result = classifier.classify("who invented Python?", file_index=None)
        assert result == ResearchSubtype.GENERAL

    def test_classifies_historical_question_as_general(self):
        """Historical questions are general knowledge."""
        classifier = ResearchSubclassifier()
        result = classifier.classify("when was the first compiler written?", file_index=None)
        assert result == ResearchSubtype.GENERAL

    def test_classifies_famous_person_question_as_general(self):
        """Questions about famous programmers are general."""
        classifier = ResearchSubclassifier()
        result = classifier.classify("what is Dijkstra famous for?", file_index=None)
        assert result == ResearchSubtype.GENERAL

    def test_classifies_concept_question_as_general(self):
        """Abstract concept questions are general."""
        classifier = ResearchSubclassifier()
        result = classifier.classify("what is a binary search algorithm?", file_index=None)
        assert result == ResearchSubtype.GENERAL

    def test_classifies_algorithm_comparison_as_general(self):
        """Algorithm comparisons are general knowledge."""
        classifier = ResearchSubclassifier()
        result = classifier.classify("which is better, quicksort vs mergesort?", file_index=None)
        assert result == ResearchSubtype.GENERAL

    def test_classifies_language_creation_question_as_general(self):
        """Language history questions are general."""
        classifier = ResearchSubclassifier()
        result = classifier.classify("who created JavaScript?", file_index=None)
        assert result == ResearchSubtype.GENERAL

    def test_classifies_greatest_programmer_as_general(self):
        """Greatest programmer questions are general."""
        classifier = ResearchSubclassifier()
        result = classifier.classify("who is the greatest programmer of all time?", file_index=None)
        assert result == ResearchSubtype.GENERAL


class TestResearchSubclassifierCodebase:
    """Tests for codebase query classification with file_index matching."""

    def test_classifies_file_question_as_codebase(self):
        """Questions about specific files are codebase queries when file matches."""
        classifier = ResearchSubclassifier()
        file_index = {"auth": ["src/auth.py"]}
        result = classifier.classify("what does src/auth.py do?", file_index=file_index)
        assert result == ResearchSubtype.CODEBASE

    def test_classifies_this_project_as_codebase(self):
        """References to 'this project' with matching terms indicate codebase."""
        classifier = ResearchSubclassifier()
        file_index = {"authentication": ["src/auth/login.py"]}
        result = classifier.classify("how does this project handle authentication?", file_index=file_index)
        assert result == ResearchSubtype.CODEBASE

    def test_classifies_function_question_as_codebase(self):
        """Questions about functions in code are codebase when matching file exists."""
        classifier = ResearchSubclassifier()
        file_index = {"auth": ["src/login.py"]}
        result = classifier.classify("explain the login function", file_index=file_index)
        assert result == ResearchSubtype.CODEBASE

    def test_classifies_class_question_as_codebase(self):
        """Questions about classes are codebase when matching file exists."""
        classifier = ResearchSubclassifier()
        file_index = {"services": ["src/user_service.py"]}
        result = classifier.classify("what does the user service class do?", file_index=file_index)
        assert result == ResearchSubtype.CODEBASE

    def test_classifies_directory_question_as_codebase(self):
        """Questions about directories are codebase when matching directory exists."""
        classifier = ResearchSubclassifier()
        file_index = {"components": ["src/components/Header.js"]}
        result = classifier.classify("what is in the src/components/ folder?", file_index=file_index)
        assert result == ResearchSubtype.CODEBASE

    def test_classifies_our_code_as_codebase(self):
        """References to 'our code' indicate codebase when matching terms exist."""
        classifier = ResearchSubclassifier()
        file_index = {"handlers": ["src/error_handling.py"]}
        result = classifier.classify("how is error handling done in our code?", file_index=file_index)
        assert result == ResearchSubtype.CODEBASE

    def test_classifies_method_question_as_codebase(self):
        """Questions about methods are codebase when matching files exist."""
        classifier = ResearchSubclassifier()
        file_index = {"models": ["src/models/save.py"]}
        result = classifier.classify("what parameters does the save method accept?", file_index=file_index)
        assert result == ResearchSubtype.CODEBASE

    def test_classifies_implementation_question_as_codebase(self):
        """Questions about implementation details are codebase when matching terms exist."""
        classifier = ResearchSubclassifier()
        file_index = {"caching": ["src/cache/redis_cache.py"]}
        result = classifier.classify("where is the caching logic implemented?", file_index=file_index)
        assert result == ResearchSubtype.CODEBASE

    def test_classifies_js_file_reference_as_codebase(self):
        """JavaScript file references are codebase when matching file exists."""
        classifier = ResearchSubclassifier()
        file_index = {"components": ["src/App.tsx"]}
        result = classifier.classify("what does App.tsx export?", file_index=file_index)
        assert result == ResearchSubtype.CODEBASE

    def test_classifies_what_does_this_as_codebase(self):
        """'What does this' questions are codebase when function file exists."""
        classifier = ResearchSubclassifier()
        file_index = {"utils": ["src/function.py"]}
        result = classifier.classify("what does this function return?", file_index=file_index)
        assert result == ResearchSubtype.CODEBASE

    def test_classifies_how_does_this_as_codebase(self):
        """'How does this' questions about modules are codebase when module exists."""
        classifier = ResearchSubclassifier()
        file_index = {"core": ["src/module.py"]}
        result = classifier.classify("how does this module work?", file_index=file_index)
        assert result == ResearchSubtype.CODEBASE


class TestResearchSubclassifierContext:
    """Tests for context-aware classification."""

    def test_context_terms_boost_codebase_score(self):
        """Project-specific terms from file_index increase codebase score."""
        classifier = ResearchSubclassifier()
        file_index = {"TaskRouter": ["src/task_router.py"]}
        result = classifier.classify(
            "how does the TaskRouter work?",
            file_index=file_index
        )
        assert result == ResearchSubtype.CODEBASE

    def test_context_with_file_names_helps_classification(self):
        """File names in file_index help with classification."""
        classifier = ResearchSubclassifier()
        file_index = {"modules": ["router.py", "classifier.py", "executor.py"]}
        result = classifier.classify(
            "explain the classifier module",
            file_index=file_index
        )
        assert result == ResearchSubtype.CODEBASE

    def test_general_query_stays_general_despite_context(self):
        """General queries remain general even with file_index."""
        classifier = ResearchSubclassifier()
        file_index = {"agent": ["src/agent_orchestrator.py"]}
        result = classifier.classify(
            "who invented the actor model?",
            file_index=file_index
        )
        assert result == ResearchSubtype.GENERAL


class TestResearchSubclassifierReportedBugs:
    """Tests for specific bug reports from PROMPT_REFINEMENT.md."""

    def test_add_rag_to_this_codebase_is_codebase(self):
        """
        Query about adding RAG should be CODEBASE when RAG-related files exist.

        Query: "how would we add rag to this codebase?"
        Expected: CODEBASE (when matching terms in file_index)
        """
        classifier = ResearchSubclassifier()
        file_index = {"codebase": ["src/codebase_manager.py"]}
        result = classifier.classify("how would we add rag to this codebase?", file_index=file_index)
        assert result == ResearchSubtype.CODEBASE

    def test_add_feature_to_this_codebase_variations(self):
        """Test various 'add X to this codebase' patterns with matching file_index."""
        classifier = ResearchSubclassifier()

        test_cases = [
            ("how would we add rag to this codebase?", {"codebase": ["src/codebase.py"]}),
            ("how can we add authentication to this codebase?", {"authentication": ["src/auth.py"]}),
            ("how do I add logging to this codebase?", {"logging": ["src/logger.py"]}),
            ("what's the best way to add caching to this codebase?", {"caching": ["src/cache.py"]}),
        ]

        for query, file_index in test_cases:
            result = classifier.classify(query, file_index=file_index)
            assert result == ResearchSubtype.CODEBASE, f"Failed for: {query}"

    def test_this_codebase_pattern_matches(self):
        """Verify 'this codebase' pattern matches with codebase files."""
        classifier = ResearchSubclassifier()
        file_index = {"codebase": ["src/codebase.py"]}

        # Direct pattern test - these all contain 'this codebase'
        queries = [
            "explain this codebase",
            "what does this codebase do?",
            "how is this codebase structured?",
            "analyze this codebase",
        ]

        for query in queries:
            result = classifier.classify(query, file_index=file_index)
            assert result == ResearchSubtype.CODEBASE, f"Failed for: {query}"


class TestResearchSubclassifierEdgeCases:
    """Tests for edge cases and ambiguous queries."""

    def test_empty_query_defaults_to_general(self):
        """Empty queries default to general without file_index."""
        classifier = ResearchSubclassifier()
        result = classifier.classify("", file_index=None)
        assert result == ResearchSubtype.GENERAL

    def test_ambiguous_query_defaults_to_general(self):
        """Ambiguous queries default to general without file_index."""
        classifier = ResearchSubclassifier()
        result = classifier.classify("tell me about sorting", file_index=None)
        assert result == ResearchSubtype.GENERAL

    def test_mixed_signals_codebase_wins_with_file_reference(self):
        """When mixed, codebase wins if matching file exists."""
        classifier = ResearchSubclassifier()
        file_index = {"main": ["main.py"]}
        result = classifier.classify("who wrote the main.py file?", file_index=file_index)
        assert result == ResearchSubtype.CODEBASE

    def test_case_insensitive_pattern_matching(self):
        """Pattern matching is case insensitive."""
        classifier = ResearchSubclassifier()
        file_index = {"project": ["src/project.py"]}
        result = classifier.classify("What does THIS PROJECT do?", file_index=file_index)
        assert result == ResearchSubtype.CODEBASE

    def test_urls_not_confused_with_file_paths(self):
        """URLs should not trigger codebase classification without file_index."""
        classifier = ResearchSubclassifier()
        result = classifier.classify("what is at https://example.com/page", file_index=None)
        assert result == ResearchSubtype.GENERAL


class TestResearchSubclassifierFileIndex:
    """Tests for project term extraction using file_index."""

    def test_zen_query_matches_zen_directory_in_file_index(self):
        """Query containing 'zen' matches file_index with .zen/ paths."""
        classifier = ResearchSubclassifier()
        file_index = {
            "zen_category": [
                ".zen/config.json",
                ".zen/templates/base.html",
                "src/zen/parser.py"
            ]
        }
        result = classifier.classify("what is zen?", file_index=file_index)
        assert result == ResearchSubtype.CODEBASE

    def test_task_router_query_matches_task_router_directory(self):
        """Query 'task router' matches task_router/ directory in file_index."""
        classifier = ResearchSubclassifier()
        file_index = {
            "routing": [
                "src/task_router/router.py",
                "src/task_router/strategies/base.py",
                "tests/task_router/test_router.py"
            ]
        }
        result = classifier.classify("how does task router work?", file_index=file_index)
        assert result == ResearchSubtype.CODEBASE

    def test_no_matches_empty_file_index_returns_general(self):
        """No matches with empty file_index returns GENERAL."""
        classifier = ResearchSubclassifier()
        file_index = {}
        result = classifier.classify("what is Python?", file_index=file_index)
        assert result == ResearchSubtype.GENERAL

    def test_no_matches_populated_file_index_returns_general(self):
        """No matches with file_index returns GENERAL (general knowledge question)."""
        classifier = ResearchSubclassifier()
        file_index = {
            "authentication": [
                "src/auth/login.py",
                "src/auth/session.py"
            ]
        }
        result = classifier.classify("what is Python?", file_index=file_index)
        assert result == ResearchSubtype.GENERAL

    def test_matches_category_name_from_file_index_keys(self):
        """Query matches category name from file_index keys."""
        classifier = ResearchSubclassifier()
        file_index = {
            "authentication": ["src/auth/login.py"],
            "database": ["src/db/models.py"]
        }
        result = classifier.classify("how does authentication work?", file_index=file_index)
        assert result == ResearchSubtype.CODEBASE

    def test_matches_file_basename_without_extension(self):
        """Query matches file basename (without extension) from paths."""
        classifier = ResearchSubclassifier()
        file_index = {
            "modules": ["src/orchestrator.py", "src/config.py"]
        }
        result = classifier.classify("explain the orchestrator", file_index=file_index)
        assert result == ResearchSubtype.CODEBASE

    def test_matches_directory_name_from_nested_path(self):
        """Query matches directory name from nested file paths."""
        classifier = ResearchSubclassifier()
        file_index = {
            "strategies": [
                "src/task_router/strategies/research_executor.py",
                "src/task_router/strategies/coding_executor.py"
            ]
        }
        result = classifier.classify("what are the strategies?", file_index=file_index)
        assert result == ResearchSubtype.CODEBASE

    def test_underscore_converted_to_space_for_matching(self):
        """Underscores in file/directory names are converted to spaces for matching."""
        classifier = ResearchSubclassifier()
        file_index = {
            "router": ["src/research_executor.py"]
        }
        # "research executor" (with space) should match "research_executor"
        result = classifier.classify("how does research executor work?", file_index=file_index)
        assert result == ResearchSubtype.CODEBASE

    def test_bigram_matching_from_query(self):
        """Bigrams extracted from query match project terms."""
        classifier = ResearchSubclassifier()
        file_index = {
            "agent": ["src/agent_context.py", "src/agent_factory.py"]
        }
        # "agent context" is a bigram that should match "agent_context" or "agent context"
        result = classifier.classify("explain the agent context system", file_index=file_index)
        assert result == ResearchSubtype.CODEBASE

    def test_case_insensitive_project_term_matching(self):
        """Project term matching is case insensitive."""
        classifier = ResearchSubclassifier()
        file_index = {
            "Router": ["src/TaskRouter.py"]  # Mixed case in file_index
        }
        result = classifier.classify("What is TASKROUTER?", file_index=file_index)
        assert result == ResearchSubtype.CODEBASE


class TestResearchSubclassifierMatchedFiles:
    """Tests for matched files extraction."""

    def test_classify_with_matches_returns_matched_files(self):
        """classify_with_matches returns files matching query terms."""
        classifier = ResearchSubclassifier()
        file_index = {
            "scripts": ["scripts/zen.py", "scripts/zen_lint.py", "scripts/other.py"]
        }
        result = classifier.classify_with_matches("how do we fix the zen script?", file_index=file_index)

        assert result.subtype == ResearchSubtype.CODEBASE
        # "zen" matches zen.py basename
        assert "scripts/zen.py" in result.matched_files
        # "zen_lint" basename doesn't match "zen" query term directly
        # but the "scripts" directory matches "script" (singular form doesn't match plural)
        # Actually only exact matches work, so zen_lint.py won't match unless "zen_lint" is in query

    def test_classify_with_matches_returns_empty_for_general(self):
        """classify_with_matches returns empty files for general queries."""
        classifier = ResearchSubclassifier()
        file_index = {
            "auth": ["src/auth.py"]
        }
        result = classifier.classify_with_matches("who invented Python?", file_index=file_index)

        assert result.subtype == ResearchSubtype.GENERAL
        assert result.matched_files == ()

    def test_matched_files_include_files_from_matching_directory(self):
        """Files in directories matching query terms are included."""
        classifier = ResearchSubclassifier()
        file_index = {
            "core": [
                "src/task_router/router.py",
                "src/task_router/classifier.py",
                "src/other/helper.py"
            ]
        }
        result = classifier.classify_with_matches("how does task router work?", file_index=file_index)

        assert result.subtype == ResearchSubtype.CODEBASE
        assert "src/task_router/router.py" in result.matched_files
        assert "src/task_router/classifier.py" in result.matched_files
        # helper.py should not match since it's in "other" directory
        assert "src/other/helper.py" not in result.matched_files

    def test_matched_files_include_files_with_matching_basename(self):
        """Files with basenames matching query terms are included."""
        classifier = ResearchSubclassifier()
        file_index = {
            "modules": ["src/orchestrator.py", "src/config.py"]
        }
        result = classifier.classify_with_matches("explain the orchestrator", file_index=file_index)

        assert result.subtype == ResearchSubtype.CODEBASE
        assert "src/orchestrator.py" in result.matched_files
        assert "src/config.py" not in result.matched_files


class TestResearchSubclassifierProtocol:
    """Tests verifying protocol compliance."""

    def test_returns_research_subtype_enum(self):
        """classify() returns ResearchSubtype enum values."""
        classifier = ResearchSubclassifier()
        result = classifier.classify("any query", file_index=None)
        assert isinstance(result, ResearchSubtype)

    def test_accepts_file_index_parameter(self):
        """classify() accepts optional file_index parameter."""
        classifier = ResearchSubclassifier()
        file_index = {"category": ["path1.py", "path2.py"]}
        result = classifier.classify("query", file_index=file_index)
        assert isinstance(result, ResearchSubtype)

    def test_accepts_none_file_index(self):
        """classify() works with file_index=None."""
        classifier = ResearchSubclassifier()
        result = classifier.classify("query", file_index=None)
        assert isinstance(result, ResearchSubtype)
