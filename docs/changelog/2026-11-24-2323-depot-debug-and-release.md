# depot carries debug and release builds as separate apps

- **`emu-publish`** reads the APK's build type (debug when debuggable) and sends it as `build`; depot requires it.
- **Pinning.** depot pins each application id to the build type of its first publish, as it does the signer. A mismatched publish gets a 409 that points at `applicationIdSuffix = ".debug"`. `/v1/status` and the catalog report each app's build type.
- **The page.** The download page lists release apps first and debug builds in a "Debug builds" section, each tagged.
- **Tested.** Release and debug builds of a test app, published to the live server, showed up in those sections.
- **Tests.** `checks.depot` covers a missing build type, both kinds of mismatch, and the catalog's order.
- **Docs.** depot/README.md documents the convention: a suffix and label for debug builds, and the same key for both. PROTOCOL.md has the new fields and rule.
- Rationale: see ADR [2026-11-24-2323-debug-builds-get-their-own-app-id](../adr/2026-11-24-2323-debug-builds-get-their-own-app-id.md)
