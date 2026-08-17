from __future__ import annotations

from enum import StrEnum


class Role(StrEnum):
    ADMIN = "admin"
    OPERATOR = "operator"
    VIEWER = "viewer"
    ML_ENGINEER = "ml_engineer"
    COMPLIANCE = "compliance"
    DETECTOR = "detector"
