from __future__ import annotations

import asyncio
from pathlib import Path

import typer

from app.config.settings import load_settings
from app.extractor.subtitle_extractor import extract_subtitle, inspect_subtitles
from app.formatter.ass_formatter import rebuild_ass
from app.muxer.mkv_muxer import mux_softsub
from app.parser.ass_parser import parse_ass
from app.quality.validator import validate_ass_file, validate_translations
from app.translator.factory import SUPPORTED_PROVIDERS, create_translator
from app.translator.pipeline import translate_lines

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
    keep_en_sub: bool = typer.Option(True, "--keep-en-sub/--no-keep-en-sub"),
    set_default_sub: bool | None = typer.Option(None, "--set-default-sub/--no-set-default-sub"),
    dry_run: bool = typer.Option(False, "--dry-run"),
    debug: bool = typer.Option(False, "--debug"),
) -> None:
    """Extract, translate, rebuild, validate, and mux a Vietnamese softsub MKV."""
    del keep_en_sub, debug
    settings = load_settings()
    provider_name = (provider or settings.provider).lower()
    if provider_name not in SUPPORTED_PROVIDERS:
        raise typer.BadParameter(f"Unsupported provider. Use one of: {', '.join(SUPPORTED_PROVIDERS)}")

    output_dir = settings.output.directory
    temp_dir = settings.output.temp_directory
    output_dir.mkdir(parents=True, exist_ok=True)
    temp_dir.mkdir(parents=True, exist_ok=True)

    typer.echo("Extracting subtitle track...")
    source_subtitle = extract_subtitle(video, temp_dir)
    parsed = parse_ass(source_subtitle)

    if dry_run:
        typer.echo(f"Dry run complete. Extracted {len(parsed.lines)} lines from {source_subtitle}.")
        return

    translator = create_translator(settings, provider_name=provider_name, model=model)
    translations = asyncio.run(
        translate_lines(
            parsed.lines,
            translator,
            chunk_size=batch_size or settings.translation.chunk_size,
            overlap_lines=settings.translation.overlap_lines,
            max_concurrency=max_concurrency or settings.translation.max_concurrency,
        )
    )

    report = validate_translations(parsed, translations)
    for warning in report.warnings:
        typer.echo(f"warning: {warning}")
    report.raise_for_errors()

    vi_ass = output_dir / f"{video.stem}.vi.ass"
    rebuild_ass(parsed, translations, vi_ass)
    validate_ass_file(vi_ass).raise_for_errors()
    typer.echo(f"Wrote subtitle: {vi_ass}")

    output_mkv = output_dir / f"{video.stem}.vi.mkv"
    mux_softsub(
        video,
        vi_ass,
        output_mkv,
        language=settings.mux.subtitle_language,
        track_name=settings.mux.subtitle_track_name,
        set_default=settings.mux.set_default_sub if set_default_sub is None else set_default_sub,
    )
    typer.echo(f"Wrote MKV: {output_mkv}")
