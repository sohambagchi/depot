# Debug and release builds are separate apps on depot

**Status:** superseded by [2026-11-24-2345-app-ids-are-com-sohambagchi](2026-11-24-2345-app-ids-are-com-sohambagchi.md)

**Context:** The user wanted depot to carry debug and release builds separately. depot keyed releases only by application id, so a debug and a release build sharing an id would replace each other on a device, and nothing stopped one from being published over the other.
**Decision:**
- **Two ids.** An app that publishes both gives its debug build its own application id (`applicationIdSuffix = ".debug"`) and label. Each id is a separate app on depot and on the device, with its own updates, pruning and pins.
- **Pinning.** `emu-publish` sends the APK's build type (debug when it is debuggable), and depot pins each id to the build type of its first publish, as it pins the signer.
- **The page.** The download page lists debug builds in a section of their own.
**Alternatives:**
- **Debug and release channels inside one id:** the two builds would replace each other on a device. A release whose version code sits below an installed debug build couldn't install. And the client and protocol would need a channel parameter.
**Consequences:**
- **Release discipline.** Apps that publish both must use the id suffix; Blot already does, and airlock-mobile doesn't yet. Pinning makes a mix-up fail at publish time with a message that names the fix.
- **Required field.** Publishing now requires `build`, so an `emu-publish` from before this change is refused until the app updates its android-emu input.
