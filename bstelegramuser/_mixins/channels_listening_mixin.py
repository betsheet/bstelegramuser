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
        """
        Start listening for new messages on all configured channels.

        Registers event handlers for every channel in ``channels_to_listen_from``
        and blocks until the client is disconnected.
        Must be called after adding at least one channel via ``add_channel_to_listen()``
        and completing the authentication flow.

        Raises:
            ValueError: If no channels have been configured.
            RuntimeError: If the client is not connected or not authenticated.
        """
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
        Add a channel to the listening list.

        Accepts any of the following formats interchangeably:
          - ``"@username"`` or ``"username"`` — used directly.
          - ``"Full channel name"`` — resolved to its ``@username`` via Telegram.

        Args:
            channel: ``@username``, username without ``@``, or full display name of the channel.

        Returns:
            ``True`` if the channel was added, ``False`` if it was already in the list.

        Raises:
            ValueError: If ``channel`` is empty or not a string.
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
        """
        Remove a channel from the listening list.

        Args:
            channel_username: The channel identifier to remove, exactly as it
                              was stored (i.e. the resolved value returned by
                              ``add_channel_to_listen``).

        Returns:
            ``True`` if the channel was found and removed, ``False`` if it was
            not in the list.
        """
        if channel_username in self.channels_to_listen_from:
            self.channels_to_listen_from.remove(channel_username)
            return True
        return False

    def get_listening_channels(self) -> list[str]:
        """
        Return a copy of the current listening channel list.

        Returns:
            A new list containing the resolved identifiers of all channels
            currently configured for listening.
        """
        return self.channels_to_listen_from.copy()
