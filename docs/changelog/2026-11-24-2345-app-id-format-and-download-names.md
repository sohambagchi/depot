# depot publishes only com.sohambagchi.<app> ids, and names downloads <app>-v<version>

- **The id rule.** `POST /v1/publish` and `emu-publish` accept only `com.sohambagchi.<app>` for release builds and `com.sohambagchi.<app>.debug` for debug builds. Others, and mismatched build types, get a 400 that states the rule. The build-type pin is removed.
- **Download names.** Downloads are named `<app>-v<version>.apk` and `<app>-v<version>.debug.apk`. On the live server: `airlock-v0.1.3.apk`, `airlock-v0.1.3.debug.apk`, `blot-v0.20.4.apk` and `blot-v0.20.4.debug.apk`.
- **Tests.** `checks.depot` uses `com.sohambagchi.*` ids and covers refused ids, mismatched suffixes and both file names. A test app's release and debug builds were published to the live server and removed.
- **Docs.** depot/README.md and PROTOCOL.md describe the rule and the names.
- Rationale: see ADR [2026-11-24-2345-app-ids-are-com-sohambagchi](../adr/2026-11-24-2345-app-ids-are-com-sohambagchi.md)
