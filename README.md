# Agent-Hub CLI

Agent-Hub is a "meta-manager" CLI for orchestrating other CLI-based AI agents
(such as interactive TUIs like `claude-code`, `codex`, or `interpreter`). It
runs agents in PTYs, watches their terminal state, and uses a Supervisor to
decide what to type next on their behalf.

## Features

- Run any CLI agent inside a PTY so TUIs (colors, spinners, progress bars) work.
- Maintain a virtual terminal screen using `pyte` for accurate visual context.
- Detect when an agent is idle (quiescent) to define "turn" boundaries.
- Capture terminal snapshots and pass them to a Supervisor.
- Inject keystrokes/commands back into the child agent.
- Support multiple agents and basic router behavior between them.

## Core Concepts

- **AgentManager**: wraps a PTY-backed child process; exposes `send_line()`,
  `send_keys()`, `snapshot()`, `wait_for_idle()`, and `stop()`.
- **TerminalWatcher**: async task that continuously reads from the PTY, feeds
  bytes into a `pyte.Screen`, and tracks last-output time for idle detection.
- **TerminalSnapshot**: contains a human-readable `screen_text` dump and
  `raw_buffer` of accumulated output.
- **Supervisor**: abstraction for deciding what the hub should type next based
  on an agent's screen.
- **Orchestrator**: manages multiple agents, handles idle/turn detection,
  captures snapshots, and calls the Supervisor.

### Supervisor Backends

All Supervisor implementations live in `agent_hub.py`:

- `LocalHeuristicSupervisor` (default)
  - Lightweight, prompt-based heuristic for quick testing.
- `ExternalProcessSupervisor`
  - Spawns an external command and writes `screen_text` to its stdin.
  - Reads stdout and uses that as the next input to the agent.
  - Ideal for plugging in scripts or wrappers around remote LLM APIs.

You can later add your own Supervisor subclass (e.g., one that calls a hosted
LLM API) without changing the orchestration core.

## Installation

Create a virtual environment and install dependencies:

```bash
python -m venv .venv
source .venv/bin/activate
pip install ptyprocess pyte rich typer
```

## CLI Usage

The main entrypoint is `agent_hub.py`.

Show help:

```bash
python agent_hub.py --help
```

You should see three commands:

- `run-agent` – run an arbitrary CLI agent under Agent-Hub supervision.
- `demo-shell` – single-shell demo showing observe/decide/act loop.
- `demo-router` – two-shell router demo.

### run-agent

Run any CLI agent under the hub:

```bash
python agent_hub.py run-agent 'bash -i' \
  --cycles 5 \
  --delay 1.0 \
  --max-wait 10.0 \
  --supervisor heuristic
```

Arguments:

- `cmd` (positional): command string to run, e.g. `"claude-code"`,
  `"interpreter"`, `"bash -i"`.
- `--delay`: idle time (seconds) before considering a turn complete.
- `--max-wait`: upper bound on how long to wait before forcing a snapshot.
- `--cycles`: maximum number of Supervisor cycles.
- `--supervisor`:
  - `"heuristic"` (default): use `LocalHeuristicSupervisor`.
  - any other string: treated as a shell command and used with
    `ExternalProcessSupervisor`.

When you run this command Agent-Hub will:

1. Spawn the agent process inside a PTY.
2. Wait for the terminal to be idle for `--delay` seconds (or until
   `--max-wait` is exceeded).
3. Capture the current `screen_text` as a `TerminalSnapshot`.
4. Call the chosen Supervisor backend to get a decision.
5. Type that decision into the agent (followed by Enter).
6. Repeat until `--cycles` is reached or the agent exits.

### Using an External Supervisor Script

You can point `--supervisor` at any executable that reads from stdin and prints
its decision to stdout. For example:

```python
#!/usr/bin/env python
# external_sup.py
import sys

screen = sys.stdin.read()
# Inspect `screen` and decide what to type next
print("echo 'Hello from external supervisor'")
```

Make it executable:

```bash
chmod +x external_sup.py
```

Then run:

```bash
python agent_hub.py run-agent 'bash -i' \
  --cycles 3 --delay 1.0 \
  --supervisor './external_sup.py'
```

Your script receives the current `screen_text` on stdin each cycle and returns
exactly what Agent-Hub should type next.

### demo-shell

Simple single-shell demo using the heuristic supervisor:

```bash
python agent_hub.py demo-shell --cycles 2 --delay 2.0
```

This is useful for verifying PTY setup, idle detection, and visual snapshots.

### demo-router

Two-agent demonstration showing basic router mode:

```bash
python agent_hub.py demo-router --cycles 2 --delay 1.0
```

It starts two shell agents, A and B, and a `RouterSupervisor` that:

- Detects when A prints `ask_B_for_pwd`.
- Sends `pwd` to B.
- Reads B's output and injects it back into A as `Result_from_B: ...`.

This provides a concrete pattern for cross-agent orchestration: one agent can
ask for help, the Supervisor routes the request to another agent, then returns
the result.

## Extending Agent-Hub

To integrate a real Supervisor AI (e.g., an LLM API), implement a new subclass
of `Supervisor` in `agent_hub.py` and wire it into `run-agent` or a new CLI
command. The core PTY orchestration (`AgentManager`, `TerminalWatcher`,
`Orchestrator`) is designed to remain stable while you experiment with
different Supervisor strategies.
