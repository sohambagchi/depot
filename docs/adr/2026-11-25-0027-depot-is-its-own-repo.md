# depot is its own repository

**Status:** accepted

**Context:** depot (server, Android client library, publish tool, protocol) grew inside android-emu, the emulator tooling repo. Apps took both from one flake input, so every depot change reached apps through an android-emu update, and the two histories were mixed. The user asked for depot to live in `~/dev/depot`.
**Decision:**
- **The new repo.** `~/dev/depot` holds the server, client, PROTOCOL.md, README.md, the NixOS module, `checks.depot`, `lib.depotEnv`, and depot's ADRs and changelogs.
- **History.** It keeps depot's history from android-emu, filtered to those paths, with `depot/` as the root. Commit subjects keep android-emu's `[0.2.x]` numbers, and later commits continue from them.
- **The publish tool.** `emu-publish` becomes `depot-publish` (`packages.depot-publish`), with its own SDK of build tools only.
- **How apps use it.** They add `depot` as a flake input beside `android-emu`.
- **The remote.** `origin` is `git@github.com:sohambagchi/depot.git`.
**Alternatives:**
- **A fresh repo importing depot at one commit:** cleaner version numbers, but loses `git log` and blame for depot's files.
**Consequences:**
- **android-emu drops depot.** Its `lib.depotEnv` and `emu-publish` stop working and say where depot went, so apps must switch inputs on their next android-emu update.
- **The flake and docs changes stay behind.** Changes made to android-emu's flake.nix and docs alongside depot aren't in this history. android-emu keeps them.
