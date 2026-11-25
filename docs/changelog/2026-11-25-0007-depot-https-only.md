# Apps reach depot over HTTPS only, and allow no plain HTTP

- **One URL.** `lib.depotEnv` gives apps only `https://depot.wheat.sohambagchi.com`; enrolling works through it for devices with Tailscale on.
- **Network security config.** The client library generates one that refuses plain HTTP, except to http:// hosts in `DEPOT_URLS` and to hosts in `DEPOT_CLEARTEXT_HOSTS` (or `-Pdepot.cleartextHosts`). It replaces the library's `usesCleartextTraffic="true"`.
- **Checked.** Built under AGP 8 and AGP 9 (with the configuration cache). The APKs' manifests point at the generated config, and it lists the expected hosts: none for the HTTPS-only URL, the direct address when `DEPOT_URLS` includes it, and an app's extra host.
- **Docs.** depot/README.md and PROTOCOL.md describe the HTTPS-only route, the emulator exception and `DEPOT_CLEARTEXT_HOSTS`.
- Rationale: see ADR [2026-11-25-0007-apps-reach-depot-over-https-only](../adr/2026-11-25-0007-apps-reach-depot-over-https-only.md)
