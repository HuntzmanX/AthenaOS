# AthenaOS PPF fonts

AthenaOS v0.4 can render the same binary `.ppf` files produced by PPF Studio and used by Mercury.

## Copy fonts to Athena

The simplest location is:

```text
/fonts/
```

Athena also searches:

```text
/athena/fonts/
/sd/fonts/
/sd/athena/fonts/
```

Fonts are loaded by **name without the `.ppf` suffix**:

```python
import _fonts

book = _fonts.load("book-12")       # /fonts/book-12.ppf
print(_fonts.available())
print(_fonts.diagnose("book-12"))
```

The loader caches parsed font headers/tables. Glyph bitmap bytes remain on disk and are streamed only while drawing, keeping RAM use small.

## Semantic roles

The renderer asks for five roles configured in `device/config.py`:

```python
FONT_BODY = "body"
FONT_SMALL = "small"
FONT_HEADING = "heading"
FONT_TITLE = "title"
FONT_MONO = "mono"
```

Change those values to the stems of your own PPF files. For example:

```python
FONT_BODY = "source-sans-12"
FONT_SMALL = "source-sans-9"
FONT_HEADING = "source-sans-bold-16"
FONT_TITLE = "source-sans-bold-20"
FONT_MONO = "code-10"
```

You can point several roles at the same file while building a font set.

A missing or invalid PPF falls back **for that role only** to Athena's previous PicoGraphics `bitmap8` rendering, so the display remains usable while fonts are being changed.

## Proportional spacing

PPF already stores a width for each glyph. Athena mirrors PPF Studio's interpretation:

```text
glyph advance = stored glyph width + 1
```

Space has no bitmap in PPF and uses the normal PPF convention derived from the file's header width.

That means proportional fonts from PPF Studio work without a new file format. A deliberately monospace PPF remains monospace.

## Rendering

Custom PPF text is monochrome and drawn into Athena's logical canvas. The same renderer therefore works in:

- 800x480 landscape
- software-mapped 480x800 portrait

Glyph rows are drawn as horizontal runs instead of one graphics call per lit pixel.

Font dimensions are intrinsic. A 12-pixel body font normally renders at 1x and pagination uses its real 12-pixel height. Large notice text may deliberately scale the title font.

## Quick hardware check

After copying one or more PPF files to `/fonts`, use Thonny:

```python
import fonts

print(fonts.available())
print(_fonts.diagnose("your-font-name"))
```

A successful diagnostic looks roughly like:

```text
{
  'exists': True,
  'loaded': True,
  'height': 12,
  'glyphs': 94,
  ...
}
```

Then set the desired role in `config.py` and send/wake a normal text or Markdown scene. No mailbox/Worker changes are required for v0.4 typography.
