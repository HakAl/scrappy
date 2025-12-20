Gemini rate limit errors are now parsed to extract retry delay. When Gemini returns a 429, the router automatically skips it until the retry window passes.
