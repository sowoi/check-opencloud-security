# The frontend

Everything the browser sees: four templates, one stylesheet, two small
scripts and three SVGs drawn for this project. No framework, no build step, no
`node_modules`, and nothing loaded from anywhere but `/static`.

The service that renders these is [`webapp/`](../webapp/README.md); the
operator's guide is [`docs/webapp.md`](../docs/webapp.md). Neither this
directory nor `webapp/` is published to PyPI - the wheel is the plugin and the
scanner.

* [Layout](#layout)
* [The rules](#the-rules)
* [Editing the design](#editing-the-design)
* [The template contract](#the-template-contract)
* [The scripts](#the-scripts)
* [Running your own frontend](#running-your-own-frontend)
* [Accessibility](#accessibility)
* [Tests](#tests)
* [Trademarks and affiliation](#trademarks-and-affiliation)

## Layout

```text
frontend/
├── templates/
│   ├── base.html    the shell: header, footer, version badge, legal notice
│   ├── index.html   the landing page, the form and the privacy pitch
│   ├── scan.html    live progress, then the result dashboard
│   └── 404.html     an unknown address or an expired scan
└── static/
    ├── css/app.css  the whole design system, tokens first
    ├── js/app.js    landing page niceties; the form works without it
    ├── js/scan.js   polls the scan until it settles, then reloads once
    ├── js/docs.js   starts Swagger UI, which may not be started inline
    ├── img/         logo.svg, hero.svg, expired.svg
    └── vendor/      Swagger UI and ReDoc, for the optional API docs pages
```

There is no build step. What is in this directory is what the browser gets.

## The rules

These are not style preferences. They are the product: the pitch is that this
service is quiet, and a page that quietly fetched a font would make it a lie.

- **No third-party anything.** No CDN, no font service, no analytics, no
  tracking pixel, no embedded video. Type comes from the reader's own system
  stack.
- **No inline styles or scripts.** The policy is `default-src 'self'` with no
  `unsafe-inline`, so an inline `style=` or `<script>` does not merely fail
  review - it fails in the browser.
- **The form works with JavaScript blocked.** `app.js` is decoration only.
  `scan.js` is load-bearing for live progress, and the page it polls renders
  the same result on a plain reload.
- **Nothing generic.** No stock photography, no icon pack, no boilerplate
  illustration. The SVGs here were drawn for this project and are inline in
  the templates or in `img/`.
- **Nothing that phones home.** `Referrer-Policy: no-referrer`, `noindex`, and
  no analytics of any kind. The scan is nobody's business but the visitor's.

Two things must survive every redesign, because they are what makes a rate
limit read as a nudge rather than a door: the **trademark notice** and the
**"run it yourself" pointer** to the project on GitHub.

## Editing the design

`app.css` opens with the tokens and everything else is built from them:

```css
:root {
    --ink / --ink-soft / --ink-faint     text
    --paper / --card / --line            surfaces
    --brand / --brand-deep / --brand-soft / --accent
    --good / --fair / --bad / --info     ratings and severities (+ *-soft)
    --radius-sm / --radius / --radius-lg
}
```

Change a colour there, not at the call site. The dark theme is a
`prefers-color-scheme: dark` block that redefines the same tokens - it is not
a second stylesheet, and a token added without a dark value will look wrong on
half the machines that visit.

Two media queries carry real obligations:

- `prefers-reduced-motion: reduce` turns off the pulse, the progress
  animation and the badge transitions. Any new animation belongs in that
  block too.
- `prefers-color-scheme: dark`, as above.

Grades and severities have their own colour pairs. Keep a rating's colour tied
to its meaning - a green **F** would be a very expensive joke.

## The template contract

`base.html` receives, on **every** page:

| Variable | What it is |
|:---------|:-----------|
| `version` | The backend version, shown as the footer badge |
| `project_url` | The project on GitHub, for the footer and the rate-limit note |
| `result_ttl_minutes` | How long a result lives, so the page can say so |

`index.html` also receives:

| Variable | What it is |
|:---------|:-----------|
| `waivers` | The allow-listed checks, each with an id, a label and an explanation |
| `tracks` | The release tracks, each with an id, a label, a description and `default` |
| `release_track` | The track to preselect - `production` unless the visitor chose otherwise |
| `target_url` | What was typed, so a rejected submission is not retyped |
| `error` | The message to show in the alert, or `None` |
| `error_self_host` | Whether to add the "run it yourself" paragraph (rate limits) |

`scan.html` receives `scan`: the record as `GET /api/scans/{uuid}` returns it
(`state`, `target`, `releaseTrack`, `expiresIn`, `queue`, and `result` once
there is one) plus `summary`, the same result regrouped for the dashboard.
`404.html` receives nothing but the base variables.

The form sends exactly four fields - `target_url`, `ignore_hardenings`,
`release_track`, `output_format` - and it posts to `/`. Adding an input that
sends anything else earns a **422** from the server, on purpose.

The address field is deliberately `type="text"`, not `type="url"`: a bare
hostname is a complete answer and the server assumes `https://`. Changing it
back would make the browser refuse `opencloud.example.com` before the request
is ever sent.

## The scripts

`app.js` (45 lines) keeps the waiver counter in the summary honest and
disables the button on submit. Delete it and the page still works.

`scan.js` (153 lines) polls `/api/scans/{uuid}` - the uuid comes from
`data-scan-uuid` on `<body>`, which came from the URL the visitor is already
on - every two seconds, backing off to fifteen on errors, and reloads once the
state is terminal. It renders no results: two implementations of the same
report would mean the untested one is the one people read.

Both are plain ES5-era JavaScript in an IIFE, because there is no bundler and
there does not need to be one.

## Running your own frontend

Point `COS_WEB_FRONTEND_DIR` at a copy:

```bash
cp -r frontend /srv/my-frontend
COS_WEB_FRONTEND_DIR=/srv/my-frontend uvicorn webapp.app:app --port 8080
```

In Docker, mount it over the copy in the image and set the variable on the
`web_app` service in [`docker/docker-compose.yml`](../docker/docker-compose.yml).

Keep the directory shape - `templates/` and `static/` - and the template
contract above. The security headers come from the application, so a copied
frontend inherits the same policy: if a change of yours needs an external
origin, it will be blocked, and that is the design working.

## Accessibility

The baseline these pages already meet, and should keep meeting: semantic
landmarks (`header`, `main`, `footer`), a skip link, a real `<label>` for
every control, `aria-describedby` on the fields that carry a hint,
`aria-live="polite"` on the progress region so a state change is announced,
visible focus styles, and `alt=""` on decorative art with meaning carried by
text instead.

## Tests

The frontend is covered from the API tests, because a template is only correct
once it is rendered:

```bash
uv run pytest tests/test_webapp_api.py
uv run pytest tests/test_webapp_worker.py -k renders
```

Among other things they assert that every `script`, `link` and `img` URL
starts with `/static/`, that the trademark notice and the version badge appear
on every page type, that the rate-limit pointer appears when it should, and
that the scan page renders in every state it can be in.

## Trademarks and affiliation

This is an independent community project. It is not affiliated with OpenCloud
GmbH and is neither recommended nor supported by the company. "OpenCloud", the
OpenCloud logo and all associated trademarks are the property of their
respective owners and are used here solely to indicate which software this
tool checks.
