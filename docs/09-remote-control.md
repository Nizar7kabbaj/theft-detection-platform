# Remote control
The dev laptop runs every service bound to loopback or a private interface. The phone reaches them through a WireGuard tunnel that terminates inside the home LAN. Laptop sits at `10.8.0.1` on the tunnel, phone at `10.8.0.2`. The tunnel is point-to-point, comes up at boot, and carries no traffic across the public internet. On top of the tunnel sit two more layers: an SSH session from a phone client that opens local port forwards into the laptop's loopback, and the dashboards (Grafana, Netdata, Portainer) reached through those forwards. The Azure Mobile App is a separate channel for the cloud-side resources.

This chapter walks the layers from the bottom up: the WireGuard tunnel, the ufw scope, the phone peer, the SSH forward that bridges loopback, the terminal client on the phone, the web dashboards exposed through the forward, the Grafana mobile app, and the Azure Mobile App.

## WireGuard tunnel
Interface `wg0` listens on UDP 51820, address `10.8.0.1/24`, MTU 1420. Config lives at `/etc/wireguard/wg0.conf`, mode 600, root-owned. The systemd unit `wg-quick@wg0.service` is enabled so the tunnel comes up at boot.

### Why a point-to-point tunnel
Every Grafana, Prometheus, and Tempo port binds to `127.0.0.1` on the laptop. That makes them invisible to the wider LAN and to anything off the laptop, including the phone. WireGuard adds a single private interface the phone can route to. The tunnel doesn't itself protect the laptop on a hostile network — it only gives the phone a path into the laptop's network namespace.

### Keypair
Generated on the laptop with `wg genkey | sudo tee /etc/wireguard/laptop_private.key`, mode 600, root-owned. Public key derived with `wg pubkey`. The private key never leaves `/etc/wireguard/`. The public key goes into the phone's peer config.

### Peer
The phone generates its own keypair on-device through the WireGuard Android app. Its public key gets pasted into `wg0.conf` under a `[Peer]` block with `AllowedIPs = 10.8.0.2/32`. The phone's matching peer block on the phone side points at the laptop's LAN IP `192.168.1.103:51820`, with `Allowed IPs = 10.8.0.0/24` and `Persistent keepalive = 25` to keep NAT mappings alive.

## ufw scope
One rule allows UDP 51820 from the home LAN subnet `192.168.1.0/24` only. Anything off that subnet sees nothing on the port. The default `deny incoming` stance covers everything else.

## Phone setup
WireGuard Android app, tunnel created from scratch. Phone interface address `10.8.0.2/32`. Peer block holds the laptop's public key, endpoint `192.168.1.103:51820`, allowed IPs `10.8.0.0/24`, persistent keepalive 25. Toggle the tunnel on and `sudo wg show` on the laptop displays the latest handshake and byte counters within a second or two.

## Reaching services through the tunnel
Every docker port binding is `127.0.0.1:PORT->PORT`. Loopback isn't the same interface as `wg0`, so `http://10.8.0.1:3000` from the phone reaches the laptop but finds nothing listening. The bridge is SSH local port forwarding from the phone into the laptop's loopback.

One SSH session opens three forwards at once: 3000 for Grafana, 9443 for Portainer, 19999 for Netdata. The phone-side SSH client points at the laptop's tunnel address `10.8.0.1:22`, the forwards land on `127.0.0.1` inside the laptop. From the phone's browser, `http://127.0.0.1:3000` then reaches Grafana through the tunnel and the SSH session.

The cleaner option is binding services to `10.8.0.1` directly in `docker-compose.yml`. That removes SSH from the loop and lets the phone hit `http://10.8.0.1:3000` straight from the browser. Docker has to start after `wg-quick@wg0.service` for the bind to succeed at boot, which a systemd `After=` line handles. Deferred to a follow-up chore.

## Terminal access from the phone
Termius is the SSH client on the phone. It holds the host entry for the laptop (`10.8.0.1`, port 22, user `nizar`), the ed25519 private key imported from Termux during initial setup, and the three port forward rules attached to the host. One tap on the host name brings up the SSH session and the forwards in the same connection.

### Key import
The ed25519 keypair was generated inside Termux with `ssh-keygen -t ed25519` during the WireGuard setup. The public key is appended to `~/.ssh/authorized_keys` on the laptop, labeled `phone-termux`. Termius imports the same private key file from the phone's storage so both clients authenticate as the same identity. Removing phone access later means removing the one labeled line from `authorized_keys`.

### Saved host
The Termius host entry holds:
- Hostname `10.8.0.1`, port 22
- Identity: imported ed25519 key
- Port forward 1: local 3000 → 127.0.0.1:3000 (Grafana)
- Port forward 2: local 9443 → 127.0.0.1:9443 (Portainer)
- Port forward 3: local 19999 → 127.0.0.1:19999 (Netdata)

Connecting to the host opens all three forwards. The phone's browser then reaches each dashboard at its loopback address.

## Web dashboards through the tunnel
Three local dashboards sit behind the SSH forwards. Each binds to `127.0.0.1` on the laptop, none are reachable from the LAN, all three are reachable from the phone once the Termius session is up.

### Grafana
Binds to `127.0.0.1:3000`. Admin user `admin`, password from the `GF_SECURITY_ADMIN_PASSWORD` env var. Anonymous access disabled, signup disabled, telemetry and update checks off. Dashboards provisioned from `config/grafana/dashboards/` and datasources from `config/grafana/provisioning/`. Phone reaches it at `http://127.0.0.1:3000` once the SSH forward is up.

### Netdata
Binds to `127.0.0.1:19999`. No Netdata Cloud — the dashboard sign-in screen gets dismissed with "Skip and use the dashboard anonymously" on first visit. The container runs with `cap_add: SYS_PTRACE` only (no `SYS_ADMIN`), AppArmor `docker-default` kept intact, hostname pinned to `legion-5`. The GPU panels work through an `nvidia` device reservation that makes `nvidia-smi` callable inside the container. Per-process disk I/O columns stay empty because the AppArmor profile plus `kernel.yama.ptrace_scope=1` deny ptrace from a confined container to unconfined host processes. CPU, RAM, network, disk, GPU, and per-container metrics all populate normally.

### Portainer
Binds to `127.0.0.1:9443` over HTTPS with a self-signed cert. Browser accepts the cert warning once and remembers it. Admin user created on first visit and stored in Bitwarden. The container mounts `/var/run/docker.sock` read-write because the point of the tool is start, stop, restart, recreate, exec — read-only would defeat the ticket. The image is distroless, so it ships no shell, no `wget`, no `curl`. The compose service has no healthcheck for that reason. The real health signal is whether the API at `/api/system/status` answers, polled from outside the container if needed.

## Grafana mobile app
The official Grafana iOS and Android app points at the same `http://127.0.0.1:3000` once the SSH forward is up. Same admin credentials. The app is a thin native wrapper around the dashboards, so alert notifications and the time-range picker feel closer to a phone UI than the browser version. The data path is identical — SSH forward → loopback → Grafana container. The app brings nothing the browser can't do, but the alert push integration and the home screen widget make it worth installing on the phone that already runs Termius.

## Azure Mobile App
Separate channel. The Azure Mobile App talks to the Azure Resource Manager API directly over the public internet, signed in with the same AAD account that owns the subscription. It sees the state backend storage account in spaincentral, any cloud resources spun up by future tickets, billing alerts, and AAD activity. It does not see anything on the laptop and does not go through WireGuard. Useful for catching a billing alert or a runaway resource from the phone without opening the portal.

## Lessons that cost time
The first `wg genkey` pipeline ran from the repo root after a `cd` failure went unnoticed. `sudo tee laptop_private.key` then dropped the keys into the repo working tree instead of `/etc/wireguard/`. The `*.key` pattern in `.gitignore` caught them so nothing leaked, but the stale files sat at the repo root until they got noticed. The fix is writing absolute paths into `sudo tee` and never trusting that `cd /etc/wireguard` succeeded.

`wg-quick up wg0` parses the whole config before bringing the interface up, and a malformed peer key kills the load. Putting a placeholder string in `[Peer] PublicKey =` to fill in later doesn't work — `wg setconf` rejects the file and tears the interface back down. The phone peer block has to be omitted from `wg0.conf` until the real key exists, then added with `wg set wg0 peer <key> allowed-ips 10.8.0.2/32` for the live interface and appended to the config for persistence across reboot.

SSH on the laptop is key-only from the linux-setup chapter (`PasswordAuthentication no`). Phone-side SSH clients that have no key get rejected with `Permission denied (publickey,keyboard-interactive)` and the server refuses to fall back to a password prompt. The fix is generating an ed25519 keypair on the phone with `ssh-keygen -t ed25519` and appending the phone's public key to `~/.ssh/authorized_keys` on the laptop with a clear label.

The phone's WireGuard endpoint shows up in `wg show` as the phone's LAN IP, not its carrier-side public IP. That confirms the tunnel terminates inside the LAN and no traffic crosses the public internet on this leg. The Azure relay for off-LAN access is a separate ticket in the cloud deployment epic.

The Netdata compose healthcheck shipped with `wget --spider` against the local API. The Netdata image has `wget` in newer builds but the version that landed didn't, so the check failed every 30s and the container stayed `unhealthy` despite the API answering on 19999. Swapping to `curl -fsS http://127.0.0.1:19999/api/v1/info > /dev/null` fixed it. Probe with `docker exec <container> sh -c 'command -v curl; command -v wget; command -v nc'` before writing a healthcheck — the image's tool set is the constraint, not the syntax.

The Portainer image is distroless. No shell, no `curl`, no `wget`, no probe possible from inside. Same trap as the mongodb-exporter and alloy from the observability sprint. The compose service ships without a healthcheck for that reason. The real health indicator is the API at `/api/system/status` answering from outside the container, the same way Prometheus `up{}` covers the other distroless services in the stack.
