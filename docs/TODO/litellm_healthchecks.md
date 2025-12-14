
1. The Direct Health Check (Best Option)
If you want to verify that a specific model is reachable and your credentials work, use litellm.health_check().[1][2][3] This sends a tiny request to the provider to confirm connectivity.[1][2][3]
code
Python
import litellm

# Sync Health Check
response = litellm.health_check(
    model="gemini/gemini-1.5-flash", 
    api_key="your-api-key"
)
print(response) 
# Returns a dictionary with 'healthy': True/False

# Async Health Check
import asyncio
async def check():
    response = await litellm.ahealth_check(
        model="gemini/gemini-1.5-flash", 
        api_key="your-api-key"
    )
    print(response)

asyncio.run(check())
2. Validate API Key Only
If you just want to know if an API key is valid without necessarily running a full "health check" logic (though it does make a test call internally), you can use check_valid_key().[1][2][3]
code
Python
from litellm import check_valid_key

# Returns True if valid, False if invalid
is_valid = check_valid_key(
    model="gemini/gemini-1.5-flash", 
    api_key="your-api-key"
)

if is_valid:
    print("Key is working!")
else:
    print("Invalid key.")
3. Check Environment Configuration
If you want to check if you have the necessary environment variables set (without making an actual network call), use validate_environment.[1][2][3]
code
Python
from litellm import validate_environment

# Checks if GEMINI_API_KEY is present in os.environ
res = validate_environment(model="gemini/gemini-1.5-flash")

if res['keys_in_environment']:
    print("Environment variables are set.")
else:
    print(f"Missing keys: {res['missing_keys']}")

Health Checks (litellm.health_check / litellm.ahealth_check)
Purpose: Perform a simple check to verify if a specific model endpoint is reachable and if the provided credentials are valid for a minimal interaction. Useful for monitoring and configuration validation.
Detailed Parameters:
model (str): Required. The model identifier string for the endpoint to check (e.g., "gpt-3.5-turbo", "azure/my-healthcheck-deploy").
mode (Literal["completion", "embedding"], optional, default="completion"): Specifies the type of minimal API call to make for the check. "completion" usually tries a very short completion; "embedding" tries a very short embedding.
LiteLLM Overrides & Controls: api_key, api_base, api_version, custom_llm_provider, timeout.
Return Object: litellm.utils.HealthCheckResponse (TypedDict)
healthy (bool): True if the minimal API call succeeded (e.g., received HTTP 200 OK), indicating reachability and valid authentication. False otherwise.
error_message (Optional[str]): If healthy is False, contains a string representation of the error encountered (e.g., "AuthenticationError: Incorrect API key provided", "NotFoundError: The model xyz does not exist", "APIConnectionError: Connection refused").
Example: Checking Multiple Endpoints

import litellm
import os
import asyncio
from typing import Dict, List

# Required Keys in Environment for models being checked

async def run_detailed_health_checks():
    endpoints_to_check: List[Dict[str, str]] = [
        {"name": "OpenAI GPT-3.5", "model": "gpt-3.5-turbo"},
        {"name": "Azure GPT-4 (Example)", "model": "azure/your-gpt4-deployment"}, # Replace with your deployment
        {"name": "Anthropic Claude Haiku", "model": "claude-3-haiku-20240307"},
        {"name": "Invalid Model Name", "model": "this-model-does-not-exist-at-all"},
        {"name": "Ollama Local", "model": "ollama/llama3"} # Needs Ollama running + OLLAMA_API_BASE
    ]

    print("--- Running Detailed Health Checks (Async) ---")
    health_results: Dict[str, Dict] = {}

    for endpoint_info in endpoints_to_check:
        name = endpoint_info["name"]
        model_id = endpoint_info["model"]
        print(f"\nChecking: {name} ({model_id})")
        try:
            # Use async health check
            status = await litellm.ahealth_check(model=model_id, timeout=15) # 15s timeout
            health_results[name] = status
            print(f"  Result -> Healthy: {status.get('healthy')}")
            if not status.get('healthy'):
                print(f"            Error: {status.get('error_message')}")
        except Exception as e:
            # Catch errors in the health_check call itself (e.g., if LiteLLM has internal issue)
            print(f"  Health check call itself failed: {type(e).__name__} - {e}")
            health_results[name] = {"healthy": False, "error_message": f"Health check function error: {e}"}

    print("\n--- Health Check Summary ---")
    for name, status in health_results.items():
         health_str = "✅ Healthy" if status.get('healthy') else f"❌ Unhealthy ({status.get('error_message', 'Unknown error')})"
         print(f"  {name:<30}: {health_str}")

# asyncio.run(run_detailed_health_checks()) # Uncomment to run
(Final sections: Router, Exceptions, Cost, Budget, Utilities, Constants will follow with exhaustive detail)