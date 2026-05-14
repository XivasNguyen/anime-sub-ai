from __future__ import annotations

import subprocess
import os
import shutil
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
    resolved_args = [_resolve_tool(args[0]), *args[1:]]
    try:
        completed = subprocess.run(
            resolved_args,
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

    return CommandResult(args=resolved_args, stdout=completed.stdout, stderr=completed.stderr)


def command_available(name: str) -> bool:
    try:
        run_command([name, "--version"])
    except ToolError:
        return False
    return True


def _resolve_tool(name: str) -> str:
    if Path(name).parts:
        direct = Path(name)
        if direct.exists():
            return str(direct)

    found = shutil.which(name)
    if found:
        return found

    for candidate in _known_windows_tool_paths(name):
        if candidate.exists():
            return str(candidate)
    return name


def _known_windows_tool_paths(name: str) -> list[Path]:
    executable = name if name.lower().endswith(".exe") else f"{name}.exe"
    candidates: list[Path] = []

    program_files = os.environ.get("ProgramFiles")
    if program_files:
        candidates.append(Path(program_files) / "MKVToolNix" / executable)

    local_app_data = os.environ.get("LOCALAPPDATA")
    if local_app_data:
        winget_root = Path(local_app_data) / "Microsoft" / "WinGet" / "Packages"
        if winget_root.exists():
            candidates.extend(winget_root.glob(f"Gyan.FFmpeg_*/*/bin/{executable}"))

    return candidates
