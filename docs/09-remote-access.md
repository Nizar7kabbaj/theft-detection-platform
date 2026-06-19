# Remote access
The dev laptop runs every service bound to loopback or a private interface. The phone reaches them through a WireGuard tunnel that terminates inside the home LAN. Laptop sits at `10.8.0.1` on the tunnel, phone at `10.8.0.2`. The tunnel is point-to-point, comes up at boot, and carries no traffic across the public internet.

This chapter covers the laptop side, the ufw scope, the phone peer, and the workaround for reaching loopback-bound services through the tunnel.

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
Every docker port binding is `127.0.0.1:PORT->PORT`. Loopback isn't the same interface as `wg0`, so `http://10.8.0.1:3000` from the phone reaches the laptop but finds nothing listening. The current bridge is SSH local port forwarding from the phone.

Termux on the phone runs an `ssh` command that opens three forwards in one session: 3000 for Grafana, 9000 for Portainer, 19999 for Netdata. The SSH key authentication side uses an ed25519 keypair generated inside Termux, with the phone's public key appended to `~/.ssh/authorized_keys` on the laptop and labeled `phone-termux` so future audits can tell it apart from the laptop's self-key. A bash alias `grafana` in `~/.bashrc` on the phone makes the full SSH command a one-word invocation.

The cleaner option is binding services to `10.8.0.1` directly in `docker-compose.yml`. That removes SSH from the loop and lets the phone hit `http://10.8.0.1:3000` straight from the browser. Docker has to start after `wg-quick@wg0.service` for the bind to succeed at boot, which a systemd `After=` line handles. Deferred to a follow-up chore.

## Lessons that cost time
The first `wg genkey` pipeline ran from the repo root after a `cd` failure went unnoticed. `sudo tee laptop_private.key` then dropped the keys into the repo working tree instead of `/etc/wireguard/`. The `*.key` pattern in `.gitignore` caught them so nothing leaked, but the stale files sat at the repo root until they got noticed. The fix is writing absolute paths into `sudo tee` and never trusting that `cd /etc/wireguard` succeeded.

`wg-quick up wg0` parses the whole config before bringing the interface up, and a malformed peer key kills the load. Putting a placeholder string in `[Peer] PublicKey =` to fill in later doesn't work — `wg setconf` rejects the file and tears the interface back down. The phone peer block has to be omitted from `wg0.conf` until the real key exists, then added with `wg set wg0 peer <key> allowed-ips 10.8.0.2/32` for the live interface and appended to the config for persistence across reboot.

SSH on the laptop is key-only from the linux-setup chapter (`PasswordAuthentication no`). Phone-side SSH clients that have no key get rejected with `Permission denied (publickey,keyboard-interactive)` and the server refuses to fall back to a password prompt. The fix is generating an ed25519 keypair on the phone with `ssh-keygen -t ed25519` and appending the phone's public key to `~/.ssh/authorized_keys` on the laptop with a clear label.

The phone's WireGuard endpoint shows up in `wg show` as the phone's LAN IP, not its carrier-side public IP. That confirms the tunnel terminates inside the LAN and no traffic crosses the public internet on this leg. The Azure relay for off-LAN access is a separate ticket in the cloud deployment epic.
