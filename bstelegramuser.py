import asyncio
import os
from datetime import datetime, timezone
from http import HTTPStatus
from typing import Optional, Callable

import requests
import requests.exceptions
from telethon import TelegramClient, events
from telethon.tl.functions.auth import ResendCodeRequest

from bsutils.apimodels.pick_message import BSTelegramPickMessage
from bsutils.logger.bslogger import BSLogger
from bsutils.telegram.util import TelegramDialogType

class BSTelegramUserClient:

    def __init__(self, api_id: int, api_hash: str, phone_number: str, session_file_path: str, logger: BSLogger, process_messages_endpoint: str) -> None:
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

    # Validation and setup
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

    # Connection and authentication
    async def connect_client(self) -> None:
        if not self.client:
            raise RuntimeError("Telegram client is not initialized")
        if not self.client.is_connected():
            await self.client.connect()
            self.logger.info("Client successfully connected to Telegram")

    async def request_verification_code(self, force_sms: bool = False) -> None:
        """
        Solicita el envío del código de verificación.

        Args:
            force_sms: Si es True, intenta forzar el envío por SMS en lugar de
                       la app de Telegram. Nota: este comportamiento depende de
                       Telegram y puede no estar siempre disponible.
        """
        self._ensure_client_ready()

        if await self.is_authenticated():
            self.logger.info("User is already authenticated; no need to request code")
            return

        sent = await self.client.send_code_request(self.phone_number, force_sms=force_sms)
        self._phone_code_hash = sent.phone_code_hash
        method = "SMS" if force_sms else "Telegram app"
        self.logger.info(f"Verification code sent to {self.phone_number} via {method}")

    async def resend_verification_code_via_sms(self) -> None:
        """
        Reenvía el código de verificación por SMS.

        Telegram envía el primer código por la app; al llamar a este método
        se solicita el reenvío por el siguiente medio disponible (normalmente SMS).
        Debes haber llamado primero a request_verification_code().
        """
        self._ensure_client_ready()

        if not self._phone_code_hash:
            raise RuntimeError(
                "No phone_code_hash available. Call request_verification_code() first."
            )

        sent = await self.client(ResendCodeRequest(
            phone_number=self.phone_number,
            phone_code_hash=self._phone_code_hash
        ))
        self._phone_code_hash = sent.phone_code_hash
        self.logger.info(f"Verification code resent to {self.phone_number} via SMS")

    async def verify_code(self, code: str) -> None:
        self._ensure_client_ready()
        if not code or not isinstance(code, str):
            raise ValueError("Verification code must be a non-empty string")

        try:
            await self.client.sign_in(self.phone_number, code)
            self.logger.info("User authenticated successfully")
        except Exception as e:
            self.logger.error(f"Authentication failed: {str(e)}")
            raise

    async def is_authenticated(self) -> bool:
        self._ensure_client_ready()
        return await self.client.is_user_authorized()

    async def _set_telegram_user_id(self) -> None:
        """Obtiene y establece el ID del usuario autenticado"""
        self._ensure_client_ready()

        if not await self.is_authenticated():
            raise RuntimeError("Cannot get user ID: client not authenticated")

        if self.telegram_user_id:
            self.logger.info(f"User ID is already set: {self.telegram_user_id}")
            return

        me = await self.client.get_me()
        self.telegram_user_id = str(me.id)
        self.logger.info(f"User ID set: {self.telegram_user_id}")

    # Listening channels management
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

    # Channel discovery
    async def get_last_n_messages(self, chat: str, n: int) -> list:
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
            if dialog["name"] == channel_name:
                self.logger.info(f"Dialog '{channel_name}' found with username: {dialog['username']}")
                return dialog["username"]

        raise LookupError(f"No dialog found with name '{channel_name}'")

    async def get_user_dialogs(self, entity_types: list[TelegramDialogType]) -> list[dict]:
        """
        Devuelve la lista de diálogos del usuario autenticado filtrados por tipo de entidad.

        Args:
            entity_types: Lista de ChannelType que indica qué tipos de entidad incluir.
                          Valores posibles: ChannelType.CHANNEL, ChannelType.USER, ChannelType.CHAT.

        Returns:
            Lista de dicts con las claves:
              - 'id'       (int)        : identificador interno de la entidad
              - 'name'     (str)        : nombre del chat/canal/usuario
              - 'username' (str | None) : @username público, o None si no tiene
              - 'type'     (str)        : 'channel', 'supergroup', 'user', 'bot' o 'group'

        Raises:
            ValueError:   Si entity_types está vacío o no es una lista.
            RuntimeError: Si el cliente no está conectado o autenticado.
        """
        if not entity_types:
            entity_types = [TelegramDialogType.CHANNEL, TelegramDialogType.USER, TelegramDialogType.CHAT]
        if not isinstance(entity_types, list):
            raise ValueError("'entity_types' must be a non-empty list of ChannelType values")

        self._ensure_client_ready()

        if not await self.is_authenticated():
            raise RuntimeError("Cannot get dialogs: client not authenticated")

        requested_types = {ct.value for ct in entity_types}
        dialogs = []

        async for dialog in self.client.iter_dialogs():
            entity = dialog.entity
            entity_type = type(entity).__name__

            if entity_type not in requested_types:
                continue

            if entity_type == "Channel":
                if getattr(entity, "gigagroup", False):
                    kind = "gigagroup"
                elif getattr(entity, "megagroup", False):
                    kind = "supergroup"
                else:
                    kind = "channel"
            elif entity_type == "User":
                kind = "bot" if getattr(entity, "bot", False) else "user"
            else:  # Chat
                kind = "group"

            dialogs.append({
                "id": entity.id,
                "name": dialog.name,
                "username": getattr(entity, "username", None),
                "type": kind,
            })

        self.logger.info(f"Found {len(dialogs)} dialog(s) for types {[ct.value for ct in entity_types]}")
        return dialogs

    def _register_channel_listeners(self) -> None:
        """Registra listeners para todos los canales configurados."""
        for channel in self.channels_to_listen_from:
            self._add_listener(channel, self._process_message_from_channel)
            self.logger.info(f"Listening messages from '{channel}'")

    def _add_listener(self, listen_from: str, on_message: Callable[[str, str], None]) -> None:
        @self.client.on(events.NewMessage(from_users=listen_from.lstrip("@")))
        async def _handler(event):
            try:
                message_text = event.message.message or ""
                message_id = str(event.message.id)
                await on_message(message_text, message_id)
            except Exception as e:
                self.logger.error(f"Error processing message from '{listen_from}': {str(e)}")

    async def _process_message_from_channel(self, message_html: str, telegram_message_id: str) -> None:
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

    async def disconnect_client(self) -> None:
        if self.client and self.client.is_connected():
            await self.client.disconnect()
            self.logger.info(f"Client with id '{self.telegram_user_id}' disconnected from Telegram")

    # Interactive flow
    async def _interactive_start(self) -> None:
        # !! la llamada a client.start() requiere de la interacción del usuario mediante input() (no vale para app web).
        # Es aquí donde se hace la autenticación del usuario (de forma interactiva)
        await self.client.start(phone=self.phone_number)
        me = await self.client.get_me()
        self.telegram_user_id = str(me.id)

    async def interactive_start_listening_channels(self):
        if not self.channels_to_listen_from:
            raise ValueError("No channels configured to listen from. Use add_channel_to_listen() first.")

        await self._interactive_start()
        self._register_channel_listeners()
        self.logger.info(f"User '{self.telegram_user_id}' started listening")
        await self.client.run_until_disconnected()

    # Context managers
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
