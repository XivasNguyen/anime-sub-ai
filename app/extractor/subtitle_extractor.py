from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from app.utils.subprocess_runner import ToolError, run_command


ASS_CODECS = {"ass", "ssa", "substation alpha"}
SRT_CODECS = {"subrip", "srt"}


@dataclass(frozen=True)
class SubtitleTrack:
    id: int
    codec: str
    language: str
    name: str


def inspect_subtitles(mkv_path: Path) -> list[SubtitleTrack]:
    if not mkv_path.exists():
        raise FileNotFoundError(mkv_path)
    try:
        return _inspect_with_mkvmerge(mkv_path)
    except ToolError:
        return _inspect_with_ffprobe(mkv_path)


def extract_subtitle(mkv_path: Path, output_dir: Path) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    tracks = inspect_subtitles(mkv_path)
    if not tracks:
        raise RuntimeError(f"No subtitle tracks found in {mkv_path}")

    selected = select_subtitle_track(tracks)
    suffix = ".ass" if selected.codec.lower() in ASS_CODECS else ".srt"
    output_path = output_dir / f"{mkv_path.stem}.en{suffix}"
    try:
        run_command(["mkvextract", "tracks", str(mkv_path), f"{selected.id}:{output_path}"])
    except ToolError:
        run_command(["ffmpeg", "-y", "-i", str(mkv_path), "-map", f"0:{selected.id}", str(output_path)])

    _ensure_utf8(output_path)
    return output_path


def select_subtitle_track(tracks: list[SubtitleTrack]) -> SubtitleTrack:
    def score(track: SubtitleTrack) -> tuple[int, int]:
        codec = track.codec.lower()
        language = track.language.lower()
        english = language in {"eng", "en", "english"}
        if english and codec in ASS_CODECS:
            return (0, track.id)
        if english and codec in SRT_CODECS:
            return (1, track.id)
        if codec in ASS_CODECS:
            return (2, track.id)
        if codec in SRT_CODECS:
            return (3, track.id)
        return (4, track.id)

    return sorted(tracks, key=score)[0]


def _inspect_with_mkvmerge(mkv_path: Path) -> list[SubtitleTrack]:
    result = run_command(["mkvmerge", "-J", str(mkv_path)])
    data = json.loads(result.stdout)
    tracks: list[SubtitleTrack] = []
    for track in data.get("tracks", []):
        if track.get("type") != "subtitles":
            continue
        props = track.get("properties", {})
        tracks.append(
            SubtitleTrack(
                id=int(track["id"]),
                codec=str(track.get("codec", "")),
                language=str(props.get("language", "")),
                name=str(props.get("track_name", "")),
            )
        )
    return tracks


def _inspect_with_ffprobe(mkv_path: Path) -> list[SubtitleTrack]:
    result = run_command(
        [
            "ffprobe",
            "-v",
            "quiet",
            "-print_format",
            "json",
            "-show_streams",
            str(mkv_path),
        ]
    )
    data = json.loads(result.stdout)
    tracks: list[SubtitleTrack] = []
    for stream in data.get("streams", []):
        if stream.get("codec_type") != "subtitle":
            continue
        tags: dict[str, Any] = stream.get("tags", {})
        tracks.append(
            SubtitleTrack(
                id=int(stream["index"]),
                codec=str(stream.get("codec_name", "")),
                language=str(tags.get("language", "")),
                name=str(tags.get("title", "")),
            )
        )
    return tracks


def _ensure_utf8(path: Path) -> None:
    raw = path.read_bytes()
    for encoding in ("utf-8-sig", "utf-8", "cp1252"):
        try:
            text = raw.decode(encoding)
            path.write_text(text, encoding="utf-8", newline="")
            return
        except UnicodeDecodeError:
            continue
    raise UnicodeDecodeError("utf-8", raw, 0, 1, f"Could not decode extracted subtitle as text: {path}")

