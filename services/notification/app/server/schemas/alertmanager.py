from datetime import datetime
from html import escape
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class Alert(BaseModel):
    model_config = ConfigDict(extra="ignore", populate_by_name=True)

    status: Literal["firing", "resolved"]
    labels: dict[str, str] = Field(default_factory=dict)
    annotations: dict[str, str] = Field(default_factory=dict)
    starts_at: datetime = Field(alias="startsAt")
    ends_at: datetime | None = Field(default=None, alias="endsAt")
    generator_url: str | None = Field(default=None, alias="generatorURL")
    fingerprint: str | None = None


class AlertmanagerWebhook(BaseModel):
    model_config = ConfigDict(extra="ignore", populate_by_name=True)

    version: str
    group_key: str = Field(alias="groupKey")
    status: Literal["firing", "resolved"]
    receiver: str
    group_labels: dict[str, str] = Field(default_factory=dict, alias="groupLabels")
    common_labels: dict[str, str] = Field(default_factory=dict, alias="commonLabels")
    common_annotations: dict[str, str] = Field(
        default_factory=dict, alias="commonAnnotations"
    )
    external_url: str = Field(alias="externalURL")
    alerts: list[Alert]

    def to_telegram_html(self) -> str:
        status_tag = "FIRING" if self.status == "firing" else "RESOLVED"
        alertname = self.common_labels.get("alertname") or self.group_labels.get(
            "alertname", "unknown"
        )
        severity = self.common_labels.get("severity", "unknown")
        service = self.common_labels.get("service", "unknown")
        summary = self.common_annotations.get("summary", "")

        lines = [
            f"<b>[{escape(status_tag)}] {escape(alertname)}</b>",
            f"severity: {escape(severity)}",
            f"service: {escape(service)}",
        ]
        if summary:
            lines.append(escape(summary))
        if len(self.alerts) > 1:
            lines.append(f"alerts in group: {len(self.alerts)}")
        return "\n".join(lines)
