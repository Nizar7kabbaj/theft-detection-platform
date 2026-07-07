#!/bin/bash
set -euo pipefail

api_pw="$(cat /run/secrets/mongo_api_password)"
notif_pw="$(cat /run/secrets/mongo_notification_password)"
monitor_pw="$(cat /run/secrets/mongo_monitor_password)"

mongosh --quiet <<EOF
db = db.getSiblingDB('theft_detection_db');
db.createUser({
  user: 'api_svc',
  pwd: '${api_pw}',
  roles: [{ role: 'readWrite', db: 'theft_detection_db' }]
});
db.createUser({
  user: 'notification_svc',
  pwd: '${notif_pw}',
  roles: [{ role: 'readWrite', db: 'theft_detection_db' }]
});
admin = db.getSiblingDB('admin');
admin.createUser({
  user: 'theft_monitor',
  pwd: '${monitor_pw}',
  roles: [
    { role: 'clusterMonitor', db: 'admin' },
    { role: 'read', db: 'theft_detection_db' }
  ]
});
EOF
