"""Sound effects for vending machine events."""

from __future__ import annotations

import sys


def play_beep(frequency: int = 880, duration: int = 150) -> None:
    if sys.platform == "win32":
        try:
            import winsound
            winsound.Beep(frequency, duration)
        except Exception:
            pass
    else:
        print("\a", end="", flush=True)


def play_success() -> None:
    play_beep(660, 100)
    play_beep(880, 200)


def play_error() -> None:
    play_beep(220, 500)
