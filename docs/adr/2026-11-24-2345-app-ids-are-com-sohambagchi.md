# Apps on depot use com.sohambagchi.<app>, plus .debug for debug builds

**Status:** accepted

**Context:** The user wanted one application id format for every app that uses depot, and download names that say which app, version and build a file is. Until now depot published any id and pinned each id's build type at its first publish ([2026-11-24-2323-debug-builds-get-their-own-app-id](2026-11-24-2323-debug-builds-get-their-own-app-id.md)).
**Decision:**
- **The format.** depot publishes only `com.sohambagchi.<app>` (lowercase letters, digits, underscores) for release builds and `com.sohambagchi.<app>.debug` for debug builds. `emu-publish` checks the same rule before uploading.
- **The id decides the build type.** A publish whose id and build type disagree gets a 400. The build-type pin is gone, since the id now fixes it.
- **Download names.** Downloads are `<app>-v<version>.apk`, or `<app>-v<version>.debug.apk` for debug builds. `<app>` is the last part of the release id.
**Alternatives:**
- **Keeping any id and pinning the build type:** it left the id format to each app, and a first publish under the wrong id locked it (as happened to airlock-mobile).
**Consequences:**
- **Blot must move.** It publishes as `app.blot`, which is refused from now on. Moving to `com.sohambagchi.blot` makes a new Android app: devices install it fresh and remove the old one, which can't update into it.
- **Existing ids stay downloadable.** Ids published before this rule keep serving their releases until they are deleted.
- **airlock-mobile already conforms.**
