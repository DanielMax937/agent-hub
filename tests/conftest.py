import os
import sys
import types


# Ensure the project root (containing agent_hub.py) is on sys.path
ROOT_DIR = os.path.dirname(os.path.dirname(__file__))
if ROOT_DIR not in sys.path:  # pragma: no cover - environment shim
    sys.path.insert(0, ROOT_DIR)


# Provide a minimal stub for pyte if it's not installed so that
# importing agent_hub works in environments without the real
# dependency. The production code still requires the real library
# at runtime.
if "pyte" not in sys.modules:  # pragma: no cover - environment shim
    pyte = types.ModuleType("pyte")

    class Screen:  # type: ignore[too-many-instance-attributes]
        def __init__(self, columns: int, rows: int) -> None:  # noqa: D401
            # Minimal attributes used by TerminalWatcher.snapshot
            self.columns = columns
            self.rows = rows
            self.display = ["" for _ in range(rows)]

    class Stream:
        def __init__(self, screen: Screen) -> None:
            self.screen = screen

        def feed(self, data: str) -> None:  # pragma: no cover - trivial stub
            # Very small stub: ignore data; tests that rely on
            # TerminalSnapshot don't depend on real terminal emulation.
            pass

    pyte.Screen = Screen
    pyte.Stream = Stream
    sys.modules["pyte"] = pyte
