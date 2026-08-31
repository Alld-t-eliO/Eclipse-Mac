from __future__ import annotations

import os
import re
import sys
import time

RESET = "\033[0m"
BOLD = "\033[1m"
CYAN = "\033[38;2;0;229;255m"
CYAN_DARK = "\033[38;2;0;145;180m"
GREEN = "\033[38;2;57;255;20m"
RED = "\033[38;2;255;45;85m"
MAGENTA = "\033[38;2;210;70;255m"
WHITE = "\033[38;2;225;245;255m"
YELLOW = "\033[38;2;255;205;45m"
ANSI_PATTERN = re.compile(r"\x1b\[[0-?]*[ -/]*[@-~]")


def enabled() -> bool:
    return sys.stdout.isatty() and os.environ.get("NO_COLOR") is None


def animations_enabled() -> bool:
    return enabled() and os.environ.get("ECLIPSE_NO_ANIMATION") is None


def paint(text: object, color: str, *, bold: bool = False) -> str:
    value = str(text)
    if not enabled():
        return value
    weight = BOLD if bold else ""
    return f"{weight}{color}{value}{RESET}"


def neon(text: object, *, bold: bool = False) -> str:
    return paint(text, CYAN, bold=bold)


def success(text: object) -> str:
    return paint(text, GREEN, bold=True)


def danger(text: object) -> str:
    return paint(text, RED, bold=True)


def accent(text: object) -> str:
    return paint(text, MAGENTA, bold=True)


def muted(text: object) -> str:
    return paint(text, CYAN_DARK)


def warning(text: object) -> str:
    return paint(text, YELLOW, bold=True)


def menu_line(number: str, label: str, *, danger_action: bool = False) -> str:
    number_text = danger(number) if danger_action else accent(number)
    return f"  {number_text} {paint(label, RED if danger_action else WHITE)}"


def prompt(label: str = "Choix") -> str:
    return f"  {neon('›', bold=True)} {paint(label, WHITE)} {accent('::')} "


def clear() -> None:
    if sys.stdout.isatty():
        print("\033[2J\033[H", end="")


def boot_animation() -> None:
    if not animations_enabled():
        return
    frames = (
        "INITIALISATION DU NOYAU LOCAL",
        "CHARGEMENT DES MODULES MAC",
        "PRÉPARATION DES EXTENSIONS",
    )
    clear()
    for index, label in enumerate(frames):
        blocks = "█" * (index + 3)
        print(f"\r  {neon('ECLIPSE//BOOT')} {muted(label):42} {success(blocks)}", end="", flush=True)
        time.sleep(0.16)
    print(f"\r  {success('●')} {neon('ECLIPSE ONLINE', bold=True)}" + " " * 60, flush=True)
    time.sleep(0.22)


def pulse_online(online: bool = True) -> str:
    return (
        f"{success('●')} {paint('CIBLE DISTANTE EN LIGNE', GREEN, bold=True)}"
        if online
        else f"{danger('●')} {paint('CIBLE DISTANTE INJOIGNABLE', RED, bold=True)}"
    )


def visible_length(value: str) -> int:
    return len(ANSI_PATTERN.sub("", value))


def gauge(percent: float, width: int = 18) -> str:
    bounded = max(0.0, min(percent, 100.0))
    filled = round(bounded / 100 * width)
    color = RED if bounded >= 90 else YELLOW if bounded >= 70 else GREEN
    bar = paint("█" * filled, color, bold=True) + muted("░" * (width - filled))
    return f"{bar} {paint(f'{bounded:5.1f}%', color, bold=True)}"


def sparkline(values: list[float], width: int = 24) -> str:
    blocks = "▁▂▃▄▅▆▇█"
    recent = values[-width:]
    padding = " " * (width - len(recent))
    rendered = "".join(blocks[min(7, max(0, round(value / 100 * 7)))] for value in recent)
    current = recent[-1] if recent else 0
    color = RED if current >= 90 else YELLOW if current >= 70 else CYAN
    return muted(padding) + paint(rendered, color, bold=True)


def columns(left: list[str], right: list[str], left_width: int = 43) -> None:
    for index in range(max(len(left), len(right))):
        left_value = left[index] if index < len(left) else ""
        right_value = right[index] if index < len(right) else ""
        padding = " " * max(2, left_width - visible_length(left_value))
        print(f"{left_value}{padding}{right_value}")
