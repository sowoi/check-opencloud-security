# Images

This directory contains repository images used in project documentation:

| File | Use |
|:--|:--|
| `opencloud-demo-scan-result.png` | Example scan-result documentation image |
| `opencloud-scan-landing.png` | Example landing-page documentation image |
| `architecture-*.png` | Rendered from the `` ```mermaid `` fences in [`ARCHITECTURE.md`](../ARCHITECTURE.md) by [`render-architecture-diagram.yml`](../.github/workflows/render-architecture-diagram.yml). Generated - do not hand-edit; change the Mermaid source instead. |

Images must use `opencloud.example.com` or another reserved example address.
Do not add screenshots containing real instance names, addresses, tokens,
scan UUIDs, credentials, or private results.

The web application does not load these files at runtime. Browser assets live
under `frontend/static/` and must remain self-hosted.

This project is independent and is not affiliated with, endorsed by, or
supported by OpenCloud GmbH. "OpenCloud" and related marks belong to their
owners and are used only to identify the software being checked.
