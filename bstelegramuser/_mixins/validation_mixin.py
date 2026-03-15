from __future__ import annotations

import os
from typing import TYPE_CHECKING

from telethon import TelegramClient

if TYPE_CHECKING:
    from telethon import TelegramClient as _TelegramClient


class ValidationMixin:
    # Attributes provided by BSTelegramUserClient.__init__; declared here for type-checker only
    session_file_path: str
    app_api_id: int
    app_api_hash: str
    client: _TelegramClient
    """Mixin for parameter validation and client setup."""

    @staticmethod
    def _validate_init_params(api_id: int, api_hash: str, phone_number: str, process_messages_endpoint: str) -> None:
        if not isinstance(api_id, int) or api_id <= 0:
            raise ValueError("API ID must be a positive integer")
        if not api_hash or not isinstance(api_hash, str):
            raise ValueError("API hash must be a non-empty string")
        if not phone_number or not isinstance(phone_number, str):
            raise ValueError("Phone number must be a non-empty string")
        if not process_messages_endpoint or not process_messages_endpoint.startswith(('http://', 'https://')):
            raise ValueError("Process messages endpoint must be a valid URL")

    def _ensure_client_ready(self) -> None:
        """Verifica que el cliente esté inicializado y conectado"""
        if not self.client:
            raise RuntimeError("Telegram client is not initialized")
        if not self.client.is_connected():
            raise RuntimeError("Client is not connected. Call connect_client() first.")

    def _setup_client(self) -> None:
        session_dir = os.path.dirname(self.session_file_path)
        if session_dir:  # Solo si hay un directorio (no es solo nombre de archivo)
            os.makedirs(session_dir, exist_ok=True)

        self.client = TelegramClient(self.session_file_path, self.app_api_id, self.app_api_hash)
        self.client.parse_mode = 'html'

