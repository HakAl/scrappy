"""Behavior tests for the LiteLLM error classification contract.

Pins the predicate matrix, the rule precedence order, and the
rule-to-kind / rule-to-class mappings. These tests import ONLY the
classification module: it must stay import-light.
"""

import pytest

from scrappy.infrastructure.exceptions.failure_kinds import FailureKind
from scrappy.infrastructure.exceptions.provider_errors import (
    AuthenticationError,
    NetworkError,
    ProviderExecutionError,
    RateLimitError,
    TimeoutError,
)
from scrappy.orchestrator.provider_error_classification import (
    RULE_TO_EXCEPTION,
    RULE_TO_FAILURE_KIND,
    LiteLLMErrorRule,
    classify_litellm_error,
)


class FakeAuthFailure(Exception):
    """Type name containing 'auth' triggers the AUTH type predicate."""


class FakeRateLimiter(Exception):
    """Type name containing 'rate' triggers the RATE_LIMIT type predicate."""


class FakeConnectionDropped(Exception):
    """Type name containing 'connection' triggers the CONNECTION type predicate."""


class FakeReadTimeout(Exception):
    """Type name containing 'timeout' triggers the TIMEOUT type predicate."""


class TestClassificationMatrix:
    """One probe per trigger: message substrings and type names."""

    @pytest.mark.parametrize(
        ("error", "rule"),
        [
            # AUTH (3): status code, message substring, type name
            (Exception("401 from provider"), LiteLLMErrorRule.AUTH),
            (Exception("request unauthorized"), LiteLLMErrorRule.AUTH),
            (FakeAuthFailure("boom"), LiteLLMErrorRule.AUTH),
            # PAYMENT (4): status code and three message substrings
            (Exception("402 from provider"), LiteLLMErrorRule.PAYMENT),
            (Exception("payment required"), LiteLLMErrorRule.PAYMENT),
            (Exception("billing issue detected"), LiteLLMErrorRule.PAYMENT),
            (Exception("insufficient_quota for key"), LiteLLMErrorRule.PAYMENT),
            # RATE_LIMIT (4): status code, two message substrings, type name
            (Exception("429 from provider"), LiteLLMErrorRule.RATE_LIMIT),
            (Exception("rate limit exceeded"), LiteLLMErrorRule.RATE_LIMIT),
            (Exception("monthly quota exceeded"), LiteLLMErrorRule.RATE_LIMIT),
            (FakeRateLimiter("boom"), LiteLLMErrorRule.RATE_LIMIT),
            # CONNECTION (3): two message substrings, type name
            (Exception("connection refused"), LiteLLMErrorRule.CONNECTION),
            (Exception("host unreachable"), LiteLLMErrorRule.CONNECTION),
            (FakeConnectionDropped("boom"), LiteLLMErrorRule.CONNECTION),
            # TIMEOUT (3): two message substrings, type name
            (Exception("request timed out"), LiteLLMErrorRule.TIMEOUT),
            (Exception("read timeout while streaming"), LiteLLMErrorRule.TIMEOUT),
            (FakeReadTimeout("boom"), LiteLLMErrorRule.TIMEOUT),
            # CONTENT_FILTER (3): content + filter/blocked/safety
            (Exception("content filter triggered"), LiteLLMErrorRule.CONTENT_FILTER),
            (Exception("content was blocked"), LiteLLMErrorRule.CONTENT_FILTER),
            (Exception("content safety violation"), LiteLLMErrorRule.CONTENT_FILTER),
            # MODEL_NOT_FOUND (4): deprecated + model with not found/unknown/invalid
            (Exception("this endpoint is deprecated"), LiteLLMErrorRule.MODEL_NOT_FOUND),
            (Exception("model not found"), LiteLLMErrorRule.MODEL_NOT_FOUND),
            (Exception("model unknown to provider"), LiteLLMErrorRule.MODEL_NOT_FOUND),
            (Exception("model invalid for account"), LiteLLMErrorRule.MODEL_NOT_FOUND),
            # SERVICE_UNAVAILABLE (3)
            (Exception("503 from provider"), LiteLLMErrorRule.SERVICE_UNAVAILABLE),
            (Exception("service unavailable right now"), LiteLLMErrorRule.SERVICE_UNAVAILABLE),
            (Exception("provider overloaded"), LiteLLMErrorRule.SERVICE_UNAVAILABLE),
            # BAD_REQUEST (2)
            (Exception("400 from provider"), LiteLLMErrorRule.BAD_REQUEST),
            (Exception("bad request rejected"), LiteLLMErrorRule.BAD_REQUEST),
            # SERVER_ERROR (2)
            (Exception("500 from provider"), LiteLLMErrorRule.SERVER_ERROR),
            (Exception("internal server error"), LiteLLMErrorRule.SERVER_ERROR),
            # UNKNOWN (1)
            (Exception("totally weird provider failure"), LiteLLMErrorRule.UNKNOWN),
        ],
    )
    def test_probe_classifies_to_rule(self, error, rule):
        assert classify_litellm_error(error) is rule


class TestPrecedence:
    """Earlier rules win when a probe matches multiple predicates."""

    def test_insufficient_quota_is_payment_not_rate_limit(self):
        # "quota" also matches the RATE_LIMIT predicate; PAYMENT is earlier.
        assert classify_litellm_error(
            Exception("insufficient_quota on account")
        ) is LiteLLMErrorRule.PAYMENT

    def test_401_timed_out_is_auth_not_timeout(self):
        # "timed out" also matches TIMEOUT; AUTH is earlier.
        assert classify_litellm_error(
            Exception("401 request timed out")
        ) is LiteLLMErrorRule.AUTH

    def test_429_connection_reset_is_rate_limit_not_connection(self):
        # "connection" also matches CONNECTION; RATE_LIMIT is earlier.
        assert classify_litellm_error(
            Exception("429 connection reset")
        ) is LiteLLMErrorRule.RATE_LIMIT


class TestRuleToFailureKind:
    """Every rule maps to its pinned FailureKind."""

    @pytest.mark.parametrize(
        ("rule", "kind"),
        [
            (LiteLLMErrorRule.AUTH, FailureKind.AUTH),
            (LiteLLMErrorRule.PAYMENT, FailureKind.PAYMENT_REQUIRED),
            (LiteLLMErrorRule.RATE_LIMIT, FailureKind.RATE_LIMIT),
            (LiteLLMErrorRule.CONNECTION, FailureKind.NETWORK),
            (LiteLLMErrorRule.TIMEOUT, FailureKind.TIMEOUT),
            (LiteLLMErrorRule.CONTENT_FILTER, FailureKind.CONTENT_REFUSED),
            (LiteLLMErrorRule.MODEL_NOT_FOUND, FailureKind.DEPRECATED),
            (LiteLLMErrorRule.SERVICE_UNAVAILABLE, FailureKind.SERVER_ERROR),
            (LiteLLMErrorRule.BAD_REQUEST, FailureKind.UNKNOWN),
            (LiteLLMErrorRule.SERVER_ERROR, FailureKind.SERVER_ERROR),
            (LiteLLMErrorRule.UNKNOWN, FailureKind.UNKNOWN),
        ],
    )
    def test_rule_maps_to_kind(self, rule, kind):
        assert RULE_TO_FAILURE_KIND[rule] is kind


class TestRuleToException:
    """Every rule maps to its pinned exception class."""

    @pytest.mark.parametrize(
        ("rule", "exception_class"),
        [
            (LiteLLMErrorRule.AUTH, AuthenticationError),
            (LiteLLMErrorRule.PAYMENT, ProviderExecutionError),
            (LiteLLMErrorRule.RATE_LIMIT, RateLimitError),
            (LiteLLMErrorRule.CONNECTION, NetworkError),
            (LiteLLMErrorRule.TIMEOUT, TimeoutError),
            (LiteLLMErrorRule.CONTENT_FILTER, ProviderExecutionError),
            (LiteLLMErrorRule.MODEL_NOT_FOUND, ProviderExecutionError),
            (LiteLLMErrorRule.SERVICE_UNAVAILABLE, ProviderExecutionError),
            (LiteLLMErrorRule.BAD_REQUEST, ProviderExecutionError),
            (LiteLLMErrorRule.SERVER_ERROR, ProviderExecutionError),
            (LiteLLMErrorRule.UNKNOWN, ProviderExecutionError),
        ],
    )
    def test_rule_maps_to_exception_class(self, rule, exception_class):
        assert RULE_TO_EXCEPTION[rule] is exception_class
