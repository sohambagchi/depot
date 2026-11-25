# Every app on depot has a "Check for updates" item, enforced at publish

**Status:** accepted

**Context:** Apps check every 6 hours and when opened after an hour. The user wanted a way to check on demand, and rejected push (ntfy or Firebase) and shorter intervals in favour of a manual, unobtrusive button that every depot app must have.
**Decision:**
- **The screen is in the library.** `Depot.updatesIntent(context)` opens "App updates", which checks at once, explains the result, and installs a ready update.
- **The app adds only the item.** It puts "Check for updates" in its settings or a menu.
- **emu-publish enforces it.** It refuses an APK whose own code never calls `Depot.updatesIntent`, found with `dexdump`. A consumer R8 rule keeps that call visible in shrunk release builds.
**Alternatives:**
- **Each app builds its own UI on `checkNow`:** every app would repeat the status and error handling, and a background check can't report its result.
- **An automatic entry (the system's App info gear, `APPLICATION_PREFERENCES`):** it clashes with an app's own settings entry, and few people look there.
- **Checking on the server:** depot would need to parse dex code; emu-publish already inspects APKs.
**Consequences:**
- **Publishing is blocked until apps add the item.** Blot and airlock-mobile can't publish until they do.
- **The check is code-level, not visual.** It confirms the call exists, not that the item is easy to find.
- **The screen's look.** It uses the system's DeviceDefault theme (light and dark), not each app's own.
