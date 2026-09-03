# Secrets in the configuration

No credential this plugin uses - a GitHub token, a webhook URL, a service
token - has to be written into the configuration file or the process
environment. Any value may instead be a reference that is resolved when it is
needed.

The file itself, where it is looked for and how its keys map onto environment
variables, is in
[Configuration file and secrets](../README.md#configuration-file-and-secrets);
`config/check-opencloud-security.example.yml` is a fully commented example.

<!-- TOC -->
* [Secrets in the configuration](#secrets-in-the-configuration)
  * [Reference forms](#reference-forms)
  * [Outside a container](#outside-a-container)
<!-- TOC -->


## Reference forms

Four prefixes are understood, wherever a value is expected:

| Reference              | Resolves to                                                                      |
|:-----------------------|:---------------------------------------------------------------------------------|
| `secret://name`        | `<secrets.dir>/name`, i.e. `/run/secrets/name` for Docker and Kubernetes secrets |
| `file:///path/to/file` | The contents of that file                                                        |
| `env://VARIABLE`       | The value of that environment variable                                           |
| `exec://command --arg` | The stdout of that command (requires `secrets.allow_exec: true`)                 |

Alternatively append `_file` to any key or variable:
`COS_RELEASES_TOKEN_FILE=/run/secrets/token` or `token_file: /run/secrets/token`.
Trailing newlines are stripped, so `echo secret > file` works as expected.

## Outside a container

`secret://name` looks below `secrets.dir` (`COS_SECRETS_DIR`), which defaults to
`/run/secrets` - exactly where Docker and Kubernetes mount their secrets.
Outside a container, point it at your own directory:

```shell
mkdir -p /etc/check-opencloud-security/secrets
printf '%s' '<github-token>' > /etc/check-opencloud-security/secrets/releases_token
chmod 600 /etc/check-opencloud-security/secrets/*

export COS_SECRETS_DIR=/etc/check-opencloud-security/secrets
check-opencloud-security --host opencloud.example.com \
  --release-token 'secret://releases_token'
```

The repository ships templates for both files in
[`secrets/`](../secrets/README.md); copy them and replace the placeholder values.
