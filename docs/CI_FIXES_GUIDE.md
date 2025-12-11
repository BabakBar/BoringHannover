# CI Quality Checks: Technical Remediation Guide

**Project**: BoringHannover
**Date**: 2025-12-11
**Status**: 129 linting errors detected by Ruff
**CI Pipeline**: `.github/workflows/ci.yml`

---

## Executive Summary

The CI pipeline has detected 129 linting violations across the codebase. While deployment is functional, these issues range from minor style violations to **critical timezone bugs** that could cause the Monday 5 PM scheduler to fail.

**Priority Breakdown:**
- 🚨 **Critical**: 32 datetime timezone bugs (could break scheduler)
- 🔧 **Auto-fixable**: 46 import/formatting issues (safe to auto-fix)
- ⚠️ **Code Quality**: 51 issues requiring manual review

---

## Table of Contents

1. [Critical Issues: Timezone-Naive Datetimes](#1-critical-timezone-naive-datetimes)
2. [Auto-fixable Issues](#2-auto-fixable-issues)
3. [Code Quality Issues](#3-code-quality-issues)
4. [Execution Strategy](#4-execution-strategy)
5. [Testing & Verification](#5-testing--verification)
6. [Prevention: Pre-commit Hooks](#6-prevention-pre-commit-hooks)
7. [References](#7-references)

---

## 1. Critical: Timezone-Naive Datetimes

### 🚨 Severity: HIGH (Scheduler Impact)

**Errors:**
- `DTZ005` (18 occurrences) - `datetime.now()` without timezone
- `DTZ001` (14 occurrences) - `datetime()` constructor without timezone
- `DTZ007` (2 occurrences) - `strptime()` without timezone

### Why This Matters

The backend runs as a **scheduled task at 17:00 CET** every Monday. Timezone-naive datetimes can cause:

1. **Incorrect event filtering**: Events might be filtered as "past" when they're actually future
2. **DST bugs**: Daylight saving transitions cause 1-hour errors
3. **Server timezone dependency**: Code breaks if server timezone != Europe/Berlin
4. **Data inconsistency**: Mixed timezone-aware and naive datetimes in comparisons

### Example of the Bug

```python
# ❌ WRONG - Server timezone dependent
from datetime import datetime

event_time = datetime.now()  # Uses server's local time (could be UTC!)
if event.start < datetime.now():
    skip_event()  # DANGER: Might skip future events!

# ✅ CORRECT - Explicit timezone
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

BERLIN_TZ = ZoneInfo("Europe/Berlin")
event_time = datetime.now(BERLIN_TZ)
if event.start < datetime.now(BERLIN_TZ):
    skip_event()
```

### How to Fix

**Step 1: Define timezone constant**

Create `src/boringhannover/constants.py`:
```python
"""Project-wide constants."""
from zoneinfo import ZoneInfo

# Berlin timezone for event scheduling
BERLIN_TZ = ZoneInfo("Europe/Berlin")
```

**Step 2: Replace all `datetime.now()` calls**

```python
# Before
now = datetime.now()

# After
from boringhannover.constants import BERLIN_TZ
now = datetime.now(BERLIN_TZ)
```

**Step 3: Replace `datetime()` constructors**

```python
# Before
event_date = datetime(2025, 12, 25, 19, 0)

# After
event_date = datetime(2025, 12, 25, 19, 0, tzinfo=BERLIN_TZ)
```

**Step 4: Fix `strptime()` calls**

```python
# Before
parsed = datetime.strptime("2025-12-25 19:00", "%Y-%m-%d %H:%M")

# After
parsed = datetime.strptime("2025-12-25 19:00", "%Y-%m-%d %H:%M").replace(tzinfo=BERLIN_TZ)
```

### Testing Strategy

```python
# tests/test_timezone_handling.py
from datetime import datetime
from zoneinfo import ZoneInfo
import pytest

def test_all_datetimes_are_timezone_aware():
    """Ensure no timezone-naive datetimes in production code."""
    from boringhannover import fetch_all_events

    events = fetch_all_events()
    for event in events:
        assert event.start.tzinfo is not None, f"Event {event.title} has naive datetime"
        assert event.end.tzinfo is not None, f"Event {event.title} has naive datetime"

def test_berlin_timezone_used():
    """Verify Berlin timezone is consistently used."""
    berlin_tz = ZoneInfo("Europe/Berlin")

    # Test that now() uses Berlin time
    from boringhannover.utils import get_current_time
    now = get_current_time()
    assert now.tzinfo.key == "Europe/Berlin"
```

### References

- [Python datetime docs](https://docs.python.org/3/library/datetime.html#aware-and-naive-objects)
- [zoneinfo module](https://docs.python.org/3/library/zoneinfo.html)
- [PEP 615 – Support for the IANA Time Zone Database](https://peps.python.org/pep-0615/)
- [Ruff DTZ rules](https://docs.astral.sh/ruff/rules/#flake8-datetimez-dtz)

---

## 2. Auto-fixable Issues

### 🔧 Severity: LOW (Style/Formatting)

**Total**: 46 errors (all safe to auto-fix)

### I001: Unsorted Imports (30 occurrences)

**What**: Import statements aren't sorted alphabetically/grouped by type

**Why it matters**: Reduces merge conflicts, improves readability

**Fix**:
```bash
# Auto-fix all import sorting
uv run ruff check --select I --fix src/ tests/

# Or fix everything at once
uv run ruff check --fix src/ tests/
```

**Example**:
```python
# Before
from datetime import datetime
import os
from pathlib import Path
import httpx
from boringhannover.models import Event

# After (auto-formatted)
import os
from datetime import datetime
from pathlib import Path

import httpx

from boringhannover.models import Event
```

### F401: Unused Imports (5 occurrences)

**What**: Imported modules/functions that aren't used in the file

**Why it matters**: Dead code, confuses readers, slows import time

**Fix**:
```bash
uv run ruff check --select F401 --fix src/ tests/
```

**Manual review needed**: Some "unused" imports might be re-exported in `__init__.py` for API purposes. Check before removing.

### TC005: Empty Type-Checking Blocks (3 occurrences)

**What**: `if TYPE_CHECKING:` block with no imports

```python
# Before
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    # Empty! Ruff complains
    pass
```

**Fix**: Remove the empty block or add the intended type imports.

### UP035: Deprecated Import (1 occurrence)

**What**: Using deprecated import paths (e.g., old typing imports)

**Example**:
```python
# Before
from typing import List, Dict

# After (Python 3.9+)
from collections.abc import Sequence, Mapping
# Or use built-in generics (Python 3.9+)
list[str], dict[str, int]
```

**Fix**:
```bash
uv run ruff check --select UP035 --fix src/ tests/
```

---

## 3. Code Quality Issues

### ⚠️ Severity: MEDIUM (Requires Manual Review)

### PLC0415: Import Outside Top-Level (13 occurrences)

**What**: Import statements inside functions instead of at module top

**Example**:
```python
# Found by linter
def scrape_events():
    import httpx  # ❌ Import inside function
    return httpx.get(...)
```

**When it's acceptable**:
- Circular import avoidance
- Optional dependencies (e.g., `import pandas` only when needed)
- Heavy imports in rarely-used code paths

**When to fix**:
- Regular imports that should be at top level
- No circular dependency issues

**How to fix**:
```python
# Move to top
import httpx

def scrape_events():
    return httpx.get(...)
```

**Decision framework**:
1. Try moving import to top
2. If circular import error → keep inside function, add comment explaining why
3. If optional dependency → keep inside function, document in docstring

### RUF022: Unsorted `__all__` (9 occurrences)

**What**: Public API exports in `__all__` aren't alphabetically sorted

**Location**: Likely in `src/boringhannover/__init__.py`

**Why it matters**: Easier to spot duplicates/missing exports

**Fix**:
```python
# Before
__all__ = [
    "Event",
    "main",
    "BaseSource",
    "AstorMovieScraper",
    "fetch_all_events",
]

# After (sorted alphabetically)
__all__ = [
    "AstorMovieScraper",
    "BaseSource",
    "Event",
    "fetch_all_events",
    "main",
]

# OR: Group logically with comments (preferred for APIs)
__all__ = [
    # Core models
    "Event",
    # Aggregator
    "fetch_all_events",
    # Sources
    "BaseSource",
    # Legacy scrapers
    "AstorMovieScraper",
    # Entry point
    "main",
]
```

**Recommendation**: Use logical grouping (add `# ruff: noqa: RUF022` if keeping groups)

### T201: Print Statements (3 occurrences)

**What**: Using `print()` instead of proper logging

**Why it matters**:
- No log levels (can't filter INFO vs ERROR)
- No timestamps
- Can't redirect to files/services
- Lost when running as Docker container

**Fix**:
```python
# Before
print(f"Scraping {venue_name}...")
print(f"ERROR: Failed to fetch {url}")

# After
import logging

logger = logging.getLogger(__name__)

logger.info("Scraping %s", venue_name)
logger.error("Failed to fetch %s", url)
```

**Where to add logging config**:

`src/boringhannover/main.py`:
```python
import logging
import sys

def setup_logging(level: str = "INFO") -> None:
    """Configure logging for the application."""
    logging.basicConfig(
        level=getattr(logging, level.upper()),
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
        stream=sys.stdout,
    )

def main():
    setup_logging(os.getenv("LOG_LEVEL", "INFO"))
    # ... rest of main
```

### ERA001: Commented-out Code (3 occurrences)

**What**: Dead code left in comments

**Example**:
```python
# Old approach (doesn't work)
# events = scrape_old_way()
# events = filter_events(events)

events = fetch_all_events()  # New approach
```

**Fix**: Delete commented code (it's in git history if needed)

**Exception**: Keep if it's:
- Documentation of an alternative approach (add explanation)
- Temporary debugging (add `# TODO: Remove after testing`)

### PLR0911: Too Many Return Statements (3 occurrences)

**What**: Function has >6 return statements (default threshold)

**Why it matters**: Hard to reason about all exit paths

**Example of the problem**:
```python
def parse_event(html):
    if not html:
        return None
    if "sold out" in html:
        return None
    if missing_title:
        return None
    if missing_date:
        return None
    if invalid_venue:
        return None
    if past_event:
        return None
    if duplicate:
        return None
    return event  # Return #8
```

**How to fix**:

Option 1: Combine conditions
```python
def parse_event(html):
    if not html or "sold out" in html:
        return None

    if any([missing_title, missing_date, invalid_venue]):
        return None

    if past_event or duplicate:
        return None

    return event
```

Option 2: Extract validation
```python
def is_valid_event(html, title, date, venue):
    """Check if event should be included."""
    return all([
        html,
        "sold out" not in html,
        title,
        date,
        venue,
        not past_event,
        not duplicate,
    ])

def parse_event(html):
    if not is_valid_event(html, title, date, venue):
        return None
    return event
```

Option 3: Suppress for specific function (if logic is clear)
```python
def parse_event(html):  # ruff: noqa: PLR0911
    # Complex parsing logic with valid multiple returns
    ...
```

### ARG002: Unused Method Arguments (2 occurrences)

**What**: Method parameter defined but never used

**Common in**:
- Interface implementations (abstract methods)
- Overridden methods (parent signature required)

**Fix**:

```python
# Before
class ConcreteSource(BaseSource):
    def fetch_events(self, start_date, end_date):  # end_date unused
        return self._scrape_all_events()

# Option 1: Use underscore prefix (signals "intentionally unused")
def fetch_events(self, start_date, _end_date):
    return self._scrape_all_events()

# Option 2: Add to **kwargs if not part of interface
def fetch_events(self, start_date, **kwargs):
    return self._scrape_all_events()

# Option 3: Suppress if required by interface
def fetch_events(self, start_date, end_date):  # ruff: noqa: ARG002
    """Fetch events. end_date unused in this source."""
    return self._scrape_all_events()
```

---

## 4. Execution Strategy

### Phase 1: Preparation (5 min)

```bash
# Create a feature branch
git checkout -b fix/ci-quality-checks

# Ensure dependencies are up to date
uv sync --all-extras --dev

# Run tests to establish baseline
uv run pytest tests/ -v
```

### Phase 2: Auto-fixes (10 min)

```bash
# Run auto-fixes (imports, formatting)
uv run ruff check --fix src/ tests/

# Format code
uv run ruff format src/ tests/

# Review changes
git diff

# Commit
git add -u
git commit -m "style: auto-fix import sorting and formatting

- Fix I001: Sort imports
- Fix F401: Remove unused imports
- Fix TC005: Remove empty type-checking blocks
- Fix UP035: Update deprecated imports

Auto-fixed with: uv run ruff check --fix"
```

### Phase 3: Critical Timezone Fixes (45-60 min)

```bash
# Create constants file
touch src/boringhannover/constants.py
# Add BERLIN_TZ constant (see section 1)

# Find all datetime.now() occurrences
uv run ruff check --select DTZ005 src/

# Fix each occurrence (see section 1)
# Add tests for timezone awareness

# Commit
git add -u
git commit -m "fix: add timezone awareness to all datetime operations

- Define BERLIN_TZ constant for Europe/Berlin
- Replace datetime.now() with timezone-aware version
- Replace datetime() constructors with tzinfo parameter
- Fix strptime() calls to include timezone
- Add tests for timezone awareness

Fixes DTZ001, DTZ005, DTZ007
Critical for Monday 5 PM scheduler reliability"
```

### Phase 4: Code Quality Cleanup (30-45 min)

```bash
# Fix print statements
# Fix commented-out code
# Review complex functions
# Move imports to top level where appropriate

git add -u
git commit -m "refactor: improve code quality

- Replace print() with logging
- Remove commented-out code
- Simplify functions with too many returns
- Move imports to top level where appropriate

Fixes T201, ERA001, PLR0911, PLC0415"
```

### Phase 5: Verification (10 min)

```bash
# Run full CI suite locally
uv run ruff check src/ tests/
uv run ruff format --check src/ tests/
uv run mypy src/
uv run pytest tests/ -v

# If all pass
git push origin fix/ci-quality-checks

# Create PR
gh pr create --title "Fix CI quality checks (129 errors)" \
  --body "Fixes all ruff linting errors including critical timezone bugs"
```

---

## 5. Testing & Verification

### Pre-merge Checklist

- [ ] All ruff checks pass: `uv run ruff check src/ tests/`
- [ ] Formatting correct: `uv run ruff format --check src/ tests/`
- [ ] Type checks pass: `uv run mypy src/`
- [ ] All tests pass: `uv run pytest tests/ -v`
- [ ] Manual test: Run backend locally to verify events are fetched
- [ ] Docker build succeeds: `docker build -f Dockerfile .`
- [ ] GitHub Actions CI passes

### Critical Tests to Add

```python
# tests/test_timezone_compliance.py
"""Ensure all datetime operations are timezone-aware."""

from datetime import datetime
import pytest
from boringhannover.constants import BERLIN_TZ


def test_berlin_timezone_constant():
    """Verify Berlin timezone is correctly defined."""
    assert BERLIN_TZ.key == "Europe/Berlin"


def test_current_time_is_timezone_aware():
    """Test that current time helper returns timezone-aware datetime."""
    from boringhannover.utils import get_current_time

    now = get_current_time()
    assert now.tzinfo is not None
    assert now.tzinfo.key == "Europe/Berlin"


def test_fetched_events_have_timezones():
    """Ensure all fetched events have timezone-aware datetimes."""
    from boringhannover import fetch_all_events

    events = fetch_all_events()

    for event in events:
        assert event.start.tzinfo is not None, (
            f"Event '{event.title}' has timezone-naive start time"
        )
        if event.end:
            assert event.end.tzinfo is not None, (
                f"Event '{event.title}' has timezone-naive end time"
            )


def test_dst_handling():
    """Test correct handling across DST transition."""
    # March 31, 2024: DST starts in Berlin (2 AM → 3 AM)
    before_dst = datetime(2024, 3, 31, 1, 0, tzinfo=BERLIN_TZ)
    after_dst = datetime(2024, 3, 31, 4, 0, tzinfo=BERLIN_TZ)

    # Should be 2 hours apart, not 3 (because 2-3 AM doesn't exist)
    diff = after_dst - before_dst
    assert diff.total_seconds() == 2 * 3600
```

---

## 6. Prevention: Pre-commit Hooks

### Install Pre-commit Framework

```bash
# Add to pyproject.toml dev dependencies
uv add --dev pre-commit

# Create .pre-commit-config.yaml
```

### Configuration

`.pre-commit-config.yaml`:
```yaml
repos:
  - repo: https://github.com/astral-sh/ruff-pre-commit
    rev: v0.8.0
    hooks:
      # Run linter
      - id: ruff
        args: [--fix]
      # Run formatter
      - id: ruff-format

  - repo: https://github.com/pre-commit/mirrors-mypy
    rev: v1.13.0
    hooks:
      - id: mypy
        additional_dependencies: [types-all]
```

### Setup

```bash
# Install git hooks
uv run pre-commit install

# Test on all files
uv run pre-commit run --all-files
```

**Result**: Linting errors caught before commit, preventing CI failures.

---

## 7. References

### Ruff Documentation
- [Ruff Rules Index](https://docs.astral.sh/ruff/rules/)
- [Configuration Guide](https://docs.astral.sh/ruff/configuration/)
- [DTZ (datetime-z) rules](https://docs.astral.sh/ruff/rules/#flake8-datetimez-dtz)

### Python DateTime Best Practices
- [Python datetime documentation](https://docs.python.org/3/library/datetime.html)
- [Working with Timezones](https://docs.python.org/3/library/zoneinfo.html)
- [Real Python: Working with Dates and Times](https://realpython.com/python-datetime/)

### Code Quality
- [PEP 8 – Style Guide for Python Code](https://peps.python.org/pep-0008/)
- [Google Python Style Guide](https://google.github.io/styleguide/pyguide.html)
- [Logging HOWTO](https://docs.python.org/3/howto/logging.html)

### Testing
- [pytest documentation](https://docs.pytest.org/)
- [Testing timezone-aware code](https://blog.ganssle.io/articles/2019/11/utcnow.html)

---

## Appendix: Quick Reference Commands

```bash
# View all errors with statistics
uv run ruff check src/ tests/ --statistics

# Fix only import sorting
uv run ruff check --select I --fix src/ tests/

# Fix all auto-fixable errors
uv run ruff check --fix src/ tests/

# Format code
uv run ruff format src/ tests/

# Run type checker
uv run mypy src/

# Run tests
uv run pytest tests/ -v

# Full CI check locally
uv run ruff check src/ tests/ && \
uv run ruff format --check src/ tests/ && \
uv run mypy src/ && \
uv run pytest tests/ -v

# Check specific file
uv run ruff check src/boringhannover/main.py

# Ignore specific rule in file
# Add to top of file:
# ruff: noqa: T201
# Or specific line:
print("debug")  # noqa: T201
```

---

**Document Version**: 1.0
**Last Updated**: 2025-12-11
**Next Review**: After all fixes are merged
