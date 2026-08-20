# ADR 0009: The public pages are indexable, a result never is

- Status: Accepted
- Date: 2026-08-20

## Context

Every page the web application served carried `noindex, nofollow`. That was
right for a result page and wrong for everything else: the landing page and
the four explanations are public documentation about a free, independent
check, and somebody looking for a way to test an OpenCloud instance could not
find them.

Relaxing that is not a cosmetic change. The same service renders a page whose
whole authorisation is a uuid in its URL, and a crawler that indexed one
would publish somebody else's security report. Any answer here has to
separate the two kinds of page by construction rather than by remembering to
add a tag.

## Decision

`webapp/seo.py` holds one list of public paths - `/`, `/how-it-works`,
`/api`, `/privacy` and `/about` - and everything else is derived from it:

- a page in that list renders `index, follow`, a canonical URL and OpenGraph
  metadata; every other page renders `noindex, nofollow` and **no** canonical
  URL, since a canonical address for a page nobody may index only invites one
  to be created;
- anything not in that list also gets an `X-Robots-Tag: noindex, nofollow`
  response header, which covers the exports, the JSON API and everything else
  that renders no template;
- `GET /sitemap.xml` is generated from the same list, with each `lastmod`
  taken from the mtime of the template that renders the page, and `GET
  /robots.txt` from the list of paths a crawler has no business in;
- `COS_WEB_PUBLIC_BASE_URL` supplies the origin for those absolute URLs,
  because behind a proxy the service only ever sees its own internal address;
- `COS_WEB_ALLOW_INDEXING=false` restores the previous behaviour completely:
  a flat `robots.txt`, a 404 for the sitemap, and `noindex` everywhere.

There is no sitemap file in the repository and no listing endpoint behind any
of it. The sitemap is rendered from the routes that exist.

## Consequences

The five pages can be found, which is the point. The result pages cannot,
which is the constraint, and it now holds in two independent channels rather
than in a template a future page might forget to extend.

A new public page means adding it to `PUBLIC_PAGES` - one place - and it
appears in the sitemap with a `lastmod` that maintains itself. A new page that
shows anything about a scan is safe by omission: not being on the list is
what makes it `noindex`.

A deployment behind a proxy that does not set `COS_WEB_PUBLIC_BASE_URL`
publishes the address it sees. That is a misconfiguration with a visible
symptom rather than a silent leak, and the setting is documented next to the
proxy guidance.

## Alternatives considered

**Keep `noindex` everywhere.** Safe, and what was there before. It also means
the only way to hear about this service is to be told about it, which for a
free check with no accounts is a strange thing to insist on. Kept as
`COS_WEB_ALLOW_INDEXING=false` for deployments that do want it.

**A static `sitemap.xml` in `frontend/static/`.** Simplest to serve and the
first thing to go stale. A sitemap that disagrees with the routes teaches a
crawler to distrust the file it reads first, and it would carry a hand-written
`lastmod` that is wrong within a release.

**Marking result pages `noindex` and leaving the rest to default.** An
allow-list fails closed and a deny-list fails open. The deny-list version
would have made every future page indexable until somebody noticed.
