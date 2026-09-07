# Tasker direction for v0.1

The Worker API is intentionally simple enough for a single Tasker task named **Send to Athena**.

Keep these as Tasker variables or project variables:

- Athena mailbox base URL
- Athena shared token
- device id (`athena`)

## Send text

HTTP POST to `/scene?device=athena`.

Header:

`Authorization: Bearer <token>`

JSON body:

```json
{
  "type": "text",
  "title": "From phone",
  "text": "Whatever Tasker is sending"
}
```

## Send an image

HTTP POST the JPEG bytes to `/image?device=athena&title=...` with:

- `Authorization: Bearer <token>`
- `Content-Type: image/jpeg`

The Worker stores the image in R2, makes it the current scene, and cleans up the previous mailbox image.

## Clear override

HTTP POST to `/clear?device=athena` with the Authorization header.

The next iteration should turn this into a proper Android share target, with Tasker branching on shared text/file/image and optionally resizing/cropping images to Athena's 800×480 canvas before upload.
