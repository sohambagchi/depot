# depot keeps the three newest releases per app

- **The command.** `depot --state DIR --prune N` keeps each app's N newest releases (by version code) and deletes older index entries and APKs, plus any APK the index doesn't list. Publishes and prunes share a lock (`state/.lock`).
- **On malt.** The user timer `depot-prune.timer` runs it with N = 3 every Friday at 03:00, and catches up after downtime (`Persistent=true`).
- **The NixOS module.** `nixosModules.depot` gains `prune.keep` and `prune.onCalendar`, for the same schedule as a system service.
- **Tests.** `checks.depot` covers pruning: older releases and stray APKs go, apps with fewer releases are untouched, and the signer pin and rising-code rule hold afterwards.
- Docs: [depot/README.md](../../depot/README.md#server-malt).
