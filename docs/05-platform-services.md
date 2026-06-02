# Platform Services

This document covers the local platform services that the backend depends on
during development. Today that means MongoDB. Future entries will cover Redis,
the metrics stack, and any other services the application talks to.

## Local MongoDB

The development MongoDB instance runs in Docker on the developer machine.
Production still uses MongoDB Atlas. The local copy lets the dev loop work
offline and removes Atlas as a hard dependency for testing platform-services
work.

### Why Docker, not a host install

The original plan was a host-installed MongoDB Community 7 from the official
apt repository. Two real problems blocked that path on this machine:

1. The official repo doesn't publish packages for Ubuntu 26.04 (resolute).
   MongoDB's currently-supported codenames stop at noble (24.04). The standard
   fallback of pointing 26.04 at the noble suite is explicitly warned against
   by upstream.

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

The same file serves as both the server certificate and the CA file. MongoDB
7.0 requires a CA file when `requireTLS` is set, and a self-signed cert is its
own CA. Clients trust it by pointing `--tlsCAFile` at the same path.

For clients outside the container, the public cert was copied to a
host-readable location in the developer's home directory. The private key
stays in `/etc/mongod-tls/`, reachable only to root and members of
`mongo-cert`.

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

The admin user was created via the localhost exception, the one-time mongod
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
connection string. The dev loop runs against local Docker. Production-parity
testing runs against Atlas by pointing the backend at `MONGODB_URL` directly.

## Troubleshooting

### Container crashes with "kernel 6.19+ incompatible"

The image tag is `mongo:8` or later. Pin to `mongo:7.0` in
`docker-compose.yml`. The TCMalloc fix isn't in any 8.x release yet.

### Container crashes with "TLS without chain of trust no longer supported"

`mongod.conf` is missing the `CAFile` line under `net.tls`. Add:

```yaml
CAFile: /etc/mongo/tls/mongod.pem
```

Same path as `certificateKeyFile`. The self-signed cert serves as its own CA.

### Container starts but clients can't connect

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

### Atlas connection works, local connection doesn't

Usually the local URL has an unencoded special character in the password.
Connection strings need `@`, `/`, `:`, and `#` URL-encoded (`%40`, `%2F`,
`%3A`, `%23`). Atlas-generated passwords contain those often. Regenerate the
local password as alphanumeric-only to avoid this.

### Smoke test

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