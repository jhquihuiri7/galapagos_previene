"""Flujo conversacional para registrar un reporte completo.

Cada callback realiza una sola transición visible. Las transiciones sensibles
se delegan a repositorios transaccionales y el identificador del reporte se
mantiene en ``context.user_data``; las evidencias, ubicación y descripción
siempre se consultan o guardan en PostgreSQL.
"""

from __future__ import annotations

import asyncio
import logging
import math
from typing import Any
from uuid import UUID

from telegram import CallbackQuery, Update
from telegram.ext import (
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    ConversationHandler,
    MessageHandler,
    filters,
)

from app.handlers.commands import cancel, help_command, start
from app.keyboards import (
    event_type_keyboard,
    location_keyboard,
    remove_keyboard,
)
from app.models import (
    EVENT_TYPE_LABELS,
    EventType,
    ReportKind,
    ReportMediaCreate,
    WorkflowStep,
)
from app.repositories.media import (
    MediaLimitReachedError,
    NoMediaFilesError,
    create_report_media,
    finalize_media_step,
)
from app.repositories.reports import (
    create_draft,
    set_event_type,
    set_location,
    submit_report,
)
from app.services.telegram_media import extract_media_data
from app.states import (
    ACTIVE_REPORT_ID_KEY,
    CHOOSE_EVENT_TYPE,
    CHOOSE_KIND,
    DB_USER_ID_KEY,
    MAX_MEDIA_FILES,
    MEDIA_CLOSED_KEY,
    MEDIA_GROUP_TIMEOUT_SECONDS,
    MEDIA_LIMIT_NOTICE_KEY,
    MEDIA_TASK_KEY,
    WAITING_DESCRIPTION,
    WAITING_LOCATION,
    WAITING_MEDIA,
)


logger = logging.getLogger(__name__)


# El enrutador solo acepta los códigos vigentes; cualquier otro callback cae en
# la respuesta genérica de «botón fuera de paso».
_EVENT_CALLBACK_PATTERN = (
    "^event:(?:" + "|".join(event.value for event in EventType) + ")$"
)

# La carga es única: se piden todos los archivos en un solo envío.
_MEDIA_PROMPT = (
    "\U0001f4f8 Ahora envíame fotos o videos de lo que está pasando.\n\n"
    "Selecciónalos todos y envíalos juntos en un solo mensaje."
)


def validate_location(latitude: float, longitude: float) -> bool:
    """Indica si las coordenadas son numéricas, finitas y están en la Tierra."""

    if isinstance(latitude, bool) or isinstance(longitude, bool):
        return False
    try:
        normalized_latitude = float(latitude)
        normalized_longitude = float(longitude)
    except (TypeError, ValueError):
        return False
    return (
        math.isfinite(normalized_latitude)
        and math.isfinite(normalized_longitude)
        and -90.0 <= normalized_latitude <= 90.0
        and -180.0 <= normalized_longitude <= 180.0
    )


def normalize_description(text: str | None) -> str | None:
    """Recorta los extremos y valida la longitud mínima de diez caracteres."""

    if not isinstance(text, str):
        return None
    normalized = text.strip()
    return normalized if len(normalized) >= 10 else None


def validate_description(text: str | None) -> bool:
    """Devuelve ``True`` cuando el texto cumple la regla de descripción."""

    return normalize_description(text) is not None


def _pool(context: ContextTypes.DEFAULT_TYPE) -> Any:
    """Obtiene el pool compartido que inicializa ``app.bot.post_init``."""

    try:
        return context.application.bot_data["db_pool"]
    except KeyError as exc:  # pragma: no cover - fallo de arranque, no del usuario
        raise RuntimeError("El pool de PostgreSQL no está inicializado") from exc


def _configured_media_limit(context: ContextTypes.DEFAULT_TYPE) -> int:
    """Lee el límite configurable y conserva 10 como valor inicial seguro."""

    settings = context.application.bot_data.get("settings")
    value = getattr(settings, "max_media_files", MAX_MEDIA_FILES)
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        logger.warning(
            "MAX_MEDIA_FILES inválido en settings; se utilizará el valor %d",
            MAX_MEDIA_FILES,
        )
        return MAX_MEDIA_FILES
    return value


def _active_report_id(context: ContextTypes.DEFAULT_TYPE) -> UUID | None:
    """Normaliza el UUID guardado en memoria, útil también para tests/mocks."""

    value = context.user_data.get(ACTIVE_REPORT_ID_KEY)
    if isinstance(value, UUID):
        return value
    if isinstance(value, str):
        try:
            return UUID(value)
        except ValueError:
            return None
    return None


async def _answer_query(query: CallbackQuery) -> None:
    """Detiene cuanto antes la animación de carga del botón inline."""

    await query.answer()


async def _missing_session(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> int:
    """Explica cómo recuperarse si se perdió el estado en memoria."""

    context.user_data.clear()
    query = update.callback_query
    if query is not None:
        await query.answer(
            "Este reporte ya no está activo. Usa /iniciar.",
            show_alert=True,
        )
    if update.effective_message is not None:
        await update.effective_message.reply_text(
            "Este reporte ya no está activo. Usa /iniciar.",
            reply_markup=remove_keyboard(),
        )
    return ConversationHandler.END


async def choose_kind(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Crea el borrador justo después de elegir Evento o Incidente."""

    query = update.callback_query
    chat = update.effective_chat
    user_id = context.user_data.get(DB_USER_ID_KEY)
    if query is None or chat is None or user_id is None:
        return await _missing_session(update, context)
    data = query.data or ""
    try:
        report_kind = ReportKind(data.removeprefix("kind:"))
    except ValueError:
        await query.answer("Esa opción no es válida.", show_alert=True)
        return CHOOSE_KIND
    await _answer_query(query)

    next_step = (
        WorkflowStep.CHOOSE_EVENT_TYPE
        if report_kind is ReportKind.EVENT
        else WorkflowStep.WAITING_MEDIA
    )
    report_id = await create_draft(
        _pool(context),
        user_id,
        chat.id,
        report_kind,
        next_step,
    )
    context.user_data[ACTIVE_REPORT_ID_KEY] = report_id

    if report_kind is ReportKind.EVENT:
        await query.edit_message_text(
            "¿Qué tipo de evento quieres reportar?",
            reply_markup=event_type_keyboard(),
        )
        return CHOOSE_EVENT_TYPE

    _reset_media_state(context)
    await query.edit_message_text(
        "\u2705 Incidente\n\n" + _MEDIA_PROMPT
    )
    return WAITING_MEDIA


async def choose_event_type(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> int:
    """Guarda el código del evento y abre la recepción de evidencias."""

    query = update.callback_query
    report_id = _active_report_id(context)
    if query is None or report_id is None:
        return await _missing_session(update, context)
    try:
        event_type = EventType((query.data or "").removeprefix("event:"))
    except ValueError:
        await query.answer("Ese tipo de evento no es válido.", show_alert=True)
        return CHOOSE_EVENT_TYPE
    updated = await set_event_type(
        _pool(context),
        report_id,
        event_type,
        WorkflowStep.WAITING_MEDIA,
    )
    if not updated:
        await query.answer(
            "No pudimos guardar esa opción. Intenta de nuevo.",
            show_alert=True,
        )
        return CHOOSE_EVENT_TYPE
    await _answer_query(query)
    _reset_media_state(context)
    await query.edit_message_text(
        f"\u2705 Evento: {EVENT_TYPE_LABELS[event_type]}\n\n" + _MEDIA_PROMPT
    )
    return WAITING_MEDIA


async def receive_media(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Guarda cada elemento del álbum y programa el cierre de la única carga."""

    message = update.effective_message
    report_id = _active_report_id(context)
    if message is None or report_id is None:
        return await _missing_session(update, context)

    if context.user_data.get(MEDIA_CLOSED_KEY):
        # La carga es única: lo que llega tarde no entra al reporte.
        await message.reply_text(
            "Ya recibí tus archivos. Ahora necesito tu ubicación.",
            reply_markup=location_keyboard(),
        )
        return WAITING_MEDIA

    extracted = extract_media_data(message)
    if extracted is None:
        await message.reply_text("Formato no válido. Envía una foto o video.")
        return WAITING_MEDIA

    caption = message.caption.strip() if message.caption else None
    media = ReportMediaCreate(
        media_type=extracted.media_type,
        telegram_message_type=extracted.telegram_message_type,
        telegram_file_id=extracted.file_id,
        telegram_file_unique_id=extracted.file_unique_id,
        telegram_message_id=message.message_id,
        telegram_media_group_id=message.media_group_id,
        mime_type=extracted.mime_type,
        original_file_name=extracted.original_file_name,
        file_size=extracted.file_size,
        width=extracted.width,
        height=extracted.height,
        duration_seconds=extracted.duration_seconds,
        caption=caption,
    )

    limit = _configured_media_limit(context)
    try:
        # La restricción UNIQUE(report_id, telegram_message_id) hace idempotente
        # el procesamiento si Telegram vuelve a entregar la misma actualización.
        await create_report_media(
            _pool(context),
            report_id,
            media,
            max_files=limit,
        )
    except MediaLimitReachedError:
        # Un álbum grande dispararía un aviso por archivo sobrante; basta uno.
        if not context.user_data.get(MEDIA_LIMIT_NOTICE_KEY):
            context.user_data[MEDIA_LIMIT_NOTICE_KEY] = True
            await message.reply_text(
                f"Solo puedo guardar {limit} archivos; los demás no se cargaron."
            )

    if message.media_group_id is None:
        # Un envío suelto no tiene más partes en camino: se cierra de inmediato.
        await _close_media_step(context, message, report_id)
    else:
        _schedule_media_close(context, message, report_id)
    return WAITING_MEDIA


def _reset_media_state(context: ContextTypes.DEFAULT_TYPE) -> None:
    """Deja el paso de evidencias listo para una carga nueva."""

    _cancel_media_close(context)
    context.user_data.pop(MEDIA_CLOSED_KEY, None)
    context.user_data.pop(MEDIA_LIMIT_NOTICE_KEY, None)


def _cancel_media_close(context: ContextTypes.DEFAULT_TYPE) -> None:
    """Anula el cierre pendiente cuando llega otro elemento del mismo álbum."""

    task = context.user_data.pop(MEDIA_TASK_KEY, None)
    if task is not None:
        task.cancel()


def _schedule_media_close(
    context: ContextTypes.DEFAULT_TYPE,
    message: Any,
    report_id: UUID,
) -> None:
    """Reinicia la ventana de espera del álbum tras cada elemento recibido."""

    _cancel_media_close(context)

    async def _wait_and_close() -> None:
        try:
            await asyncio.sleep(MEDIA_GROUP_TIMEOUT_SECONDS)
        except asyncio.CancelledError:
            return
        context.user_data.pop(MEDIA_TASK_KEY, None)
        if _active_report_id(context) != report_id:
            # El reporte se canceló o se reinició mientras esperábamos.
            return
        try:
            await _close_media_step(context, message, report_id)
        except Exception:  # pragma: no cover - el cierre corre fuera del handler
            logger.exception("No fue posible cerrar la carga de evidencias")

    context.user_data[MEDIA_TASK_KEY] = asyncio.create_task(_wait_and_close())


async def _close_media_step(
    context: ContextTypes.DEFAULT_TYPE,
    message: Any,
    report_id: UUID,
) -> None:
    """Confirma la carga completa y pide la ubicación sin pasos intermedios."""

    if context.user_data.get(MEDIA_CLOSED_KEY):
        return
    try:
        media_count = await finalize_media_step(_pool(context), report_id)
    except NoMediaFilesError:
        await message.reply_text("Envíame al menos una foto o video.")
        return

    context.user_data[MEDIA_CLOSED_KEY] = True
    await message.reply_text(
        f"✅ Recibí {media_count} archivo(s).\n\n"
        "\U0001f4cd Ahora compárteme tu ubicación.",
        reply_markup=location_keyboard(),
    )


async def receive_location(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> int:
    """Valida y guarda latitud, longitud y precisión por separado."""

    message = update.effective_message
    report_id = _active_report_id(context)
    if message is None or report_id is None:
        return await _missing_session(update, context)
    location = message.location
    if location is None or not validate_location(
        location.latitude,
        location.longitude,
    ):
        await message.reply_text(
            "Esa ubicación no es válida. Compártela otra vez.",
            reply_markup=location_keyboard(),
        )
        return WAITING_LOCATION

    updated = await set_location(
        _pool(context),
        report_id,
        float(location.latitude),
        float(location.longitude),
        location.horizontal_accuracy,
    )
    if not updated:
        await message.reply_text(
            "No pudimos guardar la ubicación. Compártela otra vez o usa /iniciar.",
            reply_markup=location_keyboard(),
        )
        return WAITING_LOCATION
    await message.reply_text(
        "✅ Listo.\n\n"
        "✍️ Último paso: cuéntame brevemente qué ocurrió.",
        reply_markup=remove_keyboard(),
    )
    return WAITING_DESCRIPTION


async def receive_description(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> int:
    """Valida la descripción y completa el reporte en una transacción."""

    message = update.effective_message
    report_id = _active_report_id(context)
    if message is None or report_id is None:
        return await _missing_session(update, context)

    description = normalize_description(message.text)
    if description is None:
        await message.reply_text(
            "La descripción debe tener al menos 10 caracteres."
        )
        return WAITING_DESCRIPTION

    await submit_report(_pool(context), report_id, description)
    context.user_data.clear()

    await message.reply_text(
        "✅ ¡Listo! Tu reporte fue enviado.\n\n"
        "🌿 Gracias por ayudar a cuidar Galápagos.\n\n"
        "🚨 En caso de emergencia, llama al ECU 911.\n\n"
        "Escribe /nuevo para reportar algo más.",
        reply_markup=remove_keyboard(),
    )
    return ConversationHandler.END


async def unexpected_kind(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Orienta cuando se escribe texto en vez de pulsar Evento/Incidente."""

    del context
    if update.effective_message is not None:
        await update.effective_message.reply_text(
            "👆 Toca uno de los botones de arriba para continuar."
        )
    return CHOOSE_KIND


async def unexpected_event_type(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> int:
    """Orienta cuando no se utiliza uno de los botones del tipo de evento."""

    del context
    if update.effective_message is not None:
        await update.effective_message.reply_text(
            "👆 Toca uno de los botones de arriba para continuar."
        )
    return CHOOSE_EVENT_TYPE


async def unexpected_media(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Rechaza texto, audio u otros adjuntos mientras se esperan evidencias."""

    message = update.effective_message
    if message is not None:
        if context.user_data.get(MEDIA_CLOSED_KEY):
            # La carga ya se cerró: el paso vigente es la ubicación.
            await message.reply_text(
                "📍 Usa el botón para compartir tu ubicación.",
                reply_markup=location_keyboard(),
            )
        else:
            await message.reply_text("📸 Necesito una foto o video.")
    return WAITING_MEDIA


async def unexpected_location(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> int:
    """Mantiene el flujo hasta recibir un objeto Location de Telegram."""

    del context
    if update.effective_message is not None:
        await update.effective_message.reply_text(
            "📍 Usa el botón para compartir tu ubicación.",
            reply_markup=location_keyboard(),
        )
    return WAITING_LOCATION


async def unexpected_description(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> int:
    """Aclara que la descripción final debe enviarse como texto."""

    del context
    if update.effective_message is not None:
        await update.effective_message.reply_text(
            "✍️ Escríbeme la descripción como mensaje de texto."
        )
    return WAITING_DESCRIPTION


async def unexpected_callback(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:
    """Responde a botones antiguos o manipulados sin cambiar de estado."""

    del context
    if update.callback_query is not None:
        await update.callback_query.answer(
            "Ese botón no corresponde al paso actual.",
            show_alert=True,
        )


def build_conversation_handler() -> ConversationHandler:
    """Construye el flujo secuencial que registra un reporte completo."""

    supported_media = (
        filters.PHOTO
        | filters.VIDEO
        | filters.Document.IMAGE
        | filters.Document.VIDEO
    )
    not_command = ~filters.COMMAND

    return ConversationHandler(
        entry_points=[
            CommandHandler(["start", "iniciar", "nuevo"], start),
        ],
        states={
            CHOOSE_KIND: [
                CallbackQueryHandler(
                    choose_kind,
                    pattern=r"^kind:(?:EVENT|INCIDENT)$",
                ),
                CallbackQueryHandler(unexpected_callback),
                MessageHandler(not_command, unexpected_kind),
            ],
            CHOOSE_EVENT_TYPE: [
                CallbackQueryHandler(
                    choose_event_type,
                    pattern=_EVENT_CALLBACK_PATTERN,
                ),
                CallbackQueryHandler(unexpected_callback),
                MessageHandler(not_command, unexpected_event_type),
            ],
            # El cierre del álbum ocurre fuera de un handler (temporizador), de
            # modo que la conversación sigue en WAITING_MEDIA hasta que llega la
            # ubicación; por eso este estado también la atiende.
            WAITING_MEDIA: [
                CallbackQueryHandler(unexpected_callback),
                MessageHandler(supported_media, receive_media),
                MessageHandler(filters.LOCATION, receive_location),
                MessageHandler(not_command, unexpected_media),
            ],
            WAITING_LOCATION: [
                MessageHandler(filters.LOCATION, receive_location),
                CallbackQueryHandler(unexpected_callback),
                MessageHandler(not_command, unexpected_location),
            ],
            WAITING_DESCRIPTION: [
                MessageHandler(filters.TEXT & not_command, receive_description),
                CallbackQueryHandler(unexpected_callback),
                MessageHandler(not_command, unexpected_description),
            ],
        },
        fallbacks=[
            CommandHandler("cancelar", cancel),
            CommandHandler("tutorial", help_command),
        ],
        allow_reentry=True,
        per_chat=True,
        per_user=True,
    )


__all__ = [
    "build_conversation_handler",
    "choose_event_type",
    "choose_kind",
    "normalize_description",
    "receive_description",
    "receive_location",
    "receive_media",
    "unexpected_callback",
    "unexpected_description",
    "unexpected_event_type",
    "unexpected_kind",
    "unexpected_location",
    "unexpected_media",
    "validate_description",
    "validate_location",
]
