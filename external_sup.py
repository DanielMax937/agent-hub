#!/usr/bin/env python
import sys
screen = sys.stdin.read()
first = screen.splitlines()[0] if screen.splitlines() else ""
print(first.upper() or "NO_SCREEN")
