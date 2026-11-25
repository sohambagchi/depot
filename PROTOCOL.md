# depot protocol, version 1

How an app built with android-emu finds and installs its own updates from `depot`, a server on
the homelab. Device identity is airlock's phone scheme
(`airlock/docs/adr/2026-11-23-2230-phone-enrolls-over-tailnet.md`), generalised so other
services can reuse it.

All bodies are JSON (UTF-8) unless stated. depot serves plain HTTP on malt's tailnet address,
reached two ways:

- **Through the proxy.** `https://depot.wheat.sohambagchi.com` is a Caddy proxy on buckwheat,
  reached from the home LAN. TLS ends at Caddy.
- **Directly.** `http://100.97.41.27:8473` over the tailnet, which WireGuard encrypts.

When the caller is depot's trusted proxy, depot takes the caller's address from the last
`X-Forwarded-For` entry (the one the proxy added); from anyone else, it ignores that header.
"A tailnet address" below means that address.

## Device identity

| Piece | Value |
| --- | --- |
| Key | P-256 key pair, generated in the Android Keystore; the private key never leaves it |
| Public key on the wire | base64 of DER SubjectPublicKeyInfo |
| Device id | `d-` + first 16 hex digits of SHA-256 of that DER; the same key always gives the same id |
| Signed message | `<context>\n<nonce>\n<device id>`, ECDSA with SHA-256, signature as base64 DER |
| Context | `depot/1` for depot; another service picks its own (airlock's phone socket uses `airlock-mobile/1`), so a signature for one is useless to another |

### Enrolling

`POST /v1/enroll` `{"name": "Pixel 7a / app.blot", "key": "<base64 DER>"}` → `{"device": "d-…"}`

- Accepted only from a tailnet address (100.64.0.0/10, fd7a:115c:a1e0::/48), otherwise **403**.
  Through the proxy the caller is a LAN address, so a client enrolls at the direct address.
- The server asks `tailscale whois` who the caller is. The login must be allowed (by default,
  the server's own login) and, if the server has a node list, the node must be on it,
  otherwise **403**. If whois can't be asked, **503**.
- Enrolling the same key again is harmless and keeps the original `enrolled_at`.
- Each app enrolls its own key: keystore keys belong to one app.
- Revoking a device means deleting its entry from the server's `devices.json`. Its tokens stop
  working on their next request.

### Getting a token

1. `GET /v1/challenge` → `{"nonce": "<base64 of 32 random bytes>", "expires_in": 60}`
2. `POST /v1/session` `{"device": "d-…", "nonce": "…", "sig": "<base64>"}` →
   `{"token": "…", "expires_in": 600}`

- A nonce is accepted once, within `expires_in` seconds. Unknown device **401**; bad, reused or
  expired nonce, or bad signature **403**.
- Requests for apps carry `Authorization: Bearer <token>`. A missing, expired or revoked token is
  **401**, and the client gets a fresh one.
- Both steps work through the proxy and directly.

## Updates

`GET /v1/apps/<app id>/latest` (bearer) → **404** if nothing is published, else:

```json
{"app": "app.blot", "code": 212, "name": "0.16.0", "size": 8123456,
 "sha256": "<hex of the APK>", "signer": "<hex SHA-256 of the signing certificate>",
 "notes": "[0.16.0] Start …", "published_at": 1764000000000,
 "url": "/v1/apps/app.blot/212.apk"}
```

`GET /v1/apps/<app id>/<code>.apk` → the APK (`application/vnd.android.package-archive`, with a
`Content-Disposition` file name). It needs a bearer token, unless the caller is on the home LAN
(a private address) or the tailnet, for the download page.

The client offers the update only when all of these hold:

- `code` is greater than the installed `versionCode`
- `signer` equals the installed app's signing certificate digest
- the downloaded file's size and SHA-256 match
- the APK's own package name, version code and signer match

Android's installer checks the signer and version code again: it refuses an update signed with a different
key or carrying a lower version code. The client checks first so that a forged answer on the LAN
never reaches the install prompt.

## Publishing

`POST /v1/publish` as `multipart/form-data` with two parts: `meta` (JSON:
`app`, `code`, `name`, `signer`, `notes`) and `apk` (the file). It answers with the release, as
in `latest`.

- Accepted only from a tailnet address whose whois login is allowed. There is no device key.
- **409** if `code` is not greater than the latest published code, or if `signer` differs from
  the app's first release (the signer is pinned). The server computes `size` and `sha256` itself.
- `emu-publish` reads `meta` from the APK (`aapt2`, `apksigner`) and sends it.
- Old releases may be pruned; malt keeps each app's three newest. The signer pin and the
  rising-code rule still count the releases that are kept.

`GET /v1/status` (tailnet, allowed login) → published apps and enrolled devices, for debugging.

## Download page

`GET /` is a static page that lists every app's latest release for a first install from a
browser. It reads:

- **`GET /v1/catalog`** → `{"apps": [release + "label", …]}`. It answers callers on the home LAN
  or the tailnet, and gives **403** to anything else.
- **`GET /v1/health`** → `{"service": "depot", "protocol": 1, …}`, with no auth.

Anyone on the home Wi-Fi can list and download releases this way. Updates still go through
`latest`, which needs an enrolled app's token. `emu-publish` sends the app's label (aapt2's
`application: label`) with each release.

## Version codes

Every publish needs a larger `versionCode`. android-emu apps take it from
`git rev-list --count HEAD` and take `versionName` from the latest `[X.Y.Z]` commit subject
(see [README.md](README.md#app-side)). `[X.Y.Z]` itself isn't monotonic across branches, so it
can't be the code.
