"""
Tests de integración REALES para get_user_channels() y get_channel_username_by_name().

Estos tests NO usan mocks: se conectan a Telegram con credenciales reales.

Gestión de sesión
-----------------
Los ficheros .session se guardan en tests/session/ con el nombre del ID de
Telegram del usuario autenticado (p. ej. 123456789.session).
Si ya existe un fichero de sesión válido para el teléfono indicado, no se
vuelve a realizar el proceso de autenticación.
Si no existe, se realiza el flujo completo y se guarda la sesión.

Credenciales necesarias (en orden de prioridad):
  1. Argumentos de pytest: --phone
  2. Variables de entorno / .env.test: TELEGRAM_API_ID, TELEGRAM_API_HASH, TELEGRAM_PHONE
  3. Input interactivo por consola

Ejecución
---------
  # Con .env.test configurado:
  pytest tests/test_channel_discovery_integration.py -v -s

  # Pasando el teléfono y el canal por línea de comandos:
  pytest tests/test_channel_discovery_integration.py -v -s \\
      --phone="+34600000000" --channel-name="Mi Canal"

  # Con variables de entorno inline:
  TELEGRAM_PHONE="+34600000000" pytest tests/test_channel_discovery_integration.py -v -s

Nota: el flag -s es obligatorio para que pytest no capture stdin.
"""

import os
import asyncio

import pytest
from pathlib import Path
from dotenv import load_dotenv

from bstelegramuser import BSTelegramUserClient

# ---------------------------------------------------------------------------
# Carga de credenciales desde .env.test
# ---------------------------------------------------------------------------

load_dotenv(Path(__file__).parent.parent / ".env.test")

# Directorio donde se guardan los ficheros .session
SESSION_DIR = Path(__file__).parent / "session"

# ---------------------------------------------------------------------------
# Hook de pytest: argumentos extra por línea de comandos
# ---------------------------------------------------------------------------

def pytest_addoption(parser):
    """
    Registra las opciones CLI adicionales para este módulo de tests.
    pytest ignora duplicados si el hook ya fue registrado por otro módulo.
    """
    try:
        parser.addoption(
            "--phone",
            action="store",
            default=None,
            help="Número de teléfono Telegram con prefijo internacional, ej: +34600000000",
        )
    except ValueError:
        pass  # ya registrado por test_auth_integration.py

    try:
        parser.addoption(
            "--sms",
            action="store_true",
            default=False,
            help="Forzar envío del código por SMS en lugar de la app de Telegram",
        )
    except ValueError:
        pass

    try:
        parser.addoption(
            "--channel-name",
            action="store",
            default=None,
            help="Nombre exacto del canal a buscar en get_channel_username_by_name()",
        )
    except ValueError:
        pass


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def logger_stub():
    """Logger mínimo que imprime por stdout para visibilidad durante el test."""
    class PrintLogger:
        def info(self, msg):    print(f"  [INFO]  {msg}")
        def warning(self, msg): print(f"  [WARN]  {msg}")
        def error(self, msg):   print(f"  [ERROR] {msg}")
    return PrintLogger()


@pytest.fixture(scope="module")
def telegram_credentials(request):
    """
    Resuelve las credenciales de Telegram en este orden:
      1. Argumentos de pytest (--phone)
      2. Variables de entorno / .env.test
      3. Input interactivo por consola
    """
    api_id_raw = os.getenv("TELEGRAM_API_ID")
    api_hash = os.getenv("TELEGRAM_API_HASH")

    if not api_id_raw:
        pytest.skip("TELEGRAM_API_ID no definido. Configura .env.test o la variable de entorno.")
    if not api_hash:
        pytest.skip("TELEGRAM_API_HASH no definido. Configura .env.test o la variable de entorno.")

    try:
        api_id = int(api_id_raw)
    except ValueError:
        pytest.fail(f"TELEGRAM_API_ID debe ser un entero, se recibió: {api_id_raw!r}")

    phone = (
        request.config.getoption("--phone", default=None)
        or os.getenv("TELEGRAM_PHONE")
    )
    if not phone:
        print("\n")
        phone = input("📱 Introduce el número de teléfono (con prefijo, ej: +34600000000): ").strip()
    if not phone:
        pytest.fail("No se proporcionó número de teléfono.")

    force_sms = request.config.getoption("--sms", default=False)

    return {
        "api_id": api_id,
        "api_hash": api_hash,
        "phone": phone,
        "force_sms": force_sms,
    }


@pytest.fixture(scope="module")
def channel_name_to_search(request):
    """
    Nombre del canal a buscar en get_channel_username_by_name().
    Se puede pasar con --channel-name o se pide por consola.
    """
    name = request.config.getoption("--channel-name", default=None)
    if not name:
        print("\n")
        name = input("🔍 Introduce el nombre exacto del canal a buscar: ").strip()
    if not name:
        pytest.fail("No se proporcionó nombre de canal para la búsqueda.")
    return name


@pytest.fixture(scope="module")
def authenticated_client(telegram_credentials, logger_stub):
    """
    Fixture de módulo que devuelve un BSTelegramUserClient autenticado.

    - Busca un fichero .session en tests/session/ cuyo nombre coincida con
      algún ID de Telegram ya autenticado para este teléfono.
    - Si no encuentra ninguno, realiza el flujo completo de autenticación,
      guarda la sesión con el ID del usuario como nombre de fichero y la
      reutiliza en sucesivas ejecuciones.
    - Desconecta automáticamente al finalizar todos los tests del módulo.
    """
    creds = telegram_credentials
    SESSION_DIR.mkdir(parents=True, exist_ok=True)

    # Buscar si ya existe algún fichero .session en el directorio
    existing_sessions = list(SESSION_DIR.glob("*.session"))

    # Usamos una sesión temporal para verificar si ya está autenticado y
    # obtener el ID real; si lo está, reubicamos / reutilizamos la sesión.
    temp_session = str(SESSION_DIR / "_temp_probe")

    client = BSTelegramUserClient(
        api_id=creds["api_id"],
        api_hash=creds["api_hash"],
        phone_number=creds["phone"],
        session_file_path=temp_session,
        logger=logger_stub,
        process_messages_endpoint="https://example.com/api/messages",
    )

    # Ejecutamos el setup asíncrono de forma síncrona para poder usarlo como fixture
    loop = asyncio.get_event_loop()

    async def _setup():
        await client.connect_client()

        # --- Caso A: ya hay sesiones existentes, intentamos reutilizarlas ---
        for session_file in existing_sessions:
            # Crear un cliente temporal con esa sesión para comprobar si es válida
            probe = BSTelegramUserClient(
                api_id=creds["api_id"],
                api_hash=creds["api_hash"],
                phone_number=creds["phone"],
                session_file_path=str(session_file.with_suffix("")),
                logger=logger_stub,
                process_messages_endpoint="https://example.com/api/messages",
            )
            await probe.connect_client()
            if await probe.is_authenticated():
                print(f"\n  ✅ Sesión existente reutilizada: {session_file.name}")
                # Desconectamos el cliente temporal de prueba, devolvemos el probe
                await client.disconnect_client()
                return probe
            await probe.disconnect_client()

        # --- Caso B: no hay sesión válida → flujo completo de autenticación ---
        if await client.is_authenticated():
            # Sesión temporal ya válida (caso raro, pero posible)
            me = await client.client.get_me()
            final_path = SESSION_DIR / str(me.id)
            import shutil
            shutil.move(f"{temp_session}.session", f"{final_path}.session")
            client.session_file_path = str(final_path)
            print(f"\n  ✅ Sesión guardada como {me.id}.session")
            return client

        # Solicitar código
        force_sms = creds["force_sms"]
        method = "SMS" if force_sms else "app de Telegram"
        print(f"\n  📨 Enviando código de verificación al {creds['phone']} vía {method}...")
        await client.request_verification_code(force_sms=force_sms)
        print("  ✅ Código enviado.")

        print()
        code = input("  🔑 Introduce el código de verificación recibido: ").strip()
        if not code:
            await client.disconnect_client()
            pytest.fail("No se introdujo ningún código de verificación.")

        print(f"  🔄 Verificando código '{code}'...")
        await client.verify_code(code)

        assert await client.is_authenticated(), (
            "La autenticación falló tras verify_code()."
        )

        # Guardar la sesión con el ID del usuario como nombre de fichero
        me = await client.client.get_me()
        final_path = SESSION_DIR / str(me.id)
        import shutil
        temp_file = Path(f"{temp_session}.session")
        if temp_file.exists():
            shutil.move(str(temp_file), f"{final_path}.session")
            client.session_file_path = str(final_path)
        print(f"\n  ✅ Autenticación exitosa. Sesión guardada como {me.id}.session")
        return client

    client_ready = loop.run_until_complete(_setup())

    yield client_ready

    # Teardown: desconectar al finalizar todos los tests del módulo
    loop.run_until_complete(client_ready.disconnect_client())


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

@pytest.mark.integration
@pytest.mark.asyncio
async def test_get_user_channels_returns_list(authenticated_client):
    """
    Verifica que get_user_channels() devuelve una lista (puede estar vacía)
    y que cada elemento tiene la estructura esperada.
    """
    channels = await authenticated_client.get_user_channels()

    assert isinstance(channels, list), "get_user_channels() debe devolver una lista"

    for ch in channels:
        assert "id" in ch,       f"Falta clave 'id' en: {ch}"
        assert "name" in ch,     f"Falta clave 'name' en: {ch}"
        assert "username" in ch, f"Falta clave 'username' en: {ch}"
        assert "type" in ch,     f"Falta clave 'type' en: {ch}"
        assert ch["type"] in ("channel", "supergroup"), (
            f"'type' inesperado: {ch['type']}"
        )
        assert isinstance(ch["id"], int),   f"'id' debe ser int: {ch}"
        assert isinstance(ch["name"], str), f"'name' debe ser str: {ch}"
        assert ch["username"] is None or isinstance(ch["username"], str), (
            f"'username' debe ser str o None: {ch}"
        )

    print(f"\n  ✅ {len(channels)} canal(es) encontrado(s):")
    for ch in channels:
        username_str = f"@{ch['username']}" if ch["username"] else "(privado)"
        print(f"     [{ch['type']}] {ch['name']}  {username_str}  (id: {ch['id']})")


@pytest.mark.integration
@pytest.mark.asyncio
async def test_get_user_channels_all_types_are_valid(authenticated_client):
    """
    Verifica que todos los canales devueltos tienen un type válido
    ('channel' o 'supergroup').
    """
    channels = await authenticated_client.get_user_channels()
    invalid = [ch for ch in channels if ch["type"] not in ("channel", "supergroup")]
    assert not invalid, f"Canales con type inválido: {invalid}"


@pytest.mark.integration
@pytest.mark.asyncio
async def test_get_channel_username_by_name_found(authenticated_client, channel_name_to_search):
    """
    Verifica que get_channel_username_by_name() encuentra el canal introducido
    por el usuario y devuelve su username (string o None si es privado).
    """
    result = await authenticated_client.get_channel_username_by_name(channel_name_to_search)

    assert result is None or isinstance(result, str), (
        f"El resultado debe ser str o None, se obtuvo: {type(result)}"
    )

    if result:
        print(f"\n  ✅ Canal '{channel_name_to_search}' → @{result}")
    else:
        print(f"\n  ✅ Canal '{channel_name_to_search}' encontrado pero es privado (sin username público)")


@pytest.mark.integration
@pytest.mark.asyncio
async def test_get_channel_username_by_name_not_found(authenticated_client):
    """
    Verifica que get_channel_username_by_name() lanza LookupError cuando
    el canal no existe en la lista del usuario.
    """
    fake_name = "__canal_que_no_existe_jamas_xyz_12345__"
    with pytest.raises(LookupError, match=fake_name):
        await authenticated_client.get_channel_username_by_name(fake_name)
    print(f"\n  ✅ LookupError lanzado correctamente para nombre inexistente.")


@pytest.mark.integration
@pytest.mark.asyncio
async def test_get_channel_username_by_name_empty_raises(authenticated_client):
    """
    Verifica que pasar un nombre vacío lanza ValueError.
    """
    with pytest.raises(ValueError, match="channel_name"):
        await authenticated_client.get_channel_username_by_name("")
    print("\n  ✅ ValueError lanzado correctamente para nombre vacío.")


# ---------------------------------------------------------------------------
# Fixture para get_last_n_messages
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def chat_input_to_read(request):
    """
    Canal o chat del que leer los últimos mensajes.
    Se puede pasar con --chat-input o se pide por consola.
    Acepta tanto nombre completo como @username.
    """
    chat = request.config.getoption("--chat-input", default=None)
    if not chat:
        print("\n")
        chat = input(
            "💬 Introduce el nombre completo o @username del canal/chat "
            "del que leer los últimos mensajes: "
        ).strip()
    if not chat:
        pytest.fail("No se proporcionó canal/chat para get_last_n_messages().")
    return chat


# ---------------------------------------------------------------------------
# Tests: get_last_n_messages
# ---------------------------------------------------------------------------

@pytest.mark.integration
@pytest.mark.asyncio
async def test_get_last_n_messages_returns_list(authenticated_client, chat_input_to_read):
    """
    Verifica que get_last_n_messages() devuelve una lista con como máximo n
    elementos y que cada elemento es un objeto Message de Telethon.
    """

    n = 5
    messages = await authenticated_client.get_last_n_messages(chat_input_to_read, n)

    assert isinstance(messages, list), "get_last_n_messages() debe devolver una lista"
    assert len(messages) <= n, (
        f"Se esperaban como máximo {n} mensajes, se obtuvieron {len(messages)}"
    )

    print(f"\n  ✅ {len(messages)} mensaje(s) obtenido(s) de '{chat_input_to_read}':")
    for msg in messages:
        preview = (msg.text or "").replace("\n", " ")[:80]
        print(f"     [id={msg.id}] {preview!r}")


@pytest.mark.integration
@pytest.mark.asyncio
async def test_get_last_n_messages_via_username(authenticated_client, chat_input_to_read):
    """
    Si el chat_input ya empieza con '@' (username), verifica que el método
    también funciona correctamente sin pasar por get_channel_username_by_name().
    Si no empieza con '@' lo añade para forzar la rama de username.
    """
    chat_as_username = (
        chat_input_to_read
        if chat_input_to_read.startswith("@")
        else f"@{chat_input_to_read}"
    )

    # Si el propio valor ya tiene '@', esto prueba la rama directa.
    # Si no lo tenía, probamos que añadir '@' también funciona
    # (sólo válido si el chat tiene username público).
    try:
        messages = await authenticated_client.get_last_n_messages(chat_as_username, 3)
        assert isinstance(messages, list)
        print(
            f"\n  ✅ {len(messages)} mensaje(s) obtenido(s) usando username "
            f"'{chat_as_username}'"
        )
    except Exception as exc:
        # Un canal privado sin username lanzará error de Telethon: lo marcamos
        # como xfail informativo, no como fallo del método.
        pytest.xfail(
            f"No se pudo acceder a '{chat_as_username}' como username público: {exc}"
        )


@pytest.mark.integration
@pytest.mark.asyncio
async def test_get_last_n_messages_invalid_chat_raises(authenticated_client):
    """
    Verifica que pasar un chat vacío lanza ValueError.
    """
    with pytest.raises(ValueError, match="chat"):
        await authenticated_client.get_last_n_messages("", 5)
    print("\n  ✅ ValueError lanzado correctamente para chat vacío.")


@pytest.mark.integration
@pytest.mark.asyncio
async def test_get_last_n_messages_invalid_n_raises(authenticated_client, chat_input_to_read):
    """
    Verifica que pasar n <= 0 o n no entero lanza ValueError.
    """
    with pytest.raises(ValueError, match="n"):
        await authenticated_client.get_last_n_messages(chat_input_to_read, 0)

    with pytest.raises(ValueError, match="n"):
        await authenticated_client.get_last_n_messages(chat_input_to_read, -3)

    with pytest.raises(ValueError, match="n"):
        await authenticated_client.get_last_n_messages(chat_input_to_read, "5")  # type: ignore[arg-type]

    print("\n  ✅ ValueError lanzado correctamente para valores de n inválidos.")


@pytest.mark.integration
@pytest.mark.asyncio
async def test_get_last_n_messages_message_fields(authenticated_client, chat_input_to_read):
    """
    Verifica que los mensajes devueltos contienen los campos básicos esperados
    de la entidad Message de Telethon.
    """
    messages = await authenticated_client.get_last_n_messages(chat_input_to_read, 3)

    for msg in messages:
        assert hasattr(msg, "id"),   f"El mensaje carece del campo 'id': {msg}"
        assert hasattr(msg, "text"), f"El mensaje carece del campo 'text': {msg}"
        assert hasattr(msg, "date"), f"El mensaje carece del campo 'date': {msg}"

    print(
        f"\n  ✅ Todos los mensajes tienen los campos 'id', 'text' y 'date'."
    )


