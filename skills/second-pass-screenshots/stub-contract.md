# Second-pass screenshot stub contract

Paste this block into a **producer** skill's prompt when the user asked to seed second-pass screenshot stubs. The producer must not take screenshots in this run. A later `second-pass-screenshots` capture pass will open each `url` in Cursor's browser and write the PNG at the relative path in the stub's `image` field.

## Producer obligations

- Emit one stub per page a browser can open. Skip anything that has no URL.
- Write stubs into the document that skill was already going to write (markdown or similar).
- If the skill returns only chat and writes no file, also write `<output-dir>/second-pass-screenshot-stubs.md` beside other outputs.
- Leave every required section of that skill intact. Do not remove or replace mandated content.
- Do not open a browser or capture images in this run.
- Do not put stubs in HTML comments. Cursor plan mode strips HTML comments on save, so a comment stub is gone before the capture pass runs.

## Stub grammar

Each stub is a fenced `text` block. The first line inside the fence is `second-pass-screenshot`. Each following line is one `key: value` field. The `image` value is a path relative to the document file. Use a `second-pass-screenshots/` subdirectory for PNGs unless the document already defines another layout.

Do not add a markdown image under a pending stub. The path lives in `image`. The capture pass writes the PNG there and adds the image line after the fence once the shot exists.

### Fields

| Field | Required | Values |
| --- | --- | --- |
| `id` | Yes | Stable kebab-case identifier unique within the document |
| `url` | Yes | Absolute URL the capture agent should open |
| `capture` | Yes | `viewport`, `fullPage`, or `element` |
| `selector` | When `capture: element` | CSS selector for the element to screenshot |
| `ready` | Yes | Plain-language condition visible on the page before capture |
| `caption` | Yes | Short label for the figure (matches alt text) |
| `status` | Yes | Start as `pending`. Capture sets `captured` or `blocked` |
| `image` | Yes | Relative PNG path, no leading slash |

Optional fields the capture agent may append inside the same fence:

- `captured-file` — relative path written on success
- `blocked-reason` — one line when `status: blocked`
- `capture-note` — one line when a shot was saved but does not match `capture` (for example the page would not scroll, so a viewport PNG was saved for a `fullPage` stub)

Keep the field order in the template. One field per line. Split a line on the first `:`.

### Template

~~~markdown
```text
second-pass-screenshot
id: example-id
url: https://example.com/path
capture: viewport
ready: the main heading is visible
caption: Example screen
status: pending
image: second-pass-screenshots/example-id.png
```
~~~

### `capture` modes

- **viewport** — visible viewport after `ready` is satisfied.
- **fullPage** — full scrollable page (no element screenshot).
- **element** — screenshot of the node matching `selector` after `ready` is satisfied.

### Example with element capture

~~~markdown
```text
second-pass-screenshot
id: run-summary
url: https://github.com/acme/widgets/actions/runs/123456
capture: element
selector: main
ready: the run conclusion badge is visible
caption: Target run summary
status: pending
image: second-pass-screenshots/run-summary.png
```
~~~

## After seeding

The parent agent checks the artifact for a fenced block whose first line is `second-pass-screenshot`. If the user asked for stubs and none appear, resume the same producer subagent once with this contract again.
