from __future__ import annotations

from pathlib import Path

from app.utils.subprocess_runner import run_command


def mux_softsub(
    mkv_path: Path,
    subtitle_path: Path,
    output_path: Path,
    language: str = "vie",
    track_name: str = "Vietnamese AI",
    set_default: bool = True,
) -> Path:
    if not mkv_path.exists():
        raise FileNotFoundError(mkv_path)
    if not subtitle_path.exists():
        raise FileNotFoundError(subtitle_path)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    args = [
        "mkvmerge",
        "-o",
        str(output_path),
        str(mkv_path),
        "--language",
        f"0:{language}",
        "--track-name",
        f"0:{track_name}",
    ]
    if set_default:
        args.extend(["--default-track", "0:yes"])
    args.append(str(subtitle_path))
    run_command(args)
    return output_path

