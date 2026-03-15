from bsutils.logger.bslogger import BSLogger

from ._mixins import (
    AuthMixin,
    ChannelsMixin,
    DiscoveryMixin,
    InteractiveMixin,
    ProcessingMixin,
    ValidationMixin,
)
class BSTelegramUserClient(
    InteractiveMixin,
    ChannelsMixin,
    DiscoveryMixin,
    ProcessingMixin,
    AuthMixin,
    ValidationMixin,
):
    """
    Telegram user client that composes authentication, channel management,
    dialog discovery, message processing and interactive flow via mixins.
    """
    def __init__(
        self,
        api_id: int,
        api_hash: str,
        phone_number: str,
        session_file_path: str,
        logger: BSLogger,
        process_messages_endpoint: str,
    ) -> None:
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
