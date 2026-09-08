# AthenaOS v0.3

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

## JPEG limitation

The Pico-side renderer still expects a display-ready **baseline/non-progressive 800x480 JPEG**.

v0.3 solves the Android transport path, not arbitrary-photo normalisation. Tasker has built-in image load/resize/crop/save actions, so phone-side preprocessing can be added later without changing `/share` or Athena's device protocol.

## v0.3 proof checklist

1. Deploy the updated Worker.
2. Confirm `GET /` reports mailbox version `0.3.0` and includes `POST /share`.
3. Send `share-text` from the desktop helper and verify `/current` changes.
4. Send `share-file README.md` and verify Athena receives a Markdown scene.
5. Build the Tasker Received Share profile from `docs/TASKER.md`.
6. Share selected Android text to **Send to Athena**.
7. Wake Athena with a non-A/B button and confirm it renders the new scene.
8. Confirm A/B still page locally without Wi-Fi first.
