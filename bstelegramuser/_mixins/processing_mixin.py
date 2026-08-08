from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from datetime import datetime, timezone
from http import HTTPStatus
from typing import Any

import requests
import requests.exceptions

from telethon import events

from telethon import TelegramClient
from bs_api_models import TelegramMessage
from bsutils.logger.bslogger import BSLogger

class ProcessingMixin:
    # Attributes provided by BSTelegramUserClient.__init__; declared here for type-checker only
    client: TelegramClient
    logger: BSLogger
    telegram_user_id: int
    process_messages_endpoint: str
    channels_to_listen_from: list[str]
    """Mixin for message listening and processing logic."""

    def _register_channel_listeners(self) -> None:
        """Register a new-message listener for every configured channel."""
        for channel in self.channels_to_listen_from:
            self._add_listener(channel, self._process_message_from_dialog)
            self.logger.info(f"Listening messages from '{channel}'")

    def _add_listener(self, listen_from: str, on_message: Callable[[str, str, str, str], Awaitable[None]]) -> None:
        """Attach a Telethon NewMessage handler that forwards incoming messages to *on_message*.

        Args:
            listen_from: Telegram username or channel identifier to listen from.
            on_message: Async callback that receives the message text, the
                message ID, the source chat ID, and the source chat name (all as strings).
        """
        @self.client.on(events.NewMessage(from_users=listen_from.lstrip("@")))
        async def _handler(event):
            try:
                message_text = event.message.message or ""
                message_id = str(event.message.id)
                chat_id = str(event.chat_id)
                chat = event.chat
                chat_name = getattr(chat, "username", None) or getattr(chat, "title", None) or listen_from
                await on_message(message_text, message_id, chat_id, chat_name)
            except Exception as e:
                self.logger.error(f"Error processing message from '{listen_from}': {str(e)}")

    async def _process_message_from_dialog(self, message_html: str, telegram_message_id: str, from_telegram_chat_id: str, from_telegram_chat_name: str) -> None:
        """Build a ``BSTelegramMessage`` from the raw event data and POST it to the processing API.

        Args:
            message_html: Plain-text (or HTML) content of the incoming Telegram message.
            telegram_message_id: Unique Telegram identifier of the message.
            from_telegram_chat_id: Telegram chat/channel ID where the message originated.
            from_telegram_chat_name: Username or display name of the source chat/channel.
        """
        payload = TelegramMessage(
            telegram_message_id=telegram_message_id,
            telegram_user_id=self.telegram_user_id,
            #from_telegram_chat_id=from_telegram_chat_id,
            from_telegram_chat_name=from_telegram_chat_name,
            content=message_html,
            timestamp=datetime.now(timezone.utc)
        )
        await self._send_message_pick_to_processing_endpoint(payload.model_dump(by_alias=True, mode='json'))



    async def _send_message_pick_to_processing_endpoint(self, payload_json: dict[str, Any]) -> None:
        telegram_message_id = payload_json["telegram_message_id"]
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

