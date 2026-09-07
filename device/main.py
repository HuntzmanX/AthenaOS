import gc
import time

import config
import inky_frame
import networking
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


def _render_and_commit(scene):
    scene = _reset_local_state(scene)
    scene_type = str(scene.get("type", "text")).lower()
    temp_asset = None

    if scene_type == "image":
        asset = scene.get("asset")
        if not asset:
            raise ValueError("Image scene is missing 'asset'")

        storage.remove(config.IMAGE_TEMP_FILE)
        temp_asset = storage.path(config.IMAGE_TEMP_FILE)
        networking.download_asset(asset, temp_asset)

    try:
        meta = render_scene(graphics, scene, temp_asset)
    except Exception:
        if temp_asset:
            storage.remove(config.IMAGE_TEMP_FILE)
        raise

    # Only replace the cached asset/manifest after the display update succeeded.
    if temp_asset:
        storage.promote(config.IMAGE_TEMP_FILE, config.IMAGE_FILE)

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


def _button_action():
    """A=previous page, E=next page, C=manual redraw."""
    try:
        if inky_frame.button_a.raw():
            return "prev"
        if inky_frame.button_e.raw():
            return "next"
        if inky_frame.button_c.raw():
            return "redraw"
    except Exception as exc:
        print("Could not read wake button:", exc)
    return None


def run_once(button_action=None):
    cached = storage.load_json(config.SCENE_FILE)
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
        if button_action == "prev":
            try:
                _turn_page(cached, -1)
            except Exception as exc:
                print("Previous page failed:", exc)
            return

        if button_action == "next":
            try:
                _turn_page(cached, 1)
            except Exception as exc:
                print("Next page failed:", exc)
            return

        if button_action == "redraw":
            try:
                print("Manual redraw")
                _render_cached(cached)
            except Exception as exc:
                print("Manual redraw failed:", exc)
            return

        if not remote:
            print("Using cached scene:", _revision(cached))
        return

    # First ever boot with no network: put something deliberate on the panel once,
    # cache it, then leave it alone on subsequent failed wake-ups.
    try:
        _render_and_commit(dict(config.BOOTSTRAP_SCENE))
    except Exception as exc:
        print("Bootstrap render failed:", exc)


try:
    woke_by_button = inky_frame.woken_by_button()
except Exception:
    woke_by_button = False

action = _button_action() if woke_by_button else None
if action:
    print("Button action:", action)

while True:
    run_once(button_action=action)
    action = None
    gc.collect()

    print("Sleeping for", config.POLL_MINUTES, "minutes")

    # On battery this schedules the external RTC and cuts power to the Pico.
    # When USB power prevents that shutdown, the fallback sleep stops a tight loop.
    try:
        inky_frame.sleep_for(config.POLL_MINUTES)
    except Exception as exc:
        print("RTC sleep unavailable:", exc)

    time.sleep(config.POLL_MINUTES * 60)
