import os
from http import HTTPStatus
from typing import Optional, Callable
from datetime import datetime, timezone
import requests.exceptions
from requests import Response
import requests
from telethon import TelegramClient, events
from telethon.tl.functions.auth import ResendCodeRequest
from bsutils.logger.bslogger import BSLogger
from bsutils.apimodels.pick_message import BSTelegramPickMessage

# TODO: recopilar todas las exceptions que tenemos.
class BSTelegramUserClient:
    # Telegram data
    client: Optional[TelegramClient]
    app_api_id: int
    app_api_hash: str
    telegram_user_id: Optional[str]
    phone_number: str
    session_file_path: str

    # Messages
    channels_to_listen_from: list[str]
    process_messages_endpoint: str

    # Auth state
    _phone_code_hash: Optional[str]

    # Logger
    logger: Optional[BSLogger]
    
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

        if not self.telegram_user_id:
            me = await self.client.get_me()
            self.telegram_user_id = str(me.id)
            self._ensure_client_ready()
            self.logger.info(f"User ID set: {self.telegram_user_id}")

        self.logger.info(f"User ID is already set: {self.telegram_user_id}")

    # Listening channels management
    async def start_listening_channels(self) -> None:
        self._ensure_client_ready()

        if not self.channels_to_listen_from:
            raise ValueError("No channels configured to listen from. Use add_channel_to_listen() first.")

        if not self.client or not self.client.is_connected():
            raise RuntimeError("Client not connected. Call connect_client() first.")

        if not await self.is_authenticated():
            raise RuntimeError("Client not authenticated. Complete authentication flow first.")

        await self._set_telegram_user_id()
        self.logger.info(f"User '{self.telegram_user_id}' started listening")

        # Configurar listeners para cada canal
        for channel in self.channels_to_listen_from:
            self._add_listener(channel, self._process_message_from_channel)
            self.logger.info(f"Listening messages from '{channel}'")

        # Mantener conexión activa
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
                username = await self.get_channel_username_by_name(chat)
                resolved = f"@{username}" if username else chat
            except LookupError:
                # No encontrado como nombre completo → tratarlo como username
                resolved = chat

        messages = await self.client.get_messages(resolved, limit=n)
        self.logger.info(f"Retrieved {len(messages)} message(s) from '{resolved}'")
        return list(messages)

    async def get_channel_username_by_name(self, channel_name: str) -> Optional[str]:
        """
        Busca un canal por nombre exacto y devuelve su @username.

        Args:
            channel_name: Nombre del canal tal como aparece en Telegram.

        Returns:
            El @username del canal (sin '@'), o None si el canal es privado
            y no tiene username público.

        Raises:
            ValueError: Si channel_name está vacío o no es string.
            RuntimeError: Si el cliente no está conectado o autenticado.
            LookupError: Si no se encuentra ningún canal con ese nombre.
        """
        if not channel_name or not isinstance(channel_name, str):
            raise ValueError("'channel_name' must be a non-empty string")

        channels = await self.get_user_channels()
        for channel in channels:
            if channel["name"] == channel_name:
                self.logger.info(f"Channel '{channel_name}' found with username: {channel['username']}")
                return channel["username"]

        raise LookupError(f"No channel found with name '{channel_name}'")


    async def get_user_channels(self) -> list[dict]:
        """
        Devuelve la lista de canales y supergrupos a los que pertenece el usuario autenticado.

        Returns:
            Lista de dicts con las claves:
              - 'id'       (int)  : identificador interno del canal
              - 'name'     (str)  : nombre del canal
              - 'username' (str | None): @username público, o None si es privado
              - 'type'     (str)  : 'channel' o 'supergroup'

        Raises:
            RuntimeError: si el cliente no está conectado o autenticado.
        """
        self._ensure_client_ready()

        if not await self.is_authenticated():
            raise RuntimeError("Cannot get channels: client not authenticated")

        channels = []
        async for dialog in self.client.iter_dialogs():
            entity = dialog.entity
            entity_type = type(entity).__name__

            # Channel: canales de difusión y supergrupos
            if entity_type == "Channel":
                kind = "supergroup" if getattr(entity, "megagroup", False) else "channel"
                # TODO: entidad Channel
                channels.append({
                    "id": entity.id,
                    "name": dialog.name,
                    "username": getattr(entity, "username", None),
                    "type": kind,
                })

        self.logger.info(f"Found {len(channels)} channels for the authenticated user")
        return channels

    def _add_listener(self, listen_from: str, on_message: Optional[Callable[[str, str], None]] = print) -> None:
        @self.client.on(events.NewMessage(from_users=listen_from.lstrip("@")))
        async def _handler(event):
            try:
                # Intentar obtener el texto del mensaje
                message_text = ""
                if hasattr(event, 'text') and event.text:
                    message_text = event.text
                elif hasattr(event, 'message') and hasattr(event.message, 'message'):
                    message_text = event.message.message

                # Intentar obtener el ID del mensaje de múltiples formas
                message_id = None

                # Opción 1: Directamente desde event.message.id
                if hasattr(event, 'message') and hasattr(event.message, 'id'):
                    message_id = str(event.message.id)
                # Opción 2: Desde event.original_update.message.id (si message es objeto)
                elif (hasattr(event, 'original_update') and
                      hasattr(event.original_update, 'message') and
                      not isinstance(event.original_update.message, str) and
                      hasattr(event.original_update.message, 'id')):
                    message_id = str(event.original_update.message.id)
                # Opción 3: Desde event.id como fallback
                elif hasattr(event, 'id'):
                    message_id = str(event.id)
                else:
                    message_id = "unknown"

                on_message(message_text, message_id)

            except Exception as e:
                self.logger.error(f"Error processing message from '{listen_from}': {str(e)}")

    def _process_message_from_channel(self, message_html: str, telegram_message_id: str):
        # Obtener timestamp actual en formato dd/mm/yyyy hh:mm:ss
        timestamp = datetime.now(timezone.utc).strftime("%d/%m/%Y %H:%M:%S")

        payload: BSTelegramPickMessage = BSTelegramPickMessage(
            from_user_id=self.telegram_user_id,
            from_telegram_chat_id="",
            content=message_html,
            timestamp=timestamp
        )
        payload_json: dict = payload.model_dump(by_alias=True, mode='json')

        try:
            response: Response = requests.post(
                url=self.process_messages_endpoint,
                json=payload_json,
                timeout=30
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
        except Exception as e:
            self.logger.error(f"Unexpected error processing message '{telegram_message_id}': {str(e)}")

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
        self.logger.info(f"User '{self.telegram_user_id}' started listening.")
        for c in self.channels_to_listen_from:
            self._add_listener(c, self._process_message_from_channel)
            self.logger.info(f"Listening messages from '{c}'")
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
