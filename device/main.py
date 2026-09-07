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


def _render_and_commit(scene):
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
        render_scene(graphics, scene, temp_asset)
    except Exception:
        if temp_asset:
            storage.remove(config.IMAGE_TEMP_FILE)
        raise

    # Only replace the cached asset/manifest after the display update succeeded.
    if temp_asset:
        storage.promote(config.IMAGE_TEMP_FILE, config.IMAGE_FILE)

    storage.save_json(config.SCENE_FILE, scene)


def _render_cached(scene):
    render_scene(graphics, scene, _cached_asset_path(scene))


def run_once(force_render=False):
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
        if force_render and cached:
            try:
                _render_cached(cached)
            except Exception as exc:
                print("Forced redraw failed:", exc)
        return

    if cached:
        print("Using cached scene:", _revision(cached))
        if force_render:
            try:
                _render_cached(cached)
            except Exception as exc:
                print("Cached redraw failed:", exc)
        return

    # First ever boot with no network: put something deliberate on the panel once,
    # cache it, then leave it alone on subsequent failed wake-ups.
    try:
        _render_and_commit(dict(config.BOOTSTRAP_SCENE))
    except Exception as exc:
        print("Bootstrap render failed:", exc)


# A button wake is useful as a manual redraw/test trigger.
try:
    force = inky_frame.woken_by_button()
except Exception:
    force = False

while True:
    run_once(force_render=force)
    force = False
    gc.collect()

    print("Sleeping for", config.POLL_MINUTES, "minutes")

    # On battery this schedules the external RTC and cuts power to the Pico.
    # When USB power prevents that shutdown, the fallback sleep stops a tight loop.
    try:
        inky_frame.sleep_for(config.POLL_MINUTES)
    except Exception as exc:
        print("RTC sleep unavailable:", exc)

    time.sleep(config.POLL_MINUTES * 60)
