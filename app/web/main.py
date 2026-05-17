from __future__ import annotations

import json
import threading
import time
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse, StreamingResponse
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel

from app.config.settings import load_settings
from app.extractor.subtitle_extractor import inspect_subtitles
from app.glossary.glossary import load_manual_glossary
from app.jobs.service import (
    TranslationJobOptions,
    cancel_job,
    create_job,
    get_progress,
    list_outputs,
    start_job,
)
from app.translator.factory import SUPPORTED_PROVIDERS
from app.translator.health import ProviderHealth, check_provider_health
from app.utils.subprocess_runner import command_available


templates = Jinja2Templates(directory=str(Path(__file__).parent / "templates"))


class JobRequest(BaseModel):
    video: str
    provider: str = "lmstudio"
    model: str | None = None
    batch_size: int | None = None
    max_concurrency: int | None = None
    limit_lines: int | None = None
    skip_mux: bool = False
    repair_warnings: bool = False
    repair_mode: str | None = None
    quality_preset: str | None = None
    dual_source: bool | None = None
    asr_model: str | None = None
    asr_device: str | None = None
    series_title: str | None = None
    knowledge: bool | None = None
    force_retranslate: bool = False


class BenchmarkRequest(JobRequest):
    lines: int = 50


class ProviderCheckRequest(BaseModel):
    provider: str = "lmstudio"
    model: str | None = None


class GlossarySaveRequest(BaseModel):
    terms: list[dict[str, Any]]


def create_app() -> FastAPI:
    app = FastAPI(title="anime-sub-ai")

    @app.get("/", response_class=HTMLResponse)
    def dashboard(request: Request) -> HTMLResponse:
        settings = load_settings()
        return templates.TemplateResponse(
            request,
            "index.html",
            {
                "providers": SUPPORTED_PROVIDERS,
                "settings": settings,
            },
        )

    @app.get("/api/settings")
    def settings_api() -> dict[str, Any]:
        settings = load_settings()
        return {
            "provider": settings.provider,
            "lmstudio": {"base_url": settings.lmstudio.base_url, "model": settings.lmstudio.model},
            "openai_key_set": bool(settings.openai.api_key),
            "cache_path": str(settings.cache.path),
            "glossary_path": str(settings.glossary.path),
            "tools": {
                "ffmpeg": command_available("ffmpeg"),
                "mkvmerge": command_available("mkvmerge"),
                "mkvextract": command_available("mkvextract"),
            },
            "asr": {
                "dual_source": settings.asr.dual_source,
                "model": settings.asr.model,
                "device": settings.asr.device,
            },
        }

    @app.get("/api/dialog/mkv")
    async def mkv_file_dialog_api() -> dict[str, str | bool]:
        try:
            selected = _pick_mkv_file()
        except Exception as exc:
            raise HTTPException(status_code=500, detail=f"Could not open file picker: {exc}") from exc
        return {"selected": bool(selected), "path": selected}

    @app.post("/api/providers/check")
    async def provider_check_api(request: ProviderCheckRequest) -> dict[str, Any]:
        _validate_provider(request.provider)
        health = await check_provider_health(load_settings(), request.provider, model=request.model)
        return health.to_json()

    @app.get("/api/inspect")
    def inspect_api(video: str) -> dict[str, Any]:
        video_path = _validate_video_path(video)
        try:
            tracks = inspect_subtitles(video_path)
        except Exception as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return {"tracks": [track.__dict__ for track in tracks]}

    @app.post("/api/jobs")
    async def create_translation_job(request: JobRequest) -> dict[str, str]:
        settings = load_settings()
        _validate_provider(request.provider)
        _validate_job_request(request)
        health = await check_provider_health(settings, request.provider, model=request.model)
        _raise_if_provider_unavailable(health)
        options = _options_from_request(request, skip_mux=request.skip_mux)
        job_id = create_job(settings, options)
        thread = threading.Thread(target=_run_job, args=(job_id, options), daemon=True)
        thread.start()
        return {"job_id": job_id}

    @app.post("/api/benchmark")
    async def benchmark_api(request: BenchmarkRequest) -> dict[str, str]:
        settings = load_settings()
        _validate_provider(request.provider)
        _validate_job_request(request)
        if request.lines < 1:
            raise HTTPException(status_code=400, detail="Benchmark lines must be greater than 0.")
        health = await check_provider_health(settings, request.provider, model=request.model)
        _raise_if_provider_unavailable(health)
        options = _options_from_request(request, skip_mux=True)
        options.limit_lines = request.lines
        job_id = create_job(settings, options)
        thread = threading.Thread(target=_run_job, args=(job_id, options), daemon=True)
        thread.start()
        return {"job_id": job_id}

    @app.get("/api/jobs/{job_id}")
    def job_status(job_id: str) -> dict[str, Any]:
        progress = get_progress(load_settings(), job_id)
        if not progress:
            raise HTTPException(status_code=404, detail="Job not found")
        return progress

    @app.post("/api/jobs/{job_id}/cancel")
    def cancel_job_api(job_id: str) -> dict[str, bool]:
        cancel_job(load_settings(), job_id)
        return {"ok": True}

    @app.get("/api/jobs/{job_id}/events")
    def job_events(job_id: str) -> StreamingResponse:
        def stream():
            while True:
                progress = get_progress(load_settings(), job_id)
                yield f"data: {json.dumps(progress, ensure_ascii=False)}\n\n"
                if progress.get("status") in {"completed", "failed", "cancelled"}:
                    break
                time.sleep(1)

        return StreamingResponse(stream(), media_type="text/event-stream")

    @app.get("/api/outputs")
    def outputs_api() -> dict[str, list[str]]:
        return {"outputs": [str(path) for path in list_outputs(load_settings())]}

    @app.get("/api/reports")
    def reports_api() -> dict[str, list[str]]:
        output_dir = load_settings().output.directory
        reports = sorted(output_dir.glob("*.report.json")) if output_dir.exists() else []
        return {"reports": [str(path) for path in reports]}

    @app.get("/api/reports/{report_name}")
    def report_detail_api(report_name: str) -> dict[str, Any]:
        output_dir = load_settings().output.directory.resolve()
        path = (output_dir / report_name).resolve()
        if output_dir not in path.parents and path != output_dir:
            raise HTTPException(status_code=400, detail="Invalid report path")
        if not path.exists() or path.suffix != ".json":
            raise HTTPException(status_code=404, detail="Report not found")
        return json.loads(path.read_text(encoding="utf-8"))

    @app.get("/api/glossary")
    def glossary_api() -> dict[str, Any]:
        settings = load_settings()
        glossary = load_manual_glossary(settings.glossary.path)
        return {"path": str(settings.glossary.path), "terms": [term.__dict__ for term in glossary.terms]}

    @app.post("/api/glossary")
    def save_glossary_api(request: GlossarySaveRequest) -> JSONResponse:
        settings = load_settings()
        settings.glossary.path.parent.mkdir(parents=True, exist_ok=True)
        settings.glossary.path.write_text(
            json.dumps({"terms": request.terms}, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        return JSONResponse({"ok": True, "path": str(settings.glossary.path)})

    return app


def _validate_provider(provider: str) -> None:
    if provider.lower() not in SUPPORTED_PROVIDERS:
        raise HTTPException(status_code=400, detail=f"Unsupported provider: {provider}")


def _raise_if_provider_unavailable(health: ProviderHealth) -> None:
    if not health.available:
        raise HTTPException(status_code=503, detail=health.to_json())


def _validate_job_request(request: JobRequest) -> None:
    _validate_video_path(request.video)
    if request.batch_size is not None and request.batch_size < 1:
        raise HTTPException(status_code=400, detail="Batch size must be greater than 0.")
    if request.max_concurrency is not None and request.max_concurrency < 1:
        raise HTTPException(status_code=400, detail="Concurrency must be greater than 0.")
    if request.limit_lines is not None and request.limit_lines < 1:
        raise HTTPException(status_code=400, detail="Limit lines must be greater than 0.")


def _validate_video_path(video: str) -> Path:
    if not video.strip():
        raise HTTPException(status_code=400, detail="MKV path is required.")
    path = Path(video.strip()).expanduser()
    if not path.exists():
        raise HTTPException(status_code=400, detail=f"MKV path does not exist: {path}")
    if not path.is_file():
        raise HTTPException(status_code=400, detail=f"MKV path is not a file: {path}")
    if path.suffix.lower() != ".mkv":
        raise HTTPException(status_code=400, detail="Input video must be an .mkv file.")
    return path


def _options_from_request(request: JobRequest, *, skip_mux: bool) -> TranslationJobOptions:
    return TranslationJobOptions(
        video=Path(request.video),
        provider_name=request.provider.lower(),
        model=request.model,
        batch_size=request.batch_size,
        max_concurrency=request.max_concurrency,
        limit_lines=request.limit_lines,
        skip_mux=skip_mux,
        repair_warnings=request.repair_warnings,
        repair_mode=request.repair_mode,
        quality_preset=request.quality_preset,
        dual_source=request.dual_source,
        asr_model=request.asr_model,
        asr_device=request.asr_device,
        series_title=request.series_title,
        knowledge_enabled=request.knowledge,
        force_retranslate=request.force_retranslate,
    )


def _run_job(job_id: str, options: TranslationJobOptions) -> None:
    try:
        start_job(load_settings(), options, job_id=job_id)
    except Exception:
        pass


def _pick_mkv_file() -> str:
    import tkinter as tk
    from tkinter import filedialog

    root = tk.Tk()
    root.withdraw()
    root.attributes("-topmost", True)
    try:
        selected = filedialog.askopenfilename(
            title="Select MKV file",
            filetypes=[("Matroska video", "*.mkv"), ("All files", "*.*")],
        )
    finally:
        root.destroy()
    return str(selected or "")


app = create_app()
