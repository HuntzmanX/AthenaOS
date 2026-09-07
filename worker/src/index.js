const ALLOWED_SCENES = new Set([
  "text",
  "notice",
  "markdown",
  "agenda",
  "tasks",
  "image",
]);

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

async function handleScene(request, env, device) {
  let scene;
  try {
    scene = await request.json();
  } catch (_) {
    return json({ error: "Body must be JSON" }, 400);
  }

  const type = String(scene.type || "text").toLowerCase();
  if (!ALLOWED_SCENES.has(type)) {
    return json({ error: `Unsupported scene type: ${type}` }, 400);
  }

  if (type === "image" && !scene.asset) {
    return json({ error: "Image scenes need an asset path" }, 400);
  }

  const previous = await readCurrent(env, device);
  const current = await setCurrent(env, device, { ...scene, type });

  if (previous.asset !== current.asset) {
    await deletePreviousImage(env, previous);
  }

  return json(current, 201);
}

async function handleImage(request, env, device) {
  const contentType = (request.headers.get("content-type") || "").toLowerCase();
  if (!contentType.includes("image/jpeg")) {
    return json({
      error: "v0.1 image upload expects a baseline JPEG (Content-Type: image/jpeg)",
    }, 415);
  }

  const url = new URL(request.url);
  const title = url.searchParams.get("title") || "";
  const key = `${device}/${Date.now()}-${crypto.randomUUID().slice(0, 8)}.jpg`;
  const previous = await readCurrent(env, device);

  await env.ATHENA_ASSETS.put(key, request.body, {
    httpMetadata: { contentType: "image/jpeg" },
  });

  const current = await setCurrent(env, device, {
    type: "image",
    title,
    asset: `/assets/${encodeURIComponent(key)}`,
  });

  await deletePreviousImage(env, previous);
  return json(current, 201);
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

      if (request.method === "POST" && url.pathname === "/clear") {
        return handleClear(env, device);
      }

      if (request.method === "GET" && url.pathname === "/") {
        return json({
          name: "Athena Mailbox",
          version: "0.1.0",
          endpoints: ["GET /current", "POST /scene", "POST /image", "POST /clear"],
        });
      }

      return json({ error: "Not found" }, 404);
    } catch (error) {
      console.error(error);
      return json({ error: String(error?.message || error) }, 500);
    }
  },
};
