# Index

## Decisions

- [2026-11-25-0027-depot-is-its-own-repo](adr/2026-11-25-0027-depot-is-its-own-repo.md) — depot is its own repo, with its history from android-emu
- [2026-11-25-0021-every-depot-app-has-a-check-for-updates-item](adr/2026-11-25-0021-every-depot-app-has-a-check-for-updates-item.md) — every app links to the "App updates" screen; depot-publish enforces it
- [2026-11-25-0007-apps-reach-depot-over-https-only](adr/2026-11-25-0007-apps-reach-depot-over-https-only.md) — apps reach depot over HTTPS only; no plain HTTP except listed hosts
- [2026-11-24-2345-app-ids-are-com-sohambagchi](adr/2026-11-24-2345-app-ids-are-com-sohambagchi.md) — com.sohambagchi.<app> and .debug ids only; downloads named <app>-v<version>
- [2026-11-24-2318-download-page-open-to-home-network](adr/2026-11-24-2318-download-page-open-to-home-network.md) — the download page and APKs are open to the home network and tailnet
- [2026-11-24-2241-depot-behind-buckwheat-proxy](adr/2026-11-24-2241-depot-behind-buckwheat-proxy.md) — depot behind Caddy on buckwheat; client address from its X-Forwarded-For only
- [2026-11-24-2209-app-updates-through-depot](adr/2026-11-24-2209-app-updates-through-depot.md) — apps update themselves from depot, with tailnet enrollment

## Changes

- [2026-11-25-0027-own-repo](changelog/2026-11-25-0027-own-repo.md) — depot moves into its own repository
- [2026-11-25-0021-check-for-updates-screen](changelog/2026-11-25-0021-check-for-updates-screen.md) — the "App updates" screen, required in every app
- [2026-11-24-2209-depot-app-updates](changelog/2026-11-24-2209-depot-app-updates.md) — depot's first version
