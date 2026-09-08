const ALLOWED_SCENES = new Set([
  "text",
  "notice",
  "markdown",
  "agenda",
  "tasks",
  "image",
]);

const SHARE_TEXT_TYPES = new Set(["text", "notice", "markdown"]);
const ALLOWED_ORIENTATIONS = new Set(["auto", "portrait", "landscape"]);
const ALLOWED_DENSITIES = new Set(["comfortable", "compact", "max"]);

function json(data, status = 200) {
  return new Response(JSON.stringify(data, null, 2), {
    status,
    headers: {
      "content-type": "application/json; charset=utf-8",
      "cache-control": "no-store",
    },
  });
}

function authorised(request, env) {
  const url = new URL(request.url);
  const queryToken = url.searchParams.get("token");
  const auth = request.headers.get("authorization") || "";
  const bearer = auth.toLowerCase().startsWith("bearer ")
    ? auth.slice(7).trim()
    : null;

  return Boolean(env.ATHENA_TOKEN) &&
    (queryToken === env.ATHENA_TOKEN || bearer === env.ATHENA_TOKEN);
}

function deviceId(request) {
  const url = new URL(request.url);
  const raw = url.searchParams.get("device") || "athena";
  return raw.replace(/[^a-zA-Z0-9_-]/g, "").slice(0, 64) || "athena";
}

function currentKey(device) {
  return `current:${device}`;
}

function revision() {
  return `${Date.now()}-${crypto.randomUUID().slice(0, 8)}`;
}

async function readCurrent(env, device) {
  const current = await env.ATHENA_STATE.get(currentKey(device), "json");
  if (current) return current;

  return {
    revision: "mailbox-empty",
    type: "text",
    title: "Athena",
    text: "Mailbox connected.\n\nSend Athena her first scene.",
  };
}

async function setCurrent(env, device, scene) {
  const completed = {
    ...scene,
    revision: revision(),
    device,
    created_at: new Date().toISOString(),
  };

  await env.ATHENA_STATE.put(currentKey(device), JSON.stringify(completed));
  return completed;
}

function assetKeyFromPath(pathname) {
  const prefix = "/assets/";
  if (!pathname.startsWith(prefix)) return null;
  return decodeURIComponent(pathname.slice(prefix.length));
}

async function deletePreviousImage(env, previous) {
  if (!previous || previous.type !== "image" || !previous.asset) return;
  const key = assetKeyFromPath(previous.asset);
  if (!key) return;
  try {
    await env.ATHENA_ASSETS.delete(key);
  } catch (_) {
    // Old asset cleanup is best-effort only.
  }
}

function normaliseScene(scene) {
  const type = String(scene?.type || "text").toLowerCase();
  if (!ALLOWED_SCENES.has(type)) {
    throw new Error(`Unsupported scene type: ${type}`);
  }

  if (type === "image" && !scene.asset) {
    throw new Error("Image scenes need an asset path");
  }

  return { ...scene, type };
}

async function commitScene(env, device, scene) {
  const normalised = normaliseScene(scene);
  const previous = await readCurrent(env, device);
  const current = await setCurrent(env, device, normalised);

  if (previous.asset !== current.asset) {
    await deletePreviousImage(env, previous);
  }

  return current;
}

function getHint(url, fields, name, fallback = "") {
  const fromField = fields && fields[name];
  if (fromField !== undefined && fromField !== null && String(fromField) !== "") {
    return String(fromField);
  }
  return url.searchParams.get(name) || fallback;
}

function shareHints(url, fields = null) {
  let type = getHint(url, fields, "type", "text").toLowerCase();
  if (type === "auto") type = "text";
  if (!SHARE_TEXT_TYPES.has(type)) type = "text";

  const title = getHint(url, fields, "title", "");
  const orientation = getHint(url, fields, "orientation", "").toLowerCase();
  const density = getHint(url, fields, "density", "").toLowerCase();

  const hints = { type, title };
  if (ALLOWED_ORIENTATIONS.has(orientation)) hints.orientation = orientation;
  if (ALLOWED_DENSITIES.has(density)) hints.density = density;
  return hints;
}

function textScene(text, hints, detectedType = null) {
  let type = hints.type;
  if (detectedType === "markdown" && type === "text") {
    type = "markdown";
  }

  const scene = {
    type,
    title: hints.title || (type === "notice" ? "Notice" : type === "markdown" ? "Document" : "Athena"),
    text: String(text || ""),
  };

  if (hints.orientation) scene.orientation = hints.orientation;
  if (hints.density) scene.density = hints.density;
  return scene;
}

async function storeImage(env, device, body, title = "") {
  const key = `${device}/${Date.now()}-${crypto.randomUUID().slice(0, 8)}.jpg`;
  const previous = await readCurrent(env, device);

  await env.ATHENA_ASSETS.put(key, body, {
    httpMetadata: { contentType: "image/jpeg" },
  });

  const current = await setCurrent(env, device, {
    type: "image",
    title,
    asset: `/assets/${encodeURIComponent(key)}`,
  });

  await deletePreviousImage(env, previous);
  return current;
}

async function handleScene(request, env, device) {
  let scene;
  try {
    scene = await request.json();
  } catch (_) {
    return json({ error: "Body must be JSON" }, 400);
  }

  try {
    return json(await commitScene(env, device, scene), 201);
  } catch (error) {
    return json({ error: String(error?.message || error) }, 400);
  }
}

async function handleImage(request, env, device) {
  const contentType = (request.headers.get("content-type") || "").toLowerCase();
  if (!contentType.includes("image/jpeg")) {
    return json({
      error: "Image upload expects JPEG (Content-Type: image/jpeg)",
    }, 415);
  }

  const url = new URL(request.url);
  const title = url.searchParams.get("title") || "";
  return json(await storeImage(env, device, request.body, title), 201);
}

function fileExtension(name) {
  const lower = String(name || "").toLowerCase();
  const dot = lower.lastIndexOf(".");
  return dot >= 0 ? lower.slice(dot) : "";
}

function isJpeg(contentType, name) {
  const type = String(contentType || "").toLowerCase();
  const ext = fileExtension(name);
  return type.includes("image/jpeg") || ext === ".jpg" || ext === ".jpeg";
}

function isMarkdown(contentType, name) {
  const type = String(contentType || "").toLowerCase();
  const ext = fileExtension(name);
  return type.includes("text/markdown") || ext === ".md" || ext === ".markdown";
}

function isTextFile(contentType, name) {
  const type = String(contentType || "").toLowerCase();
  const ext = fileExtension(name);
  return type.startsWith("text/") || ext === ".txt";
}

async function handleShareFile(env, device, file, hints) {
  const name = file.name || "";
  const contentType = file.type || "";

  if (isJpeg(contentType, name)) {
    return json(
      await storeImage(env, device, file.stream(), hints.title || name),
      201,
    );
  }

  if (isMarkdown(contentType, name)) {
    const text = await file.text();
    const scene = textScene(text, hints, "markdown");
    if (!hints.title && name) scene.title = name;
    return json(await commitScene(env, device, scene), 201);
  }

  if (isTextFile(contentType, name)) {
    const text = await file.text();
    const scene = textScene(text, hints);
    if (!hints.title && name) scene.title = name;
    return json(await commitScene(env, device, scene), 201);
  }

  return json({
    error: `Unsupported shared file: ${name || contentType || "unknown"}`,
    supported: [".txt", ".md", ".jpg", ".jpeg"],
  }, 415);
}

async function handleShare(request, env, device) {
  const url = new URL(request.url);
  const contentType = (request.headers.get("content-type") || "").toLowerCase();

  if (contentType.includes("application/json")) {
    let scene;
    try {
      scene = await request.json();
    } catch (_) {
      return json({ error: "JSON share body could not be parsed" }, 400);
    }

    try {
      return json(await commitScene(env, device, scene), 201);
    } catch (error) {
      return json({ error: String(error?.message || error) }, 400);
    }
  }

  if (contentType.includes("image/jpeg")) {
    const hints = shareHints(url);
    return json(await storeImage(env, device, request.body, hints.title), 201);
  }

  if (
    contentType.includes("multipart/form-data") ||
    contentType.includes("application/x-www-form-urlencoded")
  ) {
    const form = await request.formData();
    const fields = {};
    let file = null;

    for (const [key, value] of form.entries()) {
      if (typeof value === "string") {
        if (fields[key] === undefined) fields[key] = value;
      } else if (!file) {
        file = value;
      }
    }

    const hints = shareHints(url, fields);
    if (file) {
      return handleShareFile(env, device, file, hints);
    }

    const text = fields.text ?? fields.body ?? fields.share ?? "";
    if (!text) {
      return json({ error: "Share contained no text or supported file" }, 400);
    }
    return json(await commitScene(env, device, textScene(text, hints)), 201);
  }

  if (
    contentType.startsWith("text/") ||
    !contentType ||
    contentType.includes("application/octet-stream")
  ) {
    const hints = shareHints(url);
    const text = await request.text();
    const detectedType = contentType.includes("text/markdown") ? "markdown" : null;
    if (!text) return json({ error: "Share body is empty" }, 400);
    return json(
      await commitScene(env, device, textScene(text, hints, detectedType)),
      201,
    );
  }

  return json({
    error: `Unsupported share content type: ${contentType || "unknown"}`,
    supported: ["text/plain", "text/markdown", "image/jpeg", "multipart/form-data", "application/json"],
  }, 415);
}

async function handleAsset(request, env) {
  const url = new URL(request.url);
  const key = assetKeyFromPath(url.pathname);
  if (!key) return new Response("Not found", { status: 404 });

  const object = await env.ATHENA_ASSETS.get(key);
  if (!object) return new Response("Not found", { status: 404 });

  const headers = new Headers();
  object.writeHttpMetadata(headers);
  headers.set("etag", object.httpEtag);
  headers.set("cache-control", "private, max-age=300");
  return new Response(object.body, { headers });
}

async function handleClear(env, device) {
  const previous = await readCurrent(env, device);
  const current = await setCurrent(env, device, {
    type: "text",
    title: "Athena",
    text: "Standing by.",
  });
  await deletePreviousImage(env, previous);
  return json(current);
}

export default {
  async fetch(request, env) {
    if (!authorised(request, env)) {
      return json({ error: "Unauthorised" }, 401);
    }

    const url = new URL(request.url);
    const device = deviceId(request);

    try {
      if (request.method === "GET" && url.pathname === "/current") {
        return json(await readCurrent(env, device));
      }

      if (request.method === "GET" && url.pathname.startsWith("/assets/")) {
        return handleAsset(request, env);
      }

      if (request.method === "POST" && url.pathname === "/scene") {
        return handleScene(request, env, device);
      }

      if (request.method === "POST" && url.pathname === "/image") {
        return handleImage(request, env, device);
      }

      if (request.method === "POST" && url.pathname === "/share") {
        return handleShare(request, env, device);
      }

      if (request.method === "POST" && url.pathname === "/clear") {
        return handleClear(env, device);
      }

      if (request.method === "GET" && url.pathname === "/") {
        return json({
          name: "Athena Mailbox",
          version: "0.3.0",
          endpoints: [
            "GET /current",
            "POST /scene",
            "POST /image",
            "POST /share",
            "POST /clear",
          ],
        });
      }

      return json({ error: "Not found" }, 404);
    } catch (error) {
      console.error(error);
      return json({ error: String(error?.message || error) }, 500);
    }
  },
};
