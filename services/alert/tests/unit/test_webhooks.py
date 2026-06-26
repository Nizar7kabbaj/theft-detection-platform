from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from app.api import webhooks
from app.http_app import create_app


VALID_PAYLOAD = {
    "version": "4",
    "groupKey": "{}:{alertname=\"BackendHighErrorRate\"}",
    "status": "firing",
    "receiver": "alert-service-webhook",
    "groupLabels": {"alertname": "BackendHighErrorRate"},
    "commonLabels": {
        "alertname": "BackendHighErrorRate",
        "severity": "critical",
        "service": "theft-backend",
    },
    "commonAnnotations": {"summary": "error rate above 5 percent for 10 minutes"},
    "externalURL": "http://localhost:9093",
    "alerts": [
        {
            "status": "firing",
            "labels": {"alertname": "BackendHighErrorRate", "severity": "critical"},
            "annotations": {"summary": "error rate above 5 percent for 10 minutes"},
            "startsAt": "2026-06-18T00:00:00Z",
            "endsAt": "0001-01-01T00:00:00Z",
            "generatorURL": "http://localhost:9090/graph",
            "fingerprint": "abc123",
        }
    ],
}


@pytest.fixture
def token_file(tmp_path: Path) -> Path:
    path = tmp_path / "webhook_token"
    path.write_text("test-token-value")
    return path


@pytest.fixture
def client(token_file: Path):
    with patch.object(webhooks.settings, "ALERTMANAGER_WEBHOOK_TOKEN_FILE", token_file):
        webhooks._reset_token_cache()
        with TestClient(create_app()) as c:
            yield c
    webhooks._reset_token_cache()


def test_valid_token_and_payload_dispatches_to_telegram(client: TestClient) -> None:
    with patch("app.api.webhooks.telegram_service") as mock_telegram:
        mock_telegram.is_configured.return_value = True
        mock_telegram.send_message.return_value = True

        response = client.post(
            "/webhooks/alertmanager",
            json=VALID_PAYLOAD,
            headers={"Authorization": "Bearer test-token-value"},
        )

    assert response.status_code == 204
    mock_telegram.send_message.assert_called_once()
    sent_message = mock_telegram.send_message.call_args.args[0]
    assert "BackendHighErrorRate" in sent_message
    assert "FIRING" in sent_message


def test_missing_authorization_header_returns_401(client: TestClient) -> None:
    with patch("app.api.webhooks.telegram_service") as mock_telegram:
        response = client.post("/webhooks/alertmanager", json=VALID_PAYLOAD)

    assert response.status_code == 401
    mock_telegram.send_message.assert_not_called()


def test_wrong_token_returns_401(client: TestClient) -> None:
    with patch("app.api.webhooks.telegram_service") as mock_telegram:
        response = client.post(
            "/webhooks/alertmanager",
            json=VALID_PAYLOAD,
            headers={"Authorization": "Bearer wrong-token"},
        )

    assert response.status_code == 401
    mock_telegram.send_message.assert_not_called()


def test_malformed_payload_returns_422(client: TestClient) -> None:
    bad_payload = {k: v for k, v in VALID_PAYLOAD.items() if k != "status"}

    with patch("app.api.webhooks.telegram_service") as mock_telegram:
        response = client.post(
            "/webhooks/alertmanager",
            json=bad_payload,
            headers={"Authorization": "Bearer test-token-value"},
        )

    assert response.status_code == 422
    mock_telegram.send_message.assert_not_called()
