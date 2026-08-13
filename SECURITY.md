# Security policy

This document is about the security of **check-opencloud-security** itself.
For a vulnerability in OpenCloud, please report it to the OpenCloud project
instead - this repository only contains a monitoring plugin.

## Supported versions

Only the latest release receives fixes. There are no maintenance branches for
older versions; if you are behind, upgrade first and check whether the problem
still exists.

| Version | Supported |
|:--------|:----------|
| latest release | yes |
| anything older | no - upgrade |

`check-opencloud-security --upgrade-self` upgrades an installation made with
pipx, uv or pip.

## Reporting a vulnerability

Report privately through GitHub, using **Security → Report a vulnerability** on
[github.com/sowoi/check-opencloud-security](https://github.com/sowoi/check-opencloud-security/security/advisories/new).
Please do not open a public issue and do not describe the problem in a pull
request before it is fixed.

A useful report contains:

- what an attacker gains, and what access they need to start with,
- the version (`check-opencloud-security --version`) and how it was installed,
- the steps to reproduce it, ideally against `tests/fake_opencloud.py` rather
  than a real instance,
- a redacted configuration, if the problem depends on one.

**Never include credentials, tokens, cookies or the hostname of a production
instance in a report.** Use `opencloud.example.com` and placeholder secrets.

## What to expect

- An acknowledgement within **five working days**.
- An assessment - accepted, needs more information, or out of scope - within
  **ten working days**.
- For an accepted report, a fix in the next release, a GitHub Security
  Advisory, and credit under whatever name you would like, unless you prefer
  none.

This is a volunteer-maintained project. There is no bug bounty.

Conduct during a report is covered by the
[Code of Conduct](CODE_OF_CONDUCT.md), which applies to the private advisory
process as much as to anything public.

## Scope

In scope:

- Command or code execution triggered by a scanned instance's responses, a
  release feed, a vulnerability database or a configuration file.
- Secrets leaking into output, logs, perfdata or the webhook payload.
- A scan result that can be forged by the scanned instance so that a
  vulnerable server is reported as healthy.
- Missing certificate verification, or a way to silently disable it.
- Path traversal or privilege escalation in the setup wizard, the self-update
  or the Ansible role.

Out of scope:

- Findings that require the operator to already be able to run code as the
  user the plugin runs as.
- The deliberate escape hatches: `--insecure` (documented as disabling TLS
  verification) and `--ignore-hardening` (documented as suppressing an alert
  while keeping the evidence in the result document).
- Vulnerabilities in OpenCloud itself, or in an instance you scan.
- Denial of service caused by pointing the scanner at an instance you do not
  operate. Scan only instances you are responsible for.
- Reports produced solely by an automated scanner, without a working example.

## Verifying what you downloaded

Every release is built by a GitHub Actions workflow that signs a provenance
statement with a short-lived [Sigstore](https://www.sigstore.dev/) certificate,
so this project holds no signing key that could leak. The statement ties each
artifact to the workflow, the commit and the runner that produced it.

```shell
gh attestation verify check_opencloud_security-<version>-py3-none-any.whl \
  --repo sowoi/check-opencloud-security
```

A CycloneDX SBOM listing every dependency that ended up in the release is
attached to the same GitHub release as
`check-opencloud-security-<version>.cdx.json`, and is itself attested. Feed it
to your own vulnerability scanner rather than trusting this list of
dependencies to stay current.

## How the plugin handles your data

Worth knowing when you assess the risk of running it:

- **Nothing is sent to a third party.** The scanner is built in. The plugin
  talks to the instance you name, and - unless the update check is turned off
  with `--no-update-check` - to the configured release feed to learn the newest
  OpenCloud version.
- A webhook is only ever sent to the URL you configure yourself.
- Secrets can be kept out of the configuration file with the `secret://`,
  `file://` and `env://` prefixes, so that tokens need not be stored in plain
  text.
- `--configure` writes its file with mode `0600`.
- Tokens are redacted from debug output. If you find one that is not, that is
  a vulnerability - please report it.
