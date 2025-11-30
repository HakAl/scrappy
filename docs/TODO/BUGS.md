## Issues

---
CI failing tests

python 3.10 - ubuntu
=========================== short test summary info ============================
FAILED tests/infrastructure/test_progress.py::test_live_reporter_exception_handling - AssertionError: assert 'Error starting Live progress: Boom' in ''
 +  where '' = <_pytest.logging.LogCaptureFixture object at 0x7f38b01924a0>.text
FAILED tests/test_import_utils.py::TestImportWithFallback::test_import_with_fallback_primary_fails_fallback_success - ImportError
=========== 2 failed, 4591 passed, 7 skipped, 67 warnings in 36.69s ============
Error: Process completed with exit code 1.

python 3.10 - windows
=========================== short test summary info ===========================
FAILED tests/infrastructure/test_progress.py::test_live_reporter_exception_handling - AssertionError: assert 'Error starting Live progress: Boom' in ''
 +  where '' = <_pytest.logging.LogCaptureFixture object at 0x000001C76AE67130>.text
FAILED tests/providers/test_cohere_provider.py::TestCohereProvider::test_chat_basic - AssertionError: assert 0.0 > 0
 +  where 0.0 = LLMResponse(content='Test response from Cohere', model='command-r7b-12-2024', provider='cohere', tokens_used=23, input_tokens=15, output_tokens=8, latency_ms=0.0, raw_response=<Mock name='cohere.ClientV2().chat()' id='1956017355600'>, metadata={'model_config': {'type': 'chat', 'quality': <QualityRank.MODERATE: 'moderate'>, 'speed': <SpeedRank.VERY_FAST: 'very_fast'>, 'context': 128000, 'description': 'Smaller, faster model'}, 'session_calls': 1}, timestamp=datetime.datetime(2025, 11, 30, 2, 35, 21, 236802), tool_calls=None).latency_ms
FAILED tests/providers/test_cohere_provider.py::TestCohereProvider::test_latency_measurement - AssertionError: assert 0.0 > 0
 +  where 0.0 = LLMResponse(content='Test response from Cohere', model='command-r7b-12-2024', provider='cohere', tokens_used=23, input_tokens=15, output_tokens=8, latency_ms=0.0, raw_response=<Mock name='cohere.ClientV2().chat()' id='1956017763136'>, metadata={'model_config': {'type': 'chat', 'quality': <QualityRank.MODERATE: 'moderate'>, 'speed': <SpeedRank.VERY_FAST: 'very_fast'>, 'context': 128000, 'description': 'Smaller, faster model'}, 'session_calls': 1}, timestamp=datetime.datetime(2025, 11, 30, 2, 35, 21, 276276), tool_calls=None).latency_ms
FAILED tests/providers/test_github_models_provider.py::TestGitHubModelsProvider::test_chat_basic - AssertionError: assert 0.0 > 0
 +  where 0.0 = LLMResponse(content='Test response', model='gpt-4o', provider='github', tokens_used=15, input_tokens=10, output_tokens=5, latency_ms=0.0, raw_response=<Mock name='mock.chat.completions.with_raw_response.create().parse()' id='1956013495952'>, metadata={'finish_reason': 'stop', 'model_config': {'rpd': 10000, 'tpd': 10000000, 'context': 128000, 'speed': <SpeedRank.MODERATE: 'moderate'>, 'quality': <QualityRank.EXCELLENT: 'excellent'>}, 'rate_limits': {'remaining_requests': '9999', 'remaining_tokens': '9999995', 'limit_requests': '10000', 'limit_tokens': '10000000'}, 'region': 'eastus'}, timestamp=datetime.datetime(2025, 11, 30, 2, 35, 21, 565487), tool_calls=None).latency_ms
FAILED tests/providers/test_github_models_provider.py::TestGitHubModelsProvider::test_latency_measurement - AssertionError: assert 0.0 > 0
 +  where 0.0 = LLMResponse(content='Test response', model='gpt-4o', provider='github', tokens_used=15, input_tokens=10, output_tokens=5, latency_ms=0.0, raw_response=<Mock name='mock.chat.completions.with_raw_response.create().parse()' id='1956013530160'>, metadata={'finish_reason': 'stop', 'model_config': {'rpd': 10000, 'tpd': 10000000, 'context': 128000, 'speed': <SpeedRank.MODERATE: 'moderate'>, 'quality': <QualityRank.EXCELLENT: 'excellent'>}, 'rate_limits': {'remaining_requests': '9999', 'remaining_tokens': '9999995', 'limit_requests': '10000', 'limit_tokens': '10000000'}, 'region': 'eastus'}, timestamp=datetime.datetime(2025, 11, 30, 2, 35, 21, 632486), tool_calls=None).latency_ms
FAILED tests/test_import_utils.py::TestImportWithFallback::test_import_with_fallback_primary_fails_fallback_success - ImportError
=========== 6 failed, 4586 passed, 8 skipped, 81 warnings in 49.25s ===========
C:\hostedtoolcache\windows\Python\3.10.11\x64\lib\site-packages\rich\live.py:256: UserWarning: install "ipywidgets" for Jupyter support
  warnings.warn('install "ipywidgets" for Jupyter support')
Error: Process completed with exit code 1.

python 3.11 windows
================================== FAILURES ===================================
_____________________ TestCohereProvider.test_chat_basic ______________________
tests\providers\test_cohere_provider.py:139: in test_chat_basic
    assert response.latency_ms > 0
E   AssertionError: assert 0.0 > 0
E    +  where 0.0 = LLMResponse(content='Test response from Cohere', model='command-r7b-12-2024', provider='cohere', tokens_used=23, input_tokens=15, output_tokens=8, latency_ms=0.0, raw_response=<Mock name='cohere.ClientV2().chat()' id='2184096180624'>, metadata={'model_config': {'type': 'chat', 'quality': <QualityRank.MODERATE: 'moderate'>, 'speed': <SpeedRank.VERY_FAST: 'very_fast'>, 'context': 128000, 'description': 'Smaller, faster model'}, 'session_calls': 1}, timestamp=datetime.datetime(2025, 11, 30, 2, 35, 7, 203751), tool_calls=None).latency_ms
_________________ TestCohereProvider.test_latency_measurement _________________
tests\providers\test_cohere_provider.py:294: in test_latency_measurement
    assert response.latency_ms > 0
E   AssertionError: assert 0.0 > 0
E    +  where 0.0 = LLMResponse(content='Test response from Cohere', model='command-r7b-12-2024', provider='cohere', tokens_used=23, input_tokens=15, output_tokens=8, latency_ms=0.0, raw_response=<Mock name='cohere.ClientV2().chat()' id='2184096126352'>, metadata={'model_config': {'type': 'chat', 'quality': <QualityRank.MODERATE: 'moderate'>, 'speed': <SpeedRank.VERY_FAST: 'very_fast'>, 'context': 128000, 'description': 'Smaller, faster model'}, 'session_calls': 1}, timestamp=datetime.datetime(2025, 11, 30, 2, 35, 7, 796827), tool_calls=None).latency_ms
__________________ TestGitHubModelsProvider.test_chat_basic ___________________
tests\providers\test_github_models_provider.py:147: in test_chat_basic
    assert response.latency_ms > 0
E   AssertionError: assert 0.0 > 0
E    +  where 0.0 = LLMResponse(content='Test response', model='gpt-4o', provider='github', tokens_used=15, input_tokens=10, output_tokens=5, latency_ms=0.0, raw_response=<Mock name='mock.chat.completions.with_raw_response.create().parse()' id='2184100634640'>, metadata={'finish_reason': 'stop', 'model_config': {'rpd': 10000, 'tpd': 10000000, 'context': 128000, 'speed': <SpeedRank.MODERATE: 'moderate'>, 'quality': <QualityRank.EXCELLENT: 'excellent'>}, 'rate_limits': {'remaining_requests': '9999', 'remaining_tokens': '9999995', 'limit_requests': '10000', 'limit_tokens': '10000000'}, 'region': 'eastus'}, timestamp=datetime.datetime(2025, 11, 30, 2, 35, 7, 874941), tool_calls=None).latency_ms
______________ TestGitHubModelsProvider.test_latency_measurement ______________
tests\providers\test_github_models_provider.py:346: in test_latency_measurement
    assert response.latency_ms > 0
E   AssertionError: assert 0.0 > 0
E    +  where 0.0 = LLMResponse(content='Test response', model='gpt-4o', provider='github', tokens_used=15, input_tokens=10, output_tokens=5, latency_ms=0.0, raw_response=<Mock name='mock.chat.completions.with_raw_response.create().parse()' id='2184094873488'>, metadata={'finish_reason': 'stop', 'model_config': {'rpd': 10000, 'tpd': 10000000, 'context': 128000, 'speed': <SpeedRank.MODERATE: 'moderate'>, 'quality': <QualityRank.EXCELLENT: 'excellent'>}, 'rate_limits': {'remaining_requests': '9999', 'remaining_tokens': '9999995', 'limit_requests': '10000', 'limit_tokens': '10000000'}, 'region': 'eastus'}, timestamp=datetime.datetime(2025, 11, 30, 2, 35, 7, 939552), tool_calls=None).latency_ms
=========================== short test summary info ===========================
FAILED tests/providers/test_cohere_provider.py::TestCohereProvider::test_chat_basic - AssertionError: assert 0.0 > 0
 +  where 0.0 = LLMResponse(content='Test response from Cohere', model='command-r7b-12-2024', provider='cohere', tokens_used=23, input_tokens=15, output_tokens=8, latency_ms=0.0, raw_response=<Mock name='cohere.ClientV2().chat()' id='2184096180624'>, metadata={'model_config': {'type': 'chat', 'quality': <QualityRank.MODERATE: 'moderate'>, 'speed': <SpeedRank.VERY_FAST: 'very_fast'>, 'context': 128000, 'description': 'Smaller, faster model'}, 'session_calls': 1}, timestamp=datetime.datetime(2025, 11, 30, 2, 35, 7, 203751), tool_calls=None).latency_ms
FAILED tests/providers/test_cohere_provider.py::TestCohereProvider::test_latency_measurement - AssertionError: assert 0.0 > 0
 +  where 0.0 = LLMResponse(content='Test response from Cohere', model='command-r7b-12-2024', provider='cohere', tokens_used=23, input_tokens=15, output_tokens=8, latency_ms=0.0, raw_response=<Mock name='cohere.ClientV2().chat()' id='2184096126352'>, metadata={'model_config': {'type': 'chat', 'quality': <QualityRank.MODERATE: 'moderate'>, 'speed': <SpeedRank.VERY_FAST: 'very_fast'>, 'context': 128000, 'description': 'Smaller, faster model'}, 'session_calls': 1}, timestamp=datetime.datetime(2025, 11, 30, 2, 35, 7, 796827), tool_calls=None).latency_ms
FAILED tests/providers/test_github_models_provider.py::TestGitHubModelsProvider::test_chat_basic - AssertionError: assert 0.0 > 0
 +  where 0.0 = LLMResponse(content='Test response', model='gpt-4o', provider='github', tokens_used=15, input_tokens=10, output_tokens=5, latency_ms=0.0, raw_response=<Mock name='mock.chat.completions.with_raw_response.create().parse()' id='2184100634640'>, metadata={'finish_reason': 'stop', 'model_config': {'rpd': 10000, 'tpd': 10000000, 'context': 128000, 'speed': <SpeedRank.MODERATE: 'moderate'>, 'quality': <QualityRank.EXCELLENT: 'excellent'>}, 'rate_limits': {'remaining_requests': '9999', 'remaining_tokens': '9999995', 'limit_requests': '10000', 'limit_tokens': '10000000'}, 'region': 'eastus'}, timestamp=datetime.datetime(2025, 11, 30, 2, 35, 7, 874941), tool_calls=None).latency_ms
FAILED tests/providers/test_github_models_provider.py::TestGitHubModelsProvider::test_latency_measurement - AssertionError: assert 0.0 > 0
 +  where 0.0 = LLMResponse(content='Test response', model='gpt-4o', provider='github', tokens_used=15, input_tokens=10, output_tokens=5, latency_ms=0.0, raw_response=<Mock name='mock.chat.completions.with_raw_response.create().parse()' id='2184094873488'>, metadata={'finish_reason': 'stop', 'model_config': {'rpd': 10000, 'tpd': 10000000, 'context': 128000, 'speed': <SpeedRank.MODERATE: 'moderate'>, 'quality': <QualityRank.EXCELLENT: 'excellent'>}, 'rate_limits': {'remaining_requests': '9999', 'remaining_tokens': '9999995', 'limit_requests': '10000', 'limit_tokens': '10000000'}, 'region': 'eastus'}, timestamp=datetime.datetime(2025, 11, 30, 2, 35, 7, 939552), tool_calls=None).latency_ms
================= 4 failed, 4588 passed, 8 skipped in 42.39s ==================
Error: Process completed with exit code 1.

python 3.12 windows
================================== FAILURES ===================================
_____________________ TestCohereProvider.test_chat_basic ______________________
tests\providers\test_cohere_provider.py:139: in test_chat_basic
    assert response.latency_ms > 0
E   AssertionError: assert 0.0 > 0
E    +  where 0.0 = LLMResponse(content='Test response from Cohere', model='command-r7b-12-2024', provider='cohere', tokens_used=23, input_tokens=15, output_tokens=8, latency_ms=0.0, raw_response=<Mock name='cohere.ClientV2().chat()' id='2464960152448'>, metadata={'model_config': {'type': 'chat', 'quality': <QualityRank.MODERATE: 'moderate'>, 'speed': <SpeedRank.VERY_FAST: 'very_fast'>, 'context': 128000, 'description': 'Smaller, faster model'}, 'session_calls': 1}, timestamp=datetime.datetime(2025, 11, 30, 2, 35, 8, 343096), tool_calls=None).latency_ms
_________________ TestCohereProvider.test_latency_measurement _________________
tests\providers\test_cohere_provider.py:294: in test_latency_measurement
    assert response.latency_ms > 0
E   AssertionError: assert 0.0 > 0
E    +  where 0.0 = LLMResponse(content='Test response from Cohere', model='command-r7b-12-2024', provider='cohere', tokens_used=23, input_tokens=15, output_tokens=8, latency_ms=0.0, raw_response=<Mock name='cohere.ClientV2().chat()' id='2464994675120'>, metadata={'model_config': {'type': 'chat', 'quality': <QualityRank.MODERATE: 'moderate'>, 'speed': <SpeedRank.VERY_FAST: 'very_fast'>, 'context': 128000, 'description': 'Smaller, faster model'}, 'session_calls': 1}, timestamp=datetime.datetime(2025, 11, 30, 2, 35, 8, 893783), tool_calls=None).latency_ms
__________________ TestGitHubModelsProvider.test_chat_basic ___________________
tests\providers\test_github_models_provider.py:147: in test_chat_basic
    assert response.latency_ms > 0
E   AssertionError: assert 0.0 > 0
E    +  where 0.0 = LLMResponse(content='Test response', model='gpt-4o', provider='github', tokens_used=15, input_tokens=10, output_tokens=5, latency_ms=0.0, raw_response=<Mock name='mock.chat.completions.with_raw_response.create().parse()' id='2465015689584'>, metadata={'finish_reason': 'stop', 'model_config': {'rpd': 10000, 'tpd': 10000000, 'context': 128000, 'speed': <SpeedRank.MODERATE: 'moderate'>, 'quality': <QualityRank.EXCELLENT: 'excellent'>}, 'rate_limits': {'remaining_requests': '9999', 'remaining_tokens': '9999995', 'limit_requests': '10000', 'limit_tokens': '10000000'}, 'region': 'eastus'}, timestamp=datetime.datetime(2025, 11, 30, 2, 35, 8, 953234), tool_calls=None).latency_ms
______________ TestGitHubModelsProvider.test_latency_measurement ______________
tests\providers\test_github_models_provider.py:346: in test_latency_measurement
    assert response.latency_ms > 0
E   AssertionError: assert 0.0 > 0
E    +  where 0.0 = LLMResponse(content='Test response', model='gpt-4o', provider='github', tokens_used=15, input_tokens=10, output_tokens=5, latency_ms=0.0, raw_response=<Mock name='mock.chat.completions.with_raw_response.create().parse()' id='2465015770496'>, metadata={'finish_reason': 'stop', 'model_config': {'rpd': 10000, 'tpd': 10000000, 'context': 128000, 'speed': <SpeedRank.MODERATE: 'moderate'>, 'quality': <QualityRank.EXCELLENT: 'excellent'>}, 'rate_limits': {'remaining_requests': '9999', 'remaining_tokens': '9999995', 'limit_requests': '10000', 'limit_tokens': '10000000'}, 'region': 'eastus'}, timestamp=datetime.datetime(2025, 11, 30, 2, 35, 8, 997986), tool_calls=None).latency_ms
============================== warnings summary ===============================
C:\hostedtoolcache\windows\Python\3.12.10\x64\Lib\site-packages\onnxruntime\capi\onnxruntime_validation.py:27
  C:\hostedtoolcache\windows\Python\3.12.10\x64\Lib\site-packages\onnxruntime\capi\onnxruntime_validation.py:27: UserWarning: Unsupported Windows version (2025server). ONNX Runtime supports Windows 10 and above, only.
    warnings.warn(

-- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html
=========================== short test summary info ===========================
FAILED tests/providers/test_cohere_provider.py::TestCohereProvider::test_chat_basic - AssertionError: assert 0.0 > 0
 +  where 0.0 = LLMResponse(content='Test response from Cohere', model='command-r7b-12-2024', provider='cohere', tokens_used=23, input_tokens=15, output_tokens=8, latency_ms=0.0, raw_response=<Mock name='cohere.ClientV2().chat()' id='2464960152448'>, metadata={'model_config': {'type': 'chat', 'quality': <QualityRank.MODERATE: 'moderate'>, 'speed': <SpeedRank.VERY_FAST: 'very_fast'>, 'context': 128000, 'description': 'Smaller, faster model'}, 'session_calls': 1}, timestamp=datetime.datetime(2025, 11, 30, 2, 35, 8, 343096), tool_calls=None).latency_ms
FAILED tests/providers/test_cohere_provider.py::TestCohereProvider::test_latency_measurement - AssertionError: assert 0.0 > 0
 +  where 0.0 = LLMResponse(content='Test response from Cohere', model='command-r7b-12-2024', provider='cohere', tokens_used=23, input_tokens=15, output_tokens=8, latency_ms=0.0, raw_response=<Mock name='cohere.ClientV2().chat()' id='2464994675120'>, metadata={'model_config': {'type': 'chat', 'quality': <QualityRank.MODERATE: 'moderate'>, 'speed': <SpeedRank.VERY_FAST: 'very_fast'>, 'context': 128000, 'description': 'Smaller, faster model'}, 'session_calls': 1}, timestamp=datetime.datetime(2025, 11, 30, 2, 35, 8, 893783), tool_calls=None).latency_ms
FAILED tests/providers/test_github_models_provider.py::TestGitHubModelsProvider::test_chat_basic - AssertionError: assert 0.0 > 0
 +  where 0.0 = LLMResponse(content='Test response', model='gpt-4o', provider='github', tokens_used=15, input_tokens=10, output_tokens=5, latency_ms=0.0, raw_response=<Mock name='mock.chat.completions.with_raw_response.create().parse()' id='2465015689584'>, metadata={'finish_reason': 'stop', 'model_config': {'rpd': 10000, 'tpd': 10000000, 'context': 128000, 'speed': <SpeedRank.MODERATE: 'moderate'>, 'quality': <QualityRank.EXCELLENT: 'excellent'>}, 'rate_limits': {'remaining_requests': '9999', 'remaining_tokens': '9999995', 'limit_requests': '10000', 'limit_tokens': '10000000'}, 'region': 'eastus'}, timestamp=datetime.datetime(2025, 11, 30, 2, 35, 8, 953234), tool_calls=None).latency_ms
FAILED tests/providers/test_github_models_provider.py::TestGitHubModelsProvider::test_latency_measurement - AssertionError: assert 0.0 > 0
 +  where 0.0 = LLMResponse(content='Test response', model='gpt-4o', provider='github', tokens_used=15, input_tokens=10, output_tokens=5, latency_ms=0.0, raw_response=<Mock name='mock.chat.completions.with_raw_response.create().parse()' id='2465015770496'>, metadata={'finish_reason': 'stop', 'model_config': {'rpd': 10000, 'tpd': 10000000, 'context': 128000, 'speed': <SpeedRank.MODERATE: 'moderate'>, 'quality': <QualityRank.EXCELLENT: 'excellent'>}, 'rate_limits': {'remaining_requests': '9999', 'remaining_tokens': '9999995', 'limit_requests': '10000', 'limit_tokens': '10000000'}, 'region': 'eastus'}, timestamp=datetime.datetime(2025, 11, 30, 2, 35, 8, 997986), tool_calls=None).latency_ms
============ 4 failed, 4588 passed, 8 skipped, 1 warning in 41.99s ============
Error: Process completed with exit code 1.

python 3.10 - mac
=========================== short test summary info ============================
FAILED tests/infrastructure/test_progress.py::test_live_reporter_exception_handling - AssertionError: assert 'Error starting Live progress: Boom' in ''
 +  where '' = <_pytest.logging.LogCaptureFixture object at 0x117454460>.text
FAILED tests/test_import_utils.py::TestImportWithFallback::test_import_with_fallback_primary_fails_fallback_success - ImportError
=========== 2 failed, 4591 passed, 7 skipped, 48 warnings in 32.72s ============
Error: Process completed with exit code 1.
---

---
src/agent.py
src/orchestrator.py
---

---
automatically explore?
---

---
src/agent/core.py -- _format_codebase_structure -- does this belong here?
---

---
Problem: Provider output is truncated.
EG:  Available Providers:
 --------------------------------------------------

 GITHUB
 (Active)
   Default Model: gpt-4o
   Daily Quota: 10,000 requests
   Daily Tokens: 10,000,000 TPD
   Models: gpt-4o, gpt-4o-mini, deepseek-r1
            ... and 6 more

 CEREBRAS
 (Active)
   Default Model: qwen-3-235b-a22b-instruct-2507
   Daily Quota: 14,400 requests
   Token Limit: 60,000 TPM
   Models: llama3.1-8b, llama-3.3-70b, qwen-3-32b
            ... and 1 more

 GROQ
 (Active)
   Default Model: llama-3.1-8b-instant
   Daily Quota: 7,000 requests
   Token Limit: 20,000 TPM
   Daily Tokens: 200,000 TPD
   Models: llama-3.1-8b-instant, llama-3.3-70b-versatile, llama-3.1-70b-versatile
            ... and 3 more

 GEMINI
 (Active)
   Default Model: gemini-2.5-flash-lite
   Daily Quota: 1,000 requests
   Daily Tokens: 250,000 TPD
   Models: gemini-2.5-flash-lite, gemini-2.0-flash-lite, gemini-2.0-flash
            ... and 2 more

 COHERE
 (Active)
   Default Model: command-r7b-12-2024
   Models: command-r-08-2024, command-r7b-12-2024, command-a-03-2025
            ... and 3 more
---


---
shift selection is messed up, can't 'unselect' once a point is selected.
can't use mouse scroll during selection.  shift + scrolling
---

---
code search tool is completely useless (command tool has grep)-- more logical as a hybrid with grep/rg + semantic search?
---

===

Unconfirmed / Mixed Behavior
----