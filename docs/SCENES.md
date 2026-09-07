# Athena scene format

Every scene is JSON. The mailbox adds `revision`, `device`, and `created_at`; clients only need to send the scene content.

## Text

```json
{
  "type": "text",
  "title": "Remember",
  "text": "Measure the shelf before ordering brackets."
}
```

## Notice

```json
{
  "type": "notice",
  "title": "Oi",
  "text": "DINNER AT 7"
}
```

## Markdown

v0.1 intentionally implements a small e-ink-friendly subset: `#`, `##`, `###`, bullet lines and plain paragraphs.

```json
{
  "type": "markdown",
  "title": "Project Notes",
  "text": "# Athena\n- Mailbox works\n- Add Tasker next"
}
```

## Agenda

```json
{
  "type": "agenda",
  "title": "Monday",
  "events": [
    {"time": "09:30", "title": "Meeting"},
    {"time": "13:00", "title": "Lunch"}
  ]
}
```

## Tasks

```json
{
  "type": "tasks",
  "title": "Today",
  "items": [
    {"title": "Order parts", "done": false},
    {"title": "Charge Mercury", "done": true}
  ]
}
```

## Image

Image scenes point at an asset in the mailbox. Normally clients should use `POST /image` rather than constructing these themselves.

```json
{
  "type": "image",
  "asset": "/assets/athena/example.jpg"
}
```

For v0.1, send a **baseline/non-progressive JPEG prepared at 800×480**. Later versions can add server-side image normalisation/cropping so arbitrary phone images can be sent directly.
