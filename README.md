# AthenaOS v0.1

AthenaOS turns a Pimoroni Inky Frame 7.3" into a quiet e-ink information and art surface.

Athena is deliberately a **display endpoint**, not another general-purpose computer. Other devices put a scene into a tiny mailbox; Athena wakes, checks the scene revision, renders only when something has changed, caches it, and goes back to sleep. If Wi-Fi or the mailbox is unavailable, the previous e-ink image simply stays on screen.

## v0.1 architecture

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

### Scene types in this proof of concept

- `text`
- `notice`
- `markdown` (small useful subset)
- `agenda`
- `tasks`
- `image`

See [`docs/SCENES.md`](docs/SCENES.md).

## Storage: no SD card required

`device/storage.py` is intentionally storage-agnostic.

At boot Athena tries to mount an SD card using the standard Inky Frame pins. If that succeeds it uses:

```text
/sd/athena
```

If it fails — which is completely normal for the current hardware setup — it uses onboard flash instead:

```text
/athena
```

v0.1 only keeps:

- the current scene JSON
- at most one cached JPEG
- a temporary JPEG while a replacement is downloading

Downloads are streamed in 1 KB chunks rather than loaded into RAM. The temporary image is rendered first; Athena only replaces its cached asset/manifest after the new scene displays successfully.

## Display hardware

Current Pimoroni firmware targets the newer **Inky Frame 7.3" Spectra 6 / Pico 2 W** by default. `device/config.py` therefore starts with:

```python
DISPLAY_KIND = "spectra7"
```

If this Athena is the older seven-colour 7.3" model, change it to:

```python
DISPLAY_KIND = "legacy7"
```

## 1. Device setup

Use a current Pimoroni Inky Frame MicroPython firmware.

Copy the contents of `device/` to the root of the Inky Frame filesystem, so `main.py`, `config.py`, etc. are at `/`.

Then copy:

```text
secrets.example.py -> secrets.py
```

and set:

- phone hotspot SSID/password
- Worker URL
- shared Athena token

The shared token should be a long random string.

### Wake behaviour

Athena checks the mailbox every 15 minutes by default (`POLL_MINUTES` in `config.py`). If the revision has not changed, **the e-ink panel is not refreshed**.

On battery, `inky_frame.sleep_for()` schedules the external RTC wake and cuts power to the Pico. While testing over USB, a normal `time.sleep()` fallback prevents a tight loop if USB power keeps the board alive.

A button wake is treated as a manual redraw trigger.

## 2. Cloudflare Worker mailbox

`worker/src/index.js` expects two bindings:

- `ATHENA_STATE` — KV namespace
- `ATHENA_ASSETS` — R2 bucket

Copy `worker/wrangler.toml.example` to `worker/wrangler.toml`, fill in the KV namespace ID and make sure the R2 bucket exists.

Store the same token used in `device/secrets.py` as the Worker secret `ATHENA_TOKEN`.

The API is:

```text
GET  /current
POST /scene
POST /image
POST /clear
GET  /assets/<key>
```

Phone/desktop writers can authenticate with `Authorization: Bearer <token>`. Athena's tiny GET client uses the same token as a query parameter to keep the MicroPython networking path simple for the proof of concept.

## 3. Test without Tasker first

Install desktop Requests:

```bash
pip install requests
```

Set the mailbox details:

```bash
set ATHENA_URL=https://your-worker.workers.dev
set ATHENA_TOKEN=your-token
```

Then:

```bash
python tools/send.py text "Hello from the Athena mailbox" --title "Proof of concept"
python tools/send.py notice "DINNER AT 7" --title "Oi"
python tools/send.py markdown README.md --title "AthenaOS"
python tools/send.py image athena.jpg
python tools/send.py clear
```

A structured agenda/tasks scene can be put in a JSON file and sent with:

```bash
python tools/send.py scene scene.json
```

## Image limitation in v0.1

The Pico-side renderer uses Pimoroni's `jpegdec` directly. For the first proof of concept, image uploads should be **baseline/non-progressive JPEGs at 800×480**.

That deliberately keeps the device code and RAM/storage requirements tiny. The obvious next step is to let Tasker/the mailbox accept arbitrary phone images and normalise them to Athena's canvas automatically.

## What v0.1 proves

This version is successful if we can demonstrate all of these:

1. Athena wakes and joins the phone hotspot.
2. It fetches a tiny mailbox scene.
3. Text/agenda/tasks/markdown render locally.
4. A JPEG streams to onboard flash and renders without needing an SD card.
5. Re-checking an unchanged revision does not refresh the display.
6. Losing Wi-Fi leaves the last scene safely visible.
7. Adding an SD card later changes the storage root without changing the scene/render/network code.

Once those are solid, Tasker's **Send to Athena** share flow becomes the next layer rather than part of the risky hardware proof.
