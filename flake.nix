{
  description = "depot: apps update themselves from a server on malt";

  inputs.nixpkgs.url = "github:NixOS/nixpkgs/nixos-unstable";

  outputs = { self, nixpkgs }:
    let
      systems = [ "x86_64-linux" "aarch64-darwin" ];
      forAll = f: nixpkgs.lib.genAttrs systems (system: f system);

      mkPkgs = system: import nixpkgs {
        inherit system;
        config = {
          android_sdk.accept_license = true;
          allowUnfree = true;
        };
      };

      # depot runs on malt's tailnet address behind buckwheat's HTTPS proxy. Apps use the HTTPS
      # name only: buckwheat routes the name's LAN address over Tailscale, so a device with
      # Tailscale on reaches depot as a tailnet caller, which enrolling needs. The direct address
      # is for publishing from malt, and for emulators on malt through DEPOT_URLS. See README.md.
      depotPort = 8473;
      depotUrls = [ "https://depot.wheat.sohambagchi.com" ];
      depotPublishUrl = "http://100.97.41.27:${toString depotPort}";

      python = pkgs: pkgs.python3.withPackages (p: [ p.aiohttp p.cryptography ]);

      mkDepot = pkgs: pkgs.writeShellApplication {
        name = "depot";
        runtimeInputs = [ (python pkgs) ];
        text = ''exec python3 ${./server}/depot.py "$@"''; # with index.html, the download page
      };

      # Uploads an APK to depot (PROTOCOL.md), after checking it against depot's rules.
      mkPublish = system:
        let
          pkgs = mkPkgs system;
          buildTools = "35.0.0";
          sdk = (pkgs.androidenv.composeAndroidPackages {
            platformVersions = [ ];
            buildToolsVersions = [ buildTools ];
            includeEmulator = false;
            includeSystemImages = false;
            includeNDK = false;
          }).androidsdk;
        in pkgs.writeShellApplication {
          name = "depot-publish";
          runtimeInputs = [ pkgs.coreutils pkgs.gnused pkgs.gnugrep pkgs.gawk pkgs.unzip pkgs.curl pkgs.jq pkgs.git pkgs.jdk17_headless ];
          text = ''
            usage() { echo "Usage: depot-publish [--notes TEXT] [--allow-dirty] APK   (server: \$DEPOT_PUBLISH_URL)"; }
            notes="" allow_dirty=0 apk=""
            while (( $# )); do
              case "$1" in
                --notes) notes="''${2:?--notes needs text}"; shift 2 ;;
                --allow-dirty) allow_dirty=1; shift ;;
                -h|--help) usage; exit 0 ;;
                -*) usage >&2; exit 2 ;;
                *) apk="$1"; shift ;;
              esac
            done
            [[ -f "$apk" ]] || { usage >&2; exit 2; }
            url="''${DEPOT_PUBLISH_URL:-${depotPublishUrl}}"
            bt="${sdk}/libexec/android-sdk/build-tools/${buildTools}"

            badging="$("$bt/aapt2" dump badging "$apk")"
            app="$(sed -nE "s/^package: name='([^']+)'.*/\1/p" <<<"$badging")"
            code="$(sed -nE "s/^package: .*versionCode='([0-9]+)'.*/\1/p" <<<"$badging")"
            name="$(sed -nE "s/^package: .*versionName='([^']*)'.*/\1/p" <<<"$badging")"
            label="$(sed -nE "s/^application: label='([^']*)'.*/\1/p" <<<"$badging" | head -n1)"
            build=release
            if grep -q '^application-debuggable' <<<"$badging"; then build=debug; fi
            # depot's id rule (README.md): checked here too, before a long upload.
            if [[ ! "$app" =~ ^com\.sohambagchi\.[a-z][a-z0-9_]*(\.debug)?$ ]]; then
              echo "application id $app is not com.sohambagchi.<app> (or com.sohambagchi.<app>.debug)" >&2; exit 1
            fi
            if [[ ($build == debug && "$app" != *.debug) || ($build == release && "$app" == *.debug) ]]; then
              echo "$app is a $build build; debug builds use com.sohambagchi.<app>.debug, release builds the plain id" >&2; exit 1
            fi
            [[ -n "$app" && -n "$code" ]] || { echo "cannot read the package name and version code of $apk" >&2; exit 1; }

            certs="$("$bt/apksigner" verify --print-certs "$apk")"
            if [[ "$(grep -c '^Signer #[0-9]* certificate SHA-256 digest:' <<<"$certs")" != 1 ]]; then
              echo "$apk must have exactly one signer:" >&2; echo "$certs" >&2; exit 1
            fi
            signer="$(sed -nE 's/^Signer #1 certificate SHA-256 digest: ([0-9a-f]+)$/\1/p' <<<"$certs")"

            # Every app on depot offers a manual check: some code of the app's own must open
            # depot's updates screen (Depot.updatesIntent; README.md). The library's R8 rule
            # keeps that call visible in shrunk builds.
            dex="$(mktemp -d)"
            unzip -qo "$apk" 'classes*.dex' -d "$dex"
            # Prints whether the APK has depot's client, and how many calls outside it open the screen.
            read -r client own < <(for f in "$dex"/classes*.dex; do "$bt/dexdump" -d "$f"; done 2>/dev/null | awk '
              /^  Class descriptor/ { cls = $4; if (cls ~ /^.Lcom\/sohambagchi\/depot\/Depot;.$/) client = 1 }
              /Lcom\/sohambagchi\/depot\/Depot;\.updatesIntent:/ && cls !~ /^.Lcom\/sohambagchi\/depot\// { own++ }
              END { print client + 0, own + 0 }')
            rm -rf "$dex"
            if [[ $client == 0 ]]; then
              echo "$apk doesn't include depot's client; see depot's README.md" >&2; exit 1
            fi
            if [[ $own == 0 ]]; then
              echo "$apk has no \"Check for updates\" item: add one to the app's settings or menu that calls" >&2
              echo "  startActivity(Depot.updatesIntent(context))   (see depot's README.md)" >&2
              exit 1
            fi

            # A build from uncommitted changes can't be traced back to a commit.
            if git rev-parse --is-inside-work-tree >/dev/null 2>&1; then
              if [[ -n "$(git status --porcelain --untracked-files=no)" && $allow_dirty == 0 ]]; then
                echo "the git tree has uncommitted changes; commit, or pass --allow-dirty" >&2; exit 1
              fi
              [[ -n "$notes" ]] || notes="$(git log -1 --format=%s)"
              count="$(git rev-list --count HEAD)"
              if [[ "$code" != "$count" ]]; then
                echo "warning: versionCode $code is not this checkout's commit count ($count)" >&2
              fi
            fi

            meta="$(jq -nc --arg app "$app" --arg code "$code" --arg name "$name" --arg signer "$signer" --arg notes "$notes" --arg label "$label" --arg build "$build" \
              '{app: $app, code: ($code | tonumber), name: $name, label: $label, build: $build, signer: $signer, notes: $notes}')"
            echo "Publishing $app $name ($code, $build build) to $url"
            body="$(mktemp)"; trap 'rm -f "$body"' EXIT
            status="$(curl -sS -o "$body" -w '%{http_code}' --form-string "meta=$meta" \
              -F "apk=@$apk;type=application/vnd.android.package-archive" "$url/v1/publish")"
            if [[ "$status" != 200 ]]; then
              echo "depot refused it ($status): $(jq -r '.error // .' "$body" 2>/dev/null || cat "$body")" >&2; exit 1
            fi
            jq -r '"published \(.app) \(.name) (\(.code)), \(.size) bytes, sha256 \(.sha256)"' "$body"
          '';
        };
    in {
      lib = {
        # Merge into an app's dev shell to build in depot's client (README.md).
        depotEnv = {
          DEPOT_CLIENT = "${./client}";
          DEPOT_URLS = builtins.concatStringsSep "," depotUrls;
          DEPOT_PUBLISH_URL = depotPublishUrl;
        };
      };

      packages = forAll (system: rec {
        depot = mkDepot (mkPkgs system);
        depot-publish = mkPublish system;
        default = depot;
      });

      checks = forAll (system:
        let pkgs = mkPkgs system;
        in {
          depot = pkgs.runCommand "depot-test" { nativeBuildInputs = [ (python pkgs) ]; } ''
            cp ${./server}/* . && python3 test_depot.py && touch $out
          '';
        });

      # services.depot, a system service: the alternative to the user service malt runs
      # (README.md). The tailnet port is open wherever tailscale0 is trusted; lanInterfaces opens
      # it on other interfaces.
      nixosModules.depot = { config, lib, pkgs, ... }:
        let
          cfg = config.services.depot;
          t = lib.types;
        in {
          options.services.depot = {
            enable = lib.mkEnableOption "depot, the app update server";
            package = lib.mkOption {
              type = t.package;
              default = mkDepot pkgs;
              defaultText = lib.literalExpression "depot's server";
            };
            listen = lib.mkOption {
              type = t.listOf t.str;
              example = [ "100.97.41.27" ];
              description = "Addresses to listen on; one must be a tailnet address for enrolling and publishing.";
            };
            port = lib.mkOption { type = t.port; default = depotPort; };
            logins = lib.mkOption {
              type = t.listOf t.str;
              default = [ ];
              description = "Tailscale logins allowed to enroll devices and publish; empty means the server's own.";
            };
            nodes = lib.mkOption {
              type = t.listOf t.str;
              default = [ ];
              description = "If not empty, only these Tailscale nodes may enroll.";
            };
            trustProxy = lib.mkOption {
              type = t.listOf t.str;
              default = [ ];
              example = [ "100.77.198.14" ];
              description = "Reverse proxies whose X-Forwarded-For names the real client.";
            };
            prune = {
              keep = lib.mkOption {
                type = t.nullOr t.ints.positive;
                default = null;
                example = 3;
                description = "If set, prune on `onCalendar` to each app's newest `keep` versions (release and debug builds of a version count once), plus each build type's newest.";
              };
              onCalendar = lib.mkOption { type = t.str; default = "Fri *-*-* 03:00:00"; };
            };
            lanInterfaces = lib.mkOption {
              type = t.listOf t.str;
              default = [ ];
              description = "Interfaces to open the port on in the firewall.";
            };
          };
          config = lib.mkIf cfg.enable {
            systemd.services.depot = {
              description = "depot, the app update server";
              wantedBy = [ "multi-user.target" ];
              wants = [ "network-online.target" ];
              after = [ "network-online.target" "tailscaled.service" ];
              path = [ config.services.tailscale.package ];
              serviceConfig = {
                User = "depot"; # named, so depot-prune shares the dynamic user and its state
                ExecStart = lib.escapeShellArgs ([ "${cfg.package}/bin/depot" "--state" "/var/lib/depot" "--port" (toString cfg.port) ]
                  ++ lib.concatMap (a: [ "--listen" a ]) cfg.listen
                  ++ lib.concatMap (l: [ "--login" l ]) cfg.logins
                  ++ lib.concatMap (n: [ "--node" n ]) cfg.nodes
                  ++ lib.concatMap (p: [ "--trust-proxy" p ]) cfg.trustProxy);
                DynamicUser = true;
                StateDirectory = "depot";
                Restart = "on-failure";
                RestartSec = 5;
                NoNewPrivileges = true;
                ProtectSystem = "strict";
                ProtectHome = true;
                PrivateTmp = true;
              };
            };
            systemd.services.depot-prune = lib.mkIf (cfg.prune.keep != null) {
              description = "Prune old depot releases";
              serviceConfig = {
                Type = "oneshot";
                User = "depot";
                DynamicUser = true;
                StateDirectory = "depot";
                ExecStart = "${cfg.package}/bin/depot --state /var/lib/depot --prune ${toString cfg.prune.keep}";
              };
            };
            systemd.timers.depot-prune = lib.mkIf (cfg.prune.keep != null) {
              wantedBy = [ "timers.target" ];
              timerConfig = { OnCalendar = cfg.prune.onCalendar; Persistent = true; };
            };
            networking.firewall.interfaces = lib.genAttrs cfg.lanInterfaces (_: { allowedTCPPorts = [ cfg.port ]; });
          };
        };

      devShells = forAll (system:
        let pkgs = mkPkgs system;
        in {
          # For working on depot itself: the server's Python and depot-publish.
          default = pkgs.mkShell { packages = [ (python pkgs) (mkPublish system) ]; };
        });
    };
}
