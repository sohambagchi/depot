# depot sits behind buckwheat's HTTPS proxy and trusts only its X-Forwarded-For

**Status:** accepted

**Context:** depot is served at `https://depot.wheat.sohambagchi.com`: Caddy on buckwheat (100.77.198.14) ends TLS and forwards plain HTTP to malt at 100.97.41.27:8473. depot decides who may enroll and publish from the caller's address and `tailscale whois`, and through the proxy every connection comes from buckwheat, the user's own node. The name resolves to buckwheat's LAN address, so the proxy is reached from the home LAN.
**Decision:**
- **Proxy trust.** depot takes the caller's address from the last `X-Forwarded-For` entry, but only on connections from `--trust-proxy` (buckwheat); elsewhere it ignores the header.
- **Listening.** depot listens on malt's tailnet address only. Apps try the HTTPS name first, then `http://100.97.41.27:8473`.
- **Enrolling and publishing.** These need a tailnet caller, which the proxy never forwards, so both use the direct address. WireGuard encrypts that path.
- **How it runs.** depot runs on malt as a systemd user service, as airlockd does.
**Alternatives:**
- **Trusting `X-Forwarded-For` from anyone:** any tailnet node could claim to be any address.
- **Using the proxy's own address:** every LAN device could enroll as buckwheat.
- **Keeping depot's own LAN listener (192.168.0.102):** a cleartext LAN path, a DHCP-lease dependency, and a firewall change that needs a system rebuild.
- **The NixOS system service:** needs a sudo rebuild for no gain over a user service. It stays available as `nixosModules.depot`.
**Consequences:**
- **Cleartext.** Apps still allow cleartext HTTP, for the direct tailnet address.
- **Away from home.** Off the LAN, the HTTPS name doesn't resolve to anything reachable, so apps fall back to the tailnet.
- **If buckwheat changes.** If buckwheat's address changes, or another proxy is added, `--trust-proxy` must follow, or enrollment through it stops working. It fails closed.
