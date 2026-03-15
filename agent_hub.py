import asyncio
import os
import shlex
from dataclasses import dataclass
from typing import Callable, Dict, Optional

import pyte
from ptyprocess import PtyProcessUnicode
from rich.console import Console
from rich.panel import Panel
import typer

console = Console()


@dataclass
class TerminalSnapshot:
    screen_text: str
    raw_buffer: str


class Supervisor:
    """Abstract interface for Supervisor AIs.

    Implementations receive the current agent name and a terminal snapshot,
    and return the text to inject into that agent's input stream. This can
    be backed by a local heuristic or a remote LLM/AI service.
    """

    async def decide(self, agent_name: str, snapshot: TerminalSnapshot) -> str:  # pragma: no cover - interface
        raise NotImplementedError


def heuristic_decision(snapshot: TerminalSnapshot) -> str:
    """Default heuristic used when no external Supervisor is configured."""
    text = snapshot.screen_text.lower()
    if "python" in text:
        return "print('Hello from Agent-Hub')"
    if any(prompt in text for prompt in ["$", "%", "> "]):
        return "echo 'Hello from Agent-Hub'"
    return "echo 'Supervisor: no specific instruction'"


class LocalHeuristicSupervisor(Supervisor):
    async def decide(self, agent_name: str, snapshot: TerminalSnapshot) -> str:
        return heuristic_decision(snapshot)


class ExternalProcessSupervisor(Supervisor):
    """Supervisor that delegates decisions to an external command.

    The command receives ``screen_text`` on stdin and must return the text to
    type as its stdout. This makes it easy to plug in scripts or other
    processes (including wrappers around remote LLM APIs) without changing
    Agent-Hub's core code.
    """

    def __init__(self, command: str) -> None:
        self.command = command

    async def decide(self, agent_name: str, snapshot: TerminalSnapshot) -> str:
        proc = await asyncio.create_subprocess_shell(
            self.command,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        assert proc.stdin is not None and proc.stdout is not None
        screen = snapshot.screen_text or ""
        proc.stdin.write(screen.encode("utf-8", errors="ignore"))
        await proc.stdin.drain()
        proc.stdin.close()
        out, err = await proc.communicate()
        if proc.returncode != 0:
            console.print(f"[bold red]External supervisor exited with {proc.returncode}[/bold red]")
            if err:
                console.print(err.decode("utf-8", errors="ignore"))
            return ""
        return out.decode("utf-8", errors="ignore").strip()


class TerminalWatcher:
    """Watches a PTY-backed process and maintains a virtual screen buffer.

    For MVP, idle detection is simplified to: pause after a small delay and
    treat the latest screen as a snapshot for the supervisor.
    """

    def __init__(self, process: PtyProcessUnicode, rows: int = 24, cols: int = 80) -> None:
        self.process = process
        self.rows = rows
        self.cols = cols
        self.screen = pyte.Screen(cols, rows)
        self.stream = pyte.Stream(self.screen)
        self._buffer_chunks: list[str] = []
        self._stopped = False
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._last_data_time: float = 0.0

    async def read_loop(self) -> None:
        """Continuously read from the PTY and feed into the virtual screen."""
        loop = asyncio.get_running_loop()
        self._loop = loop
        self._last_data_time = loop.time()
        while not self._stopped and self.process.isalive():
            try:
                # Use a small timeout so we can yield control.
                data = await loop.run_in_executor(None, self.process.read, 1024)
            except EOFError:
                break
            if not data:
                await asyncio.sleep(0.05)
                continue
            self._buffer_chunks.append(data)
            self.stream.feed(data)
            self._last_data_time = loop.time()

    def snapshot(self) -> TerminalSnapshot:
        """Return a human-readable dump of the virtual screen and raw buffer."""
        lines = [self.screen.display[i] for i in range(self.rows)]
        text = "\n".join(lines).rstrip("\n")
        raw = "".join(self._buffer_chunks)
        return TerminalSnapshot(screen_text=text, raw_buffer=raw)

    def stop(self) -> None:
        self._stopped = True

    async def wait_for_idle(self, idle_time: float = 0.5, max_wait: Optional[float] = None) -> None:
        """Block until there has been no output for ``idle_time`` seconds.

        ``max_wait`` bounds how long we wait overall; if reached, the
        method returns even if the terminal is still noisy. This provides a
        practical definition of "turn complete" for interactive TUIs.
        """

        loop = self._loop or asyncio.get_running_loop()
        if self._last_data_time == 0.0:
            self._last_data_time = loop.time()
        start = loop.time()

        while self.process.isalive() and not self._stopped:
            since_last = loop.time() - self._last_data_time
            if since_last >= idle_time:
                return
            if max_wait is not None and (loop.time() - start) >= max_wait:
                return
            await asyncio.sleep(min(idle_time / 2, 0.1))


class AgentManager:
    """Manages a single child agent running in a PTY."""

    def __init__(self, command: list[str], name: str = "agent") -> None:
        self.command = command
        self.name = name
        self.process: Optional[PtyProcessUnicode] = None
        self.watcher: Optional[TerminalWatcher] = None

    async def start(self) -> None:
        """Start the agent process in a PTY and attach a watcher."""
        # PtyProcessUnicode wraps os.openpty/pty.fork for us.
        self.process = PtyProcessUnicode.spawn(self.command, dimensions=(24, 80))
        self.watcher = TerminalWatcher(self.process)
        asyncio.create_task(self.watcher.read_loop())

    def is_alive(self) -> bool:
        return bool(self.process and self.process.isalive())

    def send_keys(self, text: str) -> None:
        """Simulate typing by writing directly to the PTY."""
        if not self.process:
            raise RuntimeError("Process not started")
        # Append newline to simulate Enter
        self.process.write(text)

    def send_line(self, line: str) -> None:
        if not self.process:
            raise RuntimeError("Process not started")
        self.process.write(line + "\n")

    def snapshot(self) -> TerminalSnapshot:
        if not self.watcher:
            raise RuntimeError("Watcher not started")
        return self.watcher.snapshot()

    async def wait_for_idle(self, idle_time: float = 0.5, max_wait: Optional[float] = None) -> None:
        if not self.watcher:
            return
        await self.watcher.wait_for_idle(idle_time=idle_time, max_wait=max_wait)

    async def stop(self) -> None:
        if self.watcher:
            self.watcher.stop()
        if self.process and self.process.isalive():
            self.process.terminate(force=True)


class Orchestrator:
    """High-level orchestrator that uses a Supervisor to decide inputs.

    This class is responsible for:
    - managing multiple PTY-backed agents,
    - detecting idle/turn boundaries,
    - capturing terminal snapshots, and
    - delegating the decision about what to type next to a Supervisor.
    """

    def __init__(self, supervisor: Optional[Supervisor] = None) -> None:
        self.supervisor: Supervisor = supervisor or LocalHeuristicSupervisor()
        self.agents: Dict[str, AgentManager] = {}

    async def add_agent(self, name: str, command: list[str]) -> AgentManager:
        agent = AgentManager(command, name=name)
        await agent.start()
        self.agents[name] = agent
        return agent

    async def run_single_cycle(
        self,
        agent_name: str,
        delay: float = 2.0,
        max_wait: float = 5.0,
    ) -> None:
        """Wait for a quiet period, snapshot, ask Supervisor, then inject input."""
        agent = self.agents[agent_name]
        await agent.wait_for_idle(idle_time=delay, max_wait=max_wait)
        snap = agent.snapshot()
        self._render_snapshot(agent_name, snap)
        decision = await self.supervisor.decide(agent_name, snap)
        console.print(f"[bold green]Supervisor decision for {agent_name}:[/bold green] {decision!r}")
        if decision:
            agent.send_line(decision)

    def _render_snapshot(self, agent_name: str, snapshot: TerminalSnapshot) -> None:
        panel = Panel.fit(
            snapshot.screen_text or "<empty>",
            title=f"Agent: {agent_name} screen snapshot",
            border_style="cyan",
        )
        console.print(panel)


async def demo_shell_agent() -> None:
    """MVP demo: spawn a shell inside a PTY, snapshot, then inject a command."""
    orchestrator = Orchestrator()

    # Use the user's default shell or /bin/bash as fallback.
    shell = os.environ.get("SHELL", "/bin/bash")
    agent = await orchestrator.add_agent("shell", [shell])

    console.print("[bold yellow]Started shell agent in PTY.[/bold yellow]")
    console.print("Waiting briefly for initial prompt...")

    # Run a few supervisor cycles to show the interaction.
    for _ in range(2):
        await orchestrator.run_single_cycle("shell", delay=2.0)
        await asyncio.sleep(1.0)

    await agent.stop()
    console.print("[bold yellow]Shell agent stopped.[/bold yellow]")





app = typer.Typer(help="Agent-Hub CLI: orchestrate PTY-based agents")


@app.command()
def run_agent(
    cmd: str = typer.Argument(..., help="Command to run as the child agent, e.g. 'claude-code'"),
    delay: float = typer.Option(1.0, help="Idle time (seconds) before treating a turn as complete"),
    max_wait: float = typer.Option(10.0, help="Max seconds to wait for a turn before forcing a snapshot"),
    cycles: int = typer.Option(10, help="Maximum number of supervisor cycles to run"),
    supervisor: str = typer.Option("heuristic", help="Supervisor backend: 'heuristic' or an external command"),
) -> None:
    """Run an arbitrary CLI agent under Agent-Hub supervision.

    This mode is intended for real agents like `claude-code`, `codex`, or
    other TUI-based tools. Agent-Hub will:
    - spawn the command in a PTY,
    - wait for the UI to become idle,
    - capture the visual terminal state,
    - call the configured Supervisor, and
    - type the Supervisor's response back into the agent.
    """

    async def _run() -> None:
        # Parse the user-provided command string into argv.
        argv = shlex.split(cmd)
        if not argv:
            raise typer.BadParameter("Empty command")

        # Choose supervisor backend.
        if supervisor == "heuristic":
            sup: Supervisor = LocalHeuristicSupervisor()
        else:
            sup = ExternalProcessSupervisor(supervisor)

        orchestrator = Orchestrator(supervisor=sup)
        agent = await orchestrator.add_agent("agent", argv)
        console.print(f"[bold yellow]Started agent in PTY:[/bold yellow] {cmd!r}")

        for i in range(cycles):
            console.print(f"[bold cyan]--- Cycle {i+1}/{cycles} ---[/bold cyan]")
            if not agent.is_alive():
                console.print("[bold red]Agent process exited; stopping.[/bold red]")
                break
            await orchestrator.run_single_cycle("agent", delay=delay, max_wait=max_wait)

        await agent.stop()
        console.print("[bold yellow]run_agent finished; agent stopped.[/bold yellow]")

    asyncio.run(_run())


@app.command()
def demo_shell(
    cycles: int = typer.Option(2, help="Number of supervisor cycles to run"),
    delay: float = typer.Option(2.0, help="Seconds to wait before each snapshot"),
) -> None:
    """Run the single-shell demo showing observe/decide/act loop."""

    async def _run() -> None:
        orchestrator = Orchestrator()
        shell = os.environ.get("SHELL", "/bin/bash")
        agent = await orchestrator.add_agent("shell", [shell])
        console.print("[bold yellow]Started shell agent in PTY.[/bold yellow]")
        console.print("Waiting briefly for initial prompt...")
        for _ in range(cycles):
            await orchestrator.run_single_cycle("shell", delay=delay)
            await asyncio.sleep(1.0)
        await agent.stop()
        console.print("[bold yellow]Shell agent stopped.[/bold yellow]")

    asyncio.run(_run())


@app.command()
def demo_router(
    cycles: int = typer.Option(2, help="Number of routing cycles between A and B"),
    delay: float = typer.Option(2.0, help="Seconds to wait before each snapshot"),
) -> None:
    """Demonstrate simple router mode with two shell agents.

    Agent A asks Agent B for the current directory, Supervisor routes the
    request to B, and sends the result back to A.
    """

    async def _run() -> None:
        class RouterSupervisor(Supervisor):
            def __init__(self, orchestrator: Orchestrator, agent_b_name: str) -> None:
                self.orchestrator = orchestrator
                self.agent_b_name = agent_b_name
                self.last_b_result: Optional[str] = None

            async def decide(self, agent_name: str, snapshot: TerminalSnapshot) -> str:
                text = snapshot.screen_text.lower()
                if agent_name == "A" and "ask_b_for_pwd" in text:
                    # Route a pwd request to B.
                    console.print("[bold magenta]RouterSupervisor:[/bold magenta] routing pwd to B")
                    agent_b = self.orchestrator.agents[self.agent_b_name]
                    agent_b.send_line("pwd")
                    await self.orchestrator.run_single_cycle(self.agent_b_name, delay=delay)
                    snap_b = agent_b.snapshot()
                    # Take the last non-empty line as B's answer.
                    lines = [ln for ln in snap_b.screen_text.splitlines() if ln.strip()]
                    self.last_b_result = lines[-1] if lines else ""
                    return f"echo 'Result_from_B: {self.last_b_result}'"

                # Fall back to local heuristic for all other states.
                return heuristic_decision(snapshot)

        dummy_orchestrator = Orchestrator()  # replaced immediately below
        shell = os.environ.get("SHELL", "/bin/bash")
        orchestrator = Orchestrator()
        agent_a = await orchestrator.add_agent("A", [shell])
        agent_b = await orchestrator.add_agent("B", [shell])

        orchestrator.supervisor = RouterSupervisor(orchestrator, agent_b_name="B")  # type: ignore[attr-defined]

        console.print("[bold yellow]Started two shell agents A and B in PTYs.[/bold yellow]")
        console.print("Router demo: A will ask B for its current directory.")

        agent_a.send_line("echo 'ask_B_for_pwd'")

        for _ in range(cycles):
            await orchestrator.run_single_cycle("A", delay=delay)

        await agent_a.stop()
        await agent_b.stop()
        console.print(
            "[bold yellow]Router demo finished; agents A and B stopped.[/bold yellow]"
        )

    asyncio.run(_run())


def main() -> None:
    app()


if __name__ == "__main__":
    main()
