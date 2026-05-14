from __future__ import annotations

import subprocess
from dataclasses import dataclass
from pathlib import Path


class ToolError(RuntimeError):
    pass


@dataclass(frozen=True)
class CommandResult:
    args: list[str]
    stdout: str
    stderr: str


def run_command(args: list[str], cwd: Path | None = None) -> CommandResult:
    try:
        completed = subprocess.run(
            args,
            cwd=str(cwd) if cwd else None,
            check=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
    except FileNotFoundError as exc:
        raise ToolError(f"Required tool not found: {args[0]}") from exc
    except subprocess.CalledProcessError as exc:
        stderr = exc.stderr.strip() if exc.stderr else ""
        stdout = exc.stdout.strip() if exc.stdout else ""
        detail = stderr or stdout or str(exc)
        raise ToolError(f"Command failed ({' '.join(args)}): {detail}") from exc

    return CommandResult(args=args, stdout=completed.stdout, stderr=completed.stderr)


def command_available(name: str) -> bool:
    try:
        run_command([name, "--version"])
    except ToolError:
        return False
    return True

