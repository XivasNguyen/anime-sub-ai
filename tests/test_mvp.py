from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from app.formatter.ass_formatter import rebuild_ass
from app.parser.ass_parser import parse_ass
from app.quality.validator import validate_ass_file, validate_translations
from app.translator.chunker import chunk_subtitles
from app.translator.openai_provider import parse_translation_response


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


if __name__ == "__main__":
    unittest.main()

