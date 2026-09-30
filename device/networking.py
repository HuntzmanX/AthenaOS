import gc
import time
import ujson

try:
    import usocket as socket
except ImportError:
    import socket

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


def _api_host_port():
    """Return the mailbox host and port without depending on urllib.parse."""
    base = str(ATHENA_API_BASE).strip()
    secure = base.lower().startswith("https://")
    authority = base.split("://", 1)[-1].split("/", 1)[0]

    if ":" in authority:
        host, raw_port = authority.rsplit(":", 1)
        try:
            return host, int(raw_port)
        except ValueError:
            pass

    return authority, 443 if secure else 80


def _error_code(exc):
    try:
        return int(exc.args[0])
    except Exception:
        try:
            return int(exc)
        except Exception:
            return None


def _is_dns_error(exc):
    code = _error_code(exc)
    return code is not None and code < 0


def _sleep_ms(milliseconds):
    try:
        time.sleep_ms(milliseconds)
    except AttributeError:
        time.sleep(milliseconds / 1000)


def _network_config(wlan):
    try:
        return wlan.ifconfig()
    except Exception:
        return None


def _has_ipv4(config_values):
    if not config_values:
        return False
    try:
        address = str(config_values[0])
    except Exception:
        return False
    return bool(address and address != "0.0.0.0")


def _wifi_status(wlan):
    try:
        return wlan.status()
    except Exception:
        return None


def _wait_for_ipv4(wlan, attempts=20, delay_ms=500):
    """Wait for DHCP to assign a usable IPv4 address."""
    last_config = None

    for attempt in range(1, attempts + 1):
        last_config = _network_config(wlan)
        if _has_ipv4(last_config):
            print("Network config:", last_config)
            return last_config

        print(
            "Waiting for DHCP...",
            attempt,
            "/",
            attempts,
            "status",
            _wifi_status(wlan),
        )
        _sleep_ms(delay_ms)

    raise RuntimeError(
        "DHCP lease not acquired; last config=" + str(last_config)
    )


def _reconnect_station(wlan):
    """Cycle the station interface once if association completed without DHCP."""
    print("Cycling Wi-Fi interface for DHCP retry")

    try:
        wlan.disconnect()
    except Exception:
        pass

    _sleep_ms(250)

    try:
        wlan.active(False)
        _sleep_ms(500)
        wlan.active(True)
        _sleep_ms(250)
    except Exception as exc:
        print("Wi-Fi interface cycle warning:", exc)

    wlan.connect(WIFI_SSID, WIFI_PASSWORD)


def _wait_for_dns(attempts=8, delay_ms=500):
    """Wait briefly for DNS to become usable after Wi-Fi association/DHCP."""
    host, port = _api_host_port()
    if not host:
        raise ValueError("ATHENA_API_BASE has no hostname")

    last_error = None

    for attempt in range(1, attempts + 1):
        try:
            info = socket.getaddrinfo(host, port)
            if info:
                address = info[0][-1][0]
                print("DNS ready:", host, "->", address)
                return address
        except OSError as exc:
            last_error = exc
            if not _is_dns_error(exc):
                raise

        print("Waiting for DNS...", attempt, "/", attempts)
        _sleep_ms(delay_ms)

    if last_error is not None:
        raise last_error
    raise OSError(-2)


def connect():
    print("Connecting to", WIFI_SSID)
    ih.network_connect(WIFI_SSID, WIFI_PASSWORD)
    print("Wi-Fi associated")

    # Pimoroni's older helper can report Wi-Fi as connected while DHCP still
    # shows 0.0.0.0. DNS/HTTP cannot work until the station owns a real address.
    try:
        import network

        wlan = network.WLAN(network.STA_IF)

        try:
            _wait_for_ipv4(wlan, attempts=20, delay_ms=500)
        except Exception as first_exc:
            print("DHCP not ready after helper:", first_exc)
            _reconnect_station(wlan)
            _wait_for_ipv4(wlan, attempts=40, delay_ms=500)

    except ImportError:
        # Extremely old/trimmed firmware: keep the previous behaviour and let
        # the explicit DNS test below provide the useful failure.
        print("network module unavailable; skipping DHCP diagnostics")

    print("Wi-Fi ready")
    _wait_for_dns()


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


def _open_url(url):
    """Open a URL with one bounded DNS recovery pass."""
    try:
        return urequest.urlopen(url)
    except OSError as exc:
        if not _is_dns_error(exc):
            raise

        print("DNS lookup failed during request, retrying:", exc)
        _wait_for_dns()
        return urequest.urlopen(url)


def fetch_current():
    url = _with_auth(_base_url("/current"))
    print("Checking Athena mailbox")

    response = _open_url(url)
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
    response = _open_url(url)
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
