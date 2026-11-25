# depot's prune keeps three versions per app, across debug and release

- **What counts as an app.** `depot --prune N` treats an app's release id and its debug id (`<id>.debug`) as one app.
- **What it keeps.** The N newest version codes, where a version's release and debug builds count once, so at most 2N APKs (6 on malt). It also keeps each id's newest release, so a release build that lags behind debug builds is never deleted.
- **Tests.** `checks.depot` covers a lagging release, mixed versions and the full 6-APK case. A run against a copy of malt's live state (Blot's 101 builds) deleted nothing.
- **Docs.** README.md, PROTOCOL.md and the NixOS option describe the rule; the timer is unchanged (Fridays 03:00, `--prune 3`).
