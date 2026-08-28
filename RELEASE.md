## check-opencloud-security 1.13.0

### Added

- **TLS cipher and certificate-policy findings**: The built-in scanner now
  flags a weak negotiated cipher suite and certificates with undersized RSA or
  EC keys or MD5/SHA-1 signatures. It records the measured key type, size and
  signature in the result while leaving either check absent when it cannot
  measure the necessary evidence.
- **Automatic updates in the Docker setup wizard**: `docker/setup-wizard.py`
  now asks whether the deployment's pulled images should update themselves
  (or takes `--auto-updates`) and adds a Watchtower service to the generated
  stack when they should - scoped by label to this stack's own containers,
  and pointed at the Docker socket detected for the user running the wizard,
  including the rootless socket under `/run/user/<uid>`.
- **The Docker setup wizard reuses an existing `.env`**: re-running it
  against a directory that already holds one reads the file back and offers
  every value as the default of its question instead of regenerating the
  deployment's credentials.
