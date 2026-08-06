"""Estados y constantes del flujo conversacional del bot.

Los enteros se usan únicamente dentro de :class:`telegram.ext.ConversationHandler`.
El valor persistido en PostgreSQL se representa, en cambio, mediante
``WorkflowStep`` (definido en :mod:`app.models`). Esta separación evita acoplar
detalles internos de python-telegram-bot con los datos permanentes.
"""

from typing import Final


(
    CHOOSE_KIND,
    CHOOSE_EVENT_TYPE,
    WAITING_MEDIA,
    WAITING_LOCATION,
    WAITING_DESCRIPTION,
) = range(5)

# El límite está centralizado para poder cambiarlo sin tocar los handlers.
MAX_MEDIA_FILES: Final[int] = 10

# Claves privadas que los handlers guardan durante una conversación.
DB_USER_ID_KEY: Final[str] = "db_user_id"
ACTIVE_REPORT_ID_KEY: Final[str] = "active_report_id"


__all__ = [
    "ACTIVE_REPORT_ID_KEY",
    "CHOOSE_EVENT_TYPE",
    "CHOOSE_KIND",
    "DB_USER_ID_KEY",
    "MAX_MEDIA_FILES",
    "WAITING_DESCRIPTION",
    "WAITING_LOCATION",
    "WAITING_MEDIA",
]
