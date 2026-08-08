from __future__ import annotations
from bs_api_models import TelegramDialog
from bsutils.logger.bslogger import BSLogger
from bsutils.telegram.util import TelegramDialogType
from ._mixins import (
    AuthMixin,
    ChannelsListeningMixin,
    DiscoveryMixin,
    InteractiveMixin,
    ProcessingMixin,
    ValidationMixin,
)


def telegram_dialog_from_telethon(dialog) -> TelegramDialog:
    """
    Construye un TelegramDialog a partir del objeto dialog de Telethon
    devuelto por iter_dialogs().
    Args:
        dialog: Objeto telethon.tl.custom.Dialog devuelto por iter_dialogs().
    """
    entity = dialog.entity
    raw = dialog.dialog  # telethon.tl.types.Dialog
    entity_type = type(entity).__name__
    # ── kind y dialog_type ────────────────────────────────────────
    if entity_type == "Channel":
        dialog_type = TelegramDialogType.CHANNEL
        if getattr(entity, "gigagroup", False):
            kind = "gigagroup"
        elif getattr(entity, "megagroup", False):
            kind = "supergroup"
        else:
            kind = "channel"
    elif entity_type == "User":
        dialog_type = TelegramDialogType.USER
        kind = "bot" if getattr(entity, "bot", False) else "user"
    else:
        dialog_type = TelegramDialogType.CHAT
        kind = "group"
    # ── username principal + alternativos ─────────────────────────
    username = getattr(entity, "username", None)
    raw_extra = getattr(entity, "usernames", None) or []
    extra_usernames = [
        u.username for u in raw_extra
        if getattr(u, "username", None) and u.username != username
    ]
    if not username and extra_usernames:
        username = extra_usernames.pop(0)
    return TelegramDialog(
        # Identificación
        id=entity.id,
        name=dialog.name,
        username=username,
        access_hash=getattr(entity, "access_hash", None),
        dialog_type=dialog_type,
        kind=kind,
        extra_usernames=extra_usernames,
        # Canal / grupo
        verified=getattr(entity, "verified", None),
        scam=getattr(entity, "scam", None),
        fake=getattr(entity, "fake", None),
        restricted=getattr(entity, "restricted", None),
        participants_count=getattr(entity, "participants_count", None),
        date=getattr(entity, "date", None),
        # Usuario
        first_name=getattr(entity, "first_name", None),
        last_name=getattr(entity, "last_name", None),
        phone=getattr(entity, "phone", None),
        is_bot=getattr(entity, "bot", None),
        is_self=getattr(entity, "is_self", None),
        premium=getattr(entity, "premium", None),
        # Estado del diálogo
        unread_count=getattr(raw, "unread_count", 0) or 0,
        unread_mentions_count=getattr(raw, "unread_mentions_count", 0) or 0,
        pinned=bool(getattr(raw, "pinned", False)),
    )


class BSTelegramUserClient(
    InteractiveMixin,
    ChannelsListeningMixin,
    DiscoveryMixin,
    ProcessingMixin,
    AuthMixin,
    ValidationMixin,
):
    """
    Telegram user client that composes authentication, channel management,
    dialog discovery, message processing and interactive flow via mixins.
    """
    def __init__(
        self,
        api_id: int,
        api_hash: str,
        phone_number: str,
        session_file_path: str,
        logger: BSLogger,
        process_messages_endpoint: str,
    ) -> None:
        self._validate_init_params(api_id, api_hash, phone_number, process_messages_endpoint)
        self.app_api_hash = api_hash
        self.app_api_id = api_id
        self.phone_number = phone_number
        self.session_file_path = session_file_path
        self.process_messages_endpoint = process_messages_endpoint
        self._setup_client()
        self.telegram_user_id = None
        self.logger = logger
        self.channels_to_listen_from = []
        self._phone_code_hash = None

