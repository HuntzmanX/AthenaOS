import gc

import config
from picographics import PicoGraphics


BLACK = 0
WHITE = 1
ACCENT = 4

DENSITY_PRESETS = {
    "comfortable": {
        "margin": 24,
        "body_scale": 3,
        "line_gap": 5,
        "header_scale": 3,
        "header_gap": 16,
        "section_gap": 12,
    },
    "compact": {
        "margin": 16,
        "body_scale": 2,
        "line_gap": 3,
        "header_scale": 2,
        "header_gap": 10,
        "section_gap": 8,
    },
    "max": {
        "margin": 10,
        "body_scale": 2,
        "line_gap": 1,
        "header_scale": 2,
        "header_gap": 6,
        "section_gap": 4,
    },
}


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


class Canvas:
    """Logical landscape or software-mapped portrait drawing surface."""

    def __init__(self, graphics, orientation):
        self.graphics = graphics
        self.orientation = orientation
        self.physical_width, self.physical_height = graphics.get_bounds()
        self.portrait = orientation == "portrait"

        if self.portrait:
            self.width = self.physical_height
            self.height = self.physical_width
        else:
            self.width = self.physical_width
            self.height = self.physical_height

    def set_pen(self, pen):
        self.graphics.set_pen(pen)

    def clear(self):
        self.graphics.clear()

    def measure_text(self, text, scale):
        return self.graphics.measure_text(str(text), scale=scale)

    def _point(self, x, y):
        x = int(x)
        y = int(y)
        if not self.portrait:
            return x, y

        if config.PORTRAIT_ROTATION == 270:
            return y, self.physical_height - 1 - x

        # Clockwise portrait: logical +X points down the physical screen and
        # logical +Y points left across it.
        return self.physical_width - 1 - y, x

    def text(self, text, x, y, scale=1):
        px, py = self._point(x, y)
        if not self.portrait:
            self.graphics.text(str(text), px, py, 4096, scale)
            return

        angle = 270 if config.PORTRAIT_ROTATION == 270 else 90
        # Athena wraps lines itself, so each call renders one logical line.
        self.graphics.text(str(text), px, py, 4096, scale, angle)

    def line(self, x1, y1, x2, y2, thickness=1):
        ax, ay = self._point(x1, y1)
        bx, by = self._point(x2, y2)
        self.graphics.line(ax, ay, bx, by, thickness)

    def rectangle(self, x, y, w, h):
        if not self.portrait:
            self.graphics.rectangle(int(x), int(y), int(w), int(h))
            return

        p1 = self._point(x, y)
        p2 = self._point(x + w - 1, y + h - 1)
        left = min(p1[0], p2[0])
        top = min(p1[1], p2[1])
        width = abs(p2[0] - p1[0]) + 1
        height = abs(p2[1] - p1[1]) + 1
        self.graphics.rectangle(left, top, width, height)


def _orientation(scene, scene_type):
    requested = str(scene.get("orientation", "auto")).lower()
    if requested in ("portrait", "landscape"):
        return requested
    if scene_type in ("text", "markdown"):
        return "portrait"
    return "landscape"


def _density(scene, document=False):
    default = config.DEFAULT_DOCUMENT_DENSITY if document else config.DEFAULT_DASHBOARD_DENSITY
    name = str(scene.get("density", default)).lower()
    if name not in DENSITY_PRESETS:
        name = default
    return name, DENSITY_PRESETS[name]


def _clear(canvas):
    canvas.set_pen(WHITE)
    canvas.clear()
    canvas.set_pen(BLACK)


def _wrap(canvas, text, width, scale):
    lines = []
    for paragraph in str(text).replace("\r", "").split("\n"):
        if paragraph == "":
            lines.append("")
            continue

        words = paragraph.split(" ")
        line = ""
        for word in words:
            candidate = word if not line else line + " " + word
            if canvas.measure_text(candidate, scale) <= width:
                line = candidate
                continue

            if line:
                lines.append(line)
                line = word
                continue

            # Split a token that is wider than the whole line (URLs, hashes, etc.).
            chunk = ""
            for char in word:
                candidate = chunk + char
                if chunk and canvas.measure_text(candidate, scale) > width:
                    lines.append(chunk)
                    chunk = char
                else:
                    chunk = candidate
            line = chunk

        if line:
            lines.append(line)
    return lines


def _fit_one_line(canvas, text, width, scale):
    text = str(text)
    if canvas.measure_text(text, scale) <= width:
        return text
    suffix = "..."
    while text and canvas.measure_text(text + suffix, scale) > width:
        text = text[:-1]
    return text + suffix


def _page(scene, count):
    count = max(1, int(count))
    try:
        page = int(scene.get(config.LOCAL_PAGE_KEY, scene.get("page", 0)))
    except Exception:
        page = 0
    if page < 0:
        page = 0
    if page >= count:
        page = count - 1
    return page


def _meta(page, count, orientation, density):
    return {
        "page": int(page),
        "page_count": int(max(1, count)),
        "orientation": orientation,
        "density": density,
    }


def _content_bounds(canvas, metrics, kicker=False):
    margin = metrics["margin"]
    y = margin
    if kicker:
        y += 12
    y += (8 * metrics["header_scale"]) + metrics["header_gap"]
    bottom = canvas.height - margin - 22
    return y, bottom


def _draw_chrome(canvas, title, page, count, density, kicker=None):
    metrics = DENSITY_PRESETS[density]
    margin = metrics["margin"]
    y = margin

    if kicker:
        canvas.set_pen(ACCENT)
        canvas.text(str(kicker).upper(), margin, y, 1)
        y += 12

    scale = metrics["header_scale"]
    title_width = canvas.width - (margin * 2) - 74
    title = _fit_one_line(canvas, title or "Athena", title_width, scale)
    canvas.set_pen(BLACK)
    canvas.text(title, margin, y, scale)

    if count > 1:
        marker = str(page + 1) + "/" + str(count)
        marker_width = canvas.measure_text(marker, 1)
        canvas.set_pen(ACCENT)
        canvas.text(marker, canvas.width - margin - marker_width, y + 3, 1)

    rule_y = y + (8 * scale) + 4
    canvas.set_pen(ACCENT)
    canvas.rectangle(margin, rule_y, canvas.width - (margin * 2), 2)
    canvas.set_pen(BLACK)
    return y + (8 * scale) + metrics["header_gap"]


def _draw_footer(canvas, page, count, density):
    metrics = DENSITY_PRESETS[density]
    margin = metrics["margin"]
    y = canvas.height - margin - 9
    canvas.set_pen(ACCENT)
    canvas.line(margin, y - 5, canvas.width - margin, y - 5, 1)
    canvas.set_pen(BLACK)
    canvas.text("ATHENA", margin, y, 1)

    if count > 1:
        marker = "PAGE " + str(page + 1) + " / " + str(count)
        marker_width = canvas.measure_text(marker, 1)
        canvas.text(marker, canvas.width - margin - marker_width, y, 1)


def _paginate_lines(lines, available_height, scale, line_gap):
    line_height = (8 * scale) + line_gap
    per_page = max(1, available_height // line_height)
    pages = []
    for index in range(0, len(lines), per_page):
        pages.append(lines[index:index + per_page])
    if not pages:
        pages = [[]]
    return pages, line_height


def render_text(graphics, scene):
    orientation = _orientation(scene, "text")
    density, metrics = _density(scene, document=True)
    canvas = Canvas(graphics, orientation)
    _clear(canvas)

    margin = metrics["margin"]
    top, bottom = _content_bounds(canvas, metrics, bool(scene.get("kicker")))
    scale = int(scene.get("scale", metrics["body_scale"]))
    lines = _wrap(canvas, scene.get("text", ""), canvas.width - (margin * 2), scale)
    pages, line_height = _paginate_lines(lines, bottom - top, scale, metrics["line_gap"])
    page = _page(scene, len(pages))

    y = _draw_chrome(canvas, scene.get("title", "Athena"), page, len(pages), density, scene.get("kicker"))
    for line in pages[page]:
        if line:
            canvas.text(line, margin, y, scale)
        y += line_height

    _draw_footer(canvas, page, len(pages), density)
    return _meta(page, len(pages), orientation, density)


def render_notice(graphics, scene):
    orientation = _orientation(scene, "notice")
    density, metrics = _density(scene, document=False)
    canvas = Canvas(graphics, orientation)
    _clear(canvas)

    margin = metrics["margin"]
    title = str(scene.get("title", "NOTICE")).upper()
    text = str(scene.get("text", ""))
    canvas.set_pen(ACCENT)
    canvas.text(title, margin, margin, 3 if density == "comfortable" else 2)
    canvas.set_pen(BLACK)

    scale = int(scene.get("scale", 6 if len(text) < 90 else 4))
    lines = _wrap(canvas, text, canvas.width - (margin * 2), scale)
    line_height = (8 * scale) + 7
    block_height = len(lines) * line_height
    y = max(84, (canvas.height - block_height) // 2)
    for line in lines:
        x = max(margin, (canvas.width - canvas.measure_text(line, scale)) // 2)
        canvas.text(line, x, y, scale)
        y += line_height

    return _meta(0, 1, orientation, density)


def _strip_inline(text):
    text = str(text)
    for marker in ("**", "__", "`"):
        text = text.replace(marker, "")
    return text


def _markdown_rows(canvas, text, width, density, metrics):
    rows = []
    in_code = False

    for raw in str(text).replace("\r", "").split("\n"):
        stripped = raw.strip()

        if stripped.startswith("```"):
            in_code = not in_code
            rows.append(("", 1, metrics["section_gap"], 0))
            continue
        if stripped in ("---", "***", "___"):
            rows.append(("__RULE__", 1, metrics["section_gap"], 2))
            continue
        if raw == "":
            rows.append(("", 1, metrics["section_gap"], 0))
            continue

        if in_code:
            scale = 1 if density in ("compact", "max") else 2
            line = "  " + raw.replace("\t", "    ")
            gap = 1
            style = 0
        elif raw.startswith("# "):
            scale = 3 if density != "max" else 2
            line = _strip_inline(raw[2:])
            gap = metrics["section_gap"]
            style = 0
        elif raw.startswith("## "):
            scale = 2
            line = _strip_inline(raw[3:])
            gap = max(3, metrics["section_gap"] - 2)
            style = 1
        elif raw.startswith("### "):
            scale = 2
            line = _strip_inline(raw[4:]).upper()
            gap = max(2, metrics["section_gap"] - 3)
            style = 1
        elif raw.startswith("- ") or raw.startswith("* "):
            scale = metrics["body_scale"]
            line = "- " + _strip_inline(raw[2:])
            gap = metrics["line_gap"]
            style = 0
        elif raw.startswith("> "):
            scale = metrics["body_scale"]
            line = "> " + _strip_inline(raw[2:])
            gap = metrics["line_gap"]
            style = 1
        else:
            scale = metrics["body_scale"]
            line = _strip_inline(raw)
            gap = metrics["line_gap"]
            style = 0

        wrapped = _wrap(canvas, line, width, scale)
        if not wrapped:
            wrapped = [""]
        for index, part in enumerate(wrapped):
            row_gap = gap if index == len(wrapped) - 1 else metrics["line_gap"]
            rows.append((part, scale, row_gap, style))

    return rows


def _row_height(row):
    text, scale, gap, style = row
    if text == "__RULE__":
        return 8 + gap
    if text == "":
        return max(6, gap)
    return (8 * scale) + gap


def _paginate_rows(rows, available_height):
    pages = []
    current = []
    used = 0
    for row in rows:
        height = _row_height(row)
        if current and used + height > available_height:
            pages.append(current)
            current = []
            used = 0
        current.append(row)
        used += height
    if current or not pages:
        pages.append(current)
    return pages


def render_markdown(graphics, scene):
    orientation = _orientation(scene, "markdown")
    density, metrics = _density(scene, document=True)
    canvas = Canvas(graphics, orientation)
    _clear(canvas)

    margin = metrics["margin"]
    top, bottom = _content_bounds(canvas, metrics, True)
    width = canvas.width - (margin * 2)
    rows = _markdown_rows(canvas, scene.get("text", ""), width, density, metrics)
    pages = _paginate_rows(rows, bottom - top)
    page = _page(scene, len(pages))

    y = _draw_chrome(canvas, scene.get("title", "Document"), page, len(pages), density, "MARKDOWN")
    for text, scale, gap, style in pages[page]:
        if text == "__RULE__":
            canvas.set_pen(ACCENT)
            canvas.rectangle(margin, y + 3, width, 2)
            canvas.set_pen(BLACK)
            y += 8 + gap
            continue
        if text == "":
            y += max(6, gap)
            continue

        canvas.set_pen(ACCENT if style == 1 else BLACK)
        canvas.text(text, margin, y, scale)
        y += (8 * scale) + gap

    _draw_footer(canvas, page, len(pages), density)
    return _meta(page, len(pages), orientation, density)


def render_agenda(graphics, scene):
    orientation = _orientation(scene, "agenda")
    density, metrics = _density(scene, document=False)
    canvas = Canvas(graphics, orientation)
    _clear(canvas)

    events = scene.get("events", [])
    margin = metrics["margin"]
    top, bottom = _content_bounds(canvas, metrics, True)
    row_height = 27 if density != "comfortable" else 34
    per_page = max(1, (bottom - top) // row_height)
    page_count = max(1, (len(events) + per_page - 1) // per_page)
    page = _page(scene, page_count)

    y = _draw_chrome(canvas, scene.get("title", "Today"), page, page_count, density, "AGENDA")
    chunk = events[page * per_page:(page + 1) * per_page]
    if not chunk:
        canvas.text("Nothing scheduled.", margin, y + 10, 3)
    else:
        time_width = 100 if density == "comfortable" else 84
        title_width = canvas.width - (margin * 2) - time_width
        for event in chunk:
            if isinstance(event, dict):
                when = str(event.get("time", ""))
                title = str(event.get("title", "Untitled"))
            else:
                when = ""
                title = str(event)
            canvas.set_pen(ACCENT)
            canvas.text(_fit_one_line(canvas, when, time_width - 8, 2), margin, y, 2)
            canvas.set_pen(BLACK)
            canvas.text(_fit_one_line(canvas, title, title_width, 2), margin + time_width, y, 2)
            y += row_height
            canvas.set_pen(ACCENT)
            canvas.line(margin + time_width, y - 5, canvas.width - margin, y - 5, 1)
            canvas.set_pen(BLACK)

    _draw_footer(canvas, page, page_count, density)
    return _meta(page, page_count, orientation, density)


def render_tasks(graphics, scene):
    orientation = _orientation(scene, "tasks")
    density, metrics = _density(scene, document=False)
    canvas = Canvas(graphics, orientation)
    _clear(canvas)

    items = scene.get("items", [])
    margin = metrics["margin"]
    top, bottom = _content_bounds(canvas, metrics, True)
    row_height = 28 if density != "comfortable" else 34
    columns = 2 if orientation == "landscape" and density in ("compact", "max") else 1
    gap = 18
    col_width = (canvas.width - (margin * 2) - ((columns - 1) * gap)) // columns
    rows_per_col = max(1, (bottom - top) // row_height)
    per_page = rows_per_col * columns
    page_count = max(1, (len(items) + per_page - 1) // per_page)
    page = _page(scene, page_count)

    y = _draw_chrome(canvas, scene.get("title", "Tasks"), page, page_count, density, "TO DO")
    chunk = items[page * per_page:(page + 1) * per_page]
    if not chunk:
        canvas.text("Nothing to do.", margin, y + 10, 3)
    else:
        for index, item in enumerate(chunk):
            col = index // rows_per_col
            row = index % rows_per_col
            x = margin + col * (col_width + gap)
            item_y = y + row * row_height

            if isinstance(item, dict):
                done = bool(item.get("done", False))
                label = str(item.get("title", item.get("text", "Untitled")))
            else:
                done = False
                label = str(item)

            marker = "[x]" if done else "[ ]"
            canvas.set_pen(ACCENT if done else BLACK)
            canvas.text(marker, x, item_y, 2)
            canvas.set_pen(BLACK)
            label_x = x + 42
            label_width = col_width - 42
            canvas.text(_fit_one_line(canvas, label, label_width, 2), label_x, item_y, 2)

    _draw_footer(canvas, page, page_count, density)
    return _meta(page, page_count, orientation, density)


def render_image(graphics, asset_path):
    if not asset_path:
        raise ValueError("Image scene has no local asset path")

    import jpegdec

    gc.collect()
    jpeg = jpegdec.JPEG(graphics)
    graphics.set_pen(WHITE)
    graphics.clear()
    jpeg.open_file(asset_path)
    jpeg.decode()
    gc.collect()


def render_scene(graphics, scene, asset_path=None):
    scene_type = str(scene.get("type", "text")).lower()
    print("Rendering scene:", scene_type, _orientation(scene, scene_type))

    if scene_type == "image":
        render_image(graphics, asset_path)
        meta = _meta(0, 1, "landscape", "comfortable")
    elif scene_type == "notice":
        meta = render_notice(graphics, scene)
    elif scene_type == "markdown":
        meta = render_markdown(graphics, scene)
    elif scene_type == "agenda":
        meta = render_agenda(graphics, scene)
    elif scene_type == "tasks":
        meta = render_tasks(graphics, scene)
    elif scene_type == "text":
        meta = render_text(graphics, scene)
    else:
        raise ValueError("Unsupported scene type: " + scene_type)

    graphics.update()
    print(
        "Display updated - page",
        meta["page"] + 1,
        "of",
        meta["page_count"],
        "-",
        meta["orientation"],
        meta["density"],
    )
    gc.collect()
    return meta
