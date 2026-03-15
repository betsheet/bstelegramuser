from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from telethon import TelegramClient
    from bsutils.logger.bslogger import BSLogger


class InteractiveMixin:
    """Mixin for interactive flow and context manager support."""

    # Attributes provided by BSTelegramUserClient.__init__; declared here for type-checker only
    client: TelegramClient
    logger: BSLogger
    phone_number: str
    telegram_user_id: str | None
    channels_to_listen_from: list[str]

    async def disconnect_client(self) -> None:
        if self.client and self.client.is_connected():
            await self.client.disconnect()  # type: ignore[misc]
            self.logger.info(f"Client with id '{self.telegram_user_id}' disconnected from Telegram")

    async def _interactive_start(self) -> None:
        # !! la llamada a client.start() requiere de la interacción del usuario mediante input() (no vale para app web).
        # Es aquí donde se hace la autenticación del usuario (de forma interactiva)
        await self.client.start(phone=self.phone_number)  # type: ignore[misc]
        me = await self.client.get_me()
        self.telegram_user_id = str(me.id)

    async def interactive_start_listening_channels(self):
        if not self.channels_to_listen_from:
            raise ValueError("No channels configured to listen from. Use add_channel_to_listen() first.")

        await self._interactive_start()
        self._register_channel_listeners()
        self.logger.info(f"User '{self.telegram_user_id}' started listening")
        await self.client.run_until_disconnected()

    def __enter__(self):
        """
        Prevent usage of sync context manager.

        Raises:
            RuntimeError: Always, to force users to use async context manager
        """
        raise RuntimeError("Use async context manager (async with) instead of sync context manager")

    async def __aenter__(self):
        """
        Async context manager entry point.

        Starts the client interactively when entering the context.
        """
        await self._interactive_start()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """
        Async context manager exit point.

        Disconnects the client when exiting the context.
        """
        await self.disconnect_client()

