# AthenaOS named PPF font loader.
#
# Files are addressed by stem, like Mercury's /system/_fonts.py:
#     fonts.load("book-12")
# resolves /fonts/book-12.ppf (and the other configured directories).

try:
    import uos as os
except ImportError:
    import os

import config
from ppf_font import PPFFont


_cache = {}
_missing_reported = {}


def _normalise_name(name):
    value = str(name or "").strip()
    if value.lower().endswith(".ppf"):
        value = value[:-4]
    return value


def _directories():
    configured = getattr(config, "FONT_DIRS", None)
    if configured:
        return tuple(configured)
    return ("/fonts", "/athena/fonts", "/sd/fonts", "/sd/athena/fonts")


def _exists_file(path):
    try:
        os.stat(path)
        return True
    except OSError:
        return False


def path(name, aliases=()):
    names = []
    for raw in (name,) + tuple(aliases or ()):
        value = _normalise_name(raw)
        if value and value not in names:
            names.append(value)

    for directory in _directories():
        for value in names:
            candidate = directory.rstrip("/") + "/" + value + ".ppf"
            if _exists_file(candidate):
                return candidate
    return None


def exists(name, aliases=()):
    return path(name, aliases) is not None


def load(name, aliases=(), strict=False):
    """Load a PPF by filename stem, returning None when fallback is allowed."""
    values = [_normalise_name(name)]
    values.extend(_normalise_name(v) for v in (aliases or ()))
    key = tuple(v for v in values if v)

    if key in _cache:
        return _cache[key]

    filename = path(name, aliases)
    if filename is None:
        if strict:
            raise OSError("PPF font not found: " + str(name))
        if key and key not in _missing_reported:
            print("PPF font not found, using built-in fallback:", key[0])
            _missing_reported[key] = True
        _cache[key] = None
        return None

    try:
        font = PPFFont(filename)
        print("Loaded PPF font:", _normalise_name(name), "-", font.name, font.height, "px")
        _cache[key] = font
        return font
    except Exception as exc:
        if strict:
            raise
        if key not in _missing_reported:
            print("PPF font failed, using built-in fallback:", filename, exc)
            _missing_reported[key] = True
        _cache[key] = None
        return None


def _role_name(role_name):
    key = "FONT_" + str(role_name or "body").upper()
    return getattr(config, key, None)


def role(role_name):
    """Load the configured PPF for a semantic typography role."""
    name = _role_name(role_name)
    if not name:
        return None
    return load(name)


def available():
    found = []
    for directory in _directories():
        try:
            entries = os.listdir(directory)
        except OSError:
            continue

        for filename in entries:
            value = str(filename)
            if not value.lower().endswith(".ppf"):
                continue
            stem = value[:-4]
            if stem not in found:
                found.append(stem)

    try:
        found.sort()
    except Exception:
        pass
    return found


def clear_cache():
    _cache.clear()
    _missing_reported.clear()


def diagnose(name):
    filename = path(name)
    result = {
        "name": _normalise_name(name),
        "path": filename,
        "exists": filename is not None,
        "loaded": False,
        "error": None,
    }

    if filename is None:
        result["error"] = "Font file not found"
        return result

    try:
        font = PPFFont(filename)
        result.update({
            "loaded": True,
            "font_name": font.name,
            "glyphs": font.count,
            "width": font.header_width,
            "height": font.height,
            "space_advance": font.space_advance,
        })
    except Exception as exc:
        result["error"] = repr(exc)

    return result
