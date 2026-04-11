# nginx reverse-proxy config

Reference copies of the nginx site configs that run in front of OpenClawApi
in production. **These files are not automatically deployed** — they are
hand-maintained as a record of the live config so changes are reviewable and
reproducible.

## Files

- **`openclaw.marketsverse.com.conf`** — production site for
  `openclaw.marketsverse.com`. Proxies `/api/*` to the FastAPI uvicorn
  process on `127.0.0.1:8000` and everything else to the openclaw gateway
  Node process on `127.0.0.1:18789`. Includes explicit WebSocket upgrade
  blocks for all `/api/*/ws` endpoints and for `/api/voice/stream/{call_id}`.

## Why per-path WebSocket blocks?

The default `/api/` block intentionally omits `proxy_http_version 1.1` and
the `Upgrade` / `Connection` headers, because enabling those globally would
interfere with the Server-Sent Events streaming used by the chat completions
endpoint. Instead, every WebSocket endpoint under `/api/*` gets its own
`location` block with the upgrade headers turned on. nginx matches the most
specific `location` first, so those blocks take precedence for their exact
paths.

If you add a new WebSocket endpoint to the FastAPI app, you **must** add a
matching `location` block here AND deploy the change to the production
nginx config, otherwise the endpoint will return 404 because nginx will
forward the request as HTTP/1.0 with no `Upgrade` header and uvicorn will
not match the websocket route.

## Deploying changes

1. Edit the file in this repo and commit.
2. SSH to the production host.
3. Copy the updated file to `/etc/nginx/sites-enabled/openclaw.marketsverse.com`
   (or equivalent — check with `ls /etc/nginx/sites-enabled/` first).
4. `sudo nginx -t` to validate syntax.
5. `sudo systemctl reload nginx` to pick up the change.

Certbot-managed sections (`# managed by Certbot`) should not be edited by
hand — they are rewritten on certificate renewal.
