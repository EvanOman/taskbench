# Caddy reverse proxy

Caddy sits in front of Planka on Railway. Its only job is injecting the
security headers Planka doesn't ship with, plus extra hardening for the
attachment download path.

## Architecture

```
[Internet]
    │ HTTPS
    ▼
[Railway edge — terminates TLS]
    │ HTTP, x-forwarded-* headers
    ▼
[caddy service — public, port 80]
    │ HTTP via Railway private DNS
    ▼
[planka service — internal-only, port 1337]
    │ DATABASE_URL via Railway private DNS
    ▼
[postgres service — internal-only, port 5432]
```

Planka's public domain has been removed; only Caddy is publicly addressable.
Planka still listens internally for Caddy on `planka.railway.internal:1337`.

## What this closes from the security audit

| Audit finding                       | Severity | Closed |
|-------------------------------------|----------|--------|
| Missing HSTS                        | Medium   | ✓ |
| Missing Content-Security-Policy     | Medium   | ✓ |
| Missing X-Frame-Options             | Medium   | ✓ |
| Missing X-Content-Type-Options      | Low      | ✓ |
| Missing Referrer-Policy             | Low      | ✓ |
| Missing Permissions-Policy          | Low      | ✓ |
| Missing Cross-Origin-* headers      | Low      | ✓ |
| File-upload XSS hardening           | Medium   | ✓ (sandbox + nosniff on /attachments/*) |
| `x-exit` header info leak           | Info     | ✓ (stripped) |
| `Server` header info leak           | Info     | ✓ (stripped) |
| `X-Powered-By` (if ever set)        | Info     | ✓ (stripped) |

What this does NOT close (still requires upstream Planka work):

- No login rate limiting (needs Caddy plugin or upstream middleware)
- 365-day JWT lifetime
- No 2FA
- JSON duplicate-key auth bypass
- Stored XSS via card description API (server-side sanitization missing)
- WebSocket maxPayload of 95 MB

## Caddyfile

The full config is in `Caddyfile`. It's loaded into the Caddy service via the
`CADDYFILE_CONTENT` env var at container start (see startCommand below). The
file is the source of truth — Railway env var is just the transport.

## Deploying

The Caddy service runs `caddy:2-alpine` with a `startCommand` that materializes
`$CADDYFILE_CONTENT` to `/etc/caddy/Caddyfile` and starts Caddy:

```sh
sh -c 'echo "$CADDYFILE_CONTENT" > /etc/caddy/Caddyfile && caddy run --config /etc/caddy/Caddyfile --adapter caddyfile'
```

To redeploy after editing `Caddyfile`:

```bash
source .secrets/railway-deploy.env
TOKEN="$RAILWAY_API_TOKEN"
CADDY_SVC=<from .secrets/railway-deploy.env>

# Push updated Caddyfile content into the env var
curl -sS -X POST https://backboard.railway.com/graphql/v2 \
  -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
  -d "$(jq -nc \
        --arg pid "$PROJECT_ID" --arg eid "$ENV_ID" --arg sid "$CADDY_SVC" \
        --rawfile content deploy/railway/caddy/Caddyfile \
        '{
          query: "mutation($input: VariableUpsertInput!) { variableUpsert(input: $input) }",
          variables: { input: { projectId: $pid, environmentId: $eid, serviceId: $sid, name: "CADDYFILE_CONTENT", value: $content } }
        }')"

# Trigger redeploy
curl -sS -X POST https://backboard.railway.com/graphql/v2 \
  -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
  -d "{\"query\":\"mutation { serviceInstanceRedeploy(environmentId: \\\"$ENV_ID\\\", serviceId: \\\"$CADDY_SVC\\\") }\"}"
```

## Verifying headers post-deploy

```bash
curl -sI https://<caddy-domain>/ | grep -iE 'strict-transport|content-security|x-frame|x-content-type|referrer|permissions|cross-origin'
```

All should return values; none should be absent.
