# Vendored assets

Third-party files, kept here because this frontend loads **nothing** from a
CDN. They are used by the optional API documentation pages only
(`COS_WEB_ENABLE_DOCS=true`), which is why the rest of the application still
works with this directory removed.

| File | Version | Project | Licence |
|:-----|:--------|:--------|:--------|
| `swagger-ui-bundle.js`, `swagger-ui.css` | 5.32.13 | [swagger-ui-dist](https://github.com/swagger-api/swagger-ui) | Apache-2.0 |
| `redoc.standalone.js` | 2.5.3 | [ReDoc](https://github.com/Redocly/redoc) | MIT |

To refresh one, download the same file from the same package at the version
you want, update the table, and check that `/docs` and `/redoc` still render
with the strict policy in `webapp/app.py` - both pages need inline styles and,
for ReDoc, a blob worker, and nothing else.

```bash
curl -sSLo swagger-ui-bundle.js https://cdn.jsdelivr.net/npm/swagger-ui-dist@5.32.13/swagger-ui-bundle.js
```

Nothing here is edited by hand.
