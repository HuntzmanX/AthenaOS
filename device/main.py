import gc

import config
import inky_frame
from renderers import create_graphics, render_scene
from storage import Storage


print("AthenaOS", config.VERSION)

storage = Storage()
graphics = create_graphics()


def _revision(scene):
    if not scene:
        return None
    return str(scene.get("revision", ""))


def _cached_asset_path(scene):
    if scene and str(scene.get("type", "")).lower() == "image":
        if storage.exists(config.IMAGE_FILE):
            return storage.path(config.IMAGE_FILE)
    return None


def _apply_render_meta(scene, meta):
    if not meta:
        return
    scene[config.LOCAL_PAGE_KEY] = int(meta.get("page", 0))
    scene[config.LOCAL_PAGE_COUNT_KEY] = int(meta.get("page_count", 1))
    scene[config.LOCAL_ORIENTATION_KEY] = str(meta.get("orientation", "landscape"))
    scene[config.LOCAL_DENSITY_KEY] = str(meta.get("density", "compact"))


def _reset_local_state(scene):
    scene = dict(scene)
    scene[config.LOCAL_PAGE_KEY] = 0
    scene.pop(config.LOCAL_PAGE_COUNT_KEY, None)
    scene.pop(config.LOCAL_ORIENTATION_KEY, None)
    scene.pop(config.LOCAL_DENSITY_KEY, None)
    return scene


def _render_pending_image():
    """Render a staged JPEG before the networking stack is ever imported."""
    pending = storage.load_json(config.PENDING_SCENE_FILE)
    if not pending:
        return False

    if str(pending.get("type", "")).lower() != "image":
        print("Discarding invalid pending scene")
        storage.remove(config.PENDING_SCENE_FILE)
        storage.remove(config.IMAGE_TEMP_FILE)
        return False

    if not storage.exists(config.IMAGE_TEMP_FILE):
        print("Pending image marker has no JPEG; discarding marker")
        storage.remove(config.PENDING_SCENE_FILE)
        return False

    print("Pending image found - rendering before Wi-Fi")
    gc.collect()
    try:
        print("Fresh-boot RAM before image:", gc.mem_free())
    except Exception:
        pass

    try:
        meta = render_scene(
            graphics,
            pending,
            storage.path(config.IMAGE_TEMP_FILE),
        )
    except Exception as exc:
        # Do not create a reboot loop if a malformed/unsupported JPEG still
        # cannot be decoded. Keep the old committed scene/display intact.
        print("Pending image render failed:", exc)
        storage.remove(config.PENDING_SCENE_FILE)
        gc.collect()
        return False

    storage.promote(config.IMAGE_TEMP_FILE, config.IMAGE_FILE)
    _apply_render_meta(pending, meta)
    storage.save_json(config.SCENE_FILE, pending)
    storage.remove(config.PENDING_SCENE_FILE)

    print("Pending image committed:", _revision(pending))
    gc.collect()
    return True


def _stage_image_and_reboot(scene):
    """Download an image, persist its scene, then reboot into a clean render pass."""
    asset = scene.get("asset")
    if not asset:
        raise ValueError("Image scene is missing 'asset'")

    # Import networking only in the network phase. A reboot after this function
    # means the JPEG render phase starts without importing Wi-Fi/HTTP/TLS at all.
    import networking
    import machine

    storage.remove(config.IMAGE_TEMP_FILE)
    storage.remove(config.PENDING_SCENE_FILE)

    temp_asset = storage.path(config.IMAGE_TEMP_FILE)
    networking.download_asset(asset, temp_asset)

    pending = _reset_local_state(scene)
    storage.save_json(config.PENDING_SCENE_FILE, pending)

    print("Image staged; rebooting for clean JPEG render")
    gc.collect()

    try:
        machine.reset()
    except Exception:
        # If a firmware exposes reset differently, do not fall through and try
        # to decode in the fragmented networking heap.
        raise RuntimeError("Image staged but machine.reset() failed")


def _render_and_commit(scene):
    scene = _reset_local_state(scene)
    scene_type = str(scene.get("type", "text")).lower()

    if scene_type == "image":
        _stage_image_and_reboot(scene)
        return

    meta = render_scene(graphics, scene)
    _apply_render_meta(scene, meta)
    storage.save_json(config.SCENE_FILE, scene)


def _render_cached(scene):
    meta = render_scene(graphics, scene, _cached_asset_path(scene))
    _apply_render_meta(scene, meta)
    storage.save_json(config.SCENE_FILE, scene)


def _page_count(scene):
    try:
        return max(1, int(scene.get(config.LOCAL_PAGE_COUNT_KEY, 1)))
    except Exception:
        return 1


def _page_number(scene):
    try:
        return max(0, int(scene.get(config.LOCAL_PAGE_KEY, 0)))
    except Exception:
        return 0


def _turn_page(scene, delta):
    count = _page_count(scene)
    if count <= 1:
        print("Scene has one page")
        return False

    current = min(_page_number(scene), count - 1)
    target = current + int(delta)
    if target < 0:
        target = 0
    if target >= count:
        target = count - 1

    if target == current:
        print("Already at page", current + 1, "of", count)
        return False

    scene[config.LOCAL_PAGE_KEY] = target
    print("Turning to page", target + 1, "of", count)
    _render_cached(scene)
    return True


def _wake_action():
    """Use the Inky power/wake cycle as the UI: A=previous, B=next."""
    try:
        if not inky_frame.woken_by_button():
            return None

        if inky_frame.button_a.read():
            return "prev"
        if inky_frame.button_b.read():
            return "next"
    except Exception as exc:
        print("Could not read wake button:", exc)

    return None


def _handle_local_button(cached, action):
    if not cached or not action:
        return False

    if action == "prev":
        try:
            _turn_page(cached, -1)
        except Exception as exc:
            print("Previous page failed:", exc)
        return True

    if action == "next":
        try:
            _turn_page(cached, 1)
        except Exception as exc:
            print("Next page failed:", exc)
        return True

    return False


def run_once(button_action=None):
    cached = storage.load_json(config.SCENE_FILE)

    # Page turns are local-first. A/B button wakes never need Wi-Fi or a mailbox
    # round-trip; they simply redraw another page from the cached scene.
    if _handle_local_button(cached, button_action):
        return

    # Networking is deliberately lazy-imported. This is important for staged
    # images: their reboot render runs before this module is loaded at all.
    import networking

    remote = None

    try:
        networking.connect()
        remote = networking.fetch_current()
    except Exception as exc:
        print("Mailbox unavailable:", exc)
        gc.collect()

    if remote:
        remote_revision = _revision(remote)
        cached_revision = _revision(cached)

        if remote_revision != cached_revision:
            print("New scene:", remote_revision)
            try:
                _render_and_commit(remote)
                return
            except Exception as exc:
                # The existing e-ink image remains untouched if the new scene fails.
                print("New scene failed:", exc)
                gc.collect()
                return

        print("Scene unchanged:", remote_revision)

    if cached:
        if not remote:
            print("Using cached scene:", _revision(cached))
        return

    # First ever boot with no network: put something deliberate on the panel once,
    # cache it, then leave it alone on subsequent failed wake-ups.
    try:
        _render_and_commit(dict(config.BOOTSTRAP_SCENE))
    except Exception as exc:
        print("Bootstrap render failed:", exc)


# Staged images get first refusal on every boot, before networking is imported.
# If one succeeds, Athena has completed the requested refresh and can go straight
# back to sleep without reconnecting just to discover the same revision.
if _render_pending_image():
    print("Sleeping for", config.POLL_MINUTES, "minutes")
    inky_frame.sleep_for(config.POLL_MINUTES)


# Athena is intentionally event-driven rather than a continuously running UI.
# On battery, sleep_for() powers the Pico off and either the RTC or a front button
# starts main.py again. On USB, Pimoroni's helper emulates the wait internally.
while True:
    action = _wake_action()
    if action:
        print("Wake button action:", action)

    run_once(button_action=action)
    gc.collect()

    print("Sleeping for", config.POLL_MINUTES, "minutes")
    inky_frame.sleep_for(config.POLL_MINUTES)
