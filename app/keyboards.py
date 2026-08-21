"""Teclados del bot.

Los botones inline envían un ``callback_data`` corto y controlado por la
aplicación. El botón de ubicación es un teclado de respuesta porque Telegram
solo admite ``request_location=True`` en ese tipo de teclado.
"""

from telegram import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    ReplyKeyboardMarkup,
    ReplyKeyboardRemove,
)

from app.models import EVENT_TYPE_BUTTONS, ReportKind


def report_kind_keyboard() -> InlineKeyboardMarkup:
    """Permite elegir entre un evento natural/antrópico o un incidente."""

    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(
                    "🌋 Evento", callback_data=f"kind:{ReportKind.EVENT.value}"
                ),
                InlineKeyboardButton(
                    "⚠️ Incidente", callback_data=f"kind:{ReportKind.INCIDENT.value}"
                ),
            ]
        ]
    )


def event_type_keyboard() -> InlineKeyboardMarkup:
    """Muestra los quince eventos adversos sembrados por ``schema.sql``.

    Se agrupan de dos en dos para que la lista completa quepa en pantalla sin
    obligar al usuario a desplazarse demasiado.
    """

    buttons = [
        InlineKeyboardButton(label, callback_data=f"event:{event_type.value}")
        for event_type, label in EVENT_TYPE_BUTTONS.items()
    ]
    rows = [buttons[index : index + 2] for index in range(0, len(buttons), 2)]
    return InlineKeyboardMarkup(rows)


def finish_media_keyboard() -> InlineKeyboardMarkup:
    """Mantiene el avance bajo control explícito del usuario, incluso en álbumes."""

    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(
                    "✅ Finalizar fotos y videos", callback_data="media:finish"
                )
            ]
        ]
    )


def location_keyboard() -> ReplyKeyboardMarkup:
    """Solicita la ubicación actual; Telegram también deja elegirla en el mapa."""

    return ReplyKeyboardMarkup(
        [
            [
                KeyboardButton(
                    "📍 Compartir mi ubicación",
                    request_location=True,
                )
            ]
        ],
        resize_keyboard=True,
        one_time_keyboard=True,
    )


def remove_keyboard() -> ReplyKeyboardRemove:
    """Crea el objeto que ordena a Telegram ocultar el teclado de respuesta."""

    return ReplyKeyboardRemove()


__all__ = [
    "event_type_keyboard",
    "finish_media_keyboard",
    "location_keyboard",
    "remove_keyboard",
    "report_kind_keyboard",
]
