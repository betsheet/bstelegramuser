import os
from datetime import datetime
from typing import Optional, Callable
import requests.exceptions
from dotenv import load_dotenv
from requests import Response
import requests
from telethon import TelegramClient, events
from bsutils.apimodels.pick_message import BSTelegramPickMessage
from bsutils.logger.bslogger import BSLogger
import asyncio

class BSTelegramUserClient:
    client: TelegramClient
    
    app_api_id: int
    app_api_hash: str
    phone_number: str
    
    process_messages_endpoint: str

    session_file_path: str
    logs_dir: str

    telegram_user_id: str
    
    logger: BSLogger
    
    channels_to_listen_from: list[str]


    def __init__(self, api_id: int, api_hash: str, phone_number: str, session_file_path: str, logs_dir: str, process_messages_endpoint: str) -> None:
        if not api_id or not api_hash or not phone_number:
            raise ValueError("API credentials and phone number are required")
        if not process_messages_endpoint:
            raise ValueError("Process messages endpoint is required")
         
        self.app_api_hash = api_hash
        self.app_api_id = api_id
        self.phone_number = phone_number
        self.session_file_path = session_file_path
        self.logs_dir = logs_dir
        self.process_messages_endpoint = process_messages_endpoint


    def set_logger(self) -> None:
        os.makedirs(self.logs_dir, exist_ok=True)
        #self.logger = BSLogger(os.path.join(logs_dir, f'{self.telegram_user_id}_{str(datetime.now().strftime("%d%m%Y%H%M%S"))}.log'))
        self.logger = BSLogger(os.path.join(self.logs_dir, f'{str(datetime.now().strftime("%d%m%Y%H%M%S"))}.log'))


    def set_client(self) -> None:
        session_dir = os.path.dirname(self.session_file_path)
        if session_dir:  # Solo si hay un directorio (no es solo nombre de archivo)
            os.makedirs(session_dir, exist_ok=True)
            
        self.client = TelegramClient(self.session_file_path, self.app_api_id, self.app_api_hash)
        self.client.parse_mode = 'html'


    async def _start(self) -> None:
        await self.client.start(phone=self.phone_number)
        me = await self.client.get_me()
        self.telegram_user_id = str(me.id)
        self.set_logger()


    def add_channel_to_listen(self, channel_username: str) -> None:
        if not hasattr(self, 'channels_to_listen_from'):
            self.channels_to_listen_from = []
        self.channels_to_listen_from.append(channel_username)


    async def start_listening_channels(self):
        if not self.channels_to_listen_from:
            self.logger.warning("No channels configured to listen from")
            return

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
        """
        :param listen_from: canal/contacto/bot cuyos mensajes queremos escuchar
        :param on_message: función que se ejecuta para cada nuevo mensaje. Recibe como argumento el mensaje como string
        :return:
        """
        @self.client.on(events.NewMessage(from_users=listen_from.lstrip("@")))
        async def _handler(event):
            on_message(event.text, event.original_update.message.id)

    def _process_message_from_channel(self, message_html: str, telegram_message_id: str):
        payload: BSTelegramPickMessage = BSTelegramPickMessage(from_user_id=self.telegram_user_id, content=message_html)
        payload_json: dict = payload.model_dump(by_alias=True, mode='json')

        try:
            response: Response = requests.post(
                url=self.process_messages_endpoint,
                json=payload_json
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


             
