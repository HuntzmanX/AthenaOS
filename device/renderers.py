import gc

import config
import fonts as fontlib
from picographics import PicoGraphics


BLACK = 0
WHITE = 1
ACCENT = 4

# Scales here are used only by the built-in bitmap8 fallback. PPF fonts have
# intrinsic pixel dimensions and normally render at 1x.
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
    # PPF roles fall back to this known-good built-in font individually.
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

    def _font(self, role):
        return fontlib.role(role)

    def measure_text(self, text, role="body", fallback_scale=1, scale=1):
        font = self._font(role)
        if font is not None:
            return font.measure_text(str(text), scale=scale)
        return self.graphics.measure_text(
            str(text),
            scale=max(1, int(fallback_scale)) * max(1, int(scale)),
        )

    def text_height(self, role="body", fallback_scale=1, scale=1):
        font = self._font(role)
        if font is not None:
            return font.height * max(1, int(scale))
        return 8 * max(1, int(fallback_scale)) * max(1, int(scale))

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

    def _builtin_text(self, text, x, y, scale):
        px, py = self._point(x, y)
        if not self.portrait:
            self.graphics.text(str(text), px, py, 4096, scale)
            return

        angle = 270 if config.PORTRAIT_ROTATION == 270 else 90
        self.graphics.text(str(text), px, py, 4096, scale, angle)

    def text(self, text, x, y, role="body", fallback_scale=1, scale=1):
        font = self._font(role)
        if font is not None:
            return font.draw_text(self, str(text), x, y, scale=scale)

        builtin_scale = max(1, int(fallback_scale)) * max(1, int(scale))
        self._builtin_text(text, x, y, builtin_scale)
        return int(x) + self.graphics.measure_text(str(text), scale=builtin_scale)

    def line(self, x1, y1, x2, y2, thickness=1):
        ax, ay = self._point(x1, y1)
        bx, by = self._point(x2, y2)
        self.graphics.line(ax, ay, bx, by, thickness)

    def rectangle(self, x, y, w, h):
        if w <= 0 or h <= 0:
            return

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


def _wrap(canvas, text, width, role="body", fallback_scale=1, scale=1):
    lines = []
    for paragraph in str(text).replace("\r", "").split("\n"):
        if paragraph == "":
            lines.append("")
            continue

        words = paragraph.split(" ")
        line = ""
        for word in words:
            candidate = word if not line else line + " " + word
            if canvas.measure_text(candidate, role, fallback_scale, scale) <= width:
                line = candidate
                continue

            if line:
                lines.append(line)
                line = word
                continue

            # Split tokens wider than a whole line: URLs, hashes, paths, etc.
            chunk = ""
            for char in word:
                candidate = chunk + char
                if chunk and canvas.measure_text(
                    candidate, role, fallback_scale, scale
                ) > width:
                    lines.append(chunk)
                    chunk = char
                else:
                    chunk = candidate
            line = chunk

        if line:
            lines.append(line)
    return lines


def _fit_one_line(canvas, text, width, role="body", fallback_scale=1, scale=1):
    text = str(text)
    if canvas.measure_text(text, role, fallback_scale, scale) <= width:
        return text

    suffix = "..."
    while text and canvas.measure_text(
        text + suffix, role, fallback_scale, scale
    ) > width:
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
        y += canvas.text_height("small", 1) + 4

    y += canvas.text_height("title", metrics["header_scale"]) + metrics["header_gap"]
    footer_height = canvas.text_height("small", 1)
    bottom = canvas.height - margin - footer_height - 12
    return y, bottom


def _draw_chrome(canvas, title, page, count, density, kicker=None):
    metrics = DENSITY_PRESETS[density]
    margin = metrics["margin"]
    y = margin

    if kicker:
        canvas.set_pen(ACCENT)
        canvas.text(str(kicker).upper(), margin, y, "small", 1)
        y += canvas.text_height("small", 1) + 4

    title_fallback = metrics["header_scale"]
    title_height = canvas.text_height("title", title_fallback)
    title_width = canvas.width - (margin * 2) - 74
    title = _fit_one_line(
        canvas,
        title or "Athena",
        title_width,
        "title",
        title_fallback,
    )

    canvas.set_pen(BLACK)
    canvas.text(title, margin, y, "title", title_fallback)

    if count > 1:
        marker = str(page + 1) + "/" + str(count)
        marker_width = canvas.measure_text(marker, "small", 1)
        canvas.set_pen(ACCENT)
        canvas.text(
            marker,
            canvas.width - margin - marker_width,
            y + max(0, (title_height - canvas.text_height("small", 1)) // 2),
            "small",
            1,
        )

    rule_y = y + title_height + 4
    canvas.set_pen(ACCENT)
    canvas.rectangle(margin, rule_y, canvas.width - (margin * 2), 2)
    canvas.set_pen(BLACK)
    return y + title_height + metrics["header_gap"]


def _draw_footer(canvas, page, count, density):
    metrics = DENSITY_PRESETS[density]
    margin = metrics["margin"]
    footer_height = canvas.text_height("small", 1)
    y = canvas.height - margin - footer_height

    canvas.set_pen(ACCENT)
    canvas.line(margin, y - 5, canvas.width - margin, y - 5, 1)
    canvas.set_pen(BLACK)
    canvas.text("ATHENA", margin, y, "small", 1)

    if count > 1:
        marker = "PAGE " + str(page + 1) + " / " + str(count)
        marker_width = canvas.measure_text(marker, "small", 1)
        canvas.text(
            marker,
            canvas.width - margin - marker_width,
            y,
            "small",
            1,
        )


def _paginate_lines(canvas, lines, available_height, role, fallback_scale, line_gap, scale=1):
    line_height = canvas.text_height(role, fallback_scale, scale) + line_gap
    per_page = max(1, available_height // max(1, line_height))
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
    fallback_scale = int(scene.get("scale", metrics["body_scale"]))
    lines = _wrap(
        canvas,
        scene.get("text", ""),
        canvas.width - (margin * 2),
        "body",
        fallback_scale,
    )
    pages, line_height = _paginate_lines(
        canvas,
        lines,
        bottom - top,
        "body",
        fallback_scale,
        metrics["line_gap"],
    )
    page = _page(scene, len(pages))

    y = _draw_chrome(
        canvas,
        scene.get("title", "Athena"),
        page,
        len(pages),
        density,
        scene.get("kicker"),
    )
    for line in pages[page]:
        if line:
            canvas.text(line, margin, y, "body", fallback_scale)
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
    canvas.text(
        title,
        margin,
        margin,
        "heading",
        3 if density == "comfortable" else 2,
    )
    canvas.set_pen(BLACK)

    fallback_scale = int(scene.get("scale", 6 if len(text) < 90 else 4))
    ppf_scale = 2 if len(text) < 90 else 1
    lines = _wrap(
        canvas,
        text,
        canvas.width - (margin * 2),
        "title",
        fallback_scale,
        ppf_scale,
    )
    line_height = canvas.text_height("title", fallback_scale, ppf_scale) + 7
    block_height = len(lines) * line_height
    title_bottom = margin + canvas.text_height(
        "heading", 3 if density == "comfortable" else 2
    ) + 16
    y = max(title_bottom, (canvas.height - block_height) // 2)

    for line in lines:
        line_width = canvas.measure_text(
            line, "title", fallback_scale, ppf_scale
        )
        x = max(margin, (canvas.width - line_width) // 2)
        canvas.text(
            line,
            x,
            y,
            "title",
            fallback_scale,
            ppf_scale,
        )
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
            rows.append(("", "body", 1, 1, metrics["section_gap"], 0))
            continue

        if stripped in ("---", "***", "___"):
            rows.append(("__RULE__", "body", 1, 1, metrics["section_gap"], 2))
            continue

        if raw == "":
            rows.append(("", "body", 1, 1, metrics["section_gap"], 0))
            continue

        if in_code:
            role = "mono"
            fallback_scale = 1 if density in ("compact", "max") else 2
            line = "  " + raw.replace("\t", "    ")
            gap = 1
            style = 0
        elif raw.startswith("# "):
            role = "title"
            fallback_scale = 3 if density != "max" else 2
            line = _strip_inline(raw[2:])
            gap = metrics["section_gap"]
            style = 0
        elif raw.startswith("## "):
            role = "heading"
            fallback_scale = 2
            line = _strip_inline(raw[3:])
            gap = max(3, metrics["section_gap"] - 2)
            style = 1
        elif raw.startswith("### "):
            role = "heading"
            fallback_scale = 2
            line = _strip_inline(raw[4:]).upper()
            gap = max(2, metrics["section_gap"] - 3)
            style = 1
        elif raw.startswith("- ") or raw.startswith("* "):
            role = "body"
            fallback_scale = metrics["body_scale"]
            line = "- " + _strip_inline(raw[2:])
            gap = metrics["line_gap"]
            style = 0
        elif raw.startswith("> "):
            role = "body"
            fallback_scale = metrics["body_scale"]
            line = "> " + _strip_inline(raw[2:])
            gap = metrics["line_gap"]
            style = 1
        else:
            role = "body"
            fallback_scale = metrics["body_scale"]
            line = _strip_inline(raw)
            gap = metrics["line_gap"]
            style = 0

        wrapped = _wrap(
            canvas,
            line,
            width,
            role,
            fallback_scale,
        )
        if not wrapped:
            wrapped = [""]

        for index, part in enumerate(wrapped):
            row_gap = gap if index == len(wrapped) - 1 else metrics["line_gap"]
            rows.append((part, role, fallback_scale, 1, row_gap, style))

    return rows


def _row_height(canvas, row):
    text, role, fallback_scale, scale, gap, _style = row
    if text == "__RULE__":
        return 8 + gap
    if text == "":
        return max(6, gap)
    return canvas.text_height(role, fallback_scale, scale) + gap


def _paginate_rows(canvas, rows, available_height):
    pages = []
    current = []
    used = 0

    for row in rows:
        height = _row_height(canvas, row)
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
    rows = _markdown_rows(
        canvas,
        scene.get("text", ""),
        width,
        density,
        metrics,
    )
    pages = _paginate_rows(canvas, rows, bottom - top)
    page = _page(scene, len(pages))

    y = _draw_chrome(
        canvas,
        scene.get("title", "Document"),
        page,
        len(pages),
        density,
        "MARKDOWN",
    )

    for text, role, fallback_scale, scale, gap, style in pages[page]:
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
        canvas.text(
            text,
            margin,
            y,
            role,
            fallback_scale,
            scale,
        )
        y += canvas.text_height(role, fallback_scale, scale) + gap

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

    time_fallback = 2
    title_fallback = 2
    row_height = max(
        canvas.text_height("small", time_fallback),
        canvas.text_height("body", title_fallback),
    ) + (10 if density == "comfortable" else 6)

    per_page = max(1, (bottom - top) // row_height)
    page_count = max(1, (len(events) + per_page - 1) // per_page)
    page = _page(scene, page_count)

    y = _draw_chrome(
        canvas,
        scene.get("title", "Today"),
        page,
        page_count,
        density,
        "AGENDA",
    )
    chunk = events[page * per_page:(page + 1) * per_page]

    if not chunk:
        canvas.text("Nothing scheduled.", margin, y + 10, "body", 3)
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
            canvas.text(
                _fit_one_line(
                    canvas,
                    when,
                    time_width - 8,
                    "small",
                    time_fallback,
                ),
                margin,
                y,
                "small",
                time_fallback,
            )

            canvas.set_pen(BLACK)
            canvas.text(
                _fit_one_line(
                    canvas,
                    title,
                    title_width,
                    "body",
                    title_fallback,
                ),
                margin + time_width,
                y,
                "body",
                title_fallback,
            )

            y += row_height
            canvas.set_pen(ACCENT)
            canvas.line(
                margin + time_width,
                y - 4,
                canvas.width - margin,
                y - 4,
                1,
            )
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

    marker_fallback = 2
    label_fallback = 2
    row_height = max(
        canvas.text_height("mono", marker_fallback),
        canvas.text_height("body", label_fallback),
    ) + (10 if density == "comfortable" else 6)

    columns = 2 if orientation == "landscape" and density in ("compact", "max") else 1
    gap = 18
    col_width = (
        canvas.width - (margin * 2) - ((columns - 1) * gap)
    ) // columns
    rows_per_col = max(1, (bottom - top) // row_height)
    per_page = rows_per_col * columns
    page_count = max(1, (len(items) + per_page - 1) // per_page)
    page = _page(scene, page_count)

    y = _draw_chrome(
        canvas,
        scene.get("title", "Tasks"),
        page,
        page_count,
        density,
        "TO DO",
    )
    chunk = items[page * per_page:(page + 1) * per_page]

    if not chunk:
        canvas.text("Nothing to do.", margin, y + 10, "body", 3)
    else:
        marker_width = canvas.measure_text("[ ]", "mono", marker_fallback) + 8

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
            canvas.text(marker, x, item_y, "mono", marker_fallback)

            canvas.set_pen(BLACK)
            label_x = x + marker_width
            label_width = col_width - marker_width
            canvas.text(
                _fit_one_line(
                    canvas,
                    label,
                    label_width,
                    "body",
                    label_fallback,
                ),
                label_x,
                item_y,
                "body",
                label_fallback,
            )

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
