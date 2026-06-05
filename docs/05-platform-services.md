# Platform Services

The backend depends on four local services during development: MongoDB, Redis, Prometheus, and Grafana. Each runs in Docker on the dev laptop, published on loopback only. This doc covers what runs, why, and how to operate each one.

## Local MongoDB

The development MongoDB instance runs in Docker on the developer machine.
Production still uses MongoDB Atlas. The local copy lets the dev loop work
offline and removes Atlas as a hard dependency for testing platform-services
work.

### Why Docker, not a host install

The original plan was a host-installed MongoDB Community 7 from the official
apt repository. Two real problems blocked that path on this machine:

1. The official repo doesn't publish packages for Ubuntu 26.04 (resolute).
   MongoDB's currently-supported codenames stop at noble (24.04). Upstream
   warns against the standard fallback of pointing 26.04 at the noble suite.

2. MongoDB 8.x has a hard refusal to start on Linux kernel 6.19 and newer, due
   to an upstream incompatibility between the kernel's restartable-sequences
   interface and the TCMalloc version vendored into 8.x. This machine runs
   kernel 7.0. MongoDB 7.0 doesn't have the kernel check, but its apt packages
   only reach jammy (22.04), two LTS versions behind.

Docker sidesteps both problems. The official `mongo:7` image runs on any host
kernel because the affected TCMalloc version isn't in it. The image is the
same MongoDB Inc. binary, packaged differently. All hardening requirements
still apply: auth, TLS, loopback-only bind, smoke test.

### What runs

A single service in the project's `docker-compose.yml`:

```
service:     mongo
image:       mongo:7.0
container:   theft-mongo
port:        127.0.0.1:27017 (host) -> 27017 (container)
restart:     unless-stopped
healthcheck: mongosh ping over TLS, every 30s
```

Two bind mounts and one named volume:

```
infrastructure/mongodb/mongod.conf  ->  /etc/mongo/mongod.conf       (ro)
/etc/mongod-tls/mongod.pem          ->  /etc/mongo/tls/mongod.pem    (ro)
mongo_data (named)                  ->  /data/db
```

The container's mongod runs as UID 999 with supplementary group 972 added so
it can read the cert file. GID 972 belongs to the host's `mongo-cert` group,
which owns the TLS files at `/etc/mongod-tls/`.

### TLS

The certificate is self-signed, generated locally with openssl, valid for five
years. SAN covers `localhost` and `127.0.0.1`, which is enough for
loopback-only access.

```
location:     /etc/mongod-tls/mongod.pem
ownership:    root:mongo-cert (GID 972)
permissions:  640
expiry:       2031
```

The same file is both the server certificate and the CA file. MongoDB
7.0 requires a CA file when `requireTLS` is set, and a self-signed cert is its
own CA. Clients trust it by pointing `--tlsCAFile` at the same path.

The public cert lives at a host-readable location in the developer's home
directory for clients running outside the container. The private key stays in
`/etc/mongod-tls/`, reachable only to root and members of `mongo-cert`.

### Authentication

Two users exist in the database. Both passwords live in the password manager,
not in any file on disk and not in any committed config.

```
admin (in admin database)
  roles:   userAdminAnyDatabase, dbAdminAnyDatabase, readWriteAnyDatabase
  purpose: user management and break-glass access

theft_app (in theft_detection_db)
  roles:   readWrite on theft_detection_db only
  purpose: application connection from the backend
```

The localhost exception created the admin user — the one-time mongod
allowance that lets the first connection from `127.0.0.1` create a user when
zero users exist. That exception closes after the first user is created.

Password rotation: update the password manager entry first, then run
`db.changeUserPassword` inside mongosh authenticated as admin.

### Operating the service

```bash
# Start
docker compose up -d mongo

# Stop
docker compose stop mongo

# Status + recent logs
docker compose ps mongo
docker logs theft-mongo --tail 50
```

The healthcheck runs every 30 seconds. A healthy container shows
`Status: Up (healthy)`. Unhealthy means look at the logs first, since mongod's
startup errors are usually plain English.

### Connecting from the host

`mongosh` is not installed on the host. Connections go through `docker exec`
into the container's bundled mongosh. The host-readable cert exists for the
future case of a Python client (Motor) or another tool running directly on the
host without Docker.

```bash
docker exec -i theft-mongo mongosh \
  --tls \
  --tlsCAFile /etc/mongo/tls/mongod.pem \
  --tlsAllowInvalidHostnames \
  --quiet
```

Pass the username and password to `db.auth()` once inside the shell. The
`--tlsAllowInvalidHostnames` flag is acceptable for self-signed local trust;
the cert chain is still verified.

### Connecting from the backend

`backend/.env` holds two MongoDB URLs:

```
MONGODB_URL_LOCAL   local Docker mongo, TLS, theft_app credentials
MONGODB_URL         Atlas, production fallback
```

The backend code currently reads `MONGODB_URL`. Switching the code to prefer
`MONGODB_URL_LOCAL` when present is a separate backend change. Both URLs being
defined now means the wiring is ready when that change lands.

### Atlas fallback

The Atlas cluster stays provisioned and reachable through the `MONGODB_URL`
connection string. The dev loop runs against local Docker. Prod-parity
testing runs against Atlas by pointing the backend at `MONGODB_URL` directly.

### Troubleshooting

#### Container crashes with "kernel 6.19+ incompatible"

The image tag is `mongo:8` or later. Pin to `mongo:7.0` in
`docker-compose.yml`. The TCMalloc fix isn't in any 8.x release yet.

#### Container crashes with "TLS without chain of trust no longer supported"

`mongod.conf` is missing the `CAFile` line under `net.tls`. Add:

```yaml
CAFile: /etc/mongo/tls/mongod.pem
```

Same path as `certificateKeyFile`. The self-signed cert serves as its own CA.

#### Container starts but clients can't connect

```bash
docker compose ps mongo
```

If `Status` is unhealthy, look at logs:

```bash
docker logs theft-mongo --tail 50
```

A "Permission denied" line on `/etc/mongo/tls/mongod.pem` means either the
`group_add: ["972"]` in compose isn't propagating, or the host file
permissions drifted:

```bash
sudo ls -la /etc/mongod-tls/
```

Files should be mode 640 owned `root:mongo-cert`. Directory should be mode
750.

#### Atlas connection works, local connection doesn't

Usually the local URL has an unencoded special character in the password.
Connection strings need `@`, `/`, `:`, and `#` URL-encoded (`%40`, `%2F`,
`%3A`, `%23`). Atlas-generated passwords contain those often. Regenerate the
local password as alphanumeric-only to avoid this.

#### Smoke test

```bash
docker exec -i theft-mongo mongosh \
  --tls \
  --tlsCAFile /etc/mongo/tls/mongod.pem \
  --tlsAllowInvalidHostnames \
  --quiet
```

```javascript
use theft_detection_db
db.auth("theft_app", "<password>")
db.smoke_test.insertOne({ test: "roundtrip", at: new Date() })
db.smoke_test.findOne({ test: "roundtrip" })
db.smoke_test.deleteMany({ test: "roundtrip" })
```

A successful round-trip prints an `ObjectId`, the inserted document, and a
deletion count of 1.

## Local Redis

### Why Docker, not host apt

The Redis apt repo serves Ubuntu 26.04, and Redis 7 has none of the libc-adjacent kernel issues that forced MongoDB into Docker. A host install would have worked. Docker won out anyway because the next ticket in this epic puts Redis in `docker-compose.yml`, so installing on host now would mean tearing it down and redoing the same work in Docker an hour later.

Pinned to `redis:7.2-alpine`. The 7.2.x line is the last under plain 3-Clause BSD. From 7.4.0 onward Redis dual-licenses under RSALv2/SSPLv1, which is fine for a research project but matters for any future industrial partnership. Pinning to `7.2` (not the floating `7-alpine` tag) keeps the line BSD across image rebuilds.

### Why no TLS

MongoDB runs with TLS even on loopback. Redis doesn't.

The argument for TLS on a loopback port is defense in depth: a local-process compromise can't sniff plaintext. The argument against is that the same local process can usually read `/proc/<pid>/environ` or similar, which means TLS doesn't actually raise the bar much against the only attacker who could reach `127.0.0.1` in the first place. The cost is real: cert lifecycle, a dedicated `redis-cert` group, client-side TLS args in every consumer.

Mongo has TLS because Atlas mandates it in production and local dev should mirror that. Azure Cache for Redis offers TLS too, and the Terraform module ticket wires it on. Local dev runs `requirepass` over loopback only, which is the standard Redis pattern for a single-machine setup.

### Permissions model

The Redis config file holds the `requirepass` value as plaintext. It can't live in the repo. Same problem as the Mongo TLS cert, solved the same way:

- Live config: `infrastructure/redis/redis.conf`, owner `root`, group `redis-conf` (GID 971), mode 640
- Template: `infrastructure/redis/redis.conf.example`, world-readable, placeholder where the password belongs
- Gitignore covers the live file; the template is committed
- Container runs as UID 999 (the redis user inside the alpine image) and joins GID 971 via `group_add`

The container needs `user: "999:999"` set explicitly. Without it, the alpine entrypoint starts as root and drops to redis via `gosu`, which resets supplementary groups and silently discards the `group_add: ["971"]`. With `user:` set, the container starts as 999 directly and the group_add survives.

### Config summary

```conf
bind 0.0.0.0          # inside container only, loopback enforced by compose port map
port 6379
protected-mode yes
requirepass <40-char alphanumeric, in password manager>
appendonly yes        # AOF on
appendfsync everysec  # good durability/performance balance, Redis default
save ""               # RDB off, AOF is the only persistence path
```

### Smoke test

```bash
docker exec -i theft-redis redis-cli -a "$REDIS_PASSWORD" --no-auth-warning <<'EOF'
PING
SET smoke:test "roundtrip"
GET smoke:test
DEL smoke:test
EOF
```

Healthy output: `PONG`, `OK`, `roundtrip`, `1`.

### Known startup warning

```
WARNING Memory overcommit must be enabled! ... add 'vm.overcommit_memory = 1' to /etc/sysctl.conf
```

This affects Redis's background save fork behavior under memory pressure. Not blocking on a 16 GB laptop with this workload, but for prod-parity it should be set on the eventual deployment host. Should be a deliberate host change, not a side-effect of installing Redis.

### Troubleshooting

#### Container restarts with "Fatal error, can't open config file ... Permission denied"

The `user: "999:999"` directive is missing from the compose service, or GID 971 doesn't exist on the host, or the config file isn't group-owned by `redis-conf`. Check in that order.

#### redis-cli returns NOAUTH or WRONGPASS

`$REDIS_PASSWORD` in the shell doesn't match what's in `redis.conf`. Either the shell variable expired (new terminal session — re-source from Bitwarden) or someone edited `redis.conf` without updating Bitwarden + `.env`.

#### Healthcheck unhealthy but logs look fine

The compose healthcheck reads `requirepass` from the mounted config file and authenticates. If the file isn't readable from inside the container (back to the perms issue above) the healthcheck silently fails. Run `docker exec theft-redis cat /etc/redis/redis.conf | head -1` to check readability from the container's perspective.

## Local Prometheus

Metrics scraping for the dev stack. Server runs in Docker on `127.0.0.1:9090`, scrapes itself plus three exporters every 15 seconds, keeps 30 days of history.

### Why Docker

Prometheus's Ubuntu apt package is the v2 line, currently 2.55, EOL since December 2024. The maintained line is v3.x and Ubuntu doesn't ship it. Docker gives the upstream binary directly.

The exporter ecosystem ships only as Docker images. Mixing host-installed Prometheus with containerised exporters means juggling two networking models, which is the kind of complexity worth avoiding when nothing forces it.

Version pinning matters for reproducibility. The pin is `prom/prometheus:v3.12.0`, current stable at install time. Re-pin to the next LTS when one is declared. The 3.5 LTS expires July 31 2026 and the next isn't named yet.

### What runs

Five containers handle observability:

- `theft-prometheus`: the server. Scrapes, stores, queries.
- `theft-node-exporter`: host metrics. CPU, memory, disk, network, processes.
- `theft-mongodb-exporter`: Mongo metrics via the `theft_monitor` user.
- `theft-redis-exporter`: Redis metrics using the existing local password.
- The backend's `/metrics` endpoint exists as a stubbed scrape target in `prometheus.yml.example`, commented out until the backend instrumentation change lands.

Every port is published on `127.0.0.1` only.

### Why no auth

Same argument as Redis no-TLS. Prometheus has no native auth (the options are `web.yml` with bcrypt hashes or a reverse proxy with basic auth). On a loopback-published port, the marginal security bar is small: any local-process attacker who reaches `127.0.0.1:9090` can also read `/proc/<pid>/environ` and the env files compose loaded. The cost of cert and hash management doesn't earn its keep at this scope.

The asymmetry with Mongo (which runs TLS + auth even on loopback) is deliberate. Mongo holds project data. Prometheus holds operational metrics.

Azure-side Prometheus runs behind auth when that ticket lands.

### Permissions model

Mirrors the Redis and Mongo pattern.

- Host group `prom-conf`, GID 1971.
- `infrastructure/prometheus/prometheus.yml` lives at mode 640, owner root, group prom-conf.
- Container starts as user `nobody` (UID 65534), picks up `prom-conf` (GID 1971) as a supplementary group via compose `group_add`.

That membership lets the container read the config without giving it broader host access. Live config is gitignored. Template at `infrastructure/prometheus/prometheus.yml.example` is world-readable and committed.

### Scrape configuration

Global scrape interval: 15 seconds. Default value, fine for the stack's size.

Retention: 30 days, set via `--storage.tsdb.retention.time=30d`. Longer than the 15-day default because cross-week comparisons matter for performance work and PFE-report numbers.

Five jobs: `prometheus` (self-scrape), `node` (host), `mongodb`, `redis`, `backend` (stubbed). Targets resolve via docker-compose DNS, so each service name is a hostname inside the prometheus container.

Disk budget rule of thumb: at 15s scrape across four exporters, expect roughly 50 MB/day on the TSDB. 30 days fits comfortably in the named volume.

### The Mongo monitoring user

A dedicated user with the `clusterMonitor` role, not the admin account.

User: `theft_monitor`, role: `clusterMonitor` on the `admin` database.

`clusterMonitor` is a Mongo built-in role that grants read access to monitoring commands (`serverStatus`, `connPoolStats`, `replSetGetStatus`, `dbStats`) and read-only access to internal monitoring collections. It cannot read application data, cannot write anything, cannot change configuration.

Principle of least privilege. The exporter only needs metrics access. If the monitoring user's password leaks, the blast radius is "someone can read aggregate stats," not "someone has full database control."

Password lives only in `backend/.env` (gitignored, mode 600) and the password manager. Hash-verified on the way in to confirm no corruption between the openssl generation and the .env append.

### Operating the service

```bash
# Start everything
docker compose up -d

# Just the observability stack
docker compose up -d prometheus node-exporter mongodb-exporter redis-exporter

# Stop
docker compose stop prometheus node-exporter mongodb-exporter redis-exporter

# Status + recent logs
docker compose ps
docker compose logs --tail=50 prometheus
```

### Smoke test

```bash
# Server health
curl -s http://127.0.0.1:9090/-/healthy

# Targets, all four should report state="up"
curl -s http://127.0.0.1:9090/api/v1/targets \
  | python3 -c "import sys, json; [print(f\"{x['labels']['job']:15} {x['health']}\") for x in json.load(sys.stdin)['data']['activeTargets']]"
```

Expected: `Prometheus Server is Healthy.` from the first call, and `up` against every job from the second.

### Troubleshooting

#### Target stuck in "down" state

Check the target's `lastError` field in `/api/v1/targets` output. Common causes:

- mongodb exporter shows "auth failed": the `theft_monitor` user password in `.env` doesn't match what Mongo expects. Verify by re-authenticating with mongosh using the value from `.env`. Rotate if needed.
- redis exporter shows "WRONGPASS": same kind of mismatch on the Redis side. Check that `REDIS_PASSWORD_LOCAL` in `.env` matches the password embedded in `REDIS_URL_LOCAL`.
- node exporter shows "connection refused": the node-exporter container isn't running. `docker compose ps node-exporter` confirms.

#### Permission denied reading prometheus.yml

Container can't read the bind-mounted config. Two checks:

- File ownership: `stat -c '%a %U:%G' infrastructure/prometheus/prometheus.yml` should return `640 root:prom-conf`.
- Container's group_add: `docker inspect theft-prometheus --format '{{.HostConfig.GroupAdd}}'` should include `1971`.

If both look correct, recreate the container: `docker compose up -d --force-recreate prometheus`.

#### TSDB growing faster than expected

`du -sh /var/lib/docker/volumes/theft-detection-platform_prometheus_data` shows on-disk size. If it grows past expectations, the usual culprit is a high-cardinality label in a scrape config. Anything that emits unique IDs as labels explodes the series count fast.

#### Port 9090 already in use

Another local process has the port. `sudo lsof -iTCP:9090` identifies it. Either kill the conflict or remap to a different loopback port in compose (`127.0.0.1:9091:9090` works).

## Local Grafana

Visualisation layer for the local Prometheus instance. Server runs in Docker on `127.0.0.1:3000`, reads its datasource config from a provisioning YAML at boot, stores its own state in a named volume.

### Why Docker

Same reasoning as Prometheus. Grafana's Ubuntu apt package lags upstream by several point releases. The Docker image tracks current stable directly. Pinning to `grafana/grafana:12.4.4` gives the same fixed version everywhere and re-pinning later is one line in `docker-compose.yml`.

Grafana retired its formal LTS line around v9. The current model is rolling stable releases with roughly nine months of patch backports. Re-pin when the next minor lands or when a security fix forces it, whichever comes first.

### What runs

One container: `theft-grafana`. Port 3000 published on the loopback only. Its sqlite database, plugin install directory, dashboard versions, and user state all live in the `grafana_data` named volume, so `docker compose down` doesn't wipe the install.

On first boot Grafana auto-installs four Grafana Labs drilldown plugins (pyroscope, traces, metrics, loki). They land in the named volume and persist across restarts. First-boot takes around two minutes for the plugin downloads, subsequent boots are under ten seconds.

### TLS off, admin password on

Same loopback reasoning as Prometheus. The browser talks to Grafana over plain HTTP on `127.0.0.1`, and any local process that reaches that port can also read the env files compose loaded. A self-signed cert on loopback buys nothing.

The admin password is a different question. Grafana ships with `admin/admin` as the default, which is worse than no auth: tools fingerprint that combo on sight. A 32-byte random admin password is set on first boot via the `GF_SECURITY_ADMIN_PASSWORD` env var, generated with `openssl rand -base64 32`, stored only in `backend/.env` and the password manager, hash-verified end-to-end.

### Permissions model

Same shape as Mongo, Redis, and Prometheus.

- Host group `grafana-conf`, GID 1972.
- `infrastructure/grafana/provisioning/datasources/prometheus.yml` lives at mode 640, owner root, group grafana-conf.
- Container starts as user `grafana` (UID 472), picks up `grafana-conf` (GID 1972) as a supplementary group via compose `group_add`.

The provisioning directory is bind-mounted read-only into the container at `/etc/grafana/provisioning`. Even if Grafana is compromised, the YAML on the host can't be written from inside the container. Live config is gitignored. Template at `infrastructure/grafana/provisioning/datasources/prometheus.yml.example` is world-readable and committed.

### Provisioning

Datasources, dashboards, and alerts can all be declared as YAML files dropped into the provisioning directory. Grafana reads them on every boot and applies them. Anything declared this way is `readOnly` in the UI: the only way to change it is to edit the file on disk.

Today's setup provisions one datasource. The Prometheus instance, marked default, pointing at the docker-internal hostname `theft-prometheus:9090`. Dashboards and alerts land in later tickets via the same mechanism.

The `editable: false` flag in the YAML maps to `readOnly: true` on the datasource API. This is intentional. All datasource changes go through git, never through the UI.

### How the admin password reaches the container

The compose service references `${GF_SECURITY_ADMIN_PASSWORD}` in its `environment:` block. Compose substitutes the value at startup from `backend/.env`, found via the `.env` symlink at the repo root. The variable lands in the container's environment only because the service explicitly asks for it, not because the whole env file was sourced.

Other variables in `backend/.env` are not visible to the Grafana container.

### Operating the service

```bash
# Start everything
docker compose up -d

# Just Grafana
docker compose up -d grafana

# Stop
docker compose stop grafana

# Status + recent logs
docker compose ps grafana
docker compose logs --tail=50 grafana
```

### Smoke test

```bash
# Server health
curl -sf http://127.0.0.1:3000/api/health | python3 -m json.tool
```

```bash
# Datasource list (uses admin password from .env, value never on screen)
GF_PASS=$(grep '^GF_SECURITY_ADMIN_PASSWORD=' backend/.env | cut -d= -f2-)
curl -sf -u "admin:${GF_PASS}" http://127.0.0.1:3000/api/datasources | python3 -m json.tool
unset GF_PASS
```

```bash
# Datasource end-to-end health (Grafana actually reaches Prometheus)
GF_PASS=$(grep '^GF_SECURITY_ADMIN_PASSWORD=' backend/.env | cut -d= -f2-)
curl -sf -u "admin:${GF_PASS}" http://127.0.0.1:3000/api/datasources/uid/prometheus-local/health | python3 -m json.tool
unset GF_PASS
```

Expected: `database: ok` from the first call, one entry with `uid: prometheus-local` and `readOnly: true` from the second, `status: OK` from the third.

### Browser check

Open `http://127.0.0.1:3000`. Login as `admin` with the password from the password manager. No "change your password" prompt should appear, because the env-var path skips the first-login rotation flow. Left sidebar > Explore > query box (Code mode) > `up` > Run query. Four series should return, each with value `1`.

### Troubleshooting

#### Login fails with "invalid username or password"

The password in `backend/.env` and the password manager have drifted. Recover by hashing both and comparing.

```bash
# Hash of the value currently in .env
grep '^GF_SECURITY_ADMIN_PASSWORD=' backend/.env | cut -d= -f2- | tr -d '\n' | sha256sum
```

Compare against the hash stored in the password manager entry's notes field. If they don't match, the password manager is authoritative: copy the correct value back into `.env` and recreate the container with `docker compose up -d --force-recreate grafana`.

#### Datasource health check returns "no such host"

Grafana can't resolve `theft-prometheus` on the docker network. Two checks:

- Both containers on the same network: `docker network inspect theft-detection-platform_default` should list both `theft-grafana` and `theft-prometheus` in the Containers section.
- Prometheus actually running: `docker compose ps prometheus` should show `(healthy)`.

If Prometheus is down, start it first; Grafana's healthcheck will recover on its own within a minute.

#### Healthcheck stuck in "starting" after two minutes

First boot pulls four drilldown plugins which can take longer than the `start_period`. Watch the logs:

```bash
docker compose logs --tail=20 grafana | grep -i plugin
```

If plugins are still installing, wait it out. If you see no plugin activity and the boot looks idle, check the volume: `docker volume inspect theft-detection-platform_grafana_data` should show a mountpoint with files in it. An empty volume after first boot means Grafana failed to write its sqlite db, usually a permissions issue on the volume.

#### Provisioned datasource not appearing in the UI

Grafana logs the provisioning pass on startup. Look for the file by name:

```bash
docker compose logs grafana | grep -i provision
```

If the file is mentioned but ignored, the YAML structure is wrong. Common cause: `apiVersion` missing or set to something other than `1`. Compare against `prometheus.yml.example` byte-for-byte.

If the file isn't mentioned at all, the bind-mount didn't land. Check `docker inspect theft-grafana --format '{{range .Mounts}}{{println .Source " -> " .Destination}}{{end}}'` and confirm the provisioning path is mapped to `/etc/grafana/provisioning`.

#### Port 3000 already in use

A frontend dev server (Next.js, Vite, CRA) defaults to 3000. `sudo lsof -iTCP:3000` identifies the conflict. Either stop the other process or remap Grafana to a different loopback port in compose (`127.0.0.1:3001:3000` works, and update the password manager entry's URL field to match).
