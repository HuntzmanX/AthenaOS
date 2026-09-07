import gc
import ujson
from urllib import urequest

import config
import inky_helper as ih

try:
    from secrets import (
        WIFI_PASSWORD,
        WIFI_SSID,
        ATHENA_API_BASE,
        ATHENA_API_TOKEN,
        ATHENA_DEVICE_ID,
    )
except ImportError:
    raise RuntimeError("Copy secrets.example.py to secrets.py and configure it")


def connect():
    print("Connecting to", WIFI_SSID)
    ih.network_connect(WIFI_SSID, WIFI_PASSWORD)
    print("Wi-Fi connected")


def _base_url(path):
    return ATHENA_API_BASE.rstrip("/") + path


def _with_auth(url):
    separator = "&" if "?" in url else "?"
    return (
        url
        + separator
        + "device="
        + ATHENA_DEVICE_ID
        + "&token="
        + ATHENA_API_TOKEN
    )


def fetch_current():
    url = _with_auth(_base_url("/current"))
    print("Checking Athena mailbox")
    response = urequest.urlopen(url)
    try:
        scene = ujson.load(response)
    finally:
        response.close()
    gc.collect()
    return scene


def asset_url(asset):
    if asset.startswith("http://") or asset.startswith("https://"):
        url = asset
    elif asset.startswith("/"):
        url = _base_url(asset)
    else:
        url = _base_url("/" + asset)
    return _with_auth(url)


def download_asset(asset, destination, max_bytes=None):
    if max_bytes is None:
        max_bytes = config.MAX_ASSET_BYTES

    url = asset_url(asset)
    print("Downloading asset")
    response = urequest.urlopen(url)
    buffer = bytearray(config.DOWNLOAD_CHUNK_BYTES)
    view = memoryview(buffer)
    total = 0

    try:
        with open(destination, "wb") as handle:
            while True:
                count = response.readinto(buffer)
                if not count:
                    break

                total += count
                if total > max_bytes:
                    raise ValueError("Asset exceeds MAX_ASSET_BYTES")

                handle.write(view[:count])
    finally:
        response.close()

    del view
    del buffer
    gc.collect()
    print("Downloaded", total, "bytes")
    return total
