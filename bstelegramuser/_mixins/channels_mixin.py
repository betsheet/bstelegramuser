from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from telethon import TelegramClient
    from bsutils.logger.bslogger import BSLogger


class ChannelsMixin:
    # Attributes provided by BSTelegramUserClient.__init__; declared here for type-checker only
    client: TelegramClient
    logger: BSLogger
    telegram_user_id: str | None
    channels_to_listen_from: list[str]
    """Mixin for listening channels management."""

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

    def add_channel_to_listen(self, channel_username: str) -> bool:
        if not channel_username or not isinstance(channel_username, str):
            raise ValueError("Channel username must be a non-empty string")
        normalized_channel = channel_username.strip()
        if normalized_channel not in self.channels_to_listen_from:
            self.channels_to_listen_from.append(normalized_channel)
            return True
        else:
            self.logger.warning(f"Channel '{normalized_channel}' already added")
            return False

    def remove_channel_to_listen(self, channel_username: str) -> bool:
        if channel_username in self.channels_to_listen_from:
            self.channels_to_listen_from.remove(channel_username)
            return True
        return False

    def get_listening_channels(self) -> list[str]:
        return self.channels_to_listen_from.copy()

