from __future__ import annotations

import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from app.parser.ass_parser import SubtitleLine
from app.translator.base import AudioLineContext
from app.utils.subprocess_runner import ToolError, run_command


@dataclass(frozen=True)
class ASRSegment:
    start_ms: int
    end_ms: int
    text: str
    confidence: float = 0.0


@dataclass
class DualSourceReport:
    enabled: bool = False
    audio_path: str = ""
    model: str = ""
    device: str = ""
    runtime_seconds: float = 0.0
    segment_count: int = 0
    aligned_line_count: int = 0
    coverage: float = 0.0
    low_confidence_lines: list[int] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def to_json(self) -> dict[str, Any]:
        return {
            "enabled": self.enabled,
            "audio_path": self.audio_path,
            "model": self.model,
            "device": self.device,
            "runtime_seconds": self.runtime_seconds,
            "segment_count": self.segment_count,
            "aligned_line_count": self.aligned_line_count,
            "coverage": self.coverage,
            "low_confidence_lines": self.low_confidence_lines,
            "warnings": self.warnings,
        }


def build_dual_source_context(
    video: Path,
    lines: list[SubtitleLine],
    temp_dir: Path,
    *,
    enabled: bool,
    model: str = "turbo",
    device: str = "cuda",
    compute_type: str | None = None,
    low_confidence_threshold: float = 0.35,
) -> tuple[dict[int, AudioLineContext], DualSourceReport]:
    report = DualSourceReport(enabled=enabled, model=model, device=device)
    if not enabled:
        return {}, report

    started = time.perf_counter()
    try:
        audio_path = extract_audio(video, temp_dir)
        report.audio_path = str(audio_path)
        segments = transcribe_japanese_audio(audio_path, model=model, device=device, compute_type=compute_type)
        context = align_asr_segments(lines, segments, low_confidence_threshold=low_confidence_threshold)
        report.segment_count = len(segments)
        report.aligned_line_count = sum(1 for item in context.values() if item.japanese_text.strip())
        report.coverage = (report.aligned_line_count / len(lines)) if lines else 0.0
        report.low_confidence_lines = [
            index
            for index, item in sorted(context.items())
            if item.japanese_text.strip() and item.confidence < low_confidence_threshold
        ]
        return context, report
    except Exception as exc:
        report.warnings.append(f"Dual-source audio disabled after ASR failure: {exc}")
        return {}, report
    finally:
        report.runtime_seconds = time.perf_counter() - started


def extract_audio(video: Path, temp_dir: Path) -> Path:
    temp_dir.mkdir(parents=True, exist_ok=True)
    audio_path = temp_dir / f"{video.stem}.asr.wav"
    run_command(
        [
            "ffmpeg",
            "-y",
            "-i",
            str(video),
            "-map",
            "0:a:0",
            "-ac",
            "1",
            "-ar",
            "16000",
            "-vn",
            str(audio_path),
        ]
    )
    return audio_path


def transcribe_japanese_audio(
    audio_path: Path,
    *,
    model: str,
    device: str,
    compute_type: str | None = None,
    batch_size: int = 16,
) -> list[ASRSegment]:
    try:
        from faster_whisper import BatchedInferencePipeline, WhisperModel
    except ImportError as exc:
        raise ToolError("faster-whisper is not installed. Install project dependencies or disable dual-source ASR.") from exc

    selected_compute_type = compute_type or ("float16" if device == "cuda" else "int8")
    whisper_model = WhisperModel(model, device=device, compute_type=selected_compute_type)
    batched_model = BatchedInferencePipeline(model=whisper_model)
    raw_segments, _info = batched_model.transcribe(
        str(audio_path),
        language="ja",
        vad_filter=True,
        batch_size=batch_size,
    )
    segments: list[ASRSegment] = []
    for segment in raw_segments:
        text = str(segment.text or "").strip()
        if not text:
            continue
        confidence = _segment_confidence(segment)
        segments.append(
            ASRSegment(
                start_ms=int(float(segment.start) * 1000),
                end_ms=int(float(segment.end) * 1000),
                text=text,
                confidence=confidence,
            )
        )
    return segments


def align_asr_segments(
    lines: list[SubtitleLine],
    segments: list[ASRSegment],
    *,
    low_confidence_threshold: float = 0.35,
) -> dict[int, AudioLineContext]:
    context: dict[int, AudioLineContext] = {}
    for line in lines:
        overlaps: list[tuple[int, ASRSegment]] = []
        for segment in segments:
            overlap = _overlap_ms(line.start, line.end, segment.start_ms, segment.end_ms)
            if overlap > 0:
                overlaps.append((overlap, segment))
        if not overlaps:
            context[line.index] = AudioLineContext(index=line.index)
            continue
        overlaps.sort(key=lambda item: (item[0], item[1].confidence), reverse=True)
        selected = overlaps[:3]
        total_overlap = sum(overlap for overlap, _segment in selected)
        weighted_confidence = (
            sum(overlap * max(0.0, segment.confidence) for overlap, segment in selected) / total_overlap
            if total_overlap
            else 0.0
        )
        text = " ".join(_segment.text for _overlap, _segment in selected).strip()
        source = "faster-whisper-low-confidence" if weighted_confidence < low_confidence_threshold else "faster-whisper"
        context[line.index] = AudioLineContext(
            index=line.index,
            japanese_text=text,
            confidence=weighted_confidence,
            overlap_ms=total_overlap,
            source=source,
        )
    return context


def _overlap_ms(start_a: int, end_a: int, start_b: int, end_b: int) -> int:
    return max(0, min(end_a, end_b) - max(start_a, start_b))


def _segment_confidence(segment: Any) -> float:
    words = getattr(segment, "words", None) or []
    probabilities = [
        float(getattr(word, "probability", 0.0))
        for word in words
        if getattr(word, "probability", None) is not None
    ]
    if probabilities:
        return sum(probabilities) / len(probabilities)
    avg_logprob = getattr(segment, "avg_logprob", None)
    if avg_logprob is None:
        return 0.5
    try:
        return max(0.0, min(1.0, 1.0 + float(avg_logprob)))
    except (TypeError, ValueError):
        return 0.5
