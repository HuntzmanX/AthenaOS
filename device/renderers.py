import gc

import config
from picographics import PicoGraphics


BLACK = 0
WHITE = 1
ACCENT = 4
MARGIN = 42


def create_graphics():
    if config.DISPLAY_KIND == "legacy7":
        from picographics import DISPLAY_INKY_FRAME_7 as DISPLAY
    elif config.DISPLAY_KIND == "spectra7":
        try:
            from picographics import DISPLAY_INKY_FRAME_SPECTRA_7 as DISPLAY
        except ImportError:
            raise RuntimeError(
                "Spectra display support is missing. Flash a current Pimoroni Inky Frame firmware, "
                "or set DISPLAY_KIND='legacy7' for an older panel."
            )
    else:
        raise ValueError("Unknown DISPLAY_KIND: " + str(config.DISPLAY_KIND))

    graphics = PicoGraphics(DISPLAY)
    graphics.set_font("bitmap8")
    return graphics


def _clear(graphics):
    graphics.set_pen(WHITE)
    graphics.clear()
    graphics.set_pen(BLACK)


def _measure(graphics, text, scale):
    return graphics.measure_text(text, scale=scale)


def _wrap(graphics, text, width, scale):
    lines = []
    text = str(text).replace("\r", "")

    for paragraph in text.split("\n"):
        if paragraph == "":
            lines.append("")
            continue

        words = paragraph.split(" ")
        line = ""

        for word in words:
            candidate = word if not line else line + " " + word
            if _measure(graphics, candidate, scale) <= width:
                line = candidate
                continue

            if line:
                lines.append(line)
                line = word
            else:
                # Very long tokens (URLs etc.) get split instead of falling off-screen.
                chunk = ""
                for char in word:
                    candidate = chunk + char
                    if chunk and _measure(graphics, candidate, scale) > width:
                        lines.append(chunk)
                        chunk = char
                    else:
                        chunk = candidate
                line = chunk

        if line:
            lines.append(line)

    return lines


def _draw_header(graphics, title, kicker=None):
    width, _ = graphics.get_bounds()

    if kicker:
        graphics.set_pen(ACCENT)
        graphics.text(str(kicker).upper(), MARGIN, 28, width - (MARGIN * 2), 2)

    graphics.set_pen(BLACK)
    graphics.text(str(title), MARGIN, 52 if kicker else 36, width - (MARGIN * 2), 4)

    line_y = 102 if kicker else 86
    graphics.set_pen(ACCENT)
    graphics.rectangle(MARGIN, line_y, width - (MARGIN * 2), 4)
    graphics.set_pen(BLACK)
    return line_y + 26


def _draw_footer(graphics):
    width, height = graphics.get_bounds()
    graphics.set_pen(BLACK)
    graphics.text("ATHENA", width - 112, height - 28, 90, 1)


def _fit_body_scale(text):
    length = len(str(text))
    if length <= 180:
        return 5
    if length <= 420:
        return 4
    if length <= 850:
        return 3
    return 2


def _draw_wrapped(graphics, text, x, y, width, max_y, scale, line_gap=5):
    lines = _wrap(graphics, text, width, scale)
    line_height = (8 * scale) + line_gap

    for index, line in enumerate(lines):
        if y + line_height > max_y:
            graphics.text("...", x, y, width, scale)
            return index
        graphics.text(line, x, y, width, scale)
        y += line_height

    return len(lines)


def render_text(graphics, scene):
    width, height = graphics.get_bounds()
    _clear(graphics)
    title = scene.get("title", "Athena")
    y = _draw_header(graphics, title, scene.get("kicker"))
    body = scene.get("text", "")
    scale = int(scene.get("scale", _fit_body_scale(body)))
    _draw_wrapped(
        graphics,
        body,
        MARGIN,
        y,
        width - (MARGIN * 2),
        height - 52,
        scale,
    )
    _draw_footer(graphics)


def render_notice(graphics, scene):
    width, height = graphics.get_bounds()
    _clear(graphics)

    title = str(scene.get("title", "NOTICE")).upper()
    text = str(scene.get("text", ""))

    graphics.set_pen(ACCENT)
    graphics.text(title, MARGIN, 34, width - (MARGIN * 2), 3)
    graphics.set_pen(BLACK)

    scale = int(scene.get("scale", 6 if len(text) < 90 else 4))
    lines = _wrap(graphics, text, width - (MARGIN * 2), scale)
    line_height = (8 * scale) + 8
    block_height = len(lines) * line_height
    y = max(115, (height - block_height) // 2)

    for line in lines:
        line_width = _measure(graphics, line, scale)
        x = max(MARGIN, (width - line_width) // 2)
        graphics.text(line, x, y, width - (MARGIN * 2), scale)
        y += line_height

    _draw_footer(graphics)


def render_markdown(graphics, scene):
    width, height = graphics.get_bounds()
    _clear(graphics)
    y = _draw_header(graphics, scene.get("title", "Document"), "MARKDOWN")
    max_y = height - 48
    text_width = width - (MARGIN * 2)

    for raw in str(scene.get("text", "")).replace("\r", "").split("\n"):
        if y >= max_y:
            graphics.text("...", MARGIN, max_y - 20, text_width, 2)
            break

        if raw.startswith("# "):
            scale = 4
            line = raw[2:]
            gap = 14
        elif raw.startswith("## "):
            scale = 3
            line = raw[3:]
            gap = 10
        elif raw.startswith("### "):
            scale = 2
            line = raw[4:].upper()
            gap = 8
        elif raw.startswith("- ") or raw.startswith("* "):
            scale = 2
            line = "- " + raw[2:]
            gap = 5
        else:
            scale = 2
            line = raw
            gap = 5

        if line == "":
            y += 14
            continue

        wrapped = _wrap(graphics, line, text_width, scale)
        line_height = (8 * scale) + 5
        for part in wrapped:
            if y + line_height >= max_y:
                graphics.text("...", MARGIN, y, text_width, 2)
                _draw_footer(graphics)
                return
            graphics.text(part, MARGIN, y, text_width, scale)
            y += line_height
        y += gap

    _draw_footer(graphics)


def render_agenda(graphics, scene):
    width, height = graphics.get_bounds()
    _clear(graphics)
    y = _draw_header(graphics, scene.get("title", "Today"), "AGENDA")
    events = scene.get("events", [])

    if not events:
        graphics.text("Nothing scheduled.", MARGIN, y + 20, width - (MARGIN * 2), 4)
        _draw_footer(graphics)
        return

    for event in events:
        if y > height - 78:
            graphics.text("...", MARGIN, y, 80, 3)
            break

        if isinstance(event, dict):
            when = str(event.get("time", ""))
            title = str(event.get("title", "Untitled"))
        else:
            when = ""
            title = str(event)

        graphics.set_pen(ACCENT)
        graphics.text(when, MARGIN, y, 150, 3)
        graphics.set_pen(BLACK)
        graphics.text(title, MARGIN + 155, y, width - MARGIN - (MARGIN + 155), 3)
        y += 52
        graphics.set_pen(BLACK)
        graphics.rectangle(MARGIN + 155, y - 12, width - (MARGIN * 2) - 155, 1)

    _draw_footer(graphics)


def render_tasks(graphics, scene):
    width, height = graphics.get_bounds()
    _clear(graphics)
    y = _draw_header(graphics, scene.get("title", "Tasks"), "TO DO")
    items = scene.get("items", [])

    if not items:
        graphics.text("Nothing to do.", MARGIN, y + 20, width - (MARGIN * 2), 4)
        _draw_footer(graphics)
        return

    for item in items:
        if y > height - 72:
            graphics.text("...", MARGIN, y, 80, 3)
            break

        if isinstance(item, dict):
            done = bool(item.get("done", False))
            label = str(item.get("title", item.get("text", "Untitled")))
        else:
            done = False
            label = str(item)

        marker = "[x]" if done else "[ ]"
        graphics.set_pen(ACCENT if done else BLACK)
        graphics.text(marker, MARGIN, y, 76, 3)
        graphics.set_pen(BLACK)
        graphics.text(label, MARGIN + 88, y, width - (MARGIN * 2) - 88, 3)
        y += 48

    _draw_footer(graphics)


def render_image(graphics, asset_path):
    if not asset_path:
        raise ValueError("Image scene has no local asset path")

    import jpegdec

    gc.collect()
    jpeg = jpegdec.JPEG(graphics)
    _clear(graphics)
    jpeg.open_file(asset_path)
    jpeg.decode()
    gc.collect()


def render_scene(graphics, scene, asset_path=None):
    scene_type = str(scene.get("type", "text")).lower()
    print("Rendering scene:", scene_type)

    if scene_type == "image":
        render_image(graphics, asset_path)
    elif scene_type == "notice":
        render_notice(graphics, scene)
    elif scene_type == "markdown":
        render_markdown(graphics, scene)
    elif scene_type == "agenda":
        render_agenda(graphics, scene)
    elif scene_type == "tasks":
        render_tasks(graphics, scene)
    elif scene_type == "text":
        render_text(graphics, scene)
    else:
        raise ValueError("Unsupported scene type: " + scene_type)

    graphics.update()
    print("Display updated")
    gc.collect()
