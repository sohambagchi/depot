# Apps on depot get an "App updates" screen and must link to it

- **The screen.** The client library has an "App updates" screen, `Depot.updatesIntent`: installed version, an immediate check, the result in plain words, the update's notes and an Install button. It follows the system's light and dark themes and keeps its state across rotation and theme changes. A check run from the screen doesn't also post the "ready" notification.
- **Enforcement.** `emu-publish` refuses an APK without depot's client, or without a call to `Depot.updatesIntent` from the app's own code. A consumer R8 rule keeps that call visible in shrunk builds.
- **Checked on an API 35 emulator against the live depot,** with an R8-shrunk test app:
  - the screen reported nothing published, then 0.0.31 ready;
  - Install opened "Install unknown apps" once, then installed 31 silently;
  - after the update it reported up to date;
  - screenshots taken in light and dark.
- **Checked in emu-publish:** it refused the same app built without the button.
- **Shared emulators.** DEV_GUIDE.md records the rules the sessions agreed for sharing malt's emulators.
- Rationale: see ADR [2026-11-25-0021-every-depot-app-has-a-check-for-updates-item](../adr/2026-11-25-0021-every-depot-app-has-a-check-for-updates-item.md)
