### Integration Tests (VCR.py)

Record real API calls, replay in CI. Proves integration actually works.

**Scope (deferred):**
- Record responses from each provider
- Verify fallback triggers on rate limit
- Test tool_calls extraction with real response
- Verify streaming works

**Setup:**
```python
import vcr

@vcr.use_cassette('cassettes/groq_completion.yaml')
def test_groq_real_response():
    # First run: hits real API, records to cassette
    # Future runs: replays cassette
    ...
```

**Value:** Catches when providers change their response format.

---

### Streaming

```python
async def stream_completion(
    self,
    model: str,
    messages: list[dict],
    **kwargs
) -> AsyncIterator[str]:
    response = await self._router.acompletion(
        model=model,
        messages=messages,
        stream=True,
        **kwargs
    )
    async for chunk in response:
        if chunk.choices[0].delta.content:
            yield chunk.choices[0].delta.content
```
