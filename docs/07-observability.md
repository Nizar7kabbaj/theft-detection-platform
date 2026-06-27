# Observability

A full observability stack runs locally on the dev laptop: metrics scraped by Prometheus, dashboards rendered by Grafana, logs aggregated by Loki via Alloy, traces stored in Tempo, and alerts routed through Alertmanager to the notification-service webhook that forwards to Telegram. Three application services emit OpenTelemetry signals into that stack: backend, ai, and notification-service.

Everything below covers one component at a time: what runs, the config that matters, the smoke tests that prove it works, and the troubleshooting steps for the failures that actually happened during setup.

The three-signal model sits at the center. Metrics tell you something is wrong, logs tell you what was happening, traces tie them to a single request across services. Every component in this chapter exists to keep those three signals correlated end-to-end.

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

Password lives only in `services/api/.env` (gitignored, mode 600) and the password manager. Hash-verified on the way in to confirm no corruption between the openssl generation and the .env append.

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

## NVIDIA GPU exporter

GPU metrics for the dev laptop's RTX 3070: utilisation, memory used, temperature, power draw, clock speeds. The exporter wraps `nvidia-smi` and publishes a Prometheus-format endpoint that the local Prometheus scrapes alongside every other target.

### Why this exporter

Two real options exist for GPU metrics on a Linux box: `utkuozdemir/nvidia_gpu_exporter` (a single binary that shells out to `nvidia-smi`) and NVIDIA's own DCGM exporter (a daemon that talks to the DCGM library). DCGM is the production answer at scale: lower overhead, richer metrics, multi-GPU aware. For one GPU on a dev laptop it's overkill. The exporter in use is one container, one config-free image, one scrape job. The metric set covers everything a single-GPU AI pipeline needs to debug.

### Version pin

The image is pinned to `1.4.1`. Version `1.2.0` had a panic bug that crash-looped the container on certain `nvidia-smi` output formats. Floating versions through that release would silently break the scrape with no obvious cause from Prometheus's side: the target just shows down. `1.4.1` is the first version after the fix that the project has been on long enough to trust. Upgrades through 1.5+ require a smoke test before the bump lands.

### What runs

`theft-nvidia-gpu-exporter` on `127.0.0.1:9835`. The container reserves access to the nvidia driver with `count: all` (one GPU on this box, so "all" = the RTX 3070). It joins two host groups via `group_add`:

- `44` (video) — read access to `/dev/nvidia*` device nodes
- `990` (the host's nvidia-container group on Ubuntu) — needed for the container runtime hook to expose the device cleanly

Both group IDs are host-specific. On a different machine the second one (990) may differ; check with `getent group | grep -i nvidia` if the container fails to start with a permission error on a device node.

Healthcheck is a bash TCP probe on port 9835. If the exporter is alive it listens; if `nvidia-smi` is broken the exporter starts but returns nothing useful on scrape, which Prometheus catches separately.

### Scrape configuration

In `config/prometheus/prometheus.yml`:

```yaml
  - job_name: nvidia-gpu
    static_configs:
      - targets:
          - nvidia-gpu-exporter:9835
        labels:
          service: theft-nvidia-gpu-exporter
```

Same scrape interval as everything else (15s). No relabelling. The `service` label is set explicitly so Loki / Tempo correlation queries can join on it the same way they do for the application services.

### Operating the service

```bash
# Start everything
docker compose up -d

# Just the exporter
docker compose up -d nvidia-gpu-exporter

# Status + recent logs
docker compose ps nvidia-gpu-exporter
docker compose logs --tail=50 nvidia-gpu-exporter
```

### Smoke test

```bash
# Exporter reachable
curl -sf http://127.0.0.1:9835/metrics | head -5
```

```bash
# Prometheus has the target as up
curl -s http://127.0.0.1:9090/api/v1/targets \
  | python3 -c "import sys,json; r=json.load(sys.stdin); [print(t['labels'].get('job'), t['health']) for t in r['data']['activeTargets'] if t['labels'].get('job')=='nvidia-gpu']"
```

```bash
# Sample metric: current GPU utilisation
curl -s 'http://127.0.0.1:9090/api/v1/query?query=nvidia_smi_utilization_gpu_ratio' \
  | python3 -m json.tool
```

Expected: the `/metrics` call returns a long block of `nvidia_smi_*` series with HELP and TYPE comments. The targets call returns `nvidia-gpu up`. The utilisation query returns a value between 0 and 1.

### Troubleshooting

#### Container starts then exits immediately

`docker compose logs nvidia-gpu-exporter` will show one of two things: a Go panic stack trace, or a "failed to exec nvidia-smi" error. The panic is the v1.2.0 bug — confirm the image tag is `1.4.1`. The exec error means the nvidia-container-toolkit isn't wired up on the host. Check `nvidia-smi` works on the host first; if it does, check `/etc/docker/daemon.json` has the nvidia runtime configured and reboot Docker.

#### Target down but exporter running

`docker compose ps` shows the exporter healthy, but Prometheus reports the target down. The exporter binds inside the container; the Prometheus container reaches it by service name on the Docker network. If the network has been rebuilt without recreating Prometheus, the DNS cache may be stale. Recreate:

```bash
docker compose up -d --force-recreate prometheus
```

#### Metrics endpoint returns 200 but no nvidia_smi_* series

`nvidia-smi` ran inside the container but returned no GPU. Usually means the `deploy.resources.reservations.devices` block is missing or the GPU is being held by another process. Confirm with:

```bash
docker compose exec nvidia-gpu-exporter nvidia-smi
```

If that fails or shows no GPU, the device wasn't passed through. If it succeeds and the exporter still returns nothing, restart the exporter — the SDK initialises GPU access at startup, not per-scrape.

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

The admin password is a different question. Grafana ships with `admin/admin` as the default, which is worse than no auth: tools fingerprint that combo on sight. A 32-byte random admin password is set on first boot via the `GF_SECURITY_ADMIN_PASSWORD` env var, generated with `openssl rand -base64 32`, stored only in `services/api/.env` and the password manager, hash-verified end-to-end.

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

The compose service references `${GF_SECURITY_ADMIN_PASSWORD}` in its `environment:` block. Compose substitutes the value at startup from `services/api/.env`, found via the `.env` symlink at the repo root. The variable lands in the container's environment only because the service explicitly asks for it, not because the whole env file was sourced.

Other variables in `services/api/.env` are not visible to the Grafana container.

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
GF_PASS=$(grep '^GF_SECURITY_ADMIN_PASSWORD=' services/api/.env | cut -d= -f2-)
curl -sf -u "admin:${GF_PASS}" http://127.0.0.1:3000/api/datasources | python3 -m json.tool
unset GF_PASS
```

```bash
# Datasource end-to-end health (Grafana actually reaches Prometheus)
GF_PASS=$(grep '^GF_SECURITY_ADMIN_PASSWORD=' services/api/.env | cut -d= -f2-)
curl -sf -u "admin:${GF_PASS}" http://127.0.0.1:3000/api/datasources/uid/prometheus-local/health | python3 -m json.tool
unset GF_PASS
```

Expected: `database: ok` from the first call, one entry with `uid: prometheus-local` and `readOnly: true` from the second, `status: OK` from the third.

### Dashboards

Three dashboards ship with the stack, one per application service. Each lives as a JSON file under `config/grafana/dashboards/` and is loaded by the provisioner at startup. The `dashboards.yml` provider has `disableDeletion: true` and `allowUiUpdates: false`, so the JSON files in git are the source of truth. The Grafana UI is read-only for these three.

The split is deliberate. One dashboard per service keeps the panels focused, the queries cheap, and the time picker meaningful: an AI debugging session and a backend latency investigation almost never want the same time range or the same data. A single mega-dashboard would force every panel to share both.

#### Backend HTTP (`uid: backend-http`)

The HTTP entry path. Every panel here drives off the FastAPI server-side histogram `http_server_duration_milliseconds_*` and the active-requests gauge.

| Panel                       | Query                                                                                            | Answers                                       |
|-----------------------------|--------------------------------------------------------------------------------------------------|-----------------------------------------------|
| Request rate                | `sum(rate(http_server_duration_milliseconds_count{job="backend"}[1m]))`                          | Traffic level right now                       |
| Overall latency p95         | `histogram_quantile(0.95, sum by (le) (rate(..._bucket{job="backend"}[5m])))`                    | Is the service slow                           |
| Error rate (5xx)            | `sum(rate(..._count{...,http_status_code=~"5.."}[5m])) / sum(rate(..._count{job="backend"}[5m]))` | Server-side failure ratio                     |
| In-flight requests          | `sum(http_server_active_requests{job="backend"})`                                                | Concurrency, queue pressure                   |
| Latency p95 by route        | `histogram_quantile(0.95, sum by (le, http_target) (...))`                                       | Which endpoint is slow                        |
| 4xx by route                | `sum by (http_target) (rate(..._count{...,http_status_code=~"4.."}[1m]))`                        | Which endpoint clients are hitting wrong      |
| 5xx by route                | same with `5..`                                                                                  | Which endpoint is breaking                    |
| Response size p95 by route  | `histogram_quantile(0.95, sum by (le, http_target) (rate(http_server_response_size_bytes_bucket[5m])))` | Payload size outliers          |

The first four panels are the overview. The bottom four are the breakdown that tells you which route is causing the overview to misbehave.

#### AI Pipeline (`uid: ai-pipeline`)

The inference path. Two domain metrics from `services/ai/app/observability.py`, five GPU metrics from the nvidia-gpu-exporter.

| Panel                            | Query                                                                                                      | Answers                                            |
|----------------------------------|------------------------------------------------------------------------------------------------------------|----------------------------------------------------|
| FPS per session                  | `rate(theft_ai_frames_processed_total[1m])`                                                                | Frames per second per camera session               |
| Inference latency p95 per session| `histogram_quantile(0.95, sum by (le, session_id) (rate(theft_ai_inference_duration_milliseconds_bucket[5m])))` | Per-frame inference cost, broken out by session |
| GPU utilisation                  | `nvidia_smi_utilization_gpu_ratio`                                                                         | Is the GPU saturated                               |
| GPU temperature                  | `nvidia_smi_temperature_gpu`                                                                               | Thermal headroom                                   |
| VRAM used                        | `nvidia_smi_memory_used_bytes`                                                                             | Memory pressure                                    |
| VRAM used (percent)              | `nvidia_smi_memory_used_bytes / nvidia_smi_memory_total_bytes`                                             | Same, normalised                                   |
| GPU power draw                   | `nvidia_smi_power_draw_watts`                                                                              | Energy footprint, thermal cause indicator          |

The `session_id` label on the AI metrics is the bridge between application-level FPS and physical-level GPU stats. When FPS drops on one session, the GPU panels show whether it was the camera (no work to do), the model (low utilisation, low power, low temp), or thermal throttling (high temp, dropping clocks).

#### Notification Service (`uid: notification-service`)

The webhook → Telegram path. Domain metrics from `services/notification/app/metrics.py`.

| Panel                          | Query                                                                                                  | Answers                                           |
|--------------------------------|--------------------------------------------------------------------------------------------------------|---------------------------------------------------|
| Webhook rate by outcome        | `sum by (result) (rate(theft_alert_webhooks_total[1m]))`                                               | Are inbound webhooks landing                      |
| Telegram messages by outcome   | `sum by (result) (rate(theft_alert_telegram_messages_total[1m]))`                                      | Are outbound Telegrams sending                    |
| Webhook latency quantiles      | `histogram_quantile(0.50/0.95/0.99, sum by (le) (rate(theft_alert_webhook_duration_seconds_bucket[5m])))` | End-to-end webhook processing time             |
| Webhook accept ratio (5m)      | `accepted / total`                                                                                     | Stat panel: how clean the inbound stream is       |
| Telegram send ratio (5m)       | `sent / total`                                                                                         | Stat panel: how reliable Telegram delivery is     |
| Process memory                 | `process_resident_memory_bytes{job="notification-service"}`, `_virtual_memory_bytes`                          | Memory leak detection                             |

The two stat panels are the canary view. Both should sit near 100% in steady state. Anything below 99% means alertmanager is sending rejected webhooks, or Telegram is failing to deliver, and the timeseries above show the pattern.

The webhook duration histogram has explicit buckets (0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0 seconds) pinned in `services/notification/app/observability.py`. See the OpenTelemetry section below for why.

#### How to edit a dashboard

Because `allowUiUpdates: false`, edits in the Grafana UI don't persist. The workflow is:

1. Make the change in the UI to test it (any user can do this in their browser session).
2. Use the "JSON Model" tab in the dashboard settings to copy the updated JSON.
3. Paste over the corresponding file in `config/grafana/dashboards/`.
4. `docker compose restart grafana` to reload provisioning.

The provider polls every 30 seconds for file changes (`updateIntervalSeconds: 30`), so on most edits the restart isn't needed — the file change picks up on the next poll. The restart is for cases where Grafana caches a panel definition aggressively.

### Browser check

Open `http://127.0.0.1:3000`. Login as `admin` with the password from the password manager. No "change your password" prompt should appear, because the env-var path skips the first-login rotation flow. Left sidebar > Explore > query box (Code mode) > `up` > Run query. Four series should return, each with value `1`.

### Troubleshooting

#### Login fails with "invalid username or password"

The password in `services/api/.env` and the password manager have drifted. Recover by hashing both and comparing.

```bash
# Hash of the value currently in .env
grep '^GF_SECURITY_ADMIN_PASSWORD=' services/api/.env | cut -d= -f2- | tr -d '\n' | sha256sum
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

## Local Loki

Log aggregation backend paired with Alloy as the shipper. Loki runs on `127.0.0.1:3100`, stores chunks and indices in a named volume, retains seven days of logs. Alloy tails Docker container logs via the daemon socket and forwards them.

### Why Loki

Prometheus solves metrics. Logs are the other half of the same problem. `docker logs <name>` only shows one container at a time, the buffer rotates, and nothing persists across a recreate. A log aggregator removes those constraints: every container ships to one place, retention is enforced server-side, queries cross sources.

Loki was picked because it speaks the same operational model as Prometheus (label-based storage, time-windowed queries, Grafana as the front end) and runs in a single binary. The alternatives — Elasticsearch, Splunk, Datadog — all add either heavy infrastructure (Elasticsearch's JVM and cluster overhead) or external SaaS dependencies. Loki on filesystem storage fits the laptop footprint.

### Why Alloy and not Promtail

Promtail was the original Loki agent. Grafana Labs deprecated it in February 2025 and end-of-lifed it on March 2, 2026. No more security patches, no more bug fixes. The migration target is Alloy, Grafana Labs' OpenTelemetry-based collector that absorbed Promtail's feature set.

Picking Alloy here means the agent stays maintained, the config syntax is the one Grafana Labs will keep developing, and adding traces or profiles later doesn't require swapping the agent — Alloy already speaks OTLP.

### What runs

Two containers. `theft-loki` on port 3100, loopback only, with `loki_data` named volume mounted at `/loki` for chunks, index, compactor working directory. `theft-alloy` with its config at `/etc/alloy/config.alloy` and three bind mounts: the Docker socket read-only, `/var/lib/docker/containers` read-only for log file access, and an `alloy_data` named volume for its own write-ahead log buffer.

Alloy exposes a debug UI on `127.0.0.1:12345` showing component health and pipeline state. Useful when a forwarding rule misbehaves.

### Permissions model

Loki follows the named-volume pattern. The official image runs as UID 10001 and Docker chowns the volume mountpoint to match on first start. No host-side chown needed.

Alloy is the exception: it runs as root inside the container. Reading the Docker socket and tailing `/var/lib/docker/containers/` both need root because those paths are owned by root on the host. The mitigations: the Alloy port is loopback only, the socket is mounted read-only, and the containers directory is mounted read-only. Alloy can read everything Docker exposes but cannot write to the socket or kill containers.

### Loki configuration

`infrastructure/loki/loki-config.yml` is bind-mounted read-only into the container at `/etc/loki/loki-config.yml`. The config is committed, contains no secrets, and uses the TSDB index store with schema v13 — the current recommendation for fresh deployments.

Retention is `168h` (seven days). The compactor enforces it: without `retention_enabled: true` and `delete_request_store: filesystem`, retention is declared but never applied and chunks accumulate forever.

`analytics.reporting_enabled: false` matches the same posture used for Grafana. No usage data leaves the host.

### Alloy configuration

`infrastructure/alloy/config.alloy` uses River syntax — Alloy's component-based config language. Four components wire into a pipeline:

1. `discovery.docker "containers"` polls the Docker socket every 5s for the running container list.
2. `discovery.relabel "containers"` cleans the raw Docker metadata into Loki labels: container name (slash stripped), compose service name, log stream (stdout vs stderr).
3. `loki.source.docker "containers"` reads log lines from the discovered targets.
4. `loki.write "local"` ships lines to `http://theft-loki:3100/loki/api/v1/push`.

New containers get picked up automatically on the next discovery refresh. Removed containers stop being scraped without explicit cleanup.

### Loki datasource in Grafana

A second provisioning file at `infrastructure/grafana/provisioning/datasources/loki.yml` registers Loki as a non-default datasource with `uid: loki-local`. Same permissions model as the Prometheus one: mode 640, owner root, group grafana-conf, gitignored, template committed as `loki.yml.example`. Grafana reads provisioning files only at startup, so a `docker compose restart grafana` is required after the file lands.

### Operating the service

```bash
# Start everything
docker compose up -d

# Just Loki and Alloy
docker compose up -d loki alloy

# Stop
docker compose stop alloy loki

# Status + recent logs
docker compose ps loki alloy
docker compose logs --tail=50 loki
docker compose logs --tail=50 alloy
```

### Smoke test

```bash
# Loki ready
curl -sf http://127.0.0.1:3100/ready
```

```bash
# Labels Loki has indexed (proves Alloy is shipping)
curl -sf http://127.0.0.1:3100/loki/api/v1/labels | python3 -m json.tool
```

```bash
# Real log lines from mongo over the last five minutes
curl -sf -G 'http://127.0.0.1:3100/loki/api/v1/query_range' \
  --data-urlencode 'query={container="theft-mongo"}' \
  --data-urlencode 'limit=5' \
  --data-urlencode "start=$(date -d '5 minutes ago' +%s)000000000" \
  --data-urlencode "end=$(date +%s)000000000" \
  | python3 -m json.tool | head -40
```

Expected: `ready` from the first call, a `data` array containing at minimum `container`, `service`, `stream`, `job` from the second, a `result` array with mongo log lines from the third.

### Browser check

Open `http://127.0.0.1:3000`. Login as admin. Left sidebar > Connections > Data sources. Two entries should appear: Prometheus (default) and Loki. Left sidebar > Explore. Switch the datasource selector from Prometheus to Loki. Query `{container="theft-mongo"}` over the last 15 minutes. Log lines render with a histogram of log volume at the top. Try `{job="docker"}` to pull from every container at once.

### Troubleshooting

#### Loki datasource missing from the UI after the file is in place

Grafana provisioning runs once at startup. If `loki.yml` lands after Grafana is already up, the file is ignored until the next boot. Restart Grafana:

```bash
docker compose restart grafana
docker logs theft-grafana 2>&1 | grep -i 'inserting datasource'
```

The log line `inserting datasource from configuration name=Loki uid=loki-local` confirms the file was picked up.

#### Alloy starts but no labels appear in Loki

Alloy can be running and still not shipping if discovery fails. Check the Alloy debug UI at `http://127.0.0.1:12345` — the `discovery.docker` component should show targets equal to the running container count. Zero targets means the Docker socket bind mount is missing or wrong. Verify:

```bash
docker inspect theft-alloy --format '{{range .Mounts}}{{println .Source " -> " .Destination}}{{end}}'
```

The socket should map `/var/run/docker.sock -> /var/run/docker.sock` and the containers directory should map `/var/lib/docker/containers -> /var/lib/docker/containers`. Both must be read-only.

#### LogQL query returns nothing even though Alloy is shipping

Either the time range is wrong or the label value is. Loki rejects queries against samples older than the retention window. Pull the actual label values Loki sees:

```bash
curl -sf 'http://127.0.0.1:3100/loki/api/v1/label/container/values' | python3 -m json.tool
```

Compare against the container name in the query. The leading slash from raw Docker metadata is stripped by the relabel rule, so the value is `theft-mongo`, not `/theft-mongo`.

#### Loki container restart loop with "permission denied" on /loki

The named volume lost its UID 10001 ownership, usually after a manual chown attempt. Easiest fix: stop Loki, remove the volume, recreate.

```bash
docker compose stop loki
docker volume rm theft-detection-platform_loki_data
docker compose up -d loki
```

Historical logs are lost. For a real outage this is the wrong fix; for a dev environment it's the cheap one.

#### Port 3100 already in use

Another Loki, a Tempo distributor sharing the port, or rarely a misconfigured frontend. `sudo lsof -iTCP:3100` identifies the conflict. Remap in compose if Loki must coexist with something on the same port.

## Local OpenTelemetry

Three services on the stack are instrumented: `backend`, `ai`, and `notification-service`. Each one emits three signals — traces, metrics, structured JSON logs — and each signal carries the same `trace_id`. That's what turns three independent streams into one click-through view of a single request.

### Why three signals

Each signal answers a different question. Metrics tell you something is wrong: latency climbed, error rate spiked, GPU memory pressure. They don't tell you which request was affected. Logs record what happened during one request once you've grouped the right lines. Traces connect the request to the work it caused, every database query, every gRPC call between services, every outbound HTTP, with timing on each step.

Without correlation, an operator hops between three tools and a clock. With correlation, one click on a log line opens the trace, one click on a trace opens its logs, one click on a metric exemplar opens the trace that produced the slow observation.

### The three lanes
```
backend ──┐                         ┌─► tempo:3200

ai        ├─[OTLP HTTP traces]─► alloy:4318

alert     ──┘                       └─► (trace storage + service graph)
backend ──┐

ai        ├─[stdout JSON]─► alloy (socket tail) ─► loki:3100

alert     ──┘
backend ◄─┐

ai        ◄┼─[Prometheus pulls /metrics:9464]─── prometheus:9090

alert     ◄┘
```
Two lanes go through Alloy. Alloy already ships every container's stdout to Loki, and it speaks OTLP natively, so the `otelcol.receiver.otlp` + `processor.batch` + `exporter.otlphttp` blocks cost one container less than running a dedicated collector.

Metrics is the exception. Prometheus pulls each service's `:9464` endpoint directly. That matches the existing pattern for `node-exporter`, `mongodb-exporter`, `redis-exporter`, `nvidia-gpu-exporter`, and keeps the metrics pipeline boring.

### What each service instruments

| Service        | HTTP/gRPC              | DB / outbound | Background | Domain instruments                                                                                          |
|----------------|------------------------|---------------|------------|--------------------------------------------------------------------------------------------------------------|
| `backend`      | FastAPI                | pymongo       | —          | (none in observability module)                                                                              |
| `ai`           | gRPC server            | —             | —          | `theft_ai_frames_processed` (counter), `theft_ai_inference_duration` (histogram, ms)                        |
| `notification-service`| gRPC server + requests | —             | Celery     | `theft_alert_webhooks_total`, `theft_alert_telegram_messages_total`, `theft_alert_webhook_duration_seconds` |

Backend covers the HTTP entry path and the Mongo client. ai covers the inference RPC plus two domain instruments for frames-through and per-frame latency. notification-service covers the gRPC handoff from ai, the outbound `requests` call to Telegram, the Celery task that does the actual send, plus three domain instruments tied to the webhook → Telegram path.

### Histogram units

OTel's default histogram buckets assume the recorded value is in milliseconds. The `theft_ai_inference_duration` histogram in `services/ai/app/observability.py` records milliseconds, so the defaults fit. The `theft_alert_webhook_duration_seconds` histogram records seconds. At default buckets every sub-second observation lands in the first non-zero bucket and the p95 / p99 lose all signal. The notification-service module pins explicit buckets via an SDK `View`:

```python
_WEBHOOK_DURATION_BUCKETS = (0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0)
```

Range sized for Telegram round-trip plus webhook handling. Either match the buckets to the unit, or pin them.

### How correlation works

Three Grafana datasource settings turn three independent streams into a click-through graph.

Loki's `derivedFields` runs a regex against every log line returned by a query, pulls the `trace_id` value out of the JSON, and renders it as a clickable button pointing at the Tempo datasource. Click the field, jump to the trace.

Tempo's `tracesToLogsV2` does the reverse hop. In a trace view, a "Logs for this span" button issues a Loki query of the form `{service="theft-backend"} |= "$${__span.traceId}"` and returns every log line that mentions the trace.

Prometheus's `exemplarTraceIdDestinations` handles the metrics-to-trace hop. The OTel SDK attaches an exemplar, a sample observation paired with the `trace_id` that produced it, to histogram metrics. Grafana renders those as clickable dots over the graph that open the trace in Tempo.

The three settings live in each datasource's provisioning YAML. No code change to add, remove, or retune.

### Service identity

Each service identifies itself with four resource attributes:
```
service.name           theft-backend | theft-ai | notification

service.namespace      theft

service.version        0.1.0

deployment.environment local
```
These come from environment, not code. The SDK reads `OTEL_RESOURCE_ATTRIBUTES` automatically and merges it into the Resource that `Resource.create(...)` returns. The Python code only sets `service.name` explicitly; everything else rides the env var. That keeps deployment differences (dev / staging / prod, version bumps from CI) out of Python.

Inside the modules each service exposes the same entry point:

```python
setup_observability(service_name="theft-backend")    # backend takes an app arg too
setup_observability(service_name="theft-ai")
setup_observability(service_name="notification")
```

Each module wires the instrumentors that service actually uses. Backend wires FastAPI + pymongo. ai wires the gRPC server. notification-service wires the gRPC server + `requests` (Telegram and webhook callbacks) + Celery. All three share the trace exporter, the Prometheus metric reader on port 9464, the `LoggingInstrumentor` for trace_id injection into log records, and the `python-json-logger` stdout handler.

The three observability modules are nearly identical and will graduate into a shared internal package once the next round of refactoring lands. Tempo's `metrics_generator` is already configured with `service-graphs` and `span-metrics`, so the Grafana service map renders the call graph between backend → ai → notification-service without extra config.

### What runs

`theft-tempo` on `127.0.0.1:3200` (HTTP query), `4317` (OTLP gRPC), `4318` (OTLP HTTP), all loopback only. Named volume `tempo_data` at `/var/tempo` for blocks and WAL. Bind-mounted `infrastructure/tempo/tempo.yml`, read-only, owner root, group tempo-conf (GID 1973), mode 640. Compactor retention 168h matching Loki.

### The env block

Backend reads OTel env from `services/api/.env`:
```
OTEL_SERVICE_NAME=theft-backend

OTEL_RESOURCE_ATTRIBUTES=service.namespace=theft,deployment.environment=local,service.version=0.1.0

OTEL_EXPORTER_OTLP_ENDPOINT=http://theft-alloy:4318

OTEL_EXPORTER_OTLP_PROTOCOL=http/protobuf

OTEL_TRACES_EXPORTER=otlp

OTEL_METRICS_EXPORTER=prometheus

OTEL_LOGS_EXPORTER=none

OTEL_PYTHON_LOG_FORMAT=%(asctime)s %(levelname)s [%(name)s] [trace_id=%(otelTraceID)s span_id=%(otelSpanID)s] %(message)s

PROMETHEUS_EXPORTER_PORT=9464
```
`ai` and `notification-service` declare the same vars inline in their compose `environment:` blocks, overriding `OTEL_SERVICE_NAME` and `OTEL_RESOURCE_ATTRIBUTES` per service.

`OTEL_LOGS_EXPORTER=none` is set deliberately. Logs ship as JSON on stdout, not via OTLP. Setting it to anything else creates a second log path competing with the Alloy socket-tail one and breaks the correlation story.

### Operating the services

```bash
# Start the default stack (backend, notification-service, observability)
docker compose up -d

# Start with the AI profile (adds the ai service)
docker compose --profile ai up -d

# Just Tempo
docker compose up -d tempo

# Recreate after .env edits
docker compose up -d --force-recreate backend
docker compose --profile ai up -d --force-recreate ai
docker compose up -d --force-recreate notification-service

# Status + recent logs
docker compose ps tempo backend ai notification-service
docker compose logs --tail=50 tempo
```

The `ai` service sits behind `profiles: ["ai"]` because the laptop's GPU isn't always needed (writing docs, running tests, working on iac). Default-on services can't declare a hard `depends_on` against a profile-gated service, so `ai` starts independently when the profile is active.

### Smoke test

```bash
# Tempo ready
curl -sf http://127.0.0.1:3200/ready
```

```bash
# Generate a trace by hitting the backend
curl -sf http://127.0.0.1:8000/api/stats/ > /dev/null
```

```bash
# Search for traces from theft-backend in the last 15 minutes
curl -sf -G 'http://127.0.0.1:3200/api/search' \
  --data-urlencode 'tags=service.name=theft-backend' \
  --data-urlencode 'limit=5' \
  --data-urlencode "start=$(date -d '15 minutes ago' +%s)" \
  --data-urlencode "end=$(date +%s)" \
  | python3 -m json.tool | head -40
```

```bash
# Confirm every service scrapes healthy on Prometheus
curl -s http://127.0.0.1:9090/api/v1/targets \
  | python3 -c "import sys,json; r=json.load(sys.stdin); [print(t['labels'].get('job'), t['health']) for t in r['data']['activeTargets']]" \
  | sort -u
```

Expected: `ready` from the first call. A `traces` array from the third, each entry carrying `rootServiceName: theft-backend` and a non-empty `spanSet` with the FastAPI server span and its pymongo children. The fourth lists every job, backend, ai (when the profile is up), notification-service, plus the exporters, all `up`.

### Browser check

Open `http://127.0.0.1:3000` and go to Explore. With Loki selected, query `{service="theft-backend"}` over the last 15 minutes. Each JSON log line carries a `trace_id` field rendered as a clickable button. Click it. Tempo opens the trace with the FastAPI SERVER span at the root and pymongo CLIENT spans below. Click "Logs for this span" inside the Tempo panel: Grafana switches back to Loki with the same trace id pre-filled in the query bar.

For a cross-service trace, hit an endpoint that touches inference (any path that calls into `ai` over gRPC) and search Tempo for `service.name=theft-backend` over the last few minutes. Each result spans all three services: FastAPI server span at the root, a gRPC CLIENT span for the backend → ai hop, a gRPC SERVER span on `ai`, and downstream a gRPC CLIENT span for ai → notification-service when an alert fires. The Grafana service map renders the same graph visually.

### Troubleshooting

#### Tempo target shows up=0 in Prometheus

Tempo's own metrics scrape lives on `tempo:3200/metrics`. If the target is down, Tempo itself is not ready. `docker compose logs tempo` usually shows a config parse error or a permissions issue on `/var/tempo`. The named volume should be owned by 10001:10001 inside the container. Docker handles that on first create, so a manual chown attempt is the usual cause of breakage. Stop Tempo, remove `tempo_data`, restart:

```bash
docker compose stop tempo
docker volume rm theft-detection-platform_tempo_data
docker compose up -d tempo
```

Historical traces are lost. For a dev environment this is the cheap fix.

#### Traces visible in Tempo but log lines carry no trace_id

The logging instrumentation didn't load. Two common causes: the stdlib logger was reconfigured after `setup_observability` ran, or the JSON log format env var is missing the `%(otelTraceID)s` / `%(otelSpanID)s` placeholders. Check the running env:

```bash
docker compose exec backend env | grep OTEL_PYTHON_LOG_FORMAT
```

If the trace fields aren't in the format string, the JSON line will have a `trace_id` of empty.

#### No exemplars on Prometheus graphs

Exemplars require both the SDK side (OTel histogram exporters attach them by default) and the Prometheus side (`--enable-feature=exemplar-storage`, which the Prometheus container already runs with). If the dots don't appear, the metric in question is likely a counter or a gauge. Exemplars only attach to histograms in the current spec. Switch the query to a histogram metric like `http_server_duration_seconds_bucket` or `theft_alert_webhook_duration_seconds_bucket`.

#### Histogram p95/p99 look identical to p50

Default OTel buckets fit millisecond observations. If you add a histogram in seconds and don't pin a `View` with the right boundaries, every sub-second observation lands in the first bucket. Either record in milliseconds (matches `theft_ai_inference_duration`), or pin explicit buckets (`theft_alert_webhook_duration_seconds` is the reference).

## Alertmanager

The last hop in the observability stack. Prometheus rules fire, Alertmanager groups and routes them, notification-service receives the webhook and forwards to Telegram. The phone buzzes, the operator looks at the dashboard, the loop closes.

### Why a separate service

Prometheus can technically fire alerts on its own, but it doesn't deduplicate, group, silence, or route to multiple receivers. Alertmanager handles those four jobs. Even with a single receiver today, the split is worth keeping: silences during planned work, grouping on noisy alerts, and any future split (email for non-urgent, Telegram for urgent, PagerDuty for production) all live on the Alertmanager side without touching Prometheus.

### Rules

Three rule groups live in `config/prometheus/rules/`, one per concern. Each group evaluates every 30s.

| File          | Alert                  | Expression (short)                                              | Severity |
|---------------|------------------------|-----------------------------------------------------------------|----------|
| `backend.yml` | `BackendHigh5xxRate`   | 5xx ratio > 1% sustained for 5 minutes                          | warning  |
| `ai.yml`      | `AiServiceLowFps`      | FPS < 5 for 2 minutes while the session was active in last 5m   | warning  |
| `node.yml`    | `NodeDiskUsageHigh`    | root filesystem > 80% for 10 minutes                            | warning  |

Each rule labels the firing alert with `severity` and `service` so Alertmanager can group on the latter and the Telegram message can colour-code on the former. Annotations carry the human-readable summary and the description with templated values (`{{ $value | humanizePercentage }}`).

Every rule today is `severity=warning`. The inhibit rule in Alertmanager (critical suppresses warning for the same `(alertname, service)` pair) is forward-looking: it sits ready for the first `severity=critical` rule that lands, without changing routing.

The `AiServiceLowFps` expression has a second clause (`rate(theft_ai_frames_processed_total[5m]) > 0`) so the alert only fires for sessions that were recently active. A camera turned off shouldn't trigger a low-FPS warning forever.

### Routing

`config/alertmanager/alertmanager.yml`:

```yaml
route:
  receiver: notification-service-webhook
  group_by:
    - alertname
    - service
  group_wait: 30s
  group_interval: 5m
  repeat_interval: 4h
```

One receiver. Group on `(alertname, service)`. Hold new alerts in a group for 30 seconds before sending the first notification (`group_wait`), so a burst of related firings collapses into one Telegram message. Wait 5 minutes between updates for an evolving group (`group_interval`). Repeat unresolved alerts every 4 hours (`repeat_interval`) — long enough not to spam, short enough that an alert sitting unaddressed for a workday gets a second nudge.

`send_resolved: true` is set on the webhook receiver. When the underlying condition clears, Alertmanager fires a resolved notification with `status: "resolved"`. The notification-service formats those distinctly so the operator knows the page is over.

### Webhook receiver

`services/notification/app/api/webhooks.py` exposes one route:
```
POST /webhooks/alertmanager

Authorization: Bearer <token>
```
Three things happen on each request:

1. **Token check.** `require_bearer_token` reads the token from a mounted file (cached via `@lru_cache(maxsize=1)` — see token rotation below), parses the `Authorization` header, and compares with `secrets.compare_digest`. Constant-time compare defeats timing-attack discovery of the token value. Wrong scheme, missing token, or mismatch all return 401 and increment `theft_alert_webhooks_total{result="unauthorized"}`.
2. **Payload parse.** FastAPI validates the JSON body against the `AlertmanagerWebhook` Pydantic schema. Unknown fields are ignored (`extra="ignore"`), camelCase field names from Alertmanager (`startsAt`, `groupKey`, `externalURL`) map to snake_case Python via field aliases. Malformed payloads fail at validation with a 422 — those aren't counted on the outcome metric because they never reach the handler body.
3. **Forward to Telegram.** The schema's `to_telegram_html()` method builds an HTML message — alert name, severity, service, summary, and a group-size hint if the batch has more than one alert. Every field passes through `html.escape()` first, so an alert label containing `<script>` or `&` gets neutralised before it reaches Telegram. The send call runs in a thread (`asyncio.to_thread`) because the underlying `requests` call is synchronous.

The outcome metric covers five terminal states: `accepted`, `unauthorized`, `misconfigured`, `telegram_unconfigured`, `telegram_failed`. The Notification Service dashboard's "Webhook accept ratio (5m)" stat panel watches the ratio of `accepted` over total.

`webhook_duration_seconds` records the full handler duration in a `finally` block, so failed requests still get measured. The histogram has explicit second-scaled buckets — see the OpenTelemetry section.

### The token

The token is a 32-byte base64 string generated once and shared between Alertmanager (which sends it as `Bearer`) and notification-service (which validates it). It's not in git. The file lives at `config/alertmanager/webhook_token` on the host, bind-mounted into both containers read-only.

Generate:

```bash
openssl rand -base64 32 | tr -d '\n' > config/alertmanager/webhook_token
chmod 644 config/alertmanager/webhook_token
```

`chmod 644` matters. Alertmanager runs as uid 65534, notification-service as uid 1000. `chmod 600` with owner `nizar:nizar` would let notification-service read it (uid match) but not Alertmanager. The file is gitignored, the parent directory is `0755`, and the mount is `:ro` inside both containers. A 644 mode on a gitignored file in a personal directory is acceptable here.

#### Token rotation

The token is cached in notification-service via `@lru_cache(maxsize=1)`. Writing a new value to the file doesn't take effect until the process restarts or the cache is cleared. Workflow:

```bash
# Generate new value
openssl rand -base64 32 | tr -d '\n' > config/alertmanager/webhook_token
chmod 644 config/alertmanager/webhook_token

# Recreate both consumers (restart isn't enough for bind-mount changes)
docker compose up -d --force-recreate alertmanager notification-service
```

`docker compose restart` won't pick up the new file content reliably because bind-mounts are resolved at container creation time. `--force-recreate` is the safe move.

### What runs

`theft-alertmanager` on `127.0.0.1:9093`. Bind-mounts `config/alertmanager/alertmanager.yml` and `config/alertmanager/webhook_token`, both read-only. Storage volume for silences and notification state. Prometheus scrapes `alertmanager:9093/metrics` for its own health.

### Operating the service

```bash
# Start everything
docker compose up -d

# Just alertmanager + notification-service
docker compose up -d alertmanager notification-service

# Reload alertmanager config after editing the YAML
# (--web.enable-lifecycle is enabled in the compose command)
curl -X POST http://127.0.0.1:9093/-/reload

# Reload prometheus rules after editing a file under config/prometheus/rules/
docker compose restart prometheus
```

Prometheus 3.x disables the `/-/reload` endpoint by default — adding `--web.enable-lifecycle` to its command would enable it, but `docker compose restart prometheus` is just as fast for config-only changes and avoids one extra command-line flag to maintain.

### Smoke test

```bash
# Alertmanager ready
curl -sf http://127.0.0.1:9093/-/ready
```

```bash
# Prometheus has loaded all three rule groups
curl -s http://127.0.0.1:9090/api/v1/rules \
  | python3 -c "import sys,json; r=json.load(sys.stdin); [print(g['file'].split('/')[-1], '-', len(g['rules']), 'rules') for g in r['data']['groups']]"
```

```bash
# Send a synthetic firing alert through the full path
TOKEN=$(cat config/alertmanager/webhook_token)
curl -sf -X POST http://127.0.0.1:8000/webhooks/alertmanager \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "version": "4",
    "groupKey": "smoke-test",
    "status": "firing",
    "receiver": "notification-service-webhook",
    "groupLabels": {"alertname": "SmokeTest"},
    "commonLabels": {"alertname": "SmokeTest", "service": "smoke", "severity": "warning"},
    "commonAnnotations": {"summary": "smoke test alert"},
    "externalURL": "http://localhost:9093",
    "alerts": [{
      "status": "firing",
      "labels": {"alertname": "SmokeTest"},
      "annotations": {"summary": "smoke test alert"},
      "startsAt": "2026-01-01T00:00:00Z"
    }]
  }'
unset TOKEN
```

Expected: the first two calls succeed, the third returns 204 No Content and the Telegram chat receives a message that reads:
```
[FIRING] SmokeTest

severity: warning

service: smoke

smoke test alert
```
### Troubleshooting

#### Alertmanager starts then container exits

`docker compose logs alertmanager` shows one of two things: a YAML parse error in `alertmanager.yml`, or a permissions error on the token file. The YAML error is straightforward — fix the syntax. The permissions error usually traces back to one of the bind-mounts being a directory instead of a file.

Docker materialises bind-mount targets as **directories** when the host path doesn't exist at container start. If you launched the service before creating the token file, the host path is now a directory and the container sees a directory at `/etc/alertmanager/webhook_token`. Fix:

```bash
docker compose down alertmanager
ls -la config/alertmanager/webhook_token
# If output shows leading 'd' (directory), remove it:
sudo rmdir config/alertmanager/webhook_token
# Recreate the file properly:
openssl rand -base64 32 | tr -d '\n' > config/alertmanager/webhook_token
chmod 644 config/alertmanager/webhook_token
docker compose up -d alertmanager
```

#### Webhook returns 401 unauthorized

Token mismatch. Two common causes: the file content has trailing whitespace (the receiver strips with `.strip()`, but if you regenerated without the `tr -d '\n'` the file has a newline that Alertmanager sends literally in its Bearer header), or one of the two containers is reading a stale token.

Verify the hash on both sides without leaking the value:

```bash
sha256sum config/alertmanager/webhook_token
docker compose exec alertmanager sha256sum /etc/alertmanager/webhook_token
docker compose exec notification-service sha256sum /run/secrets/webhook_token
```

All three hashes match → token is fine, recheck the Alertmanager logs for the actual header value sent. Any mismatch → recreate that container with `docker compose up -d --force-recreate <name>`.

#### Webhook returns 503 misconfigured or telegram_unconfigured

503 with `webhook token not configured` means the token file is missing or empty inside the notification-service container. Check the bind-mount landed:

```bash
docker compose exec notification-service ls -la /run/secrets/webhook_token
```

If the file shows `0 bytes` or doesn't exist, the bind-mount is wrong — see the previous troubleshooting entry. After fixing, `--force-recreate` the notification-service so the `lru_cache` clears.

503 with `telegram not configured` means `TELEGRAM_BOT_TOKEN` or `TELEGRAM_CHAT_ID` is missing from the notification-service env. Both are set in `services/api/.env` (which notification-service inherits via `env_file`). After editing the env, recreate the service.

#### Alerts firing in Prometheus but never reaching Alertmanager

Prometheus has the rules but the routing is broken. Check both ends:

```bash
# Prometheus side: any active alerts right now
curl -s http://127.0.0.1:9090/api/v1/alerts | python3 -m json.tool | head -30

# Alertmanager side: any alerts in its store
curl -s http://127.0.0.1:9093/api/v2/alerts | python3 -m json.tool | head -30
```

Active on Prometheus but absent on Alertmanager means the `alerting` block in `prometheus.yml` points at the wrong host, or the network name resolution is failing between the two containers. Both run on the same Docker network, so DNS should be `alertmanager:9093` — confirm with `docker compose exec prometheus getent hosts alertmanager`.

#### Telegram messages stop arriving but webhooks show 204

The webhook returns 204 only after a successful Telegram send. If 204s are happening but the phone is quiet, the bot or the chat has changed. Hit `https://api.telegram.org/bot<TOKEN>/getMe` from the host to confirm the bot is reachable. If the bot is fine but messages don't show, the chat ID may have changed (left and rejoined the group, for instance — Telegram assigns a new ID).
