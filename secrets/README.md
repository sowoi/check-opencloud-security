# Secrets

`docker/docker-compose.monitoring.yml` mounts the files in this directory as Docker secrets at
`/run/secrets/<name>` inside the containers. The `.example` files are templates:
copy them, put the real value in, and never commit the result - everything in
this directory except `*.example` and this README is git-ignored.

```shell
# Token that protects the scanner service. Any random string will do.
openssl rand -hex 32 > secrets/scanner_token

# GitHub token for the release feed. A fine-grained token without any
# permission is enough - it is only used to raise the anonymous rate limit.
printf '%s' '<token>' > secrets/releases_token

chmod 600 secrets/scanner_token secrets/releases_token
```

| File | Used by | Purpose |
|:-----|:--------|:--------|
| `scanner_token` | `scanner` (`COS_SERVICE_TOKEN`) | Shared token for the scan service. Requests without it are rejected. |
| `releases_token` | `scanner` and `check` (`COS_RELEASES_TOKEN`) | Raises the GitHub rate limit for the update check against the OpenCloud release feed. |

Neither secret is required. Without `scanner_token` the scan service accepts
every request, so only run it that way on a trusted network. Without
`releases_token` the update check still works, but sixty anonymous GitHub
requests per hour and IP address are shared with everything else on that
address - with `releases.mode: auto` a rate-limited lookup silently falls back
to the release schedule bundled with the package.

Trailing newlines are stripped when a secret is read, so `openssl rand -hex 32 >
file` and `echo secret > file` both work.

Outside of Docker the same files can be referenced with `secret://scanner_token`
(resolved below `COS_SECRETS_DIR`, `/run/secrets` by default), with
`file:///path/to/file`, or with the `_FILE` environment variable convention
(`COS_RELEASES_TOKEN_FILE=/etc/check-opencloud-security/releases_token`).
