# AthenaOS v0.2

AthenaOS turns a Pimoroni Inky Frame 7.3" into a quiet e-ink information and art surface.

Athena is deliberately a **display endpoint**, not another general-purpose computer. Other devices put a scene into a tiny mailbox; Athena wakes, checks the scene revision, renders only when something has changed, caches it, and goes back to sleep. If Wi-Fi or the mailbox is unavailable, the previous e-ink image simply stays on screen.

## Architecture

```text
Phone / Tasker / PC / Hermes / Mercury
                 |
                 | POST scene or image
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

## v0.2: dense renderer

v0.2 is built around the legacy seven-colour panel's slow full refresh: **make every refresh worth it**.

- `text` and `markdown` default to a software-mapped **480x800 portrait page**.
- `notice`, `agenda`, `tasks`, and `image` remain **800x480 landscape** by default.
- Scene orientation can be overridden with `orientation: portrait|landscape|auto`.
- Renderer density can be `comfortable`, `compact`, or `max`.
- Long text and Markdown are automatically paginated.
- Long agendas and task lists paginate too.
- Compact/max landscape task lists use two columns.
- Current page is stored locally in Athena's cached scene, not in the mailbox.
- **A = previous page**, **E = next page**, **C = manual redraw**.

Portrait mode does not rely on PicoGraphics display rotation. Pimoroni only documents constructor-level 90-degree rotation for SPI LCDs, so AthenaOS maps a logical portrait canvas onto the Inky framebuffer and uses PicoGraphics' per-text angle support. `PORTRAIT_ROTATION` in `device/config.py` can be changed between `90` and `270` if the physical reading direction should be reversed.

See [`docs/SCENES.md`](docs/SCENES.md) for the scene format.

## Scene types

- `text`
- `notice`
- `markdown`
- `agenda`
- `tasks`
- `image`

## Storage: no SD card required

`device/storage.py` is storage-agnostic.

At boot Athena tries to mount an SD card. If that succeeds it uses:

```text
/sd/athena
```

If it fails, Athena uses onboard flash:

```text
/athena
```

Athena currently keeps only:

- the current scene JSON, including local pagination state
- at most one cached JPEG
- a temporary JPEG while a replacement is downloading

Downloads are streamed in 1 KB chunks rather than loaded into RAM. The temporary image is rendered first; Athena only replaces its cached asset/manifest after the new scene displays successfully.

## Display hardware

This Athena is the older seven-colour 7.3" Inky Frame, so the repository defaults to:

```python
DISPLAY_KIND = "legacy7"
```

The newer Spectra build remains supported with:

```python
DISPLAY_KIND = "spectra7"
```

## Device setup

Use a current Pimoroni Inky Frame MicroPython firmware.

Copy the contents of `device/` to the root of the Inky Frame filesystem, so `main.py`, `config.py`, etc. are at `/`.

Copy:

```text
secrets.example.py -> secrets.py
```

and set:

- phone hotspot SSID/password
- Worker URL
- shared Athena token

The shared token should be a long random string and `device/secrets.py` is ignored by Git.

### Wake behaviour

`POLL_MINUTES` controls how often Athena wakes to check its mailbox. The v0.2 branch keeps it at `1` while testing; `15` is a sensible deployed value.

If the mailbox revision has not changed, **the e-ink panel is not refreshed**.

On battery, `inky_frame.sleep_for()` schedules the external RTC wake and cuts power to the Pico. Button wakes allow local document navigation without changing the mailbox scene.

## Cloudflare Worker mailbox

`worker/src/index.js` expects two bindings:

- `ATHENA_STATE` - KV namespace
- `ATHENA_ASSETS` - R2 bucket

The API is:

```text
GET  /current
POST /scene
POST /image
POST /clear
GET  /assets/<key>
```

Phone/desktop writers authenticate with `Authorization: Bearer <token>`. Athena's small GET client uses the same token as a query parameter.

## Desktop testing

Install Requests:

```bash
pip install requests
```

Set the mailbox details, then use `tools/send.py`:

```bash
python tools/send.py text "Hello Athena" --title "Proof of concept"
python tools/send.py text "A long note..." --title "Reading" --density max
python tools/send.py text "Wide note" --orientation landscape
python tools/send.py markdown README.md --title "AthenaOS" --density compact
python tools/send.py notice "DINNER AT 7" --title "Oi"
python tools/send.py image athena.jpg
python tools/send.py clear
```

Structured agenda/task scenes can be sent from JSON:

```bash
python tools/send.py scene scene.json
```

## Image limitation

The Pico-side renderer uses Pimoroni's `jpegdec` directly. Images should currently be **baseline/non-progressive JPEGs at 800x480**.

A later AthenaOS version can move arbitrary phone-image resizing/cropping to Tasker or the mailbox so the device continues to receive a simple display-ready asset.

## v0.2 hardware test checklist

1. Send a long text scene and confirm it renders portrait.
2. If portrait reads in the wrong physical direction, change `PORTRAIT_ROTATION` from `90` to `270`.
3. Confirm the page marker shows more than one page.
4. On battery, press E to wake Athena and render the next cached page; A returns to the previous page.
5. Send `README.md` as Markdown and verify headings, bullets, rules and pagination.
6. Send a dense task list and verify the two-column landscape layout.
7. Confirm an unchanged mailbox revision still causes no display refresh.
8. Return `POLL_MINUTES` to a sensible deployed interval after testing.

Once the dense renderer is solid on hardware, the next layer is Tasker's **Send to Athena** Android share flow.
