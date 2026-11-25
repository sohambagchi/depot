# depot

Updates for apps built with android-emu. Apps fetch new builds from a server on malt:

1. `emu-publish` uploads a build to depot.
2. The app finds it on its next check, downloads and verifies it, and posts "<App> <version> is ready".
3. Tapping that notification installs the update.

The wire format, device identity and verification rules are in [PROTOCOL.md](PROTOCOL.md).

| Part | Where |
| --- | --- |
| Server | [server/depot.py](server/depot.py); `packages.depot`, `nixosModules.depot`, `checks.depot` (its test) |
| Client library | [client/](client/), plain Java, no dependencies; included as the Gradle project `:depot` |
| Publishing | `emu-publish`, in `lib.mkEmu`'s outputs and this flake's dev shell |
| Dev-shell settings | `lib.depotEnv`: `DEPOT_CLIENT`, `DEPOT_URLS`, `DEPOT_PUBLISH_URL` |

## App side

**Flake.** Merge `depotEnv` into the dev shell and add `emu-publish`:

```nix
devShells.${system}.default = pkgs.mkShell ({
  packages = [ emu.sdk emu.emu-up emu.emu-down emu.emu-shot emu.emu-publish /* ... */ ];
  # ...
} // android-emu.lib.depotEnv);
```

**settings.gradle.kts.** Include the client only when the dev shell provides it. A build without
it, such as a public open-source one, has no updater and no extra permissions.

```kotlin
// depot's update client (android-emu), built in only when the dev shell provides it. Gradle
// needs a writable project directory, so the read-only Nix store copy is mirrored into build/.
System.getenv("DEPOT_CLIENT")?.let { source ->
    val dir = file("build/depot-client")
    val stamp = dir.resolve(".source")
    if (!stamp.isFile || stamp.readText() != source) {
        dir.deleteRecursively()
        file(source).copyRecursively(dir)
        dir.walk().forEach { it.setWritable(true, true) }
        stamp.writeText(source)
    }
    include(":depot")
    project(":depot").projectDir = dir
}
```

**app/build.gradle.kts.** Add the dependency and the version convention:

```kotlin
// versionCode: the commit count; versionName: X.Y.Z from the latest "[X.Y.Z] ..." commit subject.
fun git(vararg args: String) = providers.exec { commandLine("git", *args) }.standardOutput.asText.get().trim()

android {
    defaultConfig {
        versionCode = git("rev-list", "--count", "HEAD").toInt()
        versionName = git("log", "-1", "--grep=^\\[[0-9]", "--format=%s").substringAfter("[").substringBefore("]").ifEmpty { "0.0.0" }
    }
}

dependencies {
    if (findProject(":depot") != null) implementation(project(":depot"))
}
```

No code is needed. A content provider in the library schedules the check when the app starts.
Apps that want an in-app control can use `com.sohambagchi.depot.Depot`:

- `checkNow(context)` checks as soon as there is a network.
- `pending(context)` returns the downloaded update, or null.
- `installIntent(context)` installs it.

**Requirements:**

- **Signing key.** Every build must be signed with the same key, kept outside the repo; for
  example `~/.android/<app>.jks`, as airlock-mobile does. The first published release pins its
  signer on the server.
- **Application ids.** depot only publishes `com.sohambagchi.<app>` (lowercase) for release
  builds and `com.sohambagchi.<app>.debug` for debug builds, with a label of their own:

  ```kotlin
  defaultConfig {
      applicationId = "com.sohambagchi.<app>"
      manifestPlaceholders["appLabel"] = "<app>"             // with android:label="${appLabel}"
  }
  buildTypes {
      debug {
          applicationIdSuffix = ".debug"
          manifestPlaceholders["appLabel"] = "<app> debug"
      }
  }
  ```

  Both builds may use the same signing key. They install side by side, the download page lists
  debug builds in their own section, and downloads are named `<app>-v<version>.apk` and
  `<app>-v<version>.debug.apk`.
- **Cleartext HTTP.** The library merges `android:usesCleartextTraffic="true"`, for the direct
  tailnet address, which enrolling needs. Tailscale encrypts that path. An app with its own
  `networkSecurityConfig` must permit cleartext to `100.97.41.27` there.
- **Notifications.** The "update ready" notification needs `POST_NOTIFICATIONS` (Android 13+),
  which the app must request. Without it, only `Depot.pending` shows the update.
- **Toolchains.** The client builds under AGP 8 (with the Kotlin plugin) and AGP 9 (built-in
  Kotlin). It compiles against the newest platform and build-tools in `$ANDROID_HOME`, and needs
  `minSdk` 31 or later.

**On the device:**

- **First run.** On first start with Tailscale up, the app enrolls itself at the direct tailnet
  address (a Keystore key, checked with `tailscale whois`).
- **Checks.** After that it checks every 6 hours, and on start if more than an hour has passed.
  Checks go through the HTTPS proxy first, then directly over the tailnet.
- **First tap.** The first tap on an update opens "Install unknown apps" for the app; allow it and
  tap again.
- **No system dialog.** After that, the tap installs at once. The library holds
  `UPDATE_PACKAGES_WITHOUT_USER_ACTION`, so an app updating itself skips Android's "Do you want to
  update this app?". This works even when the app was first installed with `adb install`
  (checked on API 31 and 35 emulators). A build without that permission, from before the app took
  depot in, still gets the dialog once.

## Installing on a new device

Open `https://depot.wheat.sohambagchi.com` in the device's browser on home Wi-Fi.

1. Tap **Download** for an app. Chrome warns about every APK; choose **Download anyway**.
2. Open the file. Android asks once to allow installs from that source.
3. Install it, then open the app once with Tailscale on so it enrolls for updates.

Tested on an API 35 emulator through the live proxy: download, install, enroll, and an update
installed from the tap with no dialog.

## Publishing

```sh
gradle assembleRelease assembleDebug     # from a clean, committed tree
emu-publish app/build/outputs/apk/release/app-release.apk [--notes TEXT]
emu-publish app/build/outputs/apk/debug/app-debug.apk
```

- **What it sends.** It reads the application id, version code, name, label and build type with
  `aapt2` (debug if the APK is debuggable), and the signer with `apksigner`. The notes default to
  the last commit subject.
- **Dirty trees.** It refuses a dirty tree (`--allow-dirty` overrides this), and warns when the
  version code isn't the commit count.
- **Where.** It posts to `DEPOT_PUBLISH_URL`, the direct tailnet address; through the proxy, the
  publisher would look like a LAN client.
- **What gets refused.** Both emu-publish and depot refuse an application id outside the
  `com.sohambagchi.<app>[.debug]` form, or one whose suffix doesn't match the build type. depot
  also answers 409 to a version code that isn't new, or to a different signer.

## Server (malt)

depot runs on malt as a systemd user service, as airlockd does, so changing it needs no
sudo. It listens on the tailnet address only.

```ini
# ~/.config/systemd/user/depot.service
[Service]
ExecStart=%h/.local/state/depot-server/bin/depot --listen 100.97.41.27 --port 8473 --state %h/.local/state/depot --trust-proxy 100.77.198.14
Restart=on-failure
RestartSec=5
[Install]
WantedBy=default.target
```

```sh
nix build ~/dev/android-emu#depot -o ~/.local/state/depot-server   # build or update (a GC root)
systemctl --user enable --now depot                                 # or: restart, status
journalctl --user -u depot -f                                       # access log shows fwd=<client> behind the proxy
```

Pruning: `depot-prune.timer` runs `depot --state ~/.local/state/depot --prune 3` every Friday
at 03:00. It runs at the next start if malt was off then, and logs to
`journalctl --user -u depot-prune`. A publish and a prune can't overlap (`state/.lock`).

- **What it keeps.** Each app's three newest versions. An app is its release id and its debug id
  (`<id>.debug`) together. A version is a version code, whose release and debug builds count
  once, so an app holds at most 6 APKs.
- **Never a missing build type.** Each id also keeps its own newest release, so a release build
  that lags behind newer debug builds stays.
- **What it deletes.** Everything else: older index entries and their APKs.

```ini
# ~/.config/systemd/user/depot-prune.service
[Service]
Type=oneshot
ExecStart=%h/.local/state/depot-server/bin/depot --state %h/.local/state/depot --prune 3

# ~/.config/systemd/user/depot-prune.timer
[Timer]
OnCalendar=Fri *-*-* 03:00:00
Persistent=true
[Install]
WantedBy=timers.target
```

- **The proxy.** `https://depot.wheat.sohambagchi.com` is Caddy on buckwheat (100.77.198.14):
  TLS, DNS and certificates live there. It forwards plain HTTP to 100.97.41.27:8473.
  `--trust-proxy` makes depot read the client's address from its `X-Forwarded-For`.
  The name resolves to buckwheat's LAN address, so it only works from the home LAN.
- **Away from home.** Apps also have the direct tailnet address, and use it when the proxy
  can't be reached.
- **State.** The state is in `~/.local/state/depot`:
  - `devices.json`: enrolled devices. Delete an entry to revoke it; that device enrolls again over
    Tailscale on its next check.
  - `apps/<id>/`: releases; after each Friday's prune, the app's three newest versions.
- **Status.** `curl http://100.97.41.27:8473/v1/status` lists apps and devices (tailnet only).
  `/v1/health` answers anyone, for monitoring.
- **Development.** Run `nix run .#depot -- --listen 127.0.0.1 --state /tmp/depot` for a local
  server, and `nix build .#checks.x86_64-linux.depot` for the test.
- **System service.** `nixosModules.depot` (`services.depot`) runs the same server as a system
  service, with `prune.keep` and `prune.onCalendar` for the same schedule. It isn't used on malt.
