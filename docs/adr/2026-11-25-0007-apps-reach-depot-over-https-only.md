# Apps reach depot over HTTPS only

**Status:** accepted

**Context:** Apps carried two URLs: the HTTPS name, and `http://100.97.41.27:8473` for enrolling, which needs a tailnet caller ([2026-11-24-2241-depot-behind-buckwheat-proxy](2026-11-24-2241-depot-behind-buckwheat-proxy.md)). That made every app allow plain HTTP. But buckwheat advertises the name's address, 192.168.0.69, as a Tailscale route, so a device with Tailscale on reaches the proxy over the tailnet and depot sees its tailnet address. The tablet enrolled that way on its first try. The user asked to use HTTPS only.
**Decision:**
- **One URL.** Apps get only `https://depot.wheat.sohambagchi.com` (`lib.depotEnv`'s `DEPOT_URLS`).
- **No plain HTTP.** The client library sets a generated network security config: no plain HTTP, except to the hosts of http:// URLs in `DEPOT_URLS` and to hosts the app lists in `DEPOT_CLEARTEXT_HOSTS` (Blot's approach, moved into the library).
- **The direct address stays** for publishing from malt, and for emulators on malt, whose builds add it to `DEPOT_URLS`.
**Alternatives:**
- **Keeping the direct address as a fallback:** every app allows plain HTTP to it, for a path that is only needed while buckwheat is down.
- **Tailscale's own HTTPS on malt (`tailscale serve`):** another certificate and name to run, and depot would see local connections instead of the caller's address.
**Consequences:**
- **buckwheat is required.** While it's down, apps can't enroll or check, and retry later.
- **The Tailscale route.** buckwheat's `192.168.0.69/32` route must stay advertised and approved, and devices must accept routes (Android's default).
- **Emulators on malt** need a build with the direct address added.
- **Installed apps** keep the URLs they were built with until their next update.
