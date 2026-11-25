#!/usr/bin/env python3
"""End-to-end test of the depot server over HTTP, with a fake `tailscale whois`.

Run: python3 test_depot.py   (needs aiohttp and cryptography; `nix run .#depot-test` provides them)
"""

import asyncio
import base64
import hashlib
import json
import os
import stat
import sys
import tempfile
from pathlib import Path

import aiohttp
from aiohttp import web
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec

sys.path.insert(0, str(Path(__file__).parent))
import depot  # noqa: E402

SIGNER = "ab" * 32


def fake_tailscale(dir: Path, login: str, node: str) -> str:
    path = dir / "tailscale"
    info = {"UserProfile": {"LoginName": login}, "Node": {"ComputedName": node, "Name": node + ".ts.net."}}
    # Records which address it was asked about, then answers.
    path.write_text(f"#!/bin/sh\necho \"$3\" >> {dir}/whois.log\ncat <<'EOF'\n{json.dumps(info)}\nEOF\n")
    path.chmod(path.stat().st_mode | stat.S_IEXEC)
    return str(path)


def sign(key: ec.EllipticCurvePrivateKey, nonce: str, device: str, context: bytes = depot.CONTEXT) -> str:
    return base64.b64encode(key.sign(b"\n".join([context, nonce.encode(), device.encode()]),
                                     ec.ECDSA(hashes.SHA256()))).decode()


def apk_bytes(tag: bytes) -> bytes:
    return b"PK\x03\x04" + tag * 100


async def run(tmp: Path) -> None:
    depot.TAILSCALE = fake_tailscale(tmp, "me@example", "pixel")
    # The test client is 127.0.0.1; `tailnet` decides whether that counts as a tailnet address.
    # Forwarded addresses are judged for real.
    tailnet = {"yes": True}
    real_on_tailnet = depot.on_tailnet
    depot.on_tailnet = lambda addr: tailnet["yes"] if addr == "127.0.0.1" else real_on_tailnet(addr)
    d = depot.Depot(tmp / "state", ["127.0.0.1"], logins=["me@example"], nodes=["pixel"], proxies=["127.0.0.1"])
    runner = web.AppRunner(d.app())
    await runner.setup()
    site = web.SockSite(runner, depot.bind_socket("127.0.0.1", 0))
    await site.start()
    port = site._server.sockets[0].getsockname()[1]
    base = f"http://127.0.0.1:{port}"

    key = ec.generate_private_key(ec.SECP256R1())
    der = key.public_key().public_bytes(serialization.Encoding.DER, serialization.PublicFormat.SubjectPublicKeyInfo)
    key_b64 = base64.b64encode(der).decode()

    async with aiohttp.ClientSession() as http:
        async def post(path, **kw):
            async with http.post(base + path, **kw) as r:
                return r.status, await r.json()

        async def get(path, token=None, fwd=None, full=False):
            headers = {"Authorization": f"Bearer {token}"} if token else {}
            if fwd:
                headers["X-Forwarded-For"] = fwd
            async with http.get(base + path, headers=headers) as r:
                body = await r.read()
                body = json.loads(body) if r.content_type == "application/json" else body
                return (r.status, body, r.headers) if full else (r.status, body)

        async def publish(code, signer=SIGNER, data=None, app="app.test", build="release"):
            form = aiohttp.FormData()
            meta = {"app": app, "code": code, "name": f"0.{code}.0", "label": "Test App", "signer": signer, "notes": "n"}
            if build:
                meta["build"] = build
            form.add_field("meta", json.dumps(meta), content_type="application/json")
            form.add_field("apk", data or apk_bytes(str(code).encode()), filename="a.apk")
            return await post("/v1/publish", data=form)

        async def session(device, k=key, context=depot.CONTEXT):
            _, ch = await get("/v1/challenge")
            return await post("/v1/session", json={"device": device, "nonce": ch["nonce"],
                                                   "sig": sign(k, ch["nonce"], device, context)})

        # Enrollment: refused off the tailnet, accepted on it, idempotent.
        tailnet["yes"] = False
        s, _ = await post("/v1/enroll", json={"name": "phone", "key": key_b64})
        assert s == 403, s
        tailnet["yes"] = True
        s, body = await post("/v1/enroll", json={"name": "phone", "key": key_b64})
        assert s == 200, body
        device = body["device"]
        assert device == "d-" + hashlib.sha256(der).hexdigest()[:16]
        first = d.devices()[device]["enrolled_at"]
        s, body = await post("/v1/enroll", json={"name": "phone2", "key": key_b64})
        assert s == 200 and body["device"] == device
        assert d.devices()[device]["enrolled_at"] == first and d.devices()[device]["name"] == "phone2"
        s, _ = await post("/v1/enroll", json={"name": "x", "key": "bm90IGEga2V5"})
        assert s == 400, s

        # A node outside the list may not enroll.
        depot.TAILSCALE = fake_tailscale(tmp, "me@example", "laptop")
        s, _ = await post("/v1/enroll", json={"name": "x", "key": key_b64})
        assert s == 403, s
        depot.TAILSCALE = fake_tailscale(tmp, "me@example", "pixel")

        # Sessions work off the tailnet; nonces are single use; signatures are bound to the context.
        tailnet["yes"] = False
        s, body = await session(device)
        assert s == 200, body
        token = body["token"]
        s, _ = await session("d-0000000000000000")
        assert s == 401, s
        s, _ = await session(device, context=b"airlock-mobile/1")
        assert s == 403, s
        s, _ = await session(device, k=ec.generate_private_key(ec.SECP256R1()))
        assert s == 403, s
        _, ch = await get("/v1/challenge")
        req = {"device": device, "nonce": ch["nonce"], "sig": sign(key, ch["nonce"], device)}
        assert (await post("/v1/session", json=req))[0] == 200
        assert (await post("/v1/session", json=req))[0] == 403  # replay

        # Nothing published yet; no token, no answer.
        assert (await get("/v1/apps/app.test/latest"))[0] == 401
        assert (await get("/v1/apps/app.test/latest", token))[0] == 404

        # Publishing: tailnet only; codes must rise; the signer is pinned.
        s, _ = await publish(5)
        assert s == 403, s
        tailnet["yes"] = True
        s, rel = await publish(5)
        assert s == 200, rel
        assert rel["sha256"] == hashlib.sha256(apk_bytes(b"5")).hexdigest() and rel["url"] == "/v1/apps/app.test/5.apk"
        assert (await publish(5))[0] == 409
        assert (await publish(4))[0] == 409
        assert (await publish(6, signer="cd" * 32))[0] == 409
        assert (await publish(6, data=b"not a zip"))[0] == 400
        assert (await publish(7))[0] == 200
        tailnet["yes"] = False

        s, latest = await get("/v1/apps/app.test/latest", token)
        assert s == 200 and latest["code"] == 7 and latest["name"] == "0.7.0" and latest["signer"] == SIGNER, latest
        s, body = await get(latest["url"], token)
        assert s == 200 and hashlib.sha256(body).hexdigest() == latest["sha256"]
        assert (await get("/v1/apps/app.test/6.apk", token))[0] == 404
        assert (await get("/v1/apps/..%2Fdevices.json/latest", token))[0] == 404

        # Status is tailnet-only.
        assert (await get("/v1/status"))[0] == 403
        tailnet["yes"] = True
        s, st = await get("/v1/status")
        assert s == 200 and st["apps"]["app.test"]["latest"]["code"] == 7 and st["devices"][0]["id"] == device

        # Behind the proxy, the last X-Forwarded-For entry is the client.
        tailnet["yes"] = False
        whois_log = tmp / "whois.log"
        enroll = {"name": "phone", "key": key_b64}
        s, _ = await post("/v1/enroll", json=enroll, headers={"X-Forwarded-For": "100.101.102.103"})
        assert s == 200, s
        assert whois_log.read_text().split()[-1] == "100.101.102.103"
        s, _ = await post("/v1/enroll", json=enroll, headers={"X-Forwarded-For": "192.168.0.50"})
        assert s == 403, s  # a LAN client through the proxy
        s, _ = await post("/v1/enroll", json=enroll, headers={"X-Forwarded-For": "1.2.3.4, 100.101.102.103"})
        assert s == 200, s
        s, _ = await post("/v1/enroll", json=enroll, headers={"X-Forwarded-For": "100.101.102.103, 192.168.0.50"})
        assert s == 403, s  # a forged entry before the proxy's own is ignored
        d.proxies = set()
        s, _ = await post("/v1/enroll", json=enroll, headers={"X-Forwarded-For": "100.101.102.103"})
        assert s == 403, s  # not from the proxy: the header is ignored
        d.proxies = {"127.0.0.1"}
        s, body = await get("/v1/health")
        assert s == 200 and body["service"] == "depot", body

        # The download page: open to the LAN and the tailnet, never to the internet. Updates
        # (latest) still need an enrolled app's token.
        s, page = await get("/")
        assert s == 200 and b"<title>depot</title>" in page
        for fwd in (None, "192.168.0.50", "100.101.102.103"):
            s, cat = await get("/v1/catalog", fwd=fwd)
            assert s == 200 and [(a["app"], a["code"], a["label"]) for a in cat["apps"]] == [("app.test", 7, "Test App")], cat
        assert (await get("/v1/catalog", fwd="8.8.8.8"))[0] == 403
        s, body, headers = await get("/v1/apps/app.test/7.apk", fwd="192.168.0.50", full=True)
        assert s == 200 and body == apk_bytes(b"7"), s
        assert headers["Content-Disposition"] == 'attachment; filename="app.test-0.7.0.apk"'
        assert (await get("/v1/apps/app.test/7.apk", fwd="8.8.8.8"))[0] == 401
        assert (await get("/v1/apps/app.test/latest", fwd="192.168.0.50"))[0] == 401

        # Debug and release builds: each application id takes one build type.
        tailnet["yes"] = True
        assert (await publish(8, build=None))[0] == 400
        s, body = await publish(8, build="debug")
        assert s == 409 and "applicationIdSuffix" in body["error"], body
        s, rel = await publish(3, app="app.test.debug", build="debug")
        assert s == 200 and rel["build"] == "debug", rel
        assert (await publish(4, app="app.test.debug"))[0] == 409  # a release build under the debug id
        s, cat = await get("/v1/catalog")
        assert [(a["app"], a["build"]) for a in cat["apps"]] == [("app.test", "release"), ("app.test.debug", "debug")], cat
        s, st = await get("/v1/status")
        assert st["apps"]["app.test.debug"]["build"] == "debug" and st["apps"]["app.test"]["build"] == "release"
        tailnet["yes"] = False

        # Revoking the device kills its token.
        tailnet["yes"] = True
        depot.write_json(d.devices_path, {"devices": {}})
        assert (await get("/v1/apps/app.test/latest", token))[0] == 401

        # Pruning keeps the newest releases per app, drops older entries and APKs, and leaves
        # the signer pin and the rising-code rule as they were.
        for code in (8, 9, 10):
            assert (await publish(code))[0] == 200
        assert (await publish(1, app="app.other"))[0] == 200
        apps = tmp / "state" / "apps"
        (apps / "app.test" / "3.apk").write_bytes(b"stray")
        depot.prune(tmp / "state", 3)
        assert [r["code"] for r in d.index("app.test")["releases"]] == [8, 9, 10]
        assert sorted(f.name for f in (apps / "app.test").glob("*.apk")) == ["10.apk", "8.apk", "9.apk"]
        assert [r["code"] for r in d.index("app.other")["releases"]] == [1]
        assert (await publish(9))[0] == 409
        assert (await publish(11, signer="cd" * 32))[0] == 409
        assert (await publish(11))[0] == 200

    await runner.cleanup()


def main() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        asyncio.run(run(Path(tmp)))
    print("depot: all checks passed")


if __name__ == "__main__":
    main()
