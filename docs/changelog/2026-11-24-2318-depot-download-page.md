# depot has a download page for first installs

- **The page.** `https://depot.wheat.sohambagchi.com/` lists each app's latest release (label, version, size, date, notes, sha256) with a Download button. It is a static page (`depot/server/index.html`) that reads `GET /v1/catalog`, sized for phones, in light and dark.
- **Tested.** On an API 35 emulator through the live proxy, Chrome downloaded the test app and Android installed it. The app enrolled on first run, and a later update installed from the tap with no dialog, even though the system package installer was its installer of record.
- **Downloads.** APK downloads answer LAN and tailnet callers without a token, under a `<app>-<version>.apk` file name. `latest` still needs an enrolled app's token. The health check moved from `/` to `/v1/health`.
- **Labels.** `emu-publish` sends the app's label, and the catalog shows it.
- **The settings snippet.** `depot/README.md`'s `settings.gradle.kts` snippet now copies the client from the read-only Nix store into `build/depot-client`, since Gradle 9 refuses a read-only project directory. The [blot] session found this. The client's build file no longer redirects its outputs.
- **Tests.** `checks.depot` covers the page, the catalog (LAN and tailnet allowed, internet refused), token-less LAN downloads, and `latest` still needing a token.
- Rationale: see ADR [2026-11-24-2318-download-page-open-to-home-network](../adr/2026-11-24-2318-download-page-open-to-home-network.md)
