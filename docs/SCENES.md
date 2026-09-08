# Athena scene format

Every scene is JSON. The mailbox adds `revision`, `device`, and `created_at`; clients only need to send the scene content.

AthenaOS v0.2 adds two optional display hints to every non-image scene:

```json
{
  "orientation": "auto",
  "density": "compact"
}
```

`orientation` can be `auto`, `portrait`, or `landscape`.

- `text` and `markdown` default to portrait.
- `notice`, `agenda`, and `tasks` default to landscape.
- `image` is always landscape in v0.2.

`density` can be `comfortable`, `compact`, or `max`.

- `comfortable` uses larger type and more whitespace.
- `compact` is the normal AthenaOS v0.2 setting.
- `max` uses the smallest margins and tightest spacing while retaining scale-2 body text.

Long text, Markdown, agendas, and task lists paginate locally. Athena stores the current page in its cached scene; this local state is not written back to the mailbox. On battery, button **A** wakes Athena and moves to the previous page; button **C** wakes Athena and moves to the next page. Page turns are handled from the cached scene before any Wi-Fi/mailbox work.

## Text

Text defaults to portrait so longer notes read like a book/manual page.

```json
{
  "type": "text",
  "title": "Remember",
  "text": "Measure the shelf before ordering brackets.",
  "density": "compact"
}
```

Force a landscape text page with:

```json
{
  "type": "text",
  "title": "Wide Notes",
  "orientation": "landscape",
  "density": "max",
  "text": "..."
}
```

## Notice

Notices remain landscape and deliberately use much larger text.

```json
{
  "type": "notice",
  "title": "Oi",
  "text": "DINNER AT 7"
}
```

## Markdown

Markdown defaults to portrait and is automatically paginated. v0.2 supports an intentionally small e-ink-friendly subset:

- `#`, `##`, `###` headings
- `-` / `*` bullet lines
- `>` quote lines
- fenced code blocks
- horizontal rules (`---`, `***`, `___`)
- plain paragraphs
- simple stripping of inline `**`, `__`, and backtick markers

```json
{
  "type": "markdown",
  "title": "Project Notes",
  "density": "compact",
  "text": "# Athena\n- Mailbox works\n- Dense renderer works\n\n## Next\nAdd Tasker"
}
```

## Agenda

Agenda stays landscape and uses dense time/title rows. Longer agendas paginate automatically.

```json
{
  "type": "agenda",
  "title": "Monday",
  "events": [
    {"time": "09:30", "title": "Meeting"},
    {"time": "13:00", "title": "Lunch"}
  ]
}
```

## Tasks

Compact/max task scenes use two columns in landscape. Comfortable mode or portrait overrides use one column. Longer lists paginate automatically.

```json
{
  "type": "tasks",
  "title": "Today",
  "density": "compact",
  "items": [
    {"title": "Order parts", "done": false},
    {"title": "Charge Mercury", "done": true}
  ]
}
```

## Image

Image scenes point at an asset in the mailbox. Normally clients should use `POST /image` rather than constructing these themselves.

```json
{
  "type": "image",
  "asset": "/assets/athena/example.jpg"
}
```

For v0.2, send a **baseline/non-progressive JPEG prepared at 800x480**. Server-side image normalisation/cropping is intentionally left for a later version.

## Desktop sender examples

The v0.2 desktop helper can set orientation and density directly:

```bash
python tools/send.py text "A long note..." --title "Reading" --density max
python tools/send.py text "Wide note" --title "Test" --orientation landscape
python tools/send.py markdown README.md --title "AthenaOS" --density compact
```

If no display options are supplied, Athena's scene-type defaults are used.
