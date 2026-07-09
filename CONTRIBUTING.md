# Contributing to Downstream Breakage Radar

Thank you for your interest in contributing! This guide will help you get set up and make your first contribution.

## Table of Contents

- [Getting Started](#getting-started)
- [Development Environment](#development-environment)
- [Running Tests](#running-tests)
- [Code Style](#code-style)
- [Pull Request Guidelines](#pull-request-guidelines)
- [Reporting Bugs](#reporting-bugs)
- [Suggesting Features](#suggesting-features)

## Getting Started

1. **Fork** the repository on GitHub
2. **Clone** your fork locally:
   ```bash
   git clone https://github.com/<your-username>/breakguard.git
   cd breakguard
   ```
3. **Create a branch** for your change:
   ```bash
   git checkout -b my-feature
   ```

## Development Environment

### Prerequisites

- **Python 3.10+** (3.13 recommended)
- **Git** (for the diff-based scanning)

### Setup

Install the package in editable (development) mode:

```bash
python -m venv .venv
source .venv/bin/activate   # On Windows: .venv\Scripts\activate
pip install -e .
```

There are **no external dependencies** — the project uses only the Python standard library — so that's all you need.

## Running Tests

The test suite uses the built-in `unittest` framework:

```bash
# Run all tests
python -m unittest discover -s tests -v
```

Please make sure all tests pass before submitting a PR. If you're adding a new feature, add corresponding tests.

## Code Style

- **Python 3.10+** — use modern syntax (`list[str]` over `List[str]`, `X | Y` unions where appropriate)
- **Type annotations** — all functions should have complete type hints, including return types
- **No external dependencies** — this is a deliberate design choice. The project must run with only the Python standard library
- **Docstrings** — public functions and classes should have docstrings
- **Keep it simple** — prefer readability over cleverness

### Formatting

We recommend using standard Python formatting tools, but don't enforce a specific formatter. As long as your code is clean and consistent, it will be accepted.

## Pull Request Guidelines

1. **One concern per PR** — keep changes focused. A bug fix and a new feature should be separate PRs
2. **Write a clear title** — e.g., "Add --fail-on flag to exit non-zero above a risk level"
3. **Describe your changes** — explain *what* you changed and *why*. Link to any related issues
4. **Add tests** — if your change adds or modifies behavior, include test coverage
5. **Don't break existing tests** — run the full suite before pushing
6. **Keep the diff small** — smaller PRs are easier to review and merge faster
7. **No generated files** — don't commit `__pycache__`, `.pyc`, or editor configs

### Commit Messages

Use clear, imperative-mood commit messages:

```
Add risk detection for Gradle wrapper files
Fix false positive on internal test fixtures
Update README with JSON output example
```

## Reporting Bugs

Please use the [bug report template](https://github.com/Tahiram32/breakguard/issues/new?template=bug_report.md) when filing issues. Include:

- Steps to reproduce
- Expected vs. actual behavior
- Python version and OS
- Relevant output or error messages

## Suggesting Features

Feature ideas are welcome! Use the [feature request template](https://github.com/Tahiram32/breakguard/issues/new?template=feature_request.md) and describe:

- The problem you're trying to solve
- How you'd like the feature to work
- Any alternatives you've considered

---

Thank you for helping make Downstream Breakage Radar better! ❤️
