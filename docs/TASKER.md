# Send to Athena with Tasker

AthenaOS v0.3 adds a single universal mailbox endpoint:

```text
POST /share
```

It is designed for Tasker's built-in **Received Share** event and **HTTP Request** action. No AutoShare plugin is required.

The Worker accepts:

- shared text -> `text` scene
- `.txt` -> `text` scene
- `.md` / `.markdown` -> `markdown` scene
- `.jpg` / `.jpeg` -> `image` scene
- JSON -> any normal Athena scene

Tasker 6.5+ exposes Received Share data through variables including:

```text
%rs_text
%rs_files()
%rs_mime_type
%rs_title
%rs_subject
%rs_share_trigger
```

## 1. Store the mailbox settings in Tasker

Create these Tasker global variables once:

```text
%AthenaUrl   = https://athena-mailbox.example.workers.dev
%AthenaToken = your shared ATHENA_TOKEN
```

Use the real Worker URL and the same token used by Athena. Because these contain capital letters Tasker treats them as global variables.

Do not export/share a Tasker project publicly with the real token still stored in it.

## 2. Create the share target

Create a profile:

```text
Event -> Received Share
Share Trigger -> Send to Athena
```

The share trigger can appear directly in Android's share sheet when Tasker's Direct Share Targets option is enabled.

Attach a task named something like:

```text
Athena - Receive Share
```

## 3. Choose a title

At the top of the task, create local variable `%athena_title`.

Use the first available value from:

```text
%rs_title
%rs_subject
Shared to Athena
```

A simple Tasker version is:

```text
Variable Set %athena_title = %rs_title

If %athena_title !Set
    Variable Set %athena_title = %rs_subject
End If

If %athena_title !Set
    Variable Set %athena_title = Shared to Athena
End If
```

## 4. Branch between file and text shares

Use:

```text
If %rs_files(#) > 0
```

### File branch

Add **Net -> HTTP Request**:

```text
Method:
POST

URL:
%AthenaUrl/share

Headers:
Authorization:Bearer %AthenaToken

Query Parameters:
device:athena

Body:
title=%athena_title

File To Send:
file:%rs_files(1)

Timeout:
60
```

Important: keep the `file:` prefix. With a named file plus Body, Tasker generates the multipart request that `/share` is designed to parse.

Do **not** manually add a `Content-Type` header to this branch; Tasker needs to generate the multipart boundary itself.

The Worker uses the uploaded filename/MIME type to decide whether it is text, Markdown or JPEG.

### Text branch

In the `Else` branch add another **HTTP Request**:

```text
Method:
POST

URL:
%AthenaUrl/share

Headers:
Authorization:Bearer %AthenaToken
Content-Type:text/plain; charset=utf-8

Query Parameters:
device:athena
title:%athena_title

Body:
%rs_text

Timeout:
30
```

Then close the Tasker `If` block.

The current HTTP Request result is available through `%http_response_code` and `%http_data`, so an optional final Flash action can show success/failure.

## 5. Using it

From Android:

```text
select text -> Share -> Send to Athena
```

or:

```text
share .txt/.md/JPEG -> Send to Athena
```

The share updates the mailbox immediately. Athena will display it on the next hourly RTC wake, or you can wake the frame manually with any non-page-turn button to force an immediate mailbox check.

Athena's local document controls remain:

```text
A -> previous cached page
B -> next cached page
```

A/B deliberately do not check Wi-Fi first because page turning should remain fully local.

## Optional dedicated share targets

The `/share` endpoint also accepts these query/form hints:

```text
type:text|notice|markdown
orientation:auto|portrait|landscape
density:comfortable|compact|max
title:Anything
```

That means later you can duplicate the Received Share profile and create dedicated Android targets such as:

```text
Send to Athena
Athena Notice
Athena Markdown
```

For an `Athena Notice` target, add this Query Parameter to the text HTTP Request:

```text
type:notice
```

For forced Markdown:

```text
type:markdown
```

## Clear Athena task

A separate Tasker task can clear the display mailbox without needing a share event:

```text
Method:
POST

URL:
%AthenaUrl/clear

Headers:
Authorization:Bearer %AthenaToken

Query Parameters:
device:athena
```

## JPEG limitation in v0.3

Athena's Pico-side JPEG renderer still expects a display-ready **baseline/non-progressive 800x480 JPEG**.

The v0.3 `/share` endpoint makes transporting a JPEG from Android easy, but it does not yet resize/crop arbitrary phone photos. Tasker has built-in Load Image / Resize Image / Crop Image / Save Image actions, so phone-side preprocessing can be added without changing the mailbox protocol. A later AthenaOS pass can package that into the share task cleanly.
