#!/usr/bin/env python3
"""depot: serves app updates to enrolled devices. The wire format is in ../PROTOCOL.md.

State directory layout:
  devices.json                 {"devices": {id: {name, node, login, key, enrolled_at, last_seen}}}
  apps/<app id>/index.json     {"app", "signer", "releases": [release, ...]}
  apps/<app id>/<code>.apk
  .lock                        held while an app's releases change (publish, --prune)
"""

import argparse
import asyncio
import base64
import binascii
import contextlib
import fcntl
import hashlib
import ipaddress
import json
import logging
import os
import re
import secrets
import shutil
import socket
import tempfile
import time
from pathlib import Path

from aiohttp import web
from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec

log = logging.getLogger("depot")

CONTEXT = b"depot/1"
NONCE_TTL_S = 60
TOKEN_TTL_S = 600
MAX_APK = 512 * 1024 * 1024
TAILNET = (ipaddress.ip_network("100.64.0.0/10"), ipaddress.ip_network("fd7a:115c:a1e0::/48"))
APP_ID = re.compile(r"^[A-Za-z][A-Za-z0-9_]*(\.[A-Za-z][A-Za-z0-9_]*)+$")
HEX64 = re.compile(r"^[0-9a-f]{64}$")
# What may be published: com.sohambagchi.<app> for release builds, plus ".debug" for debug builds.
PUBLISHABLE = re.compile(r"^com\.sohambagchi\.([a-z][a-z0-9_]*)(\.debug)?$")
PAGE = Path(__file__).with_name("index.html")  # the download page
BUILDS = ("debug", "release")
# A systemd service's PATH may not hold the system profile, where NixOS puts the tailscale CLI.
TAILSCALE = os.environ.get("DEPOT_TAILSCALE") or shutil.which("tailscale") or "/run/current-system/sw/bin/tailscale"


def now_ms() -> int:
    return int(time.time() * 1000)


def on_tailnet(addr: str | None) -> bool:
    try:
        ip = ipaddress.ip_address(addr or "")
    except ValueError:
        return False
    return any(ip in net for net in TAILNET)


def on_local_network(addr: str | None) -> bool:
    """A home-LAN (private) or tailnet address: the download page's audience, never the internet."""
    try:
        ip = ipaddress.ip_address(addr or "")
    except ValueError:
        return False
    return ip.is_private or on_tailnet(addr)


def write_atomic(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.", suffix=".tmp")
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(data)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, path)
    except BaseException:
        os.unlink(tmp)
        raise


def write_json(path: Path, obj) -> None:
    write_atomic(path, (json.dumps(obj, indent=2) + "\n").encode())


@contextlib.contextmanager
def state_lock(state: Path):
    """An exclusive lock on the state directory, so `--prune` never interleaves with a publish."""
    state.mkdir(parents=True, exist_ok=True)
    with open(state / ".lock", "w") as f:
        fcntl.flock(f, fcntl.LOCK_EX)
        yield


def apk_filename(idx: dict, rel: dict) -> str:
    """The download's file name: <app>-v<version>.apk, with .debug before .apk for debug builds."""
    short = family(idx).rsplit(".", 1)[-1]
    debug = ".debug" if idx.get("build") == "debug" else ""
    return re.sub(r"[^A-Za-z0-9._-]", "_", f"{short}-v{rel.get('name') or rel['code']}{debug}.apk")


def family(idx: dict) -> str:
    """The app an application id belongs to: a debug build's id without its ".debug" suffix."""
    app = idx["app"]
    return app.removesuffix(".debug") if idx.get("build") == "debug" else app


def prune(state: Path, keep: int) -> None:
    """Keeps each app's `keep` newest versions and deletes older releases: their index entries
    and APKs, plus any APK an index doesn't list.

    An app is its release id and its debug id together, and a version is a version code, whose
    debug and release builds count once (so at most 2 * keep APKs). Each id also keeps its own
    newest release, so neither build type disappears from depot."""
    with state_lock(state):
        apps: dict[str, list[tuple[Path, dict]]] = {}
        for idx_path in sorted((state / "apps").glob("*/index.json")):
            idx = json.loads(idx_path.read_text())
            apps.setdefault(family(idx), []).append((idx_path, idx))
        for members in apps.values():
            codes = sorted({r["code"] for _, idx in members for r in idx["releases"]})
            versions = set(codes[-keep:])
            for idx_path, idx in members:
                newest = max((r["code"] for r in idx["releases"]), default=None)
                kept = sorted((r for r in idx["releases"] if r["code"] in versions or r["code"] == newest),
                              key=lambda r: r["code"])
                dropped = len(idx["releases"]) - len(kept)
                if dropped:
                    idx["releases"] = kept
                    write_json(idx_path, idx)
                names = {f"{r['code']}.apk" for r in kept}
                stray = [f for f in idx_path.parent.glob("*.apk") if f.name not in names]
                for f in stray:
                    f.unlink()
                log.info("pruned %s: kept %s, dropped %d release(s), deleted %d APK(s)",
                         idx["app"], [r["code"] for r in kept], dropped, len(stray))


def bind_socket(host: str, port: int) -> socket.socket:
    """A listening socket that may bind before its address exists (Wi-Fi or Tailscale still down)."""
    family = socket.AF_INET6 if ":" in host else socket.AF_INET
    sock = socket.socket(family, socket.SOCK_STREAM)
    try:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        if hasattr(socket, "IP_FREEBIND"):
            try:
                sock.setsockopt(socket.IPPROTO_IP, socket.IP_FREEBIND, 1)
            except OSError:  # without it, the address must exist at start-up
                pass
        sock.bind((host, port))
        sock.listen(64)
    except OSError:
        sock.close()
        raise
    sock.setblocking(False)
    return sock


async def tailscale_whois(addr: str) -> dict | None:
    """`tailscale whois --json` for an address: {login, node}, or None when it can't be asked."""
    try:
        proc = await asyncio.create_subprocess_exec(
            TAILSCALE, "whois", "--json", addr,
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
        out, err = await asyncio.wait_for(proc.communicate(), 10)
    except (OSError, asyncio.TimeoutError) as e:
        log.warning("tailscale whois %s failed: %s", addr, e)
        return None
    if proc.returncode != 0:
        log.warning("tailscale whois %s: %s", addr, err.decode(errors="replace").strip())
        return None
    try:
        info = json.loads(out)
        node = info["Node"]
        return {"login": info["UserProfile"]["LoginName"],
                "node": node.get("ComputedName") or node.get("Hostinfo", {}).get("Hostname") or node["Name"]}
    except (ValueError, KeyError, TypeError) as e:
        log.warning("unreadable whois for %s: %s", addr, e)
        return None


def verify(key_b64: str, message: bytes, sig_b64: object) -> bool:
    if not isinstance(sig_b64, str):
        return False
    try:
        key = serialization.load_der_public_key(base64.b64decode(key_b64))
        key.verify(base64.b64decode(sig_b64, validate=True), message, ec.ECDSA(hashes.SHA256()))
        return True
    except (InvalidSignature, ValueError, TypeError, binascii.Error):
        return False


def error(status: int, message: str) -> web.Response:
    return web.json_response({"error": message}, status=status)


class Depot:
    def __init__(self, state: Path, hosts: list[str], logins: list[str] | None, nodes: list[str] | None,
                 proxies: list[str] | None = None):
        self.state = state
        self.hosts = hosts
        self.logins = logins  # None: the server's own login, looked up on first use
        self.nodes = nodes
        self.proxies = set(proxies or ())
        self.nonces: dict[str, float] = {}  # nonce -> expiry (monotonic)
        self.tokens: dict[str, tuple[str, float]] = {}  # token -> (device id, expiry)
        self.lock = asyncio.Lock()

    # --- state ----------------------------------------------------------------

    @property
    def devices_path(self) -> Path:
        return self.state / "devices.json"

    def devices(self) -> dict[str, dict]:
        try:
            return json.loads(self.devices_path.read_text()).get("devices", {})
        except FileNotFoundError:
            return {}
        except (OSError, ValueError, AttributeError) as e:
            log.error("cannot read %s (%s); no device can connect", self.devices_path, e)
            return {}

    def app_dir(self, app: str) -> Path:
        return self.state / "apps" / app

    def index(self, app: str) -> dict | None:
        try:
            return json.loads((self.app_dir(app) / "index.json").read_text())
        except FileNotFoundError:
            return None

    @staticmethod
    def release_view(rel: dict, app: str) -> dict:
        return rel | {"app": app, "url": f"/v1/apps/{app}/{rel['code']}.apk"}

    # --- tailnet identity -----------------------------------------------------

    async def allowed_logins(self) -> list[str]:
        if self.logins is None:
            own = next((h for h in self.hosts if on_tailnet(h)), None)
            me = await tailscale_whois(own) if own else None
            if not me:
                return []
            self.logins = [me["login"]]
            log.info("allowing the server's own login, %s", me["login"])
        return self.logins

    def client(self, request: web.Request) -> str | None:
        """The caller's address. Behind a trusted reverse proxy it is the last X-Forwarded-For
        entry, the one that proxy added; otherwise the header is ignored, so it can't be forged."""
        if request.remote in self.proxies:
            forwarded = request.headers.get("X-Forwarded-For", "")
            last = forwarded.rsplit(",", 1)[-1].strip()
            if last:
                return last
        return request.remote

    async def tailnet_caller(self, request: web.Request, *, check_node: bool) -> dict | web.Response:
        """The caller's whois if it is on the tailnet under an allowed login, else an error response."""
        addr = self.client(request)
        if not on_tailnet(addr):
            return error(403, "only over Tailscale")
        who = await tailscale_whois(addr)
        if not who:
            return error(503, "could not ask Tailscale who this is")
        if who["login"] not in await self.allowed_logins() or (check_node and self.nodes and who["node"] not in self.nodes):
            log.warning("refused %s %s from %s (%s on %s)", request.method, request.path, addr, who["login"], who["node"])
            return error(403, "not allowed")
        return who

    # --- tokens ---------------------------------------------------------------

    def prune(self) -> None:
        t = time.monotonic()
        self.nonces = {n: e for n, e in self.nonces.items() if e > t}
        self.tokens = {k: v for k, v in self.tokens.items() if v[1] > t}

    def bearer(self, request: web.Request) -> str | None:
        """The device id behind the request's token, if the token is live and the device still enrolled."""
        auth = request.headers.get("Authorization", "")
        if not auth.startswith("Bearer "):
            return None
        entry = self.tokens.get(auth[7:].strip())
        if not entry or entry[1] <= time.monotonic():
            return None
        return entry[0] if entry[0] in self.devices() else None

    # --- handlers -------------------------------------------------------------

    async def enroll(self, request: web.Request) -> web.Response:
        who = await self.tailnet_caller(request, check_node=True)
        if isinstance(who, web.Response):
            return who
        try:
            body = await request.json()
            der = base64.b64decode(body["key"], validate=True)
            key = serialization.load_der_public_key(der)
            if not isinstance(key, ec.EllipticCurvePublicKey) or key.curve.name != "secp256r1":
                raise ValueError("not a P-256 key")
            name = str(body.get("name") or "device")[:96]
        except (ValueError, KeyError, TypeError, binascii.Error) as e:
            return error(400, f"bad enrollment: {e}")
        device_id = "d-" + hashlib.sha256(der).hexdigest()[:16]
        async with self.lock:
            devices = self.devices()
            known = device_id in devices
            old = devices.get(device_id, {})
            devices[device_id] = old | {"name": name, "node": who["node"], "login": who["login"],
                                        "key": body["key"], "enrolled_at": old.get("enrolled_at", now_ms())}
            write_json(self.devices_path, {"devices": devices})
        log.info("%s %s (%s on %s)", "re-enrolled" if known else "enrolled", device_id, name, who["node"])
        return web.json_response({"device": device_id})

    async def challenge(self, request: web.Request) -> web.Response:
        self.prune()
        nonce = base64.b64encode(os.urandom(32)).decode()
        self.nonces[nonce] = time.monotonic() + NONCE_TTL_S
        return web.json_response({"nonce": nonce, "expires_in": NONCE_TTL_S})

    async def session(self, request: web.Request) -> web.Response:
        try:
            body = await request.json()
            device_id, nonce, sig = body["device"], body["nonce"], body["sig"]
            if not all(isinstance(v, str) for v in (device_id, nonce, sig)):
                raise TypeError("device, nonce and sig must be strings")
        except (ValueError, KeyError, TypeError) as e:
            return error(400, f"bad session request: {e}")
        device = self.devices().get(device_id)
        if device is None:
            return error(401, "unknown device")
        expiry = self.nonces.pop(nonce, None)  # single use, even when the signature turns out bad
        if expiry is None or expiry <= time.monotonic():
            return error(403, "unknown or expired nonce")
        if not verify(device["key"], b"\n".join([CONTEXT, nonce.encode(), device_id.encode()]), sig):
            log.warning("bad signature from %s (%s)", device_id, self.client(request))
            return error(403, "bad signature")
        self.prune()
        token = secrets.token_urlsafe(32)
        self.tokens[token] = (device_id, time.monotonic() + TOKEN_TTL_S)
        async with self.lock:
            devices = self.devices()
            if device_id in devices:
                devices[device_id]["last_seen"] = now_ms()
                write_json(self.devices_path, {"devices": devices})
        return web.json_response({"token": token, "expires_in": TOKEN_TTL_S})

    async def latest(self, request: web.Request) -> web.Response:
        if not self.bearer(request):
            return error(401, "no valid token")
        app = request.match_info["app"]
        idx = self.index(app) if APP_ID.match(app) else None
        if not idx or not idx["releases"]:
            return error(404, f"nothing published for {app}")
        return web.json_response(self.release_view(max(idx["releases"], key=lambda r: r["code"]), app))

    async def apk(self, request: web.Request) -> web.StreamResponse:
        # Enrolled apps download with their token; the download page serves anyone on the LAN or tailnet.
        if not self.bearer(request) and not on_local_network(self.client(request)):
            return error(401, "no valid token")
        app, code = request.match_info["app"], request.match_info["code"]
        path = self.app_dir(app) / f"{int(code)}.apk"
        if not APP_ID.match(app) or not path.is_file():
            return error(404, "no such release")
        idx = self.index(app) or {"app": app, "releases": []}
        rel = next((r for r in idx["releases"] if r["code"] == int(code)), {"code": int(code)})
        filename = apk_filename(idx, rel)
        return web.FileResponse(path, headers={"Content-Type": "application/vnd.android.package-archive",
                                               "Content-Disposition": f'attachment; filename="{filename}"'})

    async def catalog(self, request: web.Request) -> web.Response:
        """Every app with its kept release and debug builds, newest first, for the download page.
        An app is its release id and its debug id together (see `family`)."""
        if not on_local_network(self.client(request)):
            return error(403, "only from the home network or the tailnet")
        apps: dict[str, dict] = {}
        for idx_path in sorted((self.state / "apps").glob("*/index.json")):
            idx = json.loads(idx_path.read_text())
            build = idx.get("build") or "release"
            rels = sorted(idx["releases"], key=lambda r: r["code"], reverse=True)
            entry = apps.setdefault(family(idx), {"app": family(idx), "release": [], "debug": []})
            entry[build] = [self.release_view(r, idx["app"]) | {"build": build, "filename": apk_filename(idx, r)}
                            for r in rels]
        for entry in apps.values():
            newest = (entry["release"] or entry["debug"] or [{}])[0]
            entry["label"] = newest.get("label") or entry["app"]
        listed = [a for a in apps.values() if a["release"] or a["debug"]]
        return web.json_response({"apps": sorted(listed, key=lambda a: a["label"].lower())})

    async def publish(self, request: web.Request) -> web.Response:
        who = await self.tailnet_caller(request, check_node=False)
        if isinstance(who, web.Response):
            return who
        meta, data = None, None
        try:
            reader = await request.multipart()
            async for part in reader:
                if part.name == "meta":
                    meta = json.loads(await part.text())
                elif part.name == "apk":
                    data = await part.read()
            if meta is None or data is None:
                raise ValueError("need a meta part and an apk part")
            app, code, name = meta["app"], int(meta["code"]), str(meta.get("name") or "")
            signer, notes = str(meta["signer"]).lower(), str(meta.get("notes") or "")[:2000]
            label = str(meta.get("label") or "")[:64]
            build = meta.get("build")
            if build not in BUILDS:
                raise ValueError("build must be \"debug\" or \"release\" (is emu-publish up to date?)")
            m = PUBLISHABLE.match(app)
            if not m:
                raise ValueError(f"application id {app!r} is not com.sohambagchi.<app> (lowercase), "
                                 f"or com.sohambagchi.<app>.debug for a debug build")
            if (build == "debug") != bool(m.group(2)):
                raise ValueError(f"{app} is a {build} build; release builds use com.sohambagchi.<app> and debug "
                                 f"builds com.sohambagchi.<app>.debug (applicationIdSuffix = \".debug\")")
            if code <= 0 or not HEX64.match(signer):
                raise ValueError("code must be positive and signer a SHA-256 hex digest")
            if len(data) > MAX_APK or data[:2] != b"PK":
                raise ValueError("apk is not a zip, or too big")
        except (ValueError, KeyError, TypeError) as e:
            return error(400, f"bad publish: {e}")
        async with self.lock:
            with state_lock(self.state):  # held for milliseconds, as a prune is
                idx = self.index(app) or {"app": app, "signer": signer, "build": build, "releases": []}
                if signer != idx["signer"]:
                    return error(409, f"{app} is pinned to signer {idx['signer']}; this APK is signed by {signer}")
                top = max((r["code"] for r in idx["releases"]), default=0)
                if code <= top:
                    return error(409, f"version code {code} is not greater than the published {top}")
                rel = {"code": code, "name": name, "label": label, "build": build, "size": len(data), "sha256": hashlib.sha256(data).hexdigest(),
                       "signer": signer, "notes": notes, "published_at": now_ms(),
                       "published_by": f"{who['login']} on {who['node']}"}
                write_atomic(self.app_dir(app) / f"{code}.apk", data)
                idx["releases"].append(rel)
                write_json(self.app_dir(app) / "index.json", idx)
        log.info("published %s %s (%d) from %s", app, name, code, who["node"])
        return web.json_response(self.release_view(rel, app))

    async def status(self, request: web.Request) -> web.Response:
        who = await self.tailnet_caller(request, check_node=False)
        if isinstance(who, web.Response):
            return who
        apps = {}
        for d in sorted((self.state / "apps").glob("*/index.json")):
            idx = json.loads(d.read_text())
            rels = sorted(idx["releases"], key=lambda r: r["code"])
            apps[idx["app"]] = {"signer": idx["signer"], "build": idx.get("build"),
                                "latest": rels[-1] if rels else None, "releases": len(rels)}
        devices = [{k: d.get(k) for k in ("name", "node", "enrolled_at", "last_seen")} | {"id": i}
                   for i, d in self.devices().items()]
        return web.json_response({"apps": apps, "devices": devices, "listen": self.hosts})

    async def root(self, request: web.Request) -> web.Response:
        return web.FileResponse(PAGE, headers={"Content-Type": "text/html; charset=utf-8"})

    async def health(self, request: web.Request) -> web.Response:
        return web.json_response({"service": "depot", "protocol": 1, "docs": "android-emu/depot/PROTOCOL.md"})

    def app(self) -> web.Application:
        app = web.Application(client_max_size=MAX_APK + 1024 * 1024)
        app.router.add_get("/", self.root)
        app.router.add_get("/v1/health", self.health)
        app.router.add_get("/v1/catalog", self.catalog)
        app.router.add_post("/v1/enroll", self.enroll)
        app.router.add_get("/v1/challenge", self.challenge)
        app.router.add_post("/v1/session", self.session)
        app.router.add_get("/v1/apps/{app}/latest", self.latest)
        app.router.add_get(r"/v1/apps/{app}/{code:\d+}.apk", self.apk)
        app.router.add_post("/v1/publish", self.publish)
        app.router.add_get("/v1/status", self.status)
        return app


async def serve(depot: Depot, port: int) -> None:
    # The forwarded address is logged too, since behind the proxy %a is the proxy.
    runner = web.AppRunner(depot.app(), access_log_format='%a fwd=%{X-Forwarded-For}i "%r" %s %b "%{User-Agent}i"')
    await runner.setup()
    bound = 0
    for host in depot.hosts:
        try:
            await web.SockSite(runner, bind_socket(host, port)).start()
        except OSError as e:
            log.error("cannot listen on %s:%d (%s)", host, port, e.strerror or e)
            continue
        bound += 1
        log.info("listening on http://%s:%d/", host, port)
    if not bound:
        raise SystemExit("depot: no address to listen on")
    await asyncio.Event().wait()


def main() -> None:
    p = argparse.ArgumentParser(prog="depot", description="Serve app updates to enrolled devices (see PROTOCOL.md).")
    p.add_argument("--listen", action="append", metavar="ADDR",
                   help="address to listen on; repeat for LAN and tailnet")
    p.add_argument("--port", type=int, default=8473)
    p.add_argument("--state", type=Path, required=True, help="directory for devices.json and apps/")
    p.add_argument("--login", action="append", metavar="LOGIN",
                   help="Tailscale login allowed to enroll and publish (default: the server's own)")
    p.add_argument("--node", action="append", metavar="NAME",
                   help="if given, only these Tailscale nodes may enroll")
    p.add_argument("--trust-proxy", action="append", metavar="ADDR",
                   help="reverse proxy whose X-Forwarded-For names the real client")
    p.add_argument("--prune", type=int, metavar="KEEP",
                   help="instead of serving, keep each app's KEEP newest versions (debug and release builds "
                        "of one version count once) and each build type's newest, delete the rest, and exit")
    args = p.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    if args.prune is not None:
        if args.prune < 1:
            p.error("--prune must keep at least one release")
        prune(args.state.resolve(), args.prune)
        return
    if not args.listen:
        p.error("--listen is required to serve")
    args.state.mkdir(parents=True, exist_ok=True)
    depot = Depot(args.state.resolve(), args.listen, args.login, args.node, args.trust_proxy)
    asyncio.run(serve(depot, args.port))


if __name__ == "__main__":
    main()
