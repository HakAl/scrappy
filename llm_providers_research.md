# Cloud Model Provider Research Findings

This document summarizes the results of the discovery and integration plan for new cloud-based AI model providers. Developer accounts have been successfully created for all listed providers, and API keys have been secured. The keys are stored in our team's secure credential manager.

Below are the details for each provider's free offering.

---

## 1. Anthropic (Claude Models)

*   **Account Status:** Developer account created. API key secured.
*   **Free Offering:** One-time credit of $5.00 upon sign-up.
*   **Limitations:**
    *   The credits expire 12 months after they are granted.
    *   Usage is subject to rate limits which accommodate evaluation and light development. Once credits are exhausted, a payment method is required.

---

## 2. OpenAI (GPT Models)

*   **Account Status:** Developer account created. API key secured.
*   **Free Offering:** One-time credit of $5.00 for new accounts.
*   **Limitations:**
    *   Credits expire 3 months from the date of creation.
    *   New accounts are subject to "Tier 1" rate limits. For `gpt-4o`, this is typically 5,000 Tokens-Per-Minute (TPM) and 30 Requests-Per-Minute (RPM).
    *   There is no perpetual free tier; service requires payment after credits are used.

---

## 3. Cohere (Command Models)

*   **Account Status:** Developer account created. API key secured.
*   **Free Offering:** A perpetual, rate-limited "Developer" plan for prototyping.
*   **Limitations:**
    *   This is not a credit-based system. Access is continuous but restricted.
    *   The rate limit for the free developer API key is 10 requests per minute for the Chat, Embed, and Rerank endpoints.
    *   Intended for development/prototyping only, not for production use.

---

## 4. Groq (High-Speed Inference)

*   **Account Status:** Developer account created. API key secured.
*   **Free Offering:** A generous, rate-limited free tier.
*   **Limitations:**
    *   Rate limits are high, designed to showcase their LPU performance. Current limits are:
        *   30 Requests-Per-Minute (RPM)
        *   14,400 Requests-Per-Day
    *   Token-per-minute limits vary by model (e.g., 15,000 TPM for Llama 3 8B).
    *   This tier is excellent for performance-intensive development tasks.

---

## 5. Together AI (Model Aggregator)

*   **Account Status:** Developer account created. API key secured.
*   **Free Offering:** A one-time credit of $25.00 upon sign-up.
*   **Limitations:**
    *   Credits are valid for a limited time (typically 12 months).
    *   Can be used to access a very wide range of open-source models.
    *   Once credits are exhausted, a payment method is required to continue using the service.
