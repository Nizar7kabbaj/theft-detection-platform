from __future__ import annotations

from enum import StrEnum


class Permission(StrEnum):
    CAMERA_READ = "camera:read"
    CAMERA_WRITE = "camera:write"
    DETECTION_READ = "detection:read"
    DETECTION_WRITE = "detection:write"
    DETECTION_INFER = "detection:infer"
    ALERT_READ = "alert:read"
    ALERT_WRITE = "alert:write"
    ALERT_ACKNOWLEDGE = "alert:acknowledge"
    STATS_READ = "stats:read"
    AUDIT_QUERY = "audit:query"
    SETTINGS_READ = "settings:read"


ROLE_PERMISSIONS: dict[str, frozenset[Permission]] = {
    "admin": frozenset(Permission),
    "operator": frozenset(
        {
            Permission.CAMERA_READ,
            Permission.CAMERA_WRITE,
            Permission.DETECTION_READ,
            Permission.DETECTION_INFER,
            Permission.ALERT_READ,
            Permission.ALERT_WRITE,
            Permission.ALERT_ACKNOWLEDGE,
            Permission.STATS_READ,
        }
    ),
    "viewer": frozenset(
        {
            Permission.CAMERA_READ,
            Permission.DETECTION_READ,
            Permission.ALERT_READ,
            Permission.STATS_READ,
        }
    ),
    "ml_engineer": frozenset(
        {
            Permission.DETECTION_READ,
            Permission.DETECTION_INFER,
            Permission.STATS_READ,
        }
    ),
    "compliance": frozenset(
        {
            Permission.ALERT_READ,
            Permission.DETECTION_READ,
            Permission.AUDIT_QUERY,
            Permission.SETTINGS_READ,
        }
    ),
    "detector": frozenset({Permission.ALERT_WRITE}),
}


def resolve_permissions(roles: frozenset[str]) -> frozenset[Permission]:
    granted: set[Permission] = set()
    for role in roles:
        granted |= ROLE_PERMISSIONS.get(role, frozenset())
    return frozenset(granted)
