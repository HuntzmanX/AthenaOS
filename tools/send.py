#!/usr/bin/env python3
"""Small Athena mailbox sender for desktop testing before Tasker is wired up."""

import argparse
import json
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


def post_scene(base, token, device, scene):
    response = requests.post(
        f"{base}/scene",
        params={"device": device},
        headers={**auth(token), "Content-Type": "application/json"},
        json=scene,
        timeout=30,
    )
    response.raise_for_status()
    print(json.dumps(response.json(), indent=2))


def main():
    parser = argparse.ArgumentParser(description="Send a scene to AthenaOS")
    parser.add_argument("--url")
    parser.add_argument("--token")
    parser.add_argument("--device", default="athena")

    sub = parser.add_subparsers(dest="command", required=True)

    for command in ("text", "notice"):
        p = sub.add_parser(command)
        p.add_argument("text")
        p.add_argument("--title", default="Athena" if command == "text" else "Notice")

    md = sub.add_parser("markdown")
    md.add_argument("file")
    md.add_argument("--title", default="Document")

    image = sub.add_parser("image")
    image.add_argument("file")
    image.add_argument("--title", default="")

    structured = sub.add_parser("scene")
    structured.add_argument("file", help="JSON file containing any supported scene")

    sub.add_parser("clear")

    args = parser.parse_args()
    base, token = settings(args)

    if args.command in ("text", "notice"):
        post_scene(base, token, args.device, {
            "type": args.command,
            "title": args.title,
            "text": args.text,
        })
        return

    if args.command == "markdown":
        text = Path(args.file).read_text(encoding="utf-8")
        post_scene(base, token, args.device, {
            "type": "markdown",
            "title": args.title,
            "text": text,
        })
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
        response.raise_for_status()
        print(json.dumps(response.json(), indent=2))
        return

    if args.command == "clear":
        response = requests.post(
            f"{base}/clear",
            params={"device": args.device},
            headers=auth(token),
            timeout=30,
        )
        response.raise_for_status()
        print(json.dumps(response.json(), indent=2))


if __name__ == "__main__":
    main()
