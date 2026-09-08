from __future__ import annotations

import logging
from datetime import UTC, datetime

from pymongo.errors import DuplicateKeyError
from redis.asyncio import Redis
from redis.exceptions import RedisError

from app.core.errors import ConflictError
from app.repositories.policy_repository import PolicyRepository
from app.schemas.policy import (
    PolicyChange,
    PolicyPayload,
    PolicyResponse,
    PolicyRevision,
    PolicyRuntime,
)
from app.services.audit_service import AuditClient

logger = logging.getLogger(__name__)


def _flatten(payload: PolicyPayload) -> dict[str, float]:
    flat: dict[str, float] = {}
    for group, values in payload.model_dump().items():
        for name, value in values.items():
            flat[f"{group}.{name}"] = value
    return flat


def _diff(before: PolicyPayload, after: PolicyPayload) -> list[PolicyChange]:
    old = _flatten(before)
    new = _flatten(after)
    return [
        PolicyChange(field_name=name, previous=old[name], current=new[name])
        for name in new
        if old[name] != new[name]
    ]


class PolicyUseCase:
    CURRENT_KEY = "policy:detection:current"
    APPLIED_KEY = "policy:detection:applied"
    CHANNEL = "policy:detection"
    RESOURCE_ID = "detection_policy"

    def __init__(
        self,
        repo: PolicyRepository,
        stream: Redis,
        audit_client: AuditClient,
    ) -> None:
        self._repo = repo
        self._stream = stream
        self._audit = audit_client

    async def _runtime(self) -> PolicyRuntime:
        try:
            raw = await self._stream.hgetall(self.APPLIED_KEY)
        except RedisError as exc:
            logger.warning("runtime policy read failed: %s", exc)
            return PolicyRuntime()
        if not raw:
            return PolicyRuntime()
        reported = {
            key.decode() if isinstance(key, bytes) else key: (
                value.decode() if isinstance(value, bytes) else value
            )
            for key, value in raw.items()
        }
        applied_at = reported.get("applied_at")
        return PolicyRuntime(
            version=int(reported["version"]) if "version" in reported else None,
            applied_at=datetime.fromtimestamp(float(applied_at), tz=UTC) if applied_at else None,
            device=reported.get("device"),
        )

    async def current(self) -> PolicyResponse:
        doc = await self._repo.current()
        if doc is None:
            return PolicyResponse(
                version=0,
                policy=PolicyPayload(),
                changed_by="",
                changed_at=datetime.now(UTC),
                runtime=await self._runtime(),
            )
        return PolicyResponse(
            version=doc["version"],
            policy=PolicyPayload.model_validate(doc["policy"]),
            changed_by=doc["changed_by"],
            changed_at=doc["changed_at"],
            runtime=await self._runtime(),
        )

    async def update(
        self,
        expected_version: int,
        policy: PolicyPayload,
        actor_user_id: str,
    ) -> PolicyResponse:
        doc = await self._repo.current()
        live_version = doc["version"] if doc else 0
        if expected_version != live_version:
            raise ConflictError(
                f"policy changed since it was loaded, reload and try again "
                f"(loaded {expected_version}, current {live_version})"
            )
        before = PolicyPayload.model_validate(doc["policy"]) if doc else PolicyPayload()
        changes = _diff(before, policy)
        if not changes:
            return await self.current()
        version = live_version + 1
        changed_at = datetime.now(UTC)
        document = {
            "version": version,
            "policy": policy.model_dump(),
            "changed_by": actor_user_id,
            "changed_at": changed_at,
            "changes": [change.model_dump() for change in changes],
        }
        try:
            await self._repo.append(document)
        except DuplicateKeyError as exc:
            raise ConflictError("policy changed since it was loaded, reload and try again") from exc
        for change in changes:
            await self._audit.emit_config_changed(
                actor_user_id=actor_user_id,
                resource_id=self.RESOURCE_ID,
                field_path=change.field_name,
                before_value=str(change.previous),
                after_value=str(change.current),
            )
        await self._publish(version, policy)
        return PolicyResponse(
            version=version,
            policy=policy,
            changed_by=actor_user_id,
            changed_at=changed_at,
            runtime=await self._runtime(),
        )

    async def _publish(self, version: int, policy: PolicyPayload) -> None:
        body = PolicyResponse(
            version=version,
            policy=policy,
            changed_by="",
            changed_at=datetime.now(UTC),
        ).model_dump_json(exclude={"runtime", "changed_by", "changed_at"})
        try:
            await self._stream.set(self.CURRENT_KEY, body)
            await self._stream.publish(self.CHANNEL, body)
        except RedisError as exc:
            logger.warning("policy publish failed version=%s: %s", version, exc)

    async def history(self, limit: int = 20) -> list[PolicyRevision]:
        docs = await self._repo.history(limit=limit)
        return [
            PolicyRevision(
                version=doc["version"],
                changed_by=doc["changed_by"],
                changed_at=doc["changed_at"],
                changes=[PolicyChange.model_validate(item) for item in doc.get("changes", [])],
            )
            for doc in docs
        ]
