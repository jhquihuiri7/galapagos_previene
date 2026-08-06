"""Contrato público de la API: autenticación, proyección y paginación.

Las pruebas no tocan PostgreSQL: sustituyen el repositorio de lectura por
dobles. Lo que se verifica aquí es la frontera —qué sale, qué no sale y quién
puede pedirlo—, que es exactamente la parte que un error convertiría en una
fuga de datos.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient

from app.api import deps
from app.api.config import ApiSettings, MIN_API_KEY_LENGTH
from app.api.main import create_app
from app.api.routers import reports as reports_router
from app.config import ConfigurationError
from app.models import (
    MediaType,
    Report,
    ReportKind,
    ReportMedia,
    ReportStatus,
    TelegramMessageType,
    WorkflowStep,
)
from app.repositories.exports import ExportedReport, ReportPage


API_KEY = "k" * MIN_API_KEY_LENGTH
AUTH = {"Authorization": f"Bearer {API_KEY}"}
NOW = datetime(2026, 8, 6, 12, 0, tzinfo=timezone.utc)


def _settings() -> ApiSettings:
    return ApiSettings(
        database_url="postgresql://galapagos_api@localhost/galapagos_previene",
        api_keys=frozenset([API_KEY]),
        telegram_bot_token="123:token-de-prueba",
    )


def _report(report_id: UUID, updated_at: datetime = NOW) -> Report:
    return Report(
        id=report_id,
        user_id=uuid4(),
        telegram_chat_id=987_654_321,
        report_kind=ReportKind.EVENT,
        event_type_id=1,
        status=ReportStatus.SUBMITTED,
        workflow_step=WorkflowStep.COMPLETED,
        latitude=-0.7436,
        longitude=-90.3134,
        location_accuracy=12.5,
        description="Lluvia intensa en la vía a Bellavista.",
        created_at=NOW,
        updated_at=updated_at,
        submitted_at=NOW,
    )


def _media(report_id: UUID) -> ReportMedia:
    return ReportMedia(
        id=uuid4(),
        report_id=report_id,
        media_type=MediaType.PHOTO,
        telegram_message_type=TelegramMessageType.PHOTO,
        telegram_file_id="AgACAgEAAxkBAAI-file-id-secreto",
        telegram_file_unique_id="AQADunico",
        telegram_message_id=42,
        telegram_media_group_id=None,
        mime_type="image/jpeg",
        original_file_name=None,
        file_size=204_800,
        width=1_280,
        height=853,
        duration_seconds=None,
        caption="Vía inundada",
        created_at=NOW,
    )


def _exported(report_id: UUID, updated_at: datetime = NOW) -> ExportedReport:
    return ExportedReport(
        report=_report(report_id, updated_at),
        event_type_code="RAIN",
        event_type_name="Lluvia",
        media=(_media(report_id),),
    )


@pytest.fixture()
def client() -> TestClient:
    """Cliente con el pool sustituido para no abrir conexiones reales."""

    app = create_app(_settings())
    app.dependency_overrides[deps.get_pool] = lambda: object()
    # El lifespan no se ejecuta si no se entra en el contexto del cliente, así
    # que ni el pool ni el cliente HTTP reales llegan a crearse.
    return TestClient(app)


# --------------------------------------------------------------- autenticación

@pytest.mark.parametrize(
    "path",
    ["/v1/reports", f"/v1/reports/{uuid4()}", "/v1/event-types", f"/v1/media/{uuid4()}/content"],
)
def test_every_data_endpoint_rejects_anonymous_access(
    client: TestClient,
    path: str,
) -> None:
    assert client.get(path).status_code == 401


@pytest.mark.parametrize(
    "header",
    [
        {"Authorization": "Bearer clave-incorrecta-pero-suficientemente-larga"},
        {"Authorization": API_KEY},  # sin el esquema Bearer
        {"Authorization": "Basic " + API_KEY},
        {"Authorization": "Bearer "},
    ],
)
def test_malformed_or_wrong_credentials_are_rejected(
    client: TestClient,
    header: dict[str, str],
) -> None:
    assert client.get("/v1/reports", headers=header).status_code == 401


class _StubPool:
    """Pool mínimo para la sonda de salud, sin abrir conexiones reales."""

    def __init__(self, *, healthy: bool = True) -> None:
        self.healthy = healthy

    async def fetchval(self, _query: str) -> int:
        if not self.healthy:
            raise ConnectionError("la base no responde")
        return 1


def test_health_check_stays_public_for_the_container_probe() -> None:
    app = create_app(_settings())
    app.dependency_overrides[deps.get_pool] = lambda: _StubPool()

    response = TestClient(app).get("/healthz")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "database": "ok"}


def test_health_check_reports_503_when_postgres_is_unreachable() -> None:
    """El healthcheck de Docker debe fallar si la base no contesta."""

    app = create_app(_settings())
    app.dependency_overrides[deps.get_pool] = lambda: _StubPool(healthy=False)

    response = TestClient(app).get("/healthz")
    assert response.status_code == 503
    assert response.json()["status"] == "degraded"


# -------------------------------------------------------------------- contrato

def test_response_never_exposes_telegram_identifiers_or_personal_data(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """El file_id y el chat de Telegram no deben salir del sistema.

    Es la garantía central del diseño: publicar el ``file_id`` obligaría a
    compartir el token del bot para poder usarlo.
    """

    report_id = uuid4()

    async def _fake_get(_pool: object, _report_id: UUID) -> ExportedReport:
        return _exported(report_id)

    monkeypatch.setattr(reports_router, "get_submitted_report", _fake_get)

    response = client.get(f"/v1/reports/{report_id}", headers=AUTH)
    assert response.status_code == 200

    raw = response.text
    assert "AgACAgEAAxkBAAI-file-id-secreto" not in raw
    assert "AQADunico" not in raw
    assert "987654321" not in raw

    body = response.json()
    assert body["id"] == str(report_id)
    assert body["event_type_code"] == "RAIN"
    assert body["latitude"] == -0.7436
    assert set(body["media"][0]) == {
        "id",
        "media_type",
        "content_url",
        "mime_type",
        "original_file_name",
        "file_size",
        "width",
        "height",
        "duration_seconds",
        "caption",
        "created_at",
    }
    assert body["media"][0]["content_url"].endswith("/content")


def test_unknown_or_unsubmitted_report_returns_404(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def _fake_get(_pool: object, _report_id: UUID) -> None:
        return None

    monkeypatch.setattr(reports_router, "get_submitted_report", _fake_get)

    response = client.get(f"/v1/reports/{uuid4()}", headers=AUTH)
    assert response.status_code == 404


# ------------------------------------------------------------------ paginación

def test_page_exposes_the_cursor_needed_to_continue(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    last_id = uuid4()
    last_updated = NOW + timedelta(minutes=5)

    async def _fake_list(_pool: object, **_kwargs: object) -> ReportPage:
        return ReportPage(
            items=(_exported(uuid4()), _exported(last_id, last_updated)),
            next_updated_at=last_updated,
            next_id=last_id,
        )

    monkeypatch.setattr(reports_router, "list_submitted_reports", _fake_list)

    body = client.get("/v1/reports", headers=AUTH).json()
    assert len(body["items"]) == 2
    assert body["next"]["cursor_id"] == str(last_id)
    assert body["next"]["since"].startswith("2026-08-06T12:05")


def test_last_page_reports_no_cursor(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """`next` nulo significa "estás al día", no "no hay datos"."""

    async def _fake_list(_pool: object, **_kwargs: object) -> ReportPage:
        return ReportPage(items=(_exported(uuid4()),), next_updated_at=None, next_id=None)

    monkeypatch.setattr(reports_router, "list_submitted_reports", _fake_list)

    body = client.get("/v1/reports", headers=AUTH).json()
    assert body["next"] is None


def test_query_parameters_are_forwarded_and_validated(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, object] = {}

    async def _fake_list(_pool: object, **kwargs: object) -> ReportPage:
        captured.update(kwargs)
        return ReportPage(items=(), next_updated_at=None, next_id=None)

    monkeypatch.setattr(reports_router, "list_submitted_reports", _fake_list)

    cursor = uuid4()
    response = client.get(
        "/v1/reports",
        params={
            "since": "2026-08-06T12:00:00+00:00",
            "cursor_id": str(cursor),
            "limit": 25,
        },
        headers=AUTH,
    )

    assert response.status_code == 200
    assert captured["since"] == NOW
    assert captured["cursor_id"] == cursor
    assert captured["limit"] == 25


@pytest.mark.parametrize("limit", [0, -1, 500, "muchos"])
def test_invalid_limit_is_rejected_before_reaching_the_database(
    client: TestClient,
    limit: object,
) -> None:
    response = client.get("/v1/reports", params={"limit": limit}, headers=AUTH)
    assert response.status_code == 422


# --------------------------------------------------------------- configuración

def test_short_api_keys_are_refused_at_startup(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Una clave corta es adivinable aunque la comparación sea constante."""

    monkeypatch.setenv("API_DATABASE_URL", "postgresql://u@localhost/d")
    monkeypatch.setenv("API_KEYS", "demasiado-corta")
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "123:token")

    with pytest.raises(ConfigurationError, match="al menos"):
        ApiSettings.from_env(env_file=None)


def test_a_write_capable_url_is_not_validated_away_but_keys_are_required(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("API_DATABASE_URL", "postgresql://u@localhost/d")
    monkeypatch.delenv("API_KEYS", raising=False)
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "123:token")

    with pytest.raises(ConfigurationError, match="API_KEYS"):
        ApiSettings.from_env(env_file=None)


def test_multiple_keys_allow_rotation_without_downtime(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    old_key, new_key = "a" * 32, "b" * 40
    monkeypatch.setenv("API_DATABASE_URL", "postgresql://u@localhost/d")
    monkeypatch.setenv("API_KEYS", f"{old_key}, {new_key}")
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "123:token")

    settings = ApiSettings.from_env(env_file=None)
    assert settings.api_keys == frozenset([old_key, new_key])

    # Ambas claves deben seguir siendo válidas mientras dura la migración.
    for key in (old_key, new_key):
        deps.require_api_key(settings, f"Bearer {key}")

    with pytest.raises(Exception):
        deps.require_api_key(settings, "Bearer " + "c" * 32)
