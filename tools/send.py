#!/usr/bin/env python3
"""Athena mailbox sender for desktop testing and v0.3 share-endpoint checks."""

import argparse
import json
import mimetypes
import os
from pathlib import Path

import requests


def settings(args):
    base = (args.url or os.environ.get("ATHENA_URL") or "").rstrip("/")
    token = args.token or os.environ.get("ATHENA_TOKEN") or ""
    if not base or not token:
        raise SystemExit("Set --url/--token or ATHENA_URL/ATHENA_TOKEN")
    return base, token


def auth(token):
    return {"Authorization": f"Bearer {token}"}


def print_response(response):
    response.raise_for_status()
    print(json.dumps(response.json(), indent=2))


def post_scene(base, token, device, scene):
    response = requests.post(
        f"{base}/scene",
        params={"device": device},
        headers={**auth(token), "Content-Type": "application/json"},
        json=scene,
        timeout=30,
    )
    print_response(response)


def add_display_options(parser):
    parser.add_argument(
        "--orientation",
        choices=("auto", "portrait", "landscape"),
        default=None,
        help="Override Athena's scene-type orientation default",
    )
    parser.add_argument(
        "--density",
        choices=("comfortable", "compact", "max"),
        default=None,
        help="Override Athena's renderer density",
    )


def apply_display_options(scene, args):
    orientation = getattr(args, "orientation", None)
    density = getattr(args, "density", None)
    if orientation:
        scene["orientation"] = orientation
    if density:
        scene["density"] = density
    return scene


def share_params(args):
    params = {"device": args.device}
    for name in ("title", "type", "orientation", "density"):
        value = getattr(args, name, None)
        if value:
            params[name] = value
    return params


def main():
    parser = argparse.ArgumentParser(description="Send content to AthenaOS")
    parser.add_argument("--url")
    parser.add_argument("--token")
    parser.add_argument("--device", default="athena")

    sub = parser.add_subparsers(dest="command", required=True)

    for command in ("text", "notice"):
        p = sub.add_parser(command)
        p.add_argument("text")
        p.add_argument("--title", default="Athena" if command == "text" else "Notice")
        add_display_options(p)

    md = sub.add_parser("markdown")
    md.add_argument("file")
    md.add_argument("--title", default="Document")
    add_display_options(md)

    image = sub.add_parser("image")
    image.add_argument("file")
    image.add_argument("--title", default="")

    structured = sub.add_parser("scene")
    structured.add_argument("file", help="JSON file containing any supported scene")

    share_text = sub.add_parser("share-text", help="Exercise the v0.3 /share text path")
    share_text.add_argument("text")
    share_text.add_argument("--title", default="Shared to Athena")
    share_text.add_argument("--type", choices=("text", "notice", "markdown"), default="text")
    add_display_options(share_text)

    share_file = sub.add_parser("share-file", help="Exercise the v0.3 /share file path")
    share_file.add_argument("file")
    share_file.add_argument("--title", default="")
    share_file.add_argument("--type", choices=("text", "notice", "markdown"), default=None)
    add_display_options(share_file)

    sub.add_parser("clear")

    args = parser.parse_args()
    base, token = settings(args)

    if args.command in ("text", "notice"):
        scene = {
            "type": args.command,
            "title": args.title,
            "text": args.text,
        }
        post_scene(base, token, args.device, apply_display_options(scene, args))
        return

    if args.command == "markdown":
        text = Path(args.file).read_text(encoding="utf-8")
        scene = {
            "type": "markdown",
            "title": args.title,
            "text": text,
        }
        post_scene(base, token, args.device, apply_display_options(scene, args))
        return

    if args.command == "scene":
        scene = json.loads(Path(args.file).read_text(encoding="utf-8"))
        post_scene(base, token, args.device, scene)
        return

    if args.command == "image":
        path = Path(args.file)
        with path.open("rb") as handle:
            response = requests.post(
                f"{base}/image",
                params={"device": args.device, "title": args.title},
                headers={**auth(token), "Content-Type": "image/jpeg"},
                data=handle,
                timeout=60,
            )
        print_response(response)
        return

    if args.command == "share-text":
        response = requests.post(
            f"{base}/share",
            params=share_params(args),
            headers={**auth(token), "Content-Type": "text/plain; charset=utf-8"},
            data=args.text.encode("utf-8"),
            timeout=30,
        )
        print_response(response)
        return

    if args.command == "share-file":
        path = Path(args.file)
        guessed, _ = mimetypes.guess_type(path.name)
        content_type = guessed or "application/octet-stream"
        data = {"title": args.title}
        for name in ("type", "orientation", "density"):
            value = getattr(args, name, None)
            if value:
                data[name] = value

        with path.open("rb") as handle:
            response = requests.post(
                f"{base}/share",
                params={"device": args.device},
                headers=auth(token),
                data=data,
                files={"file": (path.name, handle, content_type)},
                timeout=60,
            )
        print_response(response)
        return

    if args.command == "clear":
        response = requests.post(
            f"{base}/clear",
            params={"device": args.device},
            headers=auth(token),
            timeout=30,
        )
        print_response(response)


if __name__ == "__main__":
    main()
