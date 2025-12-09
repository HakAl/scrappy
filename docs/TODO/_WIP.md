  Problem Analysis

  Query: "how do we fix the zen script?"


  1. Subclassification issue: The query doesn't match any CODEBASE_PATTERNS (no file extensions, no "this project",
  no "class/function/method")
  2. Context matching is weak: _score_context_matches only looks for PascalCase, snake_case, and file extensions in
  the summary - "zen" as a plain word won't match
  3. Falls back to GENERAL: Since codebase_score == 0 and general_score == 0, it returns GENERAL (line 77)

  What happens:
  1. TaskClassifier -> RESEARCH (correct, it's a question)
  2. ResearchSubclassifier -> GENERAL (wrong! "zen" is project-specific)
  3. ResearchExecutor uses _execute_general_research() with web-only tools
  4. LLM has no project context, gives generic answer

  Root causes:
  1. Subclassifier misses project-specific terms - "zen" isn't PascalCase, snake_case, or a file extension
  2. Context summary is too sparse - Only used for term extraction, not semantic understanding
  3. No file/directory awareness - The .zen/ directory exists but isn't considered

  ---
  Proposed Solution
  
  ---
  3-Step Approach

  1. Project Term Extraction (instant, zero cost)
     - Check words AND n-grams against file index + directory names
     - If matches found -> CODEBASE, pass matches to step 2

  2. Semantic Search Validation (optional, only if step 1 matched)
     - Search for matched terms
     - Enriches context for the LLM response

  3. Default Fallback
     - In project + ambiguous -> CODEBASE
     - Otherwise -> GENERAL

  ---
  Simplified Flow

  def classify_with_context(query: str, file_index: dict, semantic_search) -> tuple[ResearchSubtype, list[str]]:
      # Step 1: Extract project terms (words + bigrams against known files/dirs)
      project_terms = extract_project_terms(query, file_index)

      if project_terms:
          # Step 2: Optional semantic enrichment
          if semantic_search and semantic_search.is_ready():
              # Use matched terms for targeted search
              context = semantic_search.search(" ".join(project_terms))
          return ResearchSubtype.CODEBASE, project_terms

      # Step 3: Fallback
      if file_index:  # We're in a project
          return ResearchSubtype.CODEBASE, []
      return ResearchSubtype.GENERAL, []

  ---
  Why This Works

  | Query                          | Step 1 Result                           | Outcome
                  |
  |--------------------------------|-----------------------------------------|--------------------------------------
  ----------------|
  | "how do we fix the zen script" | ["zen"] matches .zen/                   | CODEBASE + search for "zen"
                  |
  | "explain the task router"      | ["task", "router"] matches task_router/ | CODEBASE + search for "task router"
                  |
  | "who invented Python"          | no matches                              | GENERAL (step 3 fallback, no project
  context needed) |
  | "what does this project do"    | no file matches, but in project         | CODEBASE (step 3 conservative
  default)               |

  Step 2 becomes just "use the terms we found" rather than a separate decision point. Cleaner.