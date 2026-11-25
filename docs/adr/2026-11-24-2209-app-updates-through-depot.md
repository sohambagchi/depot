# Apps update themselves from depot, a server on malt

**Status:** accepted

**Context:** airlock-mobile and Blot are sideloaded, and every new build meant `adb install` on each device. The user wanted one update mechanism that every android-emu app picks up, reusing airlock's tailnet/LAN device authentication.
**Decision:**
- **Server.** depot runs on malt, reached through buckwheat's HTTPS proxy or directly over the tailnet (see [2026-11-24-2241-depot-behind-buckwheat-proxy](2026-11-24-2241-depot-behind-buckwheat-proxy.md)). Each app includes a client library from this repo, `depot/client`.
- **Device identity.** airlock-mobile's scheme, generalised in [PROTOCOL.md](../../PROTOCOL.md): a Keystore P-256 key, enrolled over the tailnet after `tailscale whois` checks the node, then a signed nonce for each session, through the proxy or directly. Each service uses its own context string.
- **Updating.** The app downloads and verifies a newer build, then notifies; a tap installs it through a PackageInstaller self-update, with no system dialog (`UPDATE_PACKAGES_WITHOUT_USER_ACTION`).
- **Publishing.** `emu-publish` publishes from a clean tree over the tailnet. The server pins each app's first signer and rejects version codes that don't rise.
- **The client.** It is plain Java with no dependencies, compiled against whatever platform the app's SDK holds, and included only when the dev shell sets `DEPOT_CLIENT`.
**Alternatives:**
- **One updater app per device:** one enrollment and no code in the apps, but the user chose per-app self-updates.
- **Silent install when idle, or at once:** an install kills the app's process, for example mid-note. The user chose notify-then-tap.
- **A private F-Droid repo:** no tie-in to the tailnet identity, and another app on every device.
- **A Kotlin or AndroidX client:** blot (AGP 9, built-in Kotlin, SDK 37.2) and airlock-mobile (AGP 8, Kotlin plugin, SDK 35) can't share one Kotlin module or dependency set.
- **depot serving TLS itself, or a shared token:** TLS now ends at buckwheat's proxy; a token replays, for the same reasons as airlock's phone listener.
**Consequences:**
- **Release discipline.** Every app needs a fixed signing key outside the repo, and must take its `versionCode` from `git rev-list --count HEAD`.
- **What apps carry.** Apps with the library allow cleartext HTTP, hold the install permissions, and must request `POST_NOTIFICATIONS` for the notification.
- **Reach.** Enrolling needs Tailscale on the device.
- **Coupling.** The client's source is pinned through each app's `android-emu` flake input, so client changes reach an app when it updates that input.
