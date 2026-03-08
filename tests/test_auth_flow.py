import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from bstelegramuser.bstelegramuser import BSTelegramUserClient


def make_logger():
    logger = MagicMock()
    logger.info = MagicMock()
    logger.warning = MagicMock()
    logger.error = MagicMock()
    return logger


def make_sent_code(phone_code_hash="hash_abc123"):
    sent = MagicMock()
    sent.phone_code_hash = phone_code_hash
    return sent


@pytest.fixture
def client_instance():
    with patch("bstelegramuser.bstelegramuser.TelegramClient") as MockTelegramClient:
        mock_tg = MagicMock()
        mock_tg.is_connected.return_value = True
        mock_tg.parse_mode = "html"
        MockTelegramClient.return_value = mock_tg
        instance = BSTelegramUserClient(
            api_id=12345,
            api_hash="dummy_hash",
            phone_number="+34600000000",
            session_file_path="/tmp/test_session",
            logger=make_logger(),
            process_messages_endpoint="https://example.com/api/messages",
        )
        instance.client = mock_tg
        yield instance


def set_connected(instance, connected):
    instance.client.is_connected.return_value = connected


def set_authorized(instance, authorized):
    instance.client.is_user_authorized = AsyncMock(return_value=authorized)


class TestInitValidation:
    def test_invalid_api_id_raises(self):
        with pytest.raises(ValueError, match="API ID"):
            BSTelegramUserClient(api_id=-1, api_hash="hash", phone_number="+34600000000",
                session_file_path="/tmp/s", logger=make_logger(),
                process_messages_endpoint="https://example.com/api")

    def test_empty_api_hash_raises(self):
        with pytest.raises(ValueError, match="API hash"):
            BSTelegramUserClient(api_id=1, api_hash="", phone_number="+34600000000",
                session_file_path="/tmp/s", logger=make_logger(),
                process_messages_endpoint="https://example.com/api")

    def test_empty_phone_raises(self):
        with pytest.raises(ValueError, match="Phone number"):
            BSTelegramUserClient(api_id=1, api_hash="hash", phone_number="",
                session_file_path="/tmp/s", logger=make_logger(),
                process_messages_endpoint="https://example.com/api")

    def test_invalid_endpoint_raises(self):
        with pytest.raises(ValueError, match="endpoint"):
            BSTelegramUserClient(api_id=1, api_hash="hash", phone_number="+34600000000",
                session_file_path="/tmp/s", logger=make_logger(),
                process_messages_endpoint="not-a-url")


class TestIsAuthenticated:
    @pytest.mark.asyncio
    async def test_returns_true_when_authorized(self, client_instance):
        set_authorized(client_instance, True)
        assert await client_instance.is_authenticated() is True

    @pytest.mark.asyncio
    async def test_returns_false_when_not_authorized(self, client_instance):
        set_authorized(client_instance, False)
        assert await client_instance.is_authenticated() is False

    @pytest.mark.asyncio
    async def test_raises_if_not_connected(self, client_instance):
        set_connected(client_instance, False)
        with pytest.raises(RuntimeError, match="not connected"):
            await client_instance.is_authenticated()


class TestRequestVerificationCode:
    @pytest.mark.asyncio
    async def test_sends_code_via_app_by_default(self, client_instance):
        set_authorized(client_instance, False)
        sent = make_sent_code("hash_001")
        client_instance.client.send_code_request = AsyncMock(return_value=sent)
        await client_instance.request_verification_code()
        client_instance.client.send_code_request.assert_called_once_with("+34600000000", force_sms=False)
        assert client_instance._phone_code_hash == "hash_001"

    @pytest.mark.asyncio
    async def test_sends_code_via_sms_when_forced(self, client_instance):
        set_authorized(client_instance, False)
        sent = make_sent_code("hash_sms")
        client_instance.client.send_code_request = AsyncMock(return_value=sent)
        await client_instance.request_verification_code(force_sms=True)
        client_instance.client.send_code_request.assert_called_once_with("+34600000000", force_sms=True)
        assert client_instance._phone_code_hash == "hash_sms"

    @pytest.mark.asyncio
    async def test_skips_if_already_authenticated(self, client_instance):
        set_authorized(client_instance, True)
        client_instance.client.send_code_request = AsyncMock()
        await client_instance.request_verification_code()
        client_instance.client.send_code_request.assert_not_called()

    @pytest.mark.asyncio
    async def test_raises_if_not_connected(self, client_instance):
        set_connected(client_instance, False)
        with pytest.raises(RuntimeError, match="not connected"):
            await client_instance.request_verification_code()


class TestResendVerificationCodeViaSms:
    @pytest.mark.asyncio
    async def test_resends_and_updates_hash(self, client_instance):
        client_instance._phone_code_hash = "hash_original"
        sent_sms = make_sent_code("hash_new")
        async_client = AsyncMock(return_value=sent_sms)
        async_client.is_connected = MagicMock(return_value=True)
        client_instance.client = async_client
        with patch("bstelegramuser.bstelegramuser.ResendCodeRequest") as MockResend:
            MockResend.return_value = MagicMock()
            await client_instance.resend_verification_code_via_sms()
        assert client_instance._phone_code_hash == "hash_new"

    @pytest.mark.asyncio
    async def test_raises_if_no_hash(self, client_instance):
        client_instance._phone_code_hash = None
        with pytest.raises(RuntimeError, match="phone_code_hash"):
            await client_instance.resend_verification_code_via_sms()

    @pytest.mark.asyncio
    async def test_raises_if_not_connected(self, client_instance):
        set_connected(client_instance, False)
        client_instance._phone_code_hash = "some_hash"
        with pytest.raises(RuntimeError, match="not connected"):
            await client_instance.resend_verification_code_via_sms()


class TestVerifyCode:
    @pytest.mark.asyncio
    async def test_signs_in_with_correct_code(self, client_instance):
        client_instance.client.sign_in = AsyncMock()
        await client_instance.verify_code("12345")
        client_instance.client.sign_in.assert_called_once_with("+34600000000", "12345")

    @pytest.mark.asyncio
    async def test_raises_on_empty_code(self, client_instance):
        with pytest.raises(ValueError, match="Verification code"):
            await client_instance.verify_code("")

    @pytest.mark.asyncio
    async def test_raises_on_none_code(self, client_instance):
        with pytest.raises((ValueError, TypeError)):
            await client_instance.verify_code(None)

    @pytest.mark.asyncio
    async def test_propagates_sign_in_exception(self, client_instance):
        client_instance.client.sign_in = AsyncMock(side_effect=Exception("SESSION_PASSWORD_NEEDED"))
        with pytest.raises(Exception, match="SESSION_PASSWORD_NEEDED"):
            await client_instance.verify_code("99999")

    @pytest.mark.asyncio
    async def test_raises_if_not_connected(self, client_instance):
        set_connected(client_instance, False)
        with pytest.raises(RuntimeError, match="not connected"):
            await client_instance.verify_code("12345")


class TestGetUserChannels:
    def _make_channel_entity(self, name, entity_id, username=None, megagroup=False):
        entity = MagicMock()
        type(entity).__name__ = "Channel"
        entity.id = entity_id
        entity.username = username
        entity.megagroup = megagroup
        dialog = MagicMock()
        dialog.entity = entity
        dialog.name = name
        return dialog

    def _make_non_channel_entity(self, name):
        entity = MagicMock()
        type(entity).__name__ = "User"
        dialog = MagicMock()
        dialog.entity = entity
        dialog.name = name
        return dialog

    @pytest.mark.asyncio
    async def test_returns_channels_and_supergroups(self, client_instance):
        set_authorized(client_instance, True)
        dialogs = [
            self._make_channel_entity("Canal Noticias", 1001, username="noticias", megagroup=False),
            self._make_channel_entity("SuperGrupo Dev", 1002, username=None, megagroup=True),
            self._make_non_channel_entity("Amigo"),
        ]

        async def fake_iter_dialogs():
            for d in dialogs:
                yield d

        client_instance.client.iter_dialogs = fake_iter_dialogs

        result = await client_instance.get_user_channels()

        assert len(result) == 2
        assert result[0] == {"id": 1001, "name": "Canal Noticias", "username": "noticias", "type": "channel"}
        assert result[1] == {"id": 1002, "name": "SuperGrupo Dev", "username": None, "type": "supergroup"}

    @pytest.mark.asyncio
    async def test_returns_empty_list_when_no_channels(self, client_instance):
        set_authorized(client_instance, True)

        async def fake_iter_dialogs():
            return
            yield  # make it an async generator

        client_instance.client.iter_dialogs = fake_iter_dialogs
        result = await client_instance.get_user_channels()
        assert result == []

    @pytest.mark.asyncio
    async def test_raises_if_not_authenticated(self, client_instance):
        set_authorized(client_instance, False)
        with pytest.raises(RuntimeError, match="not authenticated"):
            await client_instance.get_user_channels()

    @pytest.mark.asyncio
    async def test_raises_if_not_connected(self, client_instance):
        set_connected(client_instance, False)
        with pytest.raises(RuntimeError, match="not connected"):
            await client_instance.get_user_channels()


class TestGetChannelUsernameByName:
    def _make_channels(self):
        return [
            {"id": 1001, "name": "Canal Noticias", "username": "noticias", "type": "channel"},
            {"id": 1002, "name": "SuperGrupo Dev",  "username": None,        "type": "supergroup"},
            {"id": 1003, "name": "Canal Privado",   "username": None,        "type": "channel"},
        ]

    @pytest.mark.asyncio
    async def test_returns_username_for_known_channel(self, client_instance):
        client_instance.get_user_channels = AsyncMock(return_value=self._make_channels())
        result = await client_instance.get_channel_username_by_name("Canal Noticias")
        assert result == "noticias"

    @pytest.mark.asyncio
    async def test_returns_none_for_private_channel(self, client_instance):
        client_instance.get_user_channels = AsyncMock(return_value=self._make_channels())
        result = await client_instance.get_channel_username_by_name("Canal Privado")
        assert result is None

    @pytest.mark.asyncio
    async def test_raises_lookup_error_when_not_found(self, client_instance):
        client_instance.get_user_channels = AsyncMock(return_value=self._make_channels())
        with pytest.raises(LookupError, match="No channel found with name 'Inexistente'"):
            await client_instance.get_channel_username_by_name("Inexistente")

    @pytest.mark.asyncio
    async def test_raises_value_error_on_empty_name(self, client_instance):
        with pytest.raises(ValueError, match="channel_name"):
            await client_instance.get_channel_username_by_name("")

    @pytest.mark.asyncio
    async def test_raises_value_error_on_none_name(self, client_instance):
        with pytest.raises((ValueError, TypeError)):
            await client_instance.get_channel_username_by_name(None)

    @pytest.mark.asyncio
    async def test_raises_if_not_connected(self, client_instance):
        set_connected(client_instance, False)
        with pytest.raises(RuntimeError, match="not connected"):
            await client_instance.get_channel_username_by_name("Canal Noticias")

    @pytest.mark.asyncio
    async def test_raises_if_not_authenticated(self, client_instance):
        set_authorized(client_instance, False)
        with pytest.raises(RuntimeError, match="not authenticated"):
            await client_instance.get_channel_username_by_name("Canal Noticias")


class TestFullAuthFlow:
    @pytest.mark.asyncio
    async def test_complete_auth_flow(self, client_instance):
        set_connected(client_instance, False)
        client_instance.client.connect = AsyncMock()
        set_authorized(client_instance, False)
        sent = make_sent_code("hash_flow")
        client_instance.client.send_code_request = AsyncMock(return_value=sent)
        client_instance.client.sign_in = AsyncMock()
        await client_instance.connect_client()
        client_instance.client.connect.assert_called_once()
        set_connected(client_instance, True)
        await client_instance.request_verification_code()
        assert client_instance._phone_code_hash == "hash_flow"
        await client_instance.verify_code("54321")
        client_instance.client.sign_in.assert_called_once_with("+34600000000", "54321")
        set_authorized(client_instance, True)
        assert await client_instance.is_authenticated() is True

    @pytest.mark.asyncio
    async def test_auth_flow_with_sms_resend(self, client_instance):
        set_authorized(client_instance, False)
        sent_app = make_sent_code("hash_app")
        sent_sms = make_sent_code("hash_sms_resent")
        client_instance.client.send_code_request = AsyncMock(return_value=sent_app)
        client_instance.client.sign_in = AsyncMock()
        # Paso 1: código por app
        await client_instance.request_verification_code()
        assert client_instance._phone_code_hash == "hash_app"
        # Paso 2: reenvío por SMS — sustituimos el cliente por AsyncMock para poder awaitarlo
        original_sign_in = client_instance.client.sign_in
        async_client = AsyncMock(return_value=sent_sms)
        async_client.is_connected = MagicMock(return_value=True)
        async_client.sign_in = original_sign_in
        client_instance.client = async_client
        with patch("bstelegramuser.bstelegramuser.ResendCodeRequest") as MockResend:
            MockResend.return_value = MagicMock()
            await client_instance.resend_verification_code_via_sms()
        assert client_instance._phone_code_hash == "hash_sms_resent"
        # Paso 3: verificar código
        await client_instance.verify_code("11111")
        client_instance.client.sign_in.assert_called_once_with("+34600000000", "11111")
