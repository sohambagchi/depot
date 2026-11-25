# depot: apps update themselves from malt

- **depot is live.** It serves `https://depot.wheat.sohambagchi.com` (Caddy on buckwheat) and `http://100.97.41.27:8473`. It runs on malt as the user service `depot.service`.
- **Tested.** An API 35 emulator against the live setup: it enrolled directly over the tailnet (the proxy refused it as a LAN client), checked and downloaded through the HTTPS proxy, and installed v2 from the tap with no dialog. An earlier run against a test server on API 31 and 35 emulators covered the same steps:
  - **Enroll.** Enrollment worked over the tailnet.
  - **Download and notify.** It downloaded and verified each published build and showed "<App> <version> is ready".
  - **Install.** A tap installed it with no system dialog.
- **Protocol.** [depot/PROTOCOL.md](../../depot/PROTOCOL.md) covers device identity (airlock's enroll-then-sign scheme, generalised), the update and publish endpoints, and the version-code rule.
- **Server.** `depot/server/depot.py` is an aiohttp server. It is `packages.depot` and `nixosModules.depot`, and its HTTP test is `checks.depot` (enrollment rules, nonce replay, contexts, pinned signer, rising version codes, revocation, and X-Forwarded-For only from the trusted proxy).
- **Client.** `depot/client` is a dependency-free Java library. It has:
  - a start-up provider, a 6-hourly JobScheduler check, download and verification, and the notification
  - `InstallActivity`, which installs through a PackageInstaller session
  - builds under AGP 8.10 / SDK 35 and AGP 9.5 / SDK 37.2
- **`emu-publish`** (in `lib.mkEmu`) reads the APK's id, version and signer, refuses dirty trees, and uploads.
- **`lib.depotEnv`** gives app dev shells `DEPOT_CLIENT`, `DEPOT_URLS` and `DEPOT_PUBLISH_URL`.
- How to integrate an app and run the server: [depot/README.md](../../depot/README.md).
- Rationale: see ADRs [2026-11-24-2209-app-updates-through-depot](../adr/2026-11-24-2209-app-updates-through-depot.md) and [2026-11-24-2241-depot-behind-buckwheat-proxy](../adr/2026-11-24-2241-depot-behind-buckwheat-proxy.md)
