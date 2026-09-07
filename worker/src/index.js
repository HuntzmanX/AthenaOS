export default {
  async fetch(request, env, ctx) {
    return new Response("Athena mailbox alive", {
      status: 200,
      headers: {
        "content-type": "text/plain; charset=utf-8"
      }
    });
  }
};