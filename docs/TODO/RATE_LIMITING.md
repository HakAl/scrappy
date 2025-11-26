## Rate Limiting

Orchestrator should be aware of rate limits and delegate accordingly.


src\orchestrator\rate_limiter.py

<!-- todo -- define fallback strategies until all providers are exhausted -->
**Issues**
- Defined, not enforced
- warn users of limits when approaching