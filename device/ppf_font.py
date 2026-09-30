# AthenaOS PPF font reader / renderer.
#
# PPF is the same binary format emitted by PPF Studio and used by Mercury.
# Athena keeps only the compact glyph table in RAM and streams glyph bitmaps
# from disk as they are drawn.

try:
    import uos as os
except ImportError:
    import os

MAGIC = b"ppf!"
HEADER_BYTES = 46
GLYPH_TABLE_BYTES = 6


def _u16(data, offset):
    return (data[offset] << 8) | data[offset + 1]


def _u32(data, offset):
    return (
        (data[offset] << 24)
        | (data[offset + 1] << 16)
        | (data[offset + 2] << 8)
        | data[offset + 3]
    )


class PPFError(ValueError):
    pass


class PPFFont:
    """Streaming reader for the binary PPF format produced by PPF Studio."""

    def __init__(self, path):
        self.path = str(path)
        self.name = ""
        self.flags = 0
        self.header_width = 0
        self.height = 0
        self.count = 0
        self.bytes_per_row = 0
        self.glyph_size = 0
        self.bitmap_offset = 0
        self.space_advance = 1
        self._glyphs = {}
        self._fallback_codepoint = None
        self._load_header()

    def _load_header(self):
        with open(self.path, "rb") as handle:
            header = handle.read(HEADER_BYTES)
            if len(header) < HEADER_BYTES or header[:4] != MAGIC:
                raise PPFError("Not a valid PPF file: " + self.path)

            self.flags = _u16(header, 4)
            self.count = _u32(header, 6)
            self.header_width = _u16(header, 10)
            self.height = _u16(header, 12)

            raw_name = header[14:46].split(b"\0", 1)[0]
            try:
                self.name = raw_name.decode("utf-8")
            except Exception:
                self.name = "PPF Font"

            if self.header_width <= 0 or self.height <= 0:
                raise PPFError("Invalid PPF dimensions")
            if self.count > 4096:
                raise PPFError("Unreasonable PPF glyph count")

            table = handle.read(self.count * GLYPH_TABLE_BYTES)
            if len(table) != self.count * GLYPH_TABLE_BYTES:
                raise PPFError("Truncated PPF glyph table")

            self.bytes_per_row = (self.header_width + 7) // 8
            self.glyph_size = self.bytes_per_row * self.height
            self.bitmap_offset = HEADER_BYTES + (self.count * GLYPH_TABLE_BYTES)

            for index in range(self.count):
                pos = index * GLYPH_TABLE_BYTES
                codepoint = _u32(table, pos)
                width = _u16(table, pos + 4)
                if width <= 0:
                    width = 1
                if width > self.header_width:
                    width = self.header_width
                self._glyphs[codepoint] = (width, index)

        # PPF Studio omits a bitmap for space. For monospace exports
        # header_width is advance * 3; for proportional exports it is the
        # editable cell width. This mirrors the PPF Studio/PicoVector rule.
        self.space_advance = max(1, self.header_width // 3)

        if 63 in self._glyphs:  # '?'
            self._fallback_codepoint = 63
        elif self._glyphs:
            for codepoint in self._glyphs:
                self._fallback_codepoint = codepoint
                break

    @property
    def line_height(self):
        return self.height

    def has_glyph(self, char_or_codepoint):
        if isinstance(char_or_codepoint, int):
            codepoint = char_or_codepoint
        else:
            value = str(char_or_codepoint)
            if not value:
                return False
            codepoint = ord(value[0])
        return codepoint == 32 or codepoint in self._glyphs

    def _entry(self, codepoint):
        entry = self._glyphs.get(codepoint)
        if entry is None and self._fallback_codepoint is not None:
            entry = self._glyphs.get(self._fallback_codepoint)
        return entry

    def advance_for_codepoint(self, codepoint, scale=1):
        scale = max(1, int(scale))
        if codepoint == 9:
            return self.space_advance * 4 * scale
        if codepoint == 32:
            return self.space_advance * scale

        entry = self._entry(codepoint)
        if entry is None:
            return self.space_advance * scale

        width, _index = entry
        # PPF Studio exports monospace width as advance-1 and its importer
        # reconstructs proportional advance as stored width + 1.
        return (width + 1) * scale

    def measure_text(self, text, scale=1):
        width = 0
        for char in str(text):
            if char in "\r\n":
                break
            width += self.advance_for_codepoint(ord(char), scale)
        return width

    def _read_bitmap(self, handle, index):
        handle.seek(self.bitmap_offset + (index * self.glyph_size))
        data = handle.read(self.glyph_size)
        if len(data) != self.glyph_size:
            raise PPFError("Truncated PPF glyph bitmap")
        return data

    def draw_text(self, canvas, text, x, y, scale=1):
        """Draw text onto an Athena Canvas and return the final cursor x.

        Glyph rows are emitted as horizontal runs rather than one rectangle per
        lit pixel. Canvas.rectangle() handles portrait mapping automatically.
        """
        scale = max(1, int(scale))
        cursor_x = int(x)
        origin_y = int(y)

        with open(self.path, "rb") as handle:
            for char in str(text):
                if char == "\r":
                    continue
                if char == "\n":
                    break

                codepoint = ord(char)
                if codepoint == 9:
                    cursor_x += self.space_advance * 4 * scale
                    continue
                if codepoint == 32:
                    cursor_x += self.space_advance * scale
                    continue

                entry = self._entry(codepoint)
                if entry is None:
                    cursor_x += self.space_advance * scale
                    continue

                width, index = entry
                bitmap = self._read_bitmap(handle, index)

                for row in range(self.height):
                    row_offset = row * self.bytes_per_row
                    run_start = -1

                    # One extra iteration flushes a run that reaches width.
                    for col in range(width + 1):
                        on = False
                        if col < width:
                            byte = bitmap[row_offset + (col // 8)]
                            on = bool(byte & (1 << (7 - (col & 7))))

                        if on and run_start < 0:
                            run_start = col
                        elif not on and run_start >= 0:
                            canvas.rectangle(
                                cursor_x + (run_start * scale),
                                origin_y + (row * scale),
                                (col - run_start) * scale,
                                scale,
                            )
                            run_start = -1

                cursor_x += (width + 1) * scale

        return cursor_x


def inspect(path):
    font = PPFFont(path)
    return {
        "path": font.path,
        "name": font.name,
        "glyphs": font.count,
        "width": font.header_width,
        "height": font.height,
        "space_advance": font.space_advance,
    }
