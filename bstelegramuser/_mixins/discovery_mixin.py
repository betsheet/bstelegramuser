from __future__ import annotations

from typing import TYPE_CHECKING, Optional

from bsutils.telegram.util import TelegramDialogType

if TYPE_CHECKING:
    from telethon import TelegramClient
    from bsutils.logger.bslogger import BSLogger
    from bstelegramuser.bstelegramuser import TelegramDialog


class DiscoveryMixin:
    """Mixin for channel and dialog discovery."""

    # Attributes provided by BSTelegramUserClient.__init__; declared here for type-checker only
    client: TelegramClient
    logger: BSLogger

    async def get_messages_from_dialog(self, chat: str, n: int) -> list:
        """
        Devuelve los «n» últimos mensajes de un canal o chat.

        El parámetro «chat» puede ser:
          - Un @username (con o sin '@'), p. ej. ``"@micanal"`` o ``"micanal"``.
          - El nombre completo del canal tal como aparece en Telegram,
            p. ej. ``"Mi Canal Privado"``. En ese caso se resuelve
            automáticamente el username llamando a get_channel_username_by_name().

        Args:
            chat: @username o nombre completo del canal/chat.
            n:    Número de mensajes a recuperar (debe ser un entero positivo).

        Returns:
            Lista de objetos ``telethon.tl.types.Message`` (la entidad completa),
            ordenados del más reciente al más antiguo.

        Raises:
            ValueError:  Si «chat» está vacío, no es string, o «n» no es un
                         entero positivo.
            RuntimeError: Si el cliente no está conectado o autenticado.
            LookupError: Si se proporciona un nombre completo y no se encuentra
                         ningún canal con ese nombre.
        """
        if not chat or not isinstance(chat, str):
            raise ValueError("'chat' must be a non-empty string")
        if not isinstance(n, int) or n <= 0:
            raise ValueError("'n' must be a positive integer")

        self._ensure_client_ready()
        if not await self.is_authenticated():
            raise RuntimeError("Cannot get messages: client not authenticated")

        # Detectar si es un username (empieza con '@') o un nombre completo.
        # Si empieza con '@' → username directo.
        # Si no, intentamos resolverlo como nombre completo primero;
        # si falla la búsqueda, asumimos que ya es un username sin '@'.
        if chat.startswith("@"):
            resolved = chat
        else:
            try:
                username = await self.get_dialog_username_by_name(chat)
                resolved = f"@{username}" if username else chat
            except LookupError:
                # No encontrado como nombre completo → tratarlo como username
                resolved = chat

        messages = await self.client.get_messages(resolved, limit=n)
        self.logger.info(f"Retrieved {len(messages)} message(s) from '{resolved}'")
        return list(messages)

    async def get_dialog_username_by_name(self, channel_name: str, entity_types: Optional[list[TelegramDialogType]] = None) -> Optional[str]:
        """
        Busca un diálogo por nombre exacto y devuelve su @username.

        Args:
            channel_name: Nombre del diálogo tal como aparece en Telegram.
            entity_types: Tipos de entidad donde buscar. Si no se indica,
                          se busca en los tres tipos (CHANNEL, USER, CHAT).

        Returns:
            El @username del diálogo (sin '@'), o None si no tiene username público.

        Raises:
            ValueError: Si channel_name está vacío o no es string.
            RuntimeError: Si el cliente no está conectado o autenticado.
            LookupError: Si no se encuentra ningún diálogo con ese nombre.
        """
        if not channel_name or not isinstance(channel_name, str):
            raise ValueError("'channel_name' must be a non-empty string")

        types = entity_types if entity_types is not None else list(TelegramDialogType)
        dialogs = await self.get_user_dialogs(types)
        for dialog in dialogs:
            if dialog.name == channel_name:
                self.logger.info(f"Dialog '{channel_name}' found with username: {dialog.username}")
                return dialog.username

        raise LookupError(f"No dialog found with name '{channel_name}'")

    async def get_user_dialogs(self, entity_types: Optional[list[TelegramDialogType]] = None) -> list[TelegramDialog]:
        """
        Devuelve la lista de diálogos del usuario autenticado filtrados por tipo de entidad.

        Args:
            entity_types: Lista de TelegramDialogType que indica qué tipos de entidad incluir.
                          Si no se indica, se devuelven todos los tipos.

        Returns:
            Lista de TelegramDialog ordenada por el orden que devuelve Telegram.

        Raises:
            ValueError:   Si entity_types no es una lista.
            RuntimeError: Si el cliente no está conectado o autenticado.
        """
        from bstelegramuser.bstelegramuser import TelegramDialog

        if entity_types is None:
            entity_types = list(TelegramDialogType)
        if not isinstance(entity_types, list):
            raise ValueError("'entity_types' must be a list of TelegramDialogType values")

        self._ensure_client_ready()
        if not await self.is_authenticated():
            raise RuntimeError("Cannot get dialogs: client not authenticated")

        requested_types = {ct.value for ct in entity_types}
        dialogs = []

        async for dialog in self.client.iter_dialogs():
            entity_type = type(dialog.entity).__name__
            if entity_type not in requested_types:
                continue
            dialogs.append(TelegramDialog.from_telethon(dialog))

        self.logger.info(f"Found {len(dialogs)} dialog(s) for types {[ct.value for ct in entity_types]}")
        return dialogs

