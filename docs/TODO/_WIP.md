Problem: Wizard calls litellm.completion() directly instead of going through llm_service. But llm_service is None when there are no keys.

  Proposed Solution:

  1. LiteLLMService always exists (router is Optional, not required)
    - Add validate_key(model, key) -> (bool, error_msg) method that calls litellm.completion() directly with the provided key
    - Add configure_router(router) method to set router after keys are saved
    - completion() raises clear error if router is None
  2. Factory changes:
    - create_llm_service() always returns LiteLLMService (never None)
    - Router creation is separate - can fail without failing service creation
  3. Wizard changes:
    - Inject llm_service into wizard
    - Call llm_service.validate_key(model, key) instead of validate_api_key()
  4. Post-wizard:
    - Call llm_service.configure_router(new_router) after keys saved
    - delegation_manager can then be created
  5. Remove validate_api_key() from provider_status.py

  Does this approach make sense, or do you see a different/simpler path?