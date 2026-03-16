from __future__ import annotations

from typing import TYPE_CHECKING, Awaitable, Callable

if TYPE_CHECKING:
    from telethon import TelegramClient
    from bsutils.logger.bslogger import BSLogger


class ChannelsListeningMixin:
    """Mixin for listening channels management."""

    # Attributes provided by BSTelegramUserClient.__init__; declared here for type-checker only
    client: TelegramClient
    logger: BSLogger
    telegram_user_id: str | None
    channels_to_listen_from: list[str]

    # Method provided by DiscoveryMixin via MRO
    _resolve_channel_identifier: Callable[..., Awaitable[str]]

    async def start_listening_channels(self) -> None:
        self._ensure_client_ready()

        if not self.channels_to_listen_from:
            raise ValueError("No channels configured to listen from. Use add_channel_to_listen() first.")

        if not await self.is_authenticated():
            raise RuntimeError("Client not authenticated. Complete authentication flow first.")

        await self._set_telegram_user_id()
        self._register_channel_listeners()
        self.logger.info(f"User '{self.telegram_user_id}' started listening")

        await self.client.run_until_disconnected()

    # TODO: tenemos que comprobar aquí que el channel indicado se corresponde con un dialog real del usuario
    async def add_channel_to_listen(self, channel: str) -> bool:
        """
        Añade un canal a la lista de escucha.

        Acepta indistintamente:
          - ``"@username"`` o ``"username"`` → se usa directamente.
          - ``"Nombre completo"`` → se resuelve a su @username via Telegram.

        Args:
            channel: @username, username sin '@', o nombre completo del canal.

        Returns:
            True si el canal se añadió, False si ya estaba en la lista.
        """
        if not channel or not isinstance(channel, str):
            raise ValueError("Channel must be a non-empty string")
        resolved = await self._resolve_channel_identifier(channel.strip())
        if resolved not in self.channels_to_listen_from:
            self.channels_to_listen_from.append(resolved)
            return True
        else:
            self.logger.warning(f"Channel '{resolved}' already added")
            return False

    def remove_channel_to_listen(self, channel_username: str) -> bool:
        if channel_username in self.channels_to_listen_from:
            self.channels_to_listen_from.remove(channel_username)
            return True
        return False

    def get_listening_channels(self) -> list[str]:
        return self.channels_to_listen_from.copy()

