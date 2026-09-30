import struct
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "device"))

from ppf_font import PPFFont, PPFError


def pack_bitmap(rows, header_width, height):
    bpr = (header_width + 7) // 8
    out = bytearray(bpr * height)
    for y, row in enumerate(rows[:height]):
        for x, value in enumerate(row[:header_width]):
            if value:
                out[y * bpr + (x // 8)] |= 1 << (7 - (x & 7))
    return bytes(out)


def write_fixture(path):
    width = 6
    height = 5
    glyphs = [
        (63, 3, ["111000", "001000", "011000", "000000", "010000"]),
        (65, 3, ["010000", "101000", "111000", "101000", "101000"]),
        (73, 1, ["100000", "100000", "100000", "100000", "100000"]),
    ]

    name = b"Test Proportional"
    with open(path, "wb") as handle:
        handle.write(b"ppf!")
        handle.write(struct.pack(">H", 0))
        handle.write(struct.pack(">I", len(glyphs)))
        handle.write(struct.pack(">H", width))
        handle.write(struct.pack(">H", height))
        handle.write(name + b"\0" * (32 - len(name)))

        for codepoint, glyph_width, _rows in glyphs:
            handle.write(struct.pack(">I", codepoint))
            handle.write(struct.pack(">H", glyph_width))

        for _codepoint, _glyph_width, rows in glyphs:
            bits = [[1 if c == "1" else 0 for c in row] for row in rows]
            handle.write(pack_bitmap(bits, width, height))


class FakeCanvas:
    def __init__(self):
        self.rectangles = []

    def rectangle(self, x, y, w, h):
        self.rectangles.append((x, y, w, h))


class PPFFontTests(unittest.TestCase):
    def test_proportional_measure_and_draw(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "fixture.ppf"
            write_fixture(path)
            font = PPFFont(path)

            self.assertEqual(font.name, "Test Proportional")
            self.assertEqual(font.height, 5)
            self.assertEqual(font.space_advance, 2)

            # A advances 4, I advances 2, space advances 2.
            self.assertEqual(font.measure_text("AI A"), 12)

            canvas = FakeCanvas()
            end_x = font.draw_text(canvas, "AI", 10, 20)
            self.assertEqual(end_x, 16)
            self.assertTrue(canvas.rectangles)

    def test_missing_glyph_uses_question_mark(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "fixture.ppf"
            write_fixture(path)
            font = PPFFont(path)
            self.assertEqual(font.measure_text("£"), 4)

    def test_rejects_bad_magic(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "bad.ppf"
            path.write_bytes(b"nope")
            with self.assertRaises(PPFError):
                PPFFont(path)


if __name__ == "__main__":
    unittest.main()
