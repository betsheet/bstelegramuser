import os
from typing import Optional, Callable
import requests.exceptions
from requests import Response
import requests
from telethon import TelegramClient, events
from bsutils.apimodels.pick_message import BSTelegramPickMessage
from bsutils.logger.bslogger import BSLogger


class BSTelegramUserClient:
    client: Optional[TelegramClient]
    telegram_user_id: Optional[str]
    logger: Optional[BSLogger]
    channels_to_listen_from: list[str]
    app_api_id: int
    app_api_hash: str
    phone_number: str
    process_messages_endpoint: str
    session_file_path: str
    logger: Optional[BSLogger]
    
    def __init__(self, api_id: int, api_hash: str, phone_number: str, session_file_path: str, logger: BSLogger, process_messages_endpoint: str) -> None:
        if not isinstance(api_id, int) or api_id <= 0:
            raise ValueError("API ID must be a positive integer")
        if not api_hash or not isinstance(api_hash, str):
            raise ValueError("API hash must be a non-empty string")
        if not phone_number or not isinstance(phone_number, str):
            raise ValueError("Phone number must be a non-empty string")
        if not process_messages_endpoint or not process_messages_endpoint.startswith(('http://', 'https://')):
            raise ValueError("Process messages endpoint must be a valid URL")
      
        self.app_api_hash = api_hash
        self.app_api_id = api_id
        self.phone_number = phone_number
        self.session_file_path = session_file_path

        self.process_messages_endpoint = process_messages_endpoint

        self._setup_client()

        self.telegram_user_id = None
        self.logger = logger
        self.channels_to_listen_from = []

 

    def _setup_client(self) -> None:
        session_dir = os.path.dirname(self.session_file_path)
        if session_dir:  # Solo si hay un directorio (no es solo nombre de archivo)
            os.makedirs(session_dir, exist_ok=True)
            
        self.client = TelegramClient(self.session_file_path, self.app_api_id, self.app_api_hash)
        self.client.parse_mode = 'html'


    async def _start(self) -> None:
        await self.client.start(phone=self.phone_number)
        me = await self.client.get_me()
        self.telegram_user_id = str(me.id)

    def add_channel_to_listen(self, channel_username: str) -> None:
        if not channel_username or not isinstance(channel_username, str):
            raise ValueError("Channel username must be a non-empty string")
        
        normalized_channel = channel_username.strip()
        if normalized_channel not in self.channels_to_listen_from:
            self.channels_to_listen_from.append(normalized_channel)
        else:
            if self.logger:
                self.logger.warning(f"Channel '{normalized_channel}' already added")

    def remove_channel_to_listen(self, channel_username: str) -> bool:
        if channel_username in self.channels_to_listen_from:
            self.channels_to_listen_from.remove(channel_username)
            return True
        return False

    def get_listening_channels(self) -> list[str]:
        return self.channels_to_listen_from.copy()

    async def start_listening_channels(self):
        if not self.channels_to_listen_from:
            raise ValueError("No channels configured to listen from. Use add_channel_to_listen() first.")

        await self._start()
        self.logger.info(f"User '{self.telegram_user_id}' started listening.")
        for c in self.channels_to_listen_from:
            self._add_listener(c, self._process_message_from_channel)
            self.logger.info(f"Listening messages from '{c}'")
        await self.client.run_until_disconnected()

    def __enter__(self):
        return self
    
    async def __aenter__(self):
        await self._start()
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self.client:
            await self.client.disconnect()

    def _add_listener(self, listen_from: str, on_message: Optional[Callable[[str, str], None]] = print) -> None:
        @self.client.on(events.NewMessage(from_users=listen_from.lstrip("@")))
        async def _handler(event):
            on_message(event.text, event.original_update.message.id)

    def _process_message_from_channel(self, message_html: str, telegram_message_id: str):
        payload: BSTelegramPickMessage = BSTelegramPickMessage(from_user_id=self.telegram_user_id, content=message_html)
        payload_json: dict = payload.model_dump(by_alias=True, mode='json')

        try:
            response: Response = requests.post(
                url=self.process_messages_endpoint,
                json=payload_json, 
                timeout=30
            )

            if response.status_code == 200:
                # TODO: mostrar algo más de info en el logger (id_ del pick generado, o lo que sea. Habría que devolverlo
                #  en la response que crea la API)
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


    async def verify_code(self, code: str) -> None:
        await self.client.sign_in(self.phone_number, code)

