# AthenaOS v0.4

AthenaOS turns a Pimoroni Inky Frame 7.3" into a quiet e-ink information, document and art surface.

Athena is deliberately a **display endpoint**. Other devices put a scene into a small mailbox; Athena wakes, checks the scene revision, renders only when something changed, caches it, and goes back to sleep. If Wi-Fi or the mailbox is unavailable, the previous e-ink image simply stays on screen.

## Architecture

```text
Phone / Tasker / PC / Hermes / Mercury
                 |
                 | POST scene / share / image
                 v
        Cloudflare Worker mailbox
          | KV: current scene
          | R2: current image
                 |
                 | GET on wake
                 v
              Athena
        Inky Frame 7.3" / Pico 2 W
```

## v0.4: PPF typography

v0.4 adds filesystem-loaded PPF fonts using the same binary format produced by **PPF Studio** and used by Mercury.

Fonts are loaded by filename stem:

```python
import _fonts

font = _fonts.load("book-12")  # resolves book-12.ppf
```

Athena searches `/fonts`, `/athena/fonts`, `/sd/fonts`, and `/sd/athena/fonts`.

The renderer has five semantic roles configured in `device/config.py`:

```python
FONT_BODY = "body"
FONT_SMALL = "small"
FONT_HEADING = "heading"
FONT_TITLE = "title"
FONT_MONO = "mono"
```

Point those names at any PPF files you already have. PPF's stored per-glyph widths are used directly for **proportional layout and wrapping**; deliberately monospace PPFs remain monospace.

PPF bitmap data is streamed from disk while drawing rather than keeping every glyph bitmap in RAM. Portrait and landscape use the same logical renderer, and pagination now uses the actual custom font dimensions.

Missing or invalid role fonts fall back individually to the previous PicoGraphics `bitmap8` path, so font experiments cannot make Athena unable to display a scene.

See [`docs/FONTS.md`](docs/FONTS.md) for setup and diagnostics.
## v0.3: Send to Athena

v0.3 adds a universal endpoint for Android/Tasker shares:

```text
POST /share
```

It accepts:

- plain shared text -> `text`
- `.txt` -> `text`
- `.md` / `.markdown` -> `markdown`
- `.jpg` / `.jpeg` -> `image`
- JSON -> any normal Athena scene

Optional share hints are supported:

```text
type=text|notice|markdown
orientation=auto|portrait|landscape
density=comfortable|compact|max
title=...
```

See [`docs/TASKER.md`](docs/TASKER.md) for the Android share-target setup.

## Dense renderer from v0.2

The legacy seven-colour panel has a slow full refresh, so AthenaOS is designed around **making every refresh worth it**.

- `text` and `markdown` default to a software-mapped **480x800 portrait page**.
- `notice`, `agenda`, `tasks`, and `image` remain **800x480 landscape** by default.
- Renderer density can be `comfortable`, `compact`, or `max`.
- Long text, Markdown, agendas and task lists paginate locally.
- Compact/max landscape task lists use two columns.
- Current page is stored locally in Athena's cached scene, not in the mailbox.

Portrait mode uses PicoGraphics' per-text rotation rather than display-level rotation. The confirmed hardware orientation is:

```python
PORTRAIT_ROTATION = 90
```

See [`docs/SCENES.md`](docs/SCENES.md) for the scene format.

## Wake / page controls

Athena uses the Inky Frame's native sleep/wake model rather than a continuously running UI loop.

```text
A wake -> previous cached page
B wake -> next cached page
other button wake -> immediate mailbox check
RTC wake -> mailbox check
```

A/B page turns are handled locally before Wi-Fi, so reading does not need a mailbox round-trip.

`POLL_MINUTES` is currently:

```python
POLL_MINUTES = 60
```

After one unit of work Athena calls `inky_frame.sleep_for()` again. On battery this powers down the Pico until the RTC or a front button wakes it.

## Scene types

- `text`
- `notice`
- `markdown`
- `agenda`
- `tasks`
- `image`

## Storage

No SD card is required. Athena tries SD first and otherwise uses onboard flash:

```text
/sd/athena   # when SD is available
/athena      # onboard fallback
```

It keeps only the current scene JSON, one cached JPEG, and a temporary JPEG while replacing an image. Downloads are streamed in 1 KB chunks rather than loaded into RAM.

## Display hardware

This Athena is the older seven-colour 7.3" Inky Frame:

```python
DISPLAY_KIND = "legacy7"
```

The newer Spectra driver remains available with `spectra7`.

## Device setup

Use a current Pimoroni Inky Frame MicroPython firmware.

Copy the contents of `device/` to the root of the Inky Frame filesystem and create:

```text
secrets.example.py -> secrets.py
```

Configure:

- Wi-Fi / phone hotspot SSID and password
- Worker URL
- shared Athena token

`device/secrets.py` is ignored by Git.

## Cloudflare Worker

`worker/src/index.js` expects:

- `ATHENA_STATE` - KV namespace
- `ATHENA_ASSETS` - R2 bucket
- `ATHENA_TOKEN` - Worker secret

API:

```text
GET  /current
POST /scene
POST /image
POST /share
POST /clear
GET  /assets/<key>
```

Phone/desktop writers use `Authorization: Bearer <token>`. Athena's tiny GET client uses the same token as a query parameter.

Deploy from the Worker directory:

```powershell
cd worker
npx wrangler deploy
cd ..
```

## Desktop testing

Install Requests and set `ATHENA_URL` / `ATHENA_TOKEN` as before.

Normal scene commands still work:

```powershell
python tools\send.py text "Hello Athena" --title "Proof of concept"
python tools\send.py markdown README.md --title "AthenaOS" --density compact
python tools\send.py notice "DINNER AT 7" --title "Oi"
python tools\send.py image athena.jpg
python tools\send.py clear
```

v0.3 adds share-endpoint smoke tests:

```powershell
python tools\send.py share-text "Hello from the v0.3 share endpoint" --title "Send to Athena"
python tools\send.py share-file README.md --title "README via share"
```

Structured agenda/task scenes can still be sent with:

```powershell
python tools\send.py scene scene.json
```

## Low-memory image rendering

On the legacy Inky Frame, JPEG decoding needs a large contiguous allocation and Wi-Fi/TLS can fragment the MicroPython heap. Athena therefore renders newly received images in two stages:

```text
wake -> connect -> download JPEG -> save pending scene -> machine.reset()
     -> fresh boot -> decode JPEG before Wi-Fi/full renderer imports
     -> update display -> commit scene -> sleep
```

The pending marker is `scene.pending.json` and the staged JPEG is `scene.next.jpg`. The existing committed scene/image are not replaced until the fresh-boot render succeeds. If decoding fails, the pending marker is cleared to avoid a reboot loop and the previous e-ink image remains intact.
## JPEG limitation

The Pico-side renderer still expects a display-ready **baseline/non-progressive 800x480 JPEG**.

v0.3 solves the Android transport path, not arbitrary-photo normalisation. Tasker has built-in image load/resize/crop/save actions, so phone-side preprocessing can be added later without changing `/share` or Athena's device protocol.

## v0.4 proof checklist

1. Copy one or more PPF Studio files into `/fonts` on Athena.
2. Set `FONT_BODY`, `FONT_SMALL`, `FONT_HEADING`, `FONT_TITLE`, and `FONT_MONO` to their filename stems.
3. In Thonny, run `_fonts.available()` and `_fonts.diagnose("name")` to confirm the files parse.
4. Send a long text scene and verify proportional wrapping/pagination in portrait.
5. Send Markdown and verify body/title/heading/mono roles render independently.
6. Send tasks/agenda and verify the denser custom typography still fits correctly.
7. Temporarily name one role incorrectly and confirm that role falls back to built-in `bitmap8` without breaking the page.
8. Confirm A/B local page turns and the 60-minute sleep/wake behavior are unchanged.

The v0.3 Worker/share path is unchanged by v0.4.
