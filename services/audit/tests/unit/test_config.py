from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

from app.core import database as database_module
from app.core.config import Settings, get_settings
from tests import (
    CHECKPOINT_KEY_ID,
    CHECKPOINT_PRIVATE_KEY_FILE,
    CHECKPOINT_PUBLIC_KEY_FILE,
    POSTGRES_APP_PASSWORD_FILE,
    POSTGRES_OWNER_PASSWORD_FILE,
    PSEUDONYM_KEY_FILE,
)

pytestmark = pytest.mark.unit


APP_MODULES = [
    "app.core.chain",
    "app.core.config",
    "app.core.database",
    "app.core.pseudonym",
    "app.core.redis",
    "app.core.signing",
    "app.db.base",
    "app.db.models.audit_event",
    "app.repositories.audit_repository",
    "app.server.identity",
    "app.server.interceptors",
    "app.server.servicer",
    "app.services.checkpoint_service",
    "app.services.retention",
]


def test_settings_read_the_audit_prefix(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AUDIT_SERVICE_NAME", "audit-under-test")
    get_settings.cache_clear()
    assert get_settings().service_name == "audit-under-test"


def test_settings_ignore_an_unprefixed_variable(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SERVICE_NAME", "wrong")
    get_settings.cache_clear()
    assert get_settings().service_name == "audit"


def test_unknown_variables_are_ignored(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AUDIT_NOT_A_REAL_SETTING", "value")
    get_settings.cache_clear()
    assert get_settings().service_name == "audit"


def test_settings_are_cached() -> None:
    assert get_settings() is get_settings()


def test_cache_clear_rebuilds_the_settings() -> None:
    first = get_settings()
    get_settings.cache_clear()
    assert get_settings() is not first


def test_integer_settings_are_coerced(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AUDIT_GRPC_PORT", "50555")
    get_settings.cache_clear()
    assert get_settings().grpc_port == 50555


def test_boolean_settings_are_coerced(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AUDIT_APPEND_RATE_FAIL_CLOSED", "true")
    get_settings.cache_clear()
    assert get_settings().append_rate_fail_closed is True


def test_path_settings_are_coerced() -> None:
    assert isinstance(get_settings().pseudonym_key_file, Path)


def test_a_non_numeric_port_is_refused(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AUDIT_GRPC_PORT", "not-a-port")
    get_settings.cache_clear()
    with pytest.raises(ValueError, match="grpc_port"):
        get_settings()


def test_key_material_points_at_the_test_fixtures() -> None:
    settings = get_settings()
    assert settings.pseudonym_key_file == PSEUDONYM_KEY_FILE
    assert settings.checkpoint_private_key_file == CHECKPOINT_PRIVATE_KEY_FILE
    assert settings.checkpoint_public_key_file == CHECKPOINT_PUBLIC_KEY_FILE
    assert settings.checkpoint_key_id == CHECKPOINT_KEY_ID


def test_the_compose_defaults_do_not_leak_into_the_tests() -> None:
    settings = get_settings()
    assert settings.postgres_host not in {"postgres", "postgres-harness"}
    assert settings.redis_host != "redis"
    for path in (
        settings.pseudonym_key_file,
        settings.checkpoint_private_key_file,
        settings.checkpoint_public_key_file,
        settings.postgres_app_password_file,
        settings.postgres_owner_password_file,
        settings.redis_password_file,
    ):
        assert str(path).startswith("/run/secrets") is False
        assert path.exists() is True


def test_the_default_settings_still_point_at_the_deployed_secrets() -> None:
    defaults = Settings.model_fields
    assert defaults["pseudonym_key_file"].default == Path("/run/secrets/audit_pseudonym_key")
    assert defaults["postgres_app_password_file"].default == Path(
        "/run/secrets/audit_app_postgres_password"
    )


def test_the_app_and_owner_roles_are_distinct() -> None:
    settings = get_settings()
    assert settings.postgres_app_user != settings.postgres_owner_user


def test_the_owner_role_carries_a_longer_statement_timeout() -> None:
    settings = get_settings()
    assert settings.owner_statement_timeout_ms > settings.statement_timeout_ms


def test_the_app_url_uses_the_app_role() -> None:
    assert "audit_app" in database_module.resolve_app_url()


def test_the_owner_url_uses_the_owner_role() -> None:
    assert "audit_owner" in database_module.resolve_owner_url()


def test_the_urls_use_the_asyncpg_driver() -> None:
    assert database_module.resolve_app_url().startswith("postgresql+asyncpg://")


def test_the_password_is_read_from_the_configured_file() -> None:
    expected = POSTGRES_APP_PASSWORD_FILE.read_text(encoding="utf-8").strip()
    assert expected in database_module.resolve_app_url()


def test_the_owner_password_is_read_from_its_own_file() -> None:
    expected = POSTGRES_OWNER_PASSWORD_FILE.read_text(encoding="utf-8").strip()
    assert expected in database_module.resolve_owner_url()


def test_a_password_with_url_characters_is_escaped(
    monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:
    awkward = tmp_path / "awkward_password"
    awkward.write_text("p@ss/word:with#chars\n", encoding="utf-8")
    monkeypatch.setenv("AUDIT_POSTGRES_APP_PASSWORD_FILE", str(awkward))
    get_settings.cache_clear()
    database_module._load_password.cache_clear()
    url = database_module.resolve_app_url()
    assert "p%40ss%2Fword%3Awith%23chars" in url


def test_a_missing_password_file_is_refused(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    monkeypatch.setenv("AUDIT_POSTGRES_APP_PASSWORD_FILE", str(tmp_path / "absent"))
    get_settings.cache_clear()
    database_module._load_password.cache_clear()
    with pytest.raises(database_module.DatabaseCredentialError, match="missing"):
        database_module.resolve_app_url()


def test_an_empty_password_file_is_refused(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    empty = tmp_path / "empty_password"
    empty.write_text("  \n", encoding="utf-8")
    monkeypatch.setenv("AUDIT_POSTGRES_APP_PASSWORD_FILE", str(empty))
    get_settings.cache_clear()
    database_module._load_password.cache_clear()
    with pytest.raises(database_module.DatabaseCredentialError, match="empty"):
        database_module.resolve_app_url()


def test_an_unreadable_password_file_is_refused(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    directory = tmp_path / "password_directory"
    directory.mkdir()
    monkeypatch.setenv("AUDIT_POSTGRES_APP_PASSWORD_FILE", str(directory))
    get_settings.cache_clear()
    database_module._load_password.cache_clear()
    with pytest.raises(database_module.DatabaseCredentialError, match="unreadable"):
        database_module.resolve_app_url()


def test_no_module_reads_a_secret_at_import_time() -> None:
    script = (
        "import os, sys\n"
        "for name in ["
        + ", ".join(
            repr(f"AUDIT_{field.upper()}")
            for field in (
                "pseudonym_key_file",
                "checkpoint_private_key_file",
                "checkpoint_public_key_file",
                "postgres_app_password_file",
                "postgres_owner_password_file",
                "redis_password_file",
            )
        )
        + "]:\n"
        "    os.environ[name] = '/nonexistent/secrets/' + name.lower()\n"
        "import importlib\n"
        "for module in " + repr(APP_MODULES) + ":\n"
        "    importlib.import_module(module)\n"
        "print('clean')\n"
    )
    completed = subprocess.run(
        [sys.executable, "-c", script],
        capture_output=True,
        text=True,
        cwd=Path(__file__).resolve().parents[2],
        check=False,
    )
    assert completed.returncode == 0, completed.stderr
    assert "clean" in completed.stdout
