# ADR 0008: A process asked to encrypt refuses to start without the key

- Status: Accepted
- Date: 2026-08-19

## Context

`COS_WEB_ENCRYPT_RESULTS` promises that the result document - the one piece of
stored state that describes somebody else's instance in detail - is encrypted
in Redis with AES-256-GCM. The encryption itself is decided by one argument:
`ScanStore` encrypts when it is constructed with an `encryption_config`, and
writes cleartext when it is not.

That argument was passed in the web process and forgotten in the ARQ worker,
which is the process that actually writes the result. The setting was on, the
documentation said the data was encrypted, `/healthz` was green, and every
result sat in Redis in the clear. Nothing failed, because nothing was checked:
the store has to keep working without keys for the deployments that never
asked for encryption, so an absent configuration is indistinguishable from a
deliberate one.

The same shape appears once more. A key is read from
`COS_WEB_ENCRYPTION_KEY_<version>`; if it is missing, truncated or not
hexadecimal, the failure surfaces at the first write, in a worker, inside a
job whose error the visitor sees as a failed scan.

## Decision

**A process that is asked to encrypt and cannot must refuse to start.**
`ensure_encryption_ready(config)` is called by `create_app()` and by the
worker's `startup()`, before either builds a store. It raises when
`encrypt_results` is set and there is no key, or a key is not 64 hexadecimal
characters, or it does not decode to 32 bytes.

**The worker builds its store the same way the web process does**, with the
encryption configuration when the setting is on. The two processes read and
write the same keys, so a difference between them is not a variation in
policy - it is a bug that only shows up as plaintext.

**A deployment that never enabled encryption is untouched.** The check does
nothing when `encrypt_results` is false, which is the default, so this is a
promise the operator opted into being held to.

## Consequences

A misconfigured deployment fails loudly at boot rather than quietly at rest,
which is the only place the mistake is cheap: a container that will not start
is noticed, a Redis full of cleartext is not.

The cost is that a bad key now stops a service that would previously have run.
That is the intended trade: the alternative is a service that runs while
telling its operator something untrue about the data it holds.

The regression is pinned by `tests/test_webapp_encryption.py`, which asserts
the negative case as well as the positive one - a store built without the
configuration *does* write readable JSON, so a test that passes only because
the feature works cannot be mistaken for one that would keep passing if it
were removed.
