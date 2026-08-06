"""Descarga de evidencias: el token nunca sale y el archivo nunca toca disco."""

from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID, uuid4

import httpx
import pytest
from fastapi.testclient import TestClient

from app.api import deps
from app.api.config import ApiSettings, MIN_API_KEY_LENGTH
from app.api.main import create_app
from app.api.routers import media as media_router
from app.api.telegram_files import (
    TELEGRAM_API_BASE,
    TelegramFileError,
    TelegramFileNotFoundError,
    _redact,
    resolve_file_path,
    stream_file,
)
from app.models import MediaType, ReportMedia, TelegramMessageType
from app.repositories.exports import MAX_PAGE_SIZE, _clamp_limit


TOKEN = "123456:AAH-token-muy-secreto-del-bot"
API_KEY = "k" * MIN_API_KEY_LENGTH
AUTH = {"Authorization": f"Bearer {API_KEY}"}
NOW = datetime(2026, 8, 6, 12, 0, tzinfo=timezone.utc)


def _settings() -> ApiSettings:
    return ApiSettings(
        database_url="postgresql://galapagos_api@localhost/galapagos_previene",
        api_keys=frozenset([API_KEY]),
        telegram_bot_token=TOKEN,
        media_chunk_size=8,
    )


def _media(*, file_name: str | None = None, mime: str | None = "image/jpeg") -> ReportMedia:
    return ReportMedia(
        id=uuid4(),
        report_id=uuid4(),
        media_type=MediaType.PHOTO,
        telegram_message_type=TelegramMessageType.PHOTO,
        telegram_file_id="file-id-secreto",
        telegram_file_unique_id="unico",
        telegram_message_id=42,
        telegram_media_group_id=None,
        mime_type=mime,
        original_file_name=file_name,
        file_size=11,
        width=100,
        height=80,
        duration_seconds=None,
        caption=None,
        created_at=NOW,
    )


def _client(app_settings: ApiSettings, handler) -> TestClient:
    """Monta la app con un transporte falso hacia api.telegram.org."""

    app = create_app(app_settings)
    app.dependency_overrides[deps.get_pool] = lambda: object()
    app.state.http_client = httpx.AsyncClient(
        transport=httpx.MockTransport(handler)
    )
    return TestClient(app)


# ------------------------------------------------------------ resolución y flujo

def _telegram_ok(request: httpx.Request) -> httpx.Response:
    if request.url.path.endswith("/getFile"):
        return httpx.Response(
            200, json={"ok": True, "result": {"file_path": "photos/file_7.jpg"}}
        )
    return httpx.Response(200, content=b"bytes-de-la")


def test_media_is_streamed_from_telegram_without_leaking_the_token(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    media = _media()
    seen: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(str(request.url))
        return _telegram_ok(request)

    async def _fake_get(_pool: object, _media_id: UUID) -> ReportMedia:
        return media

    monkeypatch.setattr(media_router, "get_submitted_media", _fake_get)
    client = _client(_settings(), handler)

    response = client.get(f"/v1/media/{media.id}/content", headers=AUTH)

    assert response.status_code == 200
    assert response.content == b"bytes-de-la"
    assert response.headers["content-type"].startswith("image/jpeg")
    # El token aparece en la URL hacia Telegram, pero nunca en la respuesta.
    assert any(TOKEN in url for url in seen)
    assert TOKEN not in response.text
    assert TOKEN not in str(response.headers)


def test_missing_media_returns_404_without_calling_telegram(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    called = False

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal called
        called = True
        return _telegram_ok(request)

    async def _fake_get(_pool: object, _media_id: UUID) -> None:
        return None

    monkeypatch.setattr(media_router, "get_submitted_media", _fake_get)
    client = _client(_settings(), handler)

    response = client.get(f"/v1/media/{uuid4()}/content", headers=AUTH)
    assert response.status_code == 404
    assert not called


def test_expired_file_becomes_404_and_telegram_outage_becomes_502(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    media = _media()

    async def _fake_get(_pool: object, _media_id: UUID) -> ReportMedia:
        return media

    monkeypatch.setattr(media_router, "get_submitted_media", _fake_get)

    expired = _client(_settings(), lambda _r: httpx.Response(400, json={"ok": False}))
    assert expired.get(f"/v1/media/{media.id}/content", headers=AUTH).status_code == 404

    down = _client(_settings(), lambda _r: httpx.Response(500, text="boom"))
    response = down.get(f"/v1/media/{media.id}/content", headers=AUTH)
    assert response.status_code == 502
    assert TOKEN not in response.text


def test_hostile_file_name_cannot_inject_a_response_header(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """``original_file_name`` lo elige quien envía el reporte."""

    media = _media(file_name='evil"\r\nX-Injected: 1.jpg')

    async def _fake_get(_pool: object, _media_id: UUID) -> ReportMedia:
        return media

    monkeypatch.setattr(media_router, "get_submitted_media", _fake_get)
    client = _client(_settings(), _telegram_ok)

    response = client.get(f"/v1/media/{media.id}/content", headers=AUTH)
    assert response.status_code == 200
    assert "x-injected" not in response.headers
    disposition = response.headers["content-disposition"]
    assert "\r" not in disposition and "\n" not in disposition
    assert disposition.startswith("attachment; filename*=UTF-8''")


def test_missing_mime_falls_back_by_media_type_not_by_file_name(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    media = _media(file_name="factura.exe", mime=None)

    async def _fake_get(_pool: object, _media_id: UUID) -> ReportMedia:
        return media

    monkeypatch.setattr(media_router, "get_submitted_media", _fake_get)
    client = _client(_settings(), _telegram_ok)

    response = client.get(f"/v1/media/{media.id}/content", headers=AUTH)
    assert response.headers["content-type"].startswith("image/jpeg")


# ---------------------------------------------------- utilidades de bajo nivel

async def test_resolve_file_path_rejects_a_traversal_style_path() -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200, json={"ok": True, "result": {"file_path": "../../etc/passwd"}}
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(TelegramFileError, match="formato inesperado"):
            await resolve_file_path(client, TOKEN, "cualquier-file-id")


async def test_resolve_file_path_maps_a_rejected_id_to_not_found() -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(404, json={"ok": False})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(TelegramFileNotFoundError):
            await resolve_file_path(client, TOKEN, "file-id-caducado")


async def test_network_failures_never_carry_the_token_in_their_message() -> None:
    """httpx incluye la URL en sus errores, y la URL lleva el token."""

    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("fallo al conectar", request=request)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(TelegramFileError) as excinfo:
            await resolve_file_path(client, TOKEN, "file-id")
        assert TOKEN not in str(excinfo.value)

        with pytest.raises(TelegramFileError) as excinfo:
            async for _chunk in stream_file(client, TOKEN, "photos/a.jpg", 1024):
                pass
        assert TOKEN not in str(excinfo.value)


def test_redact_replaces_every_occurrence_of_the_token() -> None:
    message = f"GET {TELEGRAM_API_BASE}/bot{TOKEN}/getFile falló; token={TOKEN}"
    assert TOKEN not in _redact(message, TOKEN)
    assert _redact("sin token", "") == "sin token"


def test_page_size_is_capped_so_a_client_cannot_ask_for_the_whole_table() -> None:
    assert _clamp_limit(10) == 10
    assert _clamp_limit(MAX_PAGE_SIZE + 5_000) == MAX_PAGE_SIZE
    for invalid in (0, -1, True, "50"):
        with pytest.raises(ValueError):
            _clamp_limit(invalid)  # type: ignore[arg-type]
