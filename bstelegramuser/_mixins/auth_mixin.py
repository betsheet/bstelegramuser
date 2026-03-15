from __future__ import annotations

from typing import TYPE_CHECKING, Optional

from telethon.tl.functions.auth import ResendCodeRequest

if TYPE_CHECKING:
    from telethon import TelegramClient
    from bsutils.logger.bslogger import BSLogger


class AuthMixin:
    # Attributes provided by BSTelegramUserClient.__init__; declared here for type-checker only
    client: TelegramClient
    logger: BSLogger
    phone_number: str
    telegram_user_id: Optional[str]
    _phone_code_hash: Optional[str]
    """Mixin for connection and authentication logic."""

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

