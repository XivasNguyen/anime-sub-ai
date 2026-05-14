from __future__ import annotations

from pathlib import Path

import typer

from app.config.settings import load_settings
from app.extractor.subtitle_extractor import extract_subtitle, inspect_subtitles
from app.jobs.service import TranslationJobOptions, start_job
from app.muxer.mkv_muxer import mux_softsub
from app.quality.validator import validate_ass_file
from app.translator.factory import SUPPORTED_PROVIDERS

app = typer.Typer(help="Anime AI subtitle pipeline MVP.")


@app.command()
def inspect(video: Path) -> None:
    """List subtitle tracks in an MKV file."""
    tracks = inspect_subtitles(video)
    if not tracks:
        typer.echo("No subtitle tracks found.")
        raise typer.Exit(code=1)
    for track in tracks:
        typer.echo(f"id={track.id} codec={track.codec} language={track.language or '-'} name={track.name or '-'}")


@app.command()
def extract(
    video: Path,
    output_dir: Path = typer.Option(Path("temp"), "--output-dir", "-o"),
) -> None:
    """Extract the best subtitle track from an MKV file."""
    subtitle = extract_subtitle(video, output_dir)
    typer.echo(str(subtitle))


@app.command()
def validate(subtitle: Path) -> None:
    """Validate that an ASS subtitle file can be loaded."""
    report = validate_ass_file(subtitle)
    for warning in report.warnings:
        typer.echo(f"warning: {warning}")
    report.raise_for_errors()
    typer.echo("ASS validation passed.")


@app.command()
def mux(
    video: Path,
    subtitle: Path,
    output: Path | None = typer.Option(None, "--output", "-o"),
    set_default_sub: bool = typer.Option(True, "--set-default-sub/--no-set-default-sub"),
) -> None:
    """Mux a Vietnamese ASS subtitle into the original MKV as a softsub track."""
    settings = load_settings()
    output_path = output or Path("output") / f"{video.stem}.vi.mkv"
    result = mux_softsub(
        video,
        subtitle,
        output_path,
        language=settings.mux.subtitle_language,
        track_name=settings.mux.subtitle_track_name,
        set_default=set_default_sub,
    )
    typer.echo(str(result))


@app.command()
def translate(
    video: Path,
    provider: str | None = typer.Option(None, "--provider"),
    model: str | None = typer.Option(None, "--model"),
    batch_size: int | None = typer.Option(None, "--batch-size"),
    max_concurrency: int | None = typer.Option(None, "--max-concurrency"),
    start_line: int = typer.Option(1, "--start-line", min=1),
    limit_lines: int | None = typer.Option(None, "--limit-lines", min=1),
    skip_mux: bool = typer.Option(False, "--skip-mux"),
    keep_en_sub: bool = typer.Option(True, "--keep-en-sub/--no-keep-en-sub"),
    set_default_sub: bool | None = typer.Option(None, "--set-default-sub/--no-set-default-sub"),
    resume: bool = typer.Option(True, "--resume/--no-resume"),
    force_retranslate: bool = typer.Option(False, "--force-retranslate"),
    cache_path: Path | None = typer.Option(None, "--cache-path"),
    series_title: str | None = typer.Option(None, "--series-title"),
    knowledge: bool | None = typer.Option(None, "--knowledge/--no-knowledge"),
    knowledge_web: bool | None = typer.Option(None, "--knowledge-web/--no-knowledge-web"),
    spoiler_mode: str | None = typer.Option(None, "--spoiler-mode"),
    dry_run: bool = typer.Option(False, "--dry-run"),
    debug: bool = typer.Option(False, "--debug"),
) -> None:
    """Extract, translate, rebuild, validate, and mux a Vietnamese softsub MKV."""
    del keep_en_sub, debug
    settings = load_settings()
    provider_name = (provider or settings.provider).lower()
    if provider_name not in SUPPORTED_PROVIDERS:
        raise typer.BadParameter(f"Unsupported provider. Use one of: {', '.join(SUPPORTED_PROVIDERS)}")

    typer.echo("Starting translation job...")
    result = start_job(
        settings,
        TranslationJobOptions(
            video=video,
            provider_name=provider_name,
            model=model,
            batch_size=batch_size,
            max_concurrency=max_concurrency,
            start_line=start_line,
            limit_lines=limit_lines,
            skip_mux=skip_mux,
            set_default_sub=set_default_sub,
            dry_run=dry_run,
            series_title=series_title,
            knowledge_enabled=knowledge,
            knowledge_web=knowledge_web,
            spoiler_mode=spoiler_mode,
            resume=resume,
            force_retranslate=force_retranslate,
            cache_path=cache_path,
        ),
    )
    for warning in result.report.warnings:
        typer.echo(f"warning: {warning}")
    if result.subtitle_path:
        typer.echo(f"Wrote subtitle: {result.subtitle_path}")
    if result.mkv_path:
        typer.echo(f"Wrote MKV: {result.mkv_path}")
    if result.report_path:
        typer.echo(f"Wrote report: {result.report_path}")
    typer.echo(
        f"Translated {result.report.translated_lines} lines in {result.report.elapsed_seconds:.1f}s "
        f"({result.report.lines_per_second:.2f} lines/s, cache hits={result.report.cache_hits})."
    )


@app.command()
def benchmark(
    video: Path,
    provider: str | None = typer.Option("lmstudio", "--provider"),
    model: str | None = typer.Option(None, "--model"),
    lines: int = typer.Option(50, "--lines", min=1),
    batch_sizes: str = typer.Option("6,8,10,12", "--batch-sizes"),
    series_title: str | None = typer.Option(None, "--series-title"),
    knowledge: bool | None = typer.Option(None, "--knowledge/--no-knowledge"),
    force_retranslate: bool = typer.Option(True, "--force-retranslate/--use-cache"),
) -> None:
    """Benchmark provider/model batch sizes on a small subtitle slice."""
    settings = load_settings()
    provider_name = (provider or settings.provider).lower()
    if provider_name not in SUPPORTED_PROVIDERS:
        raise typer.BadParameter(f"Unsupported provider. Use one of: {', '.join(SUPPORTED_PROVIDERS)}")
    sizes = [int(item.strip()) for item in batch_sizes.split(",") if item.strip()]
    typer.echo(f"Benchmarking {provider_name} for {lines} lines...")
    for size in sizes:
        result = start_job(
            settings,
            TranslationJobOptions(
                video=video,
                provider_name=provider_name,
                model=model,
                batch_size=size,
                max_concurrency=1,
                limit_lines=lines,
                skip_mux=True,
                series_title=series_title,
                knowledge_enabled=knowledge,
                force_retranslate=force_retranslate,
            ),
        )
        estimated_382 = 382 / result.report.lines_per_second if result.report.lines_per_second > 0 else 0.0
        typer.echo(
            f"batch={size}: {result.report.elapsed_seconds:.1f}s, "
            f"{result.report.lines_per_second:.2f} lines/s, "
            f"est382={estimated_382:.1f}s, warnings={len(result.report.warnings)}, "
            f"cache_hits={result.report.cache_hits}"
        )
