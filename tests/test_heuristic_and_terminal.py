from agent_hub import heuristic_decision, TerminalSnapshot, app
from typer.main import Typer


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


def test_terminal_snapshot_preserves_screen_and_raw():
    text = "line1\nline2"
    snap = TerminalSnapshot(screen_text=text, raw_buffer=text)
    assert snap.screen_text == text
    assert snap.raw_buffer == text


def test_cli_has_expected_commands():
    assert isinstance(app, Typer)
    callbacks = {info.callback.__name__ for info in app.registered_commands}
    assert "run_agent" in callbacks
    assert "demo_shell" in callbacks
    assert "demo_router" in callbacks
