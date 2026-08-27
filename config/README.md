# Configuration examples

`check-opencloud-security.example.yml` is the complete YAML example for the
plugin and scanner. Copy it to a configuration location, remove options that
do not apply, and replace example values with your own settings.

The plugin reads YAML by default and JSON when the configuration file ends in
`.json`. Settings use this precedence:

1. CLI flags
2. `COS_` environment variables
3. Configuration file values
4. Built-in defaults

Nested file keys become flat environment variable names. For example,
`scanner.timeout` corresponds to `COS_SCANNER_TIMEOUT`. Do not store tokens or
other credentials in a committed configuration file. Use `secret://`,
`file://`, `env://`, or a `*_file` setting as documented in the example.

Run `check-opencloud-security --configure` to create an initial configuration
interactively. The full option reference is in
[`README.md`](../README.md#configuration-file-and-secrets).

This project is independent and is not affiliated with, endorsed by, or
supported by OpenCloud GmbH. "OpenCloud" and related marks belong to their
owners and are used only to identify the software being checked.
