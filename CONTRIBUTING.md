# Contributing to Scrappy

First off, thank you for considering contributing! We're excited to have you. 
This project is built by the community, and we welcome contributions of all sizes. 
From creating issues, to fixing typos, to implementing major new features.

This document provides a set of guidelines to help you contribute effectively.

## Table of Contents

- [How to Contribute](#how-to-contribute)
  - [Reporting Bugs](#reporting-bugs)
  - [Suggesting Enhancements](#suggesting-enhancements)
  - [Your First Code Contribution](#your-first-code-contribution)
- [Development Setup](#development-setup)
- [Code Contribution Workflow](#code-contribution-workflow)
  - [Step 1: Fork and Clone the Repository](#step-1-fork-and-clone-the-repository)
  - [Step 2: Create a Virtual Environment](#step-2-create-a-virtual-environment)
  - [Step 3: Create a New Branch](#step-3-create-a-new-branch)
  - [Step 4: Write Code and Tests](#step-4-write-code-and-tests)
  - [Step 5: Run All Tests](#step-5-run-all-tests)
  - [Step 6: Submit a Pull Request](#step-6-submit-a-pull-request)
- [Code Guidelines](#code-guidelines)
- [Test Quality Policy](#test-quality-policy)
  - [What Makes a Good Test](#what-makes-a-good-test)
  - [Red Flags (Avoid These)](#red-flags-avoid-these)
  - [Writing Tests](#writing-tests)
  - [Test Commands](#test-commands)
  - [A Note on Coverage](#a-note-on-coverage)
- [AI-Assisted Development (Beads)](#ai-assisted-development-beads)

## How to Contribute

### Finding Work

Check [GitHub Issues](https://github.com/HakAl/scrappy/issues) for bugs and feature requests. Issues tagged `good
first issue` are great starting points.

### Reporting Bugs

If you find a bug, please open an issue on our GitHub repository. A great bug report includes:
- A clear and descriptive title.
- A step-by-step description of how to reproduce the bug.
- The expected behavior and what happened instead.
- Your operating system, Python version, and any other relevant environment details.
- Images may help for UX issues.

### Suggesting Enhancements

Have an idea for a new feature? We'd love to hear it! Please open an issue and use the "Feature Request" template. This allows us to discuss the idea before any code is written.

### Your First Code Contribution

Unsure where to begin? Look for issues tagged with `good first issue` or `help wanted`. These are tasks that have been identified as good entry points to the project.
A great way to learn a new codebase is by exercising it. 

Run:
```pytest tests/ --cov=src --cov-report=html --cov-report=term-missing```

Open: `htmlcov/index.html`

Find an area that could use more coverage, and get to know it!

## Development Setup

Before you can contribute, you need to set up the project on your local machine.

1.  **Fork the repository** on GitHub.
2.  **Clone your fork** to your local machine:
    ```bash
    git clone https://github.com/YOUR_USERNAME/scrappy.git
    cd scrappy
    ```
3.  **Create a virtual environment**. This isolates the project's dependencies.
    ```bash
    python -m venv .venv
    source .venv/bin/activate  # On Windows, use: .venv\Scripts\activate
    ```
4.  **Install the project in editable mode** with its development dependencies:
    ```bash
    pip install -e ".[dev]"
    ```

## Code Contribution Workflow

Please adhere to the following steps for every code change.

#### Step 1: Fork and Clone the Repository
(See [Development Setup](#development-setup) above)

#### Step 2: Create a Virtual Environment
(See [Development Setup](#development-setup) above)

#### Step 3: Create a New Branch
Create a branch for your changes from the `main` branch. Use a descriptive name, like `fix/login-bug` or `feat/user-authentication`.
```bash
git checkout -b your-branch-name
```

#### Step 4: Write Code and Tests
Implement your bug fix or feature. As you code, write or update tests that prove your changes work correctly and meet the standards in our Test Quality Policy.
For a bug fix, it's often helpful to first write a failing test that reproduces the bug, then write the code to make that test pass. For a new feature, tests should demonstrate that the feature works as expected.

#### Step 5: Run All Tests
Ensure that your changes haven't broken any other part of the project. Run the full test suite.
```bash
# Run all tests
python -m pytest tests/ -v
```

#### Step 6: Submit a Pull Request
Push your branch to your fork on GitHub and open a pull request to the main repository.

A great pull request includes:
- A clear title and a detailed description of the changes.
- A link to the issue it resolves (e.g., "Fixes #123").
- Confirmation that all tests are passing.

---

## Code Guidelines
  Before writing code, read [CLAUDE.md](CLAUDE.md) for architectural principles. Key requirements:

- Protocol-first design (define interfaces before implementations)
- Dependency injection (all dependencies injected via constructors)
- No emojis or special characters

---

## Test Quality Policy

**Write tests that prove features work and provide confidence for changes.**

### What Makes a Good Test

Tests must demonstrate functionality and serve as guardrails for refactoring:

1.  **Test behavior, not implementation** - Verify what the code does, not how it does it internally.
2.  **Cover edge cases and failure modes** - The happy path alone is insufficient; test boundaries, errors, and invalid inputs.
3.  **Prove the feature works** - Tests should fail when requirements break, not when implementation details change.
4.  **Enable confident refactoring** - If you can't refactor without breaking tests, the tests are testing the wrong things.

### Red Flags (Avoid These)

-   Tests that mock everything and verify mock calls instead of outcomes.
-   Tests that only cover the happy path.
-   Tests that break when you refactor but behavior stays the same.
-   Tests that pass when actual functionality is broken.
-   High coverage numbers with no real safety guarantees.

### Writing Tests

When adding or modifying functionality:

1.  **Start with edge cases** - What inputs break this? What are the boundaries?
2.  **Test failure modes** - How should this behave when things go wrong?
3.  **Verify observable outcomes** - Assert on return values, state changes, and side effects users care about.
4.  **Ask: "Does this test give me confidence?"** - If not, rewrite it.

### Test Commands

Our tests rely on `pytest`. Here are the most common commands:
```bash
# Useful mocks can be found in!
tests/helpers.py

# Run all tests with verbose output
python -m pytest tests/ -v

# Run a specific test file
python -m pytest tests/test_<module>.py -v

# Run tests with a coverage report (use as a guide, not a target)
python -m pytest tests/ --cov=src --cov-report=term-missing
```

### A Note on Coverage

Coverage metrics are informational only. High coverage with poor tests provides a false sense of confidence. Focus on test quality: meaningful assertions, edge case coverage, and behavior verification.

---

## AI-Assisted Development (Beads)

This project uses [Beads](https://github.com/steveyegge/beads) for issue tracking during AI-assisted development sessions. Beads is a lightweight, git-backed issue tracker designed for AI coding agents.

### Setup (Optional)

If you're using Claude Code or similar AI assistants, Beads helps maintain context across sessions:

1. **Download the binary** from [Beads releases](https://github.com/steveyegge/beads/releases)
2. **Place it in `.beads/`** directory (already gitignored)
3. **Check current work:** `.beads/bd.exe ready`

### Why Beads?

- **Session continuity** - AI agents lose context between sessions. Beads provides persistent memory.
- **Work discovery** - Track issues discovered during implementation with `bd create --discovered-from <id>`
- **Dependency management** - Model task dependencies so agents know what's blocked

### Quick Reference

```bash
# See what's ready to work on
.beads/bd.exe ready

# See current work in progress
.beads/bd.exe list --status in_progress

# Create a new issue
.beads/bd.exe create "Fix auth bug" -t bug -p 1

# Start working on an issue
.beads/bd.exe update <id> --status in_progress

# Complete an issue
.beads/bd.exe close <id>
```

### For Human Contributors

Beads is optional. You can ignore the `.beads/` directory entirely and use GitHub Issues instead. The two systems are independent.
