from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class ConcealmentPolicy(BaseModel):
    model_config = ConfigDict(extra="forbid")

    grab_ratio: float = Field(default=0.6, ge=0.1, le=1.5)
    missing_seconds: float = Field(default=1.0, ge=0.2, le=5.0)
    keypoint_confidence: float = Field(default=0.5, ge=0.1, le=0.95)
    expiry_seconds: float = Field(default=10.0, ge=2.0, le=60.0)


class ClassifierPolicy(BaseModel):
    model_config = ConfigDict(extra="forbid")

    anomaly_threshold: float = Field(default=0.6, ge=0.05, le=0.95)
    person_confidence: float = Field(default=0.7, ge=0.1, le=0.95)
    object_confidence: float = Field(default=0.35, ge=0.05, le=0.95)


class PolicyPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    concealment: ConcealmentPolicy = Field(default_factory=ConcealmentPolicy)
    classifier: ClassifierPolicy = Field(default_factory=ClassifierPolicy)


class PolicyUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    expected_version: int = Field(ge=0)
    policy: PolicyPayload


class PolicyRuntime(BaseModel):
    version: int | None = None
    applied_at: datetime | None = None
    device: str | None = None


class PolicyResponse(BaseModel):
    version: int
    policy: PolicyPayload
    changed_by: str
    changed_at: datetime
    runtime: PolicyRuntime = Field(default_factory=PolicyRuntime)


class PolicyChange(BaseModel):
    field_name: str
    previous: float
    current: float


class PolicyRevision(BaseModel):
    version: int
    changed_by: str
    changed_at: datetime
    changes: list[PolicyChange]
