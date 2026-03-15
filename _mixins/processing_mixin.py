from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from datetime import datetime, timezone
from http import HTTPStatus
from typing import TYPE_CHECKING

import requests
import requests.exceptions

from bsutils.apimodels.pick_message import BSTelegramPickMessage
from telethon import events

if TYPE_CHECKING:
    from telethon import TelegramClient
    from bsutils.logger.bslogger import BSLogger


class ProcessingMixin:
    # Attributes provided by BSTelegramUserClient.__init__; declared here for type-checker only
    client: TelegramClient
    logger: BSLogger
    telegram_user_id: str | None
    process_messages_endpoint: str
    channels_to_listen_from: list[str]
    """Mixin for message listening and processing logic."""

    def _register_channel_listeners(self) -> None:
        """Registra listeners para todos los canales configurados."""
        for channel in self.channels_to_listen_from:
            self._add_listener(channel, self._process_message_from_dialog)
            self.logger.info(f"Listening messages from '{channel}'")

    def _add_listener(self, listen_from: str, on_message: Callable[[str, str], Awaitable[None]]) -> None:
        @self.client.on(events.NewMessage(from_users=listen_from.lstrip("@")))
        async def _handler(event):
            try:
                message_text = event.message.message or ""
                message_id = str(event.message.id)
                await on_message(message_text, message_id)
            except Exception as e:
                self.logger.error(f"Error processing message from '{listen_from}': {str(e)}")

    async def _process_message_from_dialog(self, message_html: str, telegram_message_id: str) -> None:
        timestamp = datetime.now(timezone.utc).strftime("%d/%m/%Y %H:%M:%S")

        payload = BSTelegramPickMessage(
            from_user_id=self.telegram_user_id,
            from_telegram_chat_id="",
            content=message_html,
            timestamp=timestamp
        )
        payload_json = payload.model_dump(by_alias=True, mode='json')

        try:
            response = await asyncio.to_thread(
                requests.post,
                url=self.process_messages_endpoint,
                json=payload_json,
                timeout=30,
            )

            if response.status_code == HTTPStatus.OK:
                self.logger.info(f"Message with id '{telegram_message_id}' successfully processed.")
            else:
                self.logger.error(f"Failed to process message '{telegram_message_id}'. "
                                  f"Status: {response.status_code}, Response: {response.text}")

        except requests.exceptions.Timeout:
            self.logger.error(f"Timeout processing message '{telegram_message_id}'")
        except requests.exceptions.ConnectionError:
            self.logger.error(f"Connection error processing message '{telegram_message_id}'")
        except requests.exceptions.RequestException as e:
            self.logger.error(f"Request error processing message '{telegram_message_id}': {str(e)}")

