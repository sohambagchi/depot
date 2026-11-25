# The download page serves anyone on the home network

**Status:** accepted

**Context:** A new device needs its first copy of an app before it can enroll. The user wanted a download page at `https://depot.wheat.sohambagchi.com`, which resolves to buckwheat's LAN address. Through that proxy, depot sees every device as a plain LAN address and can't use Tailscale to tell the user's devices from a guest's.
**Decision:**
- **Who may download.** `GET /` (a static page), `GET /v1/catalog` and APK downloads answer any caller on a private (home LAN) or tailnet address, with no enrollment or token. Public addresses are refused.
- **Updates are unchanged.** They still need an enrolled app's token for `latest`; the page doesn't bypass enrollment.
**Alternatives:**
- **Tailnet only (whois on each request):** consistent with enrollment, but it only works at that name once its DNS record points to buckwheat's Tailscale address. The user chose LAN access.
- **No page (`adb install` for first installs):** the status quo.
**Consequences:**
- **Guests on the Wi-Fi.** They can download every published APK, so apps must not embed secrets or homelab details. The user is removing those from airlock-mobile.
- **Tampering.** Downloads still can't be tampered with: the hash is on the page, and later updates are checked against the pinned signer.
- **Exposure.** If the proxy were ever exposed to the internet, the public-address check refuses those callers.
