# Agent-Hub Testing Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add an initial pytest-based test suite for Agent-Hub, covering heuristic_decision, TerminalWatcher snapshot behavior, and basic CLI wiring.

**Architecture:** Use plain pytest unit tests alongside the existing `agent_hub.py` module. Focus on deterministic, non-PTY heavy behavior where possible (pure functions and small units), and keep CLI tests as lightweight smoke tests using Typer's testing utilities.

**Tech Stack:** Python 3, pytest, Typer testing utilities (if available via typer.testing).

---

### Task 1: Set up pytest test skeleton

**Files:**
- Create: `tests/test_heuristic_and_terminal.py`
- (No modifications to existing code for this task.)

**Step 1: Write the failing test file with a placeholder test**

```python
# tests/test_heuristic_and_terminal.py

from agent_hub import heuristic_decision, TerminalSnapshot


def test_placeholder():
    # This will be replaced by real tests in later tasks.
    assert heuristic_decision(TerminalSnapshot(screen_text="", raw_buffer=""))
```

**Step 2: Run pytest to verify it fails or at least exercises imports**

Run: `pytest -q`
Expected: Test run executes and may fail if environment is missing pytest; once pytest is installed, this should pass and confirm test discovery and imports.

**Step 3: Commit**

```bash
git add tests/test_heuristic_and_terminal.py
git commit -m "test: add initial pytest skeleton"
```

---

### Task 2: Add tests for heuristic_decision behavior

**Files:**
- Modify: `tests/test_heuristic_and_terminal.py`

**Step 1: Write failing tests for heuristic_decision variants**

```python
from agent_hub import heuristic_decision, TerminalSnapshot


def test_heuristic_python_prompt_uses_python_print():
    snapshot = TerminalSnapshot(screen_text="Python 3.11.0 (main)", raw_buffer="")
    decision = heuristic_decision(snapshot)
    assert "print(" in decision
    assert "Hello from Agent-Hub" in decision


def test_heuristic_shell_prompt_uses_echo():
    snapshot = TerminalSnapshot(screen_text="$ ", raw_buffer="")
    decision = heuristic_decision(snapshot)
    assert decision.startswith("echo ")
    assert "Hello from Agent-Hub" in decision


def test_heuristic_default_message_when_no_match():
    snapshot = TerminalSnapshot(screen_text="some random output", raw_buffer="")
    decision = heuristic_decision(snapshot)
    assert "Supervisor: no specific instruction" in decision
```

**Step 2: Run pytest to see tests fail if behavior changes**

Run: `pytest tests/test_heuristic_and_terminal.py -q`
Expected: PASS with current implementation; this step verifies that tests are wired to current behavior and will catch regressions later.

**Step 3: Commit**

```bash
git add tests/test_heuristic_and_terminal.py
git commit -m "test: cover heuristic_decision behavior"
```

---

### Task 3: Add tests for TerminalWatcher.snapshot via a fake screen

**Files:**
- Modify: `tests/test_heuristic_and_terminal.py`

**Step 1: Add a small helper to construct a TerminalSnapshot-like object**

```python
from agent_hub import TerminalSnapshot


def make_snapshot(text: str) -> TerminalSnapshot:
    return TerminalSnapshot(screen_text=text, raw_buffer=text)
```

**Step 2: Write tests asserting snapshot content is preserved**

```python

def test_terminal_snapshot_preserves_screen_and_raw():
    text = "line1\nline2"
    snap = make_snapshot(text)
    assert snap.screen_text == text
    assert snap.raw_buffer == text
```

**Step 3: Run pytest for these tests**

Run: `pytest tests/test_heuristic_and_terminal.py::test_terminal_snapshot_preserves_screen_and_raw -q`
Expected: PASS, validating the dataclass behavior we rely on when constructing snapshots.

**Step 4: Commit**

```bash
git add tests/test_heuristic_and_terminal.py
git commit -m "test: verify TerminalSnapshot behavior"
```

---

### Task 4: Add a minimal CLI smoke test for Typer app

**Files:**
- Modify: `tests/test_heuristic_and_terminal.py`

**Step 1: Add a smoke test that ensures the Typer app defines commands**

```python
from typer.main import Typer
from agent_hub import app


def test_cli_has_expected_commands():
    assert isinstance(app, Typer)
    # Basic sanity: commands registered
    assert "run-agent" in app.registered_commands
    assert "demo-shell" in app.registered_commands
    assert "demo-router" in app.registered_commands
```

**Step 2: Run pytest for this test**

Run: `pytest tests/test_heuristic_and_terminal.py::test_cli_has_expected_commands -q`
Expected: PASS, confirming the CLI surface is wired and named as expected.

**Step 3: Commit**

```bash
git add tests/test_heuristic_and_terminal.py
git commit -m "test: add CLI smoke test for Typer app"
```

