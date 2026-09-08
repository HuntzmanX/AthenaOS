# AthenaOS device configuration

VERSION = "0.2.0"

# Newer Pico 2 W Inky Frame 7.3" units use the Spectra 6 panel.
# Athena's current hardware is the older seven-colour 7.3" panel.
DISPLAY_KIND = "legacy7"  # "spectra7" or "legacy7"

# How often Athena wakes to check its mailbox.
# Keep this at 1 while testing; 15 is a sensible deployed default.
POLL_MINUTES = 15

# Portrait document rendering is software-mapped because PicoGraphics only
# documents constructor rotation for SPI LCDs, not Inky Frame.
# 90 = clockwise, 270 = counter-clockwise.
PORTRAIT_ROTATION = 90

# Dense-renderer defaults. Scenes can override with:
#   orientation: "portrait" | "landscape" | "auto"
#   density: "comfortable" | "compact" | "max"
DEFAULT_DOCUMENT_DENSITY = "compact"
DEFAULT_DASHBOARD_DENSITY = "compact"

# Athena will use /sd/athena automatically when an SD card can be mounted,
# otherwise it falls back to /athena on the Pico's onboard filesystem.
USE_SD_IF_AVAILABLE = True
INTERNAL_ROOT = "/athena"
SD_MOUNT = "/sd"
SD_ROOT = "/sd/athena"

# Standard Inky Frame SD wiring.
SD_SPI_ID = 0
SD_SCK_PIN = 18
SD_MOSI_PIN = 19
SD_MISO_PIN = 16
SD_CS_PIN = 22

# Keep a sanity cap so a bad URL cannot fill the Pico's flash.
MAX_ASSET_BYTES = 900_000
DOWNLOAD_CHUNK_BYTES = 1024

# Local cache names.
SCENE_FILE = "scene.json"
IMAGE_FILE = "scene.jpg"
IMAGE_TEMP_FILE = "scene.next.jpg"

# Local-only keys saved into the cached scene after a successful render.
LOCAL_PAGE_KEY = "_page"
LOCAL_PAGE_COUNT_KEY = "_page_count"
LOCAL_ORIENTATION_KEY = "_orientation"
LOCAL_DENSITY_KEY = "_density"

# A local scene used only when Athena has never successfully received one.
BOOTSTRAP_SCENE = {
    "revision": "local-bootstrap",
    "type": "text",
    "title": "Athena",
    "orientation": "portrait",
    "density": "compact",
    "text": "AthenaOS is ready.\n\nWaiting for the first scene from the mailbox.",
}
