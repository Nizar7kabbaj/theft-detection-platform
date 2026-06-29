from opentelemetry import metrics

_meter = metrics.get_meter("theft.alert")

webhooks_total = _meter.create_counter(
    name="theft_alert_webhooks_total",
    description="alertmanager webhook posts received, by outcome",
    unit="1",
)

telegram_messages_total = _meter.create_counter(
    name="theft_alert_telegram_messages_total",
    description="telegram messages attempted, by outcome",
    unit="1",
)

webhook_duration_seconds = _meter.create_histogram(
    name="theft_alert_webhook_duration_seconds",
    description="end-to-end duration of alertmanager webhook handling",
    unit="s",
)
