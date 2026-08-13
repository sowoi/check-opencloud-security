## check-opencloud-security 1.2.3

### Security

- Block webhook notifications to private, loopback, and link-local addresses
  by default to prevent server-side request forgery. Internal receivers require
  the explicit `--allow-private-webhooks` / `COS_ALLOW_PRIVATE_WEBHOOKS` opt-out.
