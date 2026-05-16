from __future__ import annotations

import tempfile
import unittest
import asyncio
import json
from pathlib import Path
from fastapi.testclient import TestClient

from app.cache.sqlite_cache import TranslationCache, chunk_cache_key
from app.formatter.ass_formatter import rebuild_ass
from app.glossary.glossary import build_glossary, load_manual_glossary, merge_glossaries
from app.knowledge.series_bible import infer_series_title, load_or_create_series_bible
from app.parser.ass_parser import parse_ass
from app.quality.report import build_quality_report
from app.quality.validator import preserve_missing_ass_tags, validate_ass_file, validate_translations
from app.review.export import export_review_set
from app.translator.ass_mask import mask_ass_text, restore_ass_text
from app.translator.base import PromptContext, PromptTerm, TranslationChunk, TranslationResult, TranslatorProvider
from app.translator.chunker import chunk_subtitles
from app.translator.factory import create_translator
from app.translator.lmstudio_provider import LMStudioTranslator
from app.translator.json_response import parse_translation_response
from app.translator.ollama_provider import OllamaTranslator
from app.config.settings import Settings
from app.translator.pipeline import translate_lines
from app.web.main import create_app


class FakeTranslator(TranslatorProvider):
    def __init__(self) -> None:
        self.calls = 0

    async def translate(self, chunk: TranslationChunk) -> list[TranslationResult]:
        self.calls += 1
        return [TranslationResult(line.index, f"VI {line.raw_text}") for line in chunk.lines]


SAMPLE_ASS = """[Script Info]
Title: Test
ScriptType: v4.00+

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,Arial,20,&H00FFFFFF,&H000000FF,&H00000000,&H64000000,0,0,0,0,100,100,0,0,1,2,0,2,10,10,10,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
Dialogue: 0,0:00:01.00,0:00:03.00,Default,,0,0,0,,{\\an8}You're an idiot!
Dialogue: 0,0:00:04.00,0:00:05.00,Default,,0,0,0,,I know.
"""


class MvpTests(unittest.TestCase):
    def test_parse_chunk_validate_and_rebuild_ass(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            source = Path(temp) / "sample.ass"
            output = Path(temp) / "sample.vi.ass"
            source.write_text(SAMPLE_ASS, encoding="utf-8")

            parsed = parse_ass(source)
            self.assertEqual(len(parsed.lines), 2)
            self.assertEqual(parsed.lines[0].raw_text, "{\\an8}You're an idiot!")

            chunks = chunk_subtitles(parsed.lines, chunk_size=1, overlap_lines=1)
            self.assertEqual(len(chunks), 2)
            self.assertEqual([line.index for line in chunks[1].context_before], [1])

            translations = {
                1: "{\\an8}Cậu đúng là đồ ngốc!",
                2: "Tôi biết.",
            }
            report = validate_translations(parsed, translations)
            self.assertTrue(report.ok, report.errors)

            rebuild_ass(parsed, translations, output)
            self.assertTrue(validate_ass_file(output).ok)
            rebuilt = parse_ass(output)
            self.assertEqual(rebuilt.lines[0].raw_text, "{\\an8}Cậu đúng là đồ ngốc!")

    def test_parse_translation_response_rejects_missing_line(self) -> None:
        with self.assertRaisesRegex(RuntimeError, "Missing translations"):
            parse_translation_response(
                '{"translations":[{"index":1,"translated_text":"Xin chào"}]}',
                {1, 2},
            )

    def test_parse_translation_response_extracts_json_from_text(self) -> None:
        response = """
        Here is the JSON:
        ```json
        {"translations":[{"index":1,"translated_text":"Xin chào"}]}
        ```
        """
        parsed = parse_translation_response(response, {1})
        self.assertEqual(parsed[0].translated_text, "Xin chào")

    def test_parse_translation_response_repairs_trailing_comma(self) -> None:
        parsed = parse_translation_response(
            '{"translations":[{"index":1,"translated_text":"Xin chào",},],}',
            {1},
        )
        self.assertEqual(parsed[0].translated_text, "Xin chào")

    def test_ass_tag_mask_and_restore(self) -> None:
        original = "{\\an8}Hello {\\i1}there\\Nfriend"
        masked = mask_ass_text(original)
        self.assertEqual(masked.text, "[[ASS_TAG_00]]Hello [[ASS_TAG_01]]there\\Nfriend")
        restored = restore_ass_text("[[ASS_TAG_00]]Xin chào [[ASS_TAG_01]]bạn\\Nơi", original)
        self.assertEqual(restored, "{\\an8}Xin chào {\\i1}bạn\\Nơi")

    def test_sqlite_cache_round_trip_and_key_changes_by_glossary_version(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            source = Path(temp) / "sample.ass"
            source.write_text(SAMPLE_ASS, encoding="utf-8")
            parsed = parse_ass(source)
            chunk = chunk_subtitles(
                parsed.lines,
                chunk_size=2,
                prompt_context=PromptContext(
                    series_title="Test",
                    terms=[PromptTerm(source="Ayanokoji", target="Ayanokoji")],
                    version="glossary-a",
                ),
            )[0]
            key_a = chunk_cache_key(
                chunk,
                provider="lmstudio",
                model="qwen",
                prompt_version="p1",
                glossary_version="glossary-a",
                ass_version="a1",
            )
            key_b = chunk_cache_key(
                chunk,
                provider="lmstudio",
                model="qwen",
                prompt_version="p1",
                glossary_version="glossary-b",
                ass_version="a1",
            )
            self.assertNotEqual(key_a, key_b)

            cache = TranslationCache(Path(temp) / "cache.sqlite")
            cache.put_chunk(key_a, [TranslationResult(1, "Xin chào")], {"model": "qwen"})
            cached = cache.get_chunk(key_a)
            cache.close()
            self.assertIsNotNone(cached)
            assert cached is not None
            self.assertEqual(cached[0].translated_text, "Xin chào")

    def test_translate_lines_uses_cache_on_second_run(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            source = Path(temp) / "sample.ass"
            source.write_text(SAMPLE_ASS, encoding="utf-8")
            parsed = parse_ass(source)
            cache = TranslationCache(Path(temp) / "cache.sqlite")
            provider = FakeTranslator()

            first = asyncio.run(
                translate_lines(
                    parsed.lines,
                    provider,
                    chunk_size=2,
                    overlap_lines=0,
                    max_concurrency=1,
                    prompt_context=PromptContext(series_title="Test", version="v1"),
                    cache=cache,
                    provider_name="fake",
                    model="fake-model",
                )
            )
            second = asyncio.run(
                translate_lines(
                    parsed.lines,
                    provider,
                    chunk_size=2,
                    overlap_lines=0,
                    max_concurrency=1,
                    prompt_context=PromptContext(series_title="Test", version="v1"),
                    cache=cache,
                    provider_name="fake",
                    model="fake-model",
                )
            )
            cache.close()
            self.assertEqual(first, second)
            self.assertEqual(provider.calls, 1)

    def test_series_bible_cached_without_web(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            title = infer_series_title(Path("[SubsPlease] Example Anime S2 - 10 (1080p).mkv"))
            self.assertEqual(title, "Example Anime")
            bible = load_or_create_series_bible(title, Path(temp), enable_web=False)
            loaded = load_or_create_series_bible(title, Path(temp), enable_web=False)
            self.assertEqual(bible.title, loaded.title)

    def test_glossary_extracts_repeated_terms_and_validates_protected_terms(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            source = Path(temp) / "sample.ass"
            source.write_text(
                SAMPLE_ASS
                + "Dialogue: 0,0:00:06.00,0:00:07.00,Default,,0,0,0,,Ayanokoji is here.\n"
                + "Dialogue: 0,0:00:08.00,0:00:09.00,Default,,0,0,0,,Ayanokoji-kun?\n",
                encoding="utf-8",
            )
            parsed = parse_ass(source)
            glossary = build_glossary(parsed.lines)
            self.assertIn("Ayanokoji", {term.source for term in glossary.terms})
            report = validate_translations(
                parsed,
                {
                    1: "{\\an8}Cậu đúng là đồ ngốc!",
                    2: "Tôi biết.",
                    3: "Cậu ấy ở đây.",
                    4: "Cậu ấy à?",
                },
                glossary=glossary,
            )
            self.assertTrue(any("protected glossary term" in warning.lower() for warning in report.warnings))

    def test_manual_glossary_overrides_auto_terms(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "glossary.json"
            path.write_text(
                json.dumps({"terms": [{"source": "Ayanokoji", "target": "Ayanokouji", "protected": True}]}),
                encoding="utf-8",
            )
            manual = load_manual_glossary(path)
            auto = build_glossary([])
            merged = merge_glossaries(manual, auto)
            self.assertEqual(merged.terms[0].target, "Ayanokouji")

    def test_quality_report_flags_cjk_and_placeholder_leak(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            source = Path(temp) / "sample.ass"
            source.write_text(SAMPLE_ASS, encoding="utf-8")
            parsed = parse_ass(source)
            report = build_quality_report(
                parsed.lines[:1],
                {1: "{\\an8}Xin chào [[ASS_TAG_00]] 你好"},
            )
            codes = {item.code for item in report.diagnostics}
            self.assertIn("placeholder_leak", codes)
            self.assertIn("cjk_leakage", codes)

    def test_preserve_missing_ass_tags(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            source = Path(temp) / "sample.ass"
            source.write_text(SAMPLE_ASS, encoding="utf-8")
            parsed = parse_ass(source)

            fixed = preserve_missing_ass_tags(parsed.lines[:1], {1: "Cậu tới muộn rồi."})
            self.assertEqual(fixed[1], "{\\an8}Cậu tới muộn rồi.")

    def test_export_review_set_json(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            source = Path(temp) / "source.ass"
            translated = Path(temp) / "translated.ass"
            output = Path(temp) / "review.json"
            source.write_text(SAMPLE_ASS, encoding="utf-8")
            translated.write_text(SAMPLE_ASS.replace("You're an idiot!", "Cậu đúng là đồ ngốc!"), encoding="utf-8")

            export_review_set(source, translated, output, limit_lines=1)
            rows = json.loads(output.read_text(encoding="utf-8"))
            self.assertEqual(rows[0]["index"], 1)
            self.assertIn("Cậu đúng là đồ ngốc!", rows[0]["translated_text"])

    def test_create_ollama_translator(self) -> None:
        settings = Settings(provider="ollama")
        translator = create_translator(settings, provider_name="ollama", model="qwen2.5:7b")
        self.assertIsInstance(translator, OllamaTranslator)
        self.assertEqual(translator.model, "qwen2.5:7b")

    def test_create_lmstudio_translator(self) -> None:
        settings = Settings(provider="lmstudio")
        translator = create_translator(settings, provider_name="lmstudio", model="google/gemma-3-12b")
        self.assertIsInstance(translator, LMStudioTranslator)
        self.assertEqual(translator.model, "google/gemma-3-12b")

    def test_web_dashboard_and_settings_routes(self) -> None:
        client = TestClient(create_app())
        dashboard = client.get("/")
        self.assertEqual(dashboard.status_code, 200)
        settings = client.get("/api/settings")
        self.assertEqual(settings.status_code, 200)
        self.assertIn("tools", settings.json())


if __name__ == "__main__":
    unittest.main()
