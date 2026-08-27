#!/bin/sh
# Generate the secrets docker-compose.authentik.yml needs, once.
#
#   cd docker
#   ./authentik-env.sh
#   docker compose -f docker-compose.authentik.yml up -d
#
# Five values go into `.env` next to this script. Nothing here is clever; it
# exists because the alternative is a page of instructions telling somebody to
# run openssl five times and paste the results into the right places, which is
# how a deployment ends up with a memorable password in it.
#
# Existing values are never overwritten. Run it again after adding a setting
# and it fills in only what is missing, so it is safe on a live deployment.
#
# Back the resulting file up with the database. AUTHENTIK_SECRET_KEY signs
# everything Authentik stores, so a database restored beside a different one
# is an unusable database.
set -eu

env_file="${1:-.env}"
umask 077
[ -f "$env_file" ] || : > "$env_file"

random() {
    # Base64 without the newline, and without the characters that would need
    # quoting in an env file every consumer parses slightly differently.
    openssl rand -base64 "$1" | tr -d '\n=+/' | cut -c "1-$2"
}

have() {
    grep -q "^$1=" "$env_file" 2>/dev/null
}

put() {
    if have "$1"; then
        echo "  $1 already set, left alone"
    else
        printf '%s=%s\n' "$1" "$2" >> "$env_file"
        echo "  $1 written"
    fi
}

command -v openssl > /dev/null || {
    echo "openssl is needed to generate the secrets" >&2
    exit 1
}

echo "Writing secrets to $env_file"

# Redis holds every live scan and every result still inside its TTL. It is on
# an internal network with no published port, but "only our containers are on
# this network" is an assumption rather than a control, so it asks for a
# password as well. Both compose stacks read this name.
put COS_REDIS_PASSWORD "$(random 48 40)"

# Django's SECRET_KEY. Authentik wants at least 50 characters, and changing it
# later invalidates every session and token it has ever signed.
put AUTHENTIK_SECRET_KEY "$(random 72 64)"
put AUTHENTIK_PG_PASS "$(random 48 40)"

# The OAuth2 client the blueprint creates. The ID is not a secret - it is the
# audience, and it is published in every token - but it does have to be the
# same on both sides, which is the whole reason it is generated here rather
# than copied out of the admin interface afterwards.
put AUTHENTIK_CLIENT_ID "opencloud-scanner-$(random 24 20)"
put AUTHENTIK_CLIENT_SECRET "$(random 48 40)"

# The scanner's own erasure credential, unrelated to any of the above: it
# authorises DELETE /api/purge, and with the sign-in on it travels in
# X-Purge-Authorization rather than Authorization.
put COS_WEB_PURGE_TOKEN "$(random 40 32)"

# Mail, which is not a secret to generate but is a setting to fill in, and one
# nobody remembers exists until a password reset silently goes nowhere. The
# placeholders are written commented out, so the file says what to set without
# switching anything on: an empty host leaves Authentik on its built-in local
# delivery, which is right for a stack with one account in it.
if ! grep -q "AUTHENTIK_EMAIL_HOST" "$env_file" 2>/dev/null; then
    cat >> "$env_file" <<'MAIL'

# SMTP for Authentik. Uncomment and fill in to have password recovery and
# invitations actually arrive. Port 587 goes with USE_TLS (STARTTLS), port 465
# with USE_SSL; setting both is how a submission hangs until the timeout.
#AUTHENTIK_EMAIL_HOST=smtp.example.com
#AUTHENTIK_EMAIL_PORT=587
#AUTHENTIK_EMAIL_USERNAME=authentik@example.com
#AUTHENTIK_EMAIL_PASSWORD=
#AUTHENTIK_EMAIL_USE_TLS=true
#AUTHENTIK_EMAIL_USE_SSL=false
#AUTHENTIK_EMAIL_FROM=authentik@example.com
MAIL
    echo "  SMTP placeholders written, commented out"
else
    echo "  SMTP settings already present, left alone"
fi

cat <<'NEXT'

Done. Next:

  docker compose -f docker-compose.authentik.yml up -d
  open http://localhost:9000/if/flow/initial-setup/   (the trailing slash matters)

That sets the first Authentik password. The OAuth2 provider and application
are already there - the blueprint created them - so there is nothing to
configure before an agent can sign in.

docs/authentik.md has the rest: getting a token, pointing an agent at it,
running this on a real hostname, and the backup.
NEXT
