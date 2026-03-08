"""
Test de integración REAL del flujo de autenticación con Telegram.

Este test NO usa mocks: realiza conexión real a Telegram, envía un código
al teléfono del usuario y espera que lo introduzca por línea de comandos.

Credenciales necesarias (en orden de prioridad):
  1. Variables de entorno:  TELEGRAM_API_ID, TELEGRAM_API_HASH, TELEGRAM_PHONE
  2. Archivo .env en la raíz del proyecto (mismo formato)
  3. Argumento --phone de pytest (solo el número de teléfono)

Ejecución:
  # Con .env configurado:
  pytest tests/test_auth_integration.py -v -s

  # Pasando el teléfono por línea de comandos:
  pytest tests/test_auth_integration.py -v -s --phone="+34600000000"

  # Con variables de entorno inline:
  TELEGRAM_PHONE="+34600000000" pytest tests/test_auth_integration.py -v -s

Flags adicionales:
  --sms   Fuerza el envío del código por SMS en lugar de la app de Telegram.

Nota: el flag -s es obligatorio para que pytest no capture stdin
      (necesario para que el usuario pueda introducir el código).
"""

import os
import sys
import asyncio
import pytest

from pathlib import Path
from dotenv import load_dotenv
from bstelegramuser.bstelegramuser import BSTelegramUserClient

# ---------------------------------------------------------------------------
# Carga de credenciales desde .env
# ---------------------------------------------------------------------------

load_dotenv(Path(__file__).parent.parent / ".env.test")


# ---------------------------------------------------------------------------
# Hook de pytest: argumentos extra por línea de comandos
# ---------------------------------------------------------------------------

def pytest_addoption(parser):
    parser.addoption(
        "--phone",
        action="store",
        default=None,
        help="Número de teléfono Telegram con prefijo internacional, ej: +34600000000",
    )
    parser.addoption(
        "--sms",
        action="store_true",
        default=False,
        help="Forzar envío del código por SMS en lugar de la app de Telegram",
    )


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def telegram_credentials(request):
    """
    Resuelve las credenciales de Telegram en este orden:
      1. Argumentos de pytest (--phone)
      2. Variables de entorno / .env
      3. Input interactivo por consola
    """
    api_id_raw = os.getenv("TELEGRAM_API_ID")
    api_hash = os.getenv("TELEGRAM_API_HASH")

    if not api_id_raw:
        pytest.skip("TELEGRAM_API_ID no definido. Configura el archivo .env o la variable de entorno.")
    if not api_hash:
        pytest.skip("TELEGRAM_API_HASH no definido. Configura el archivo .env o la variable de entorno.")

    try:
        api_id = int(api_id_raw)
    except ValueError:
        pytest.fail(f"TELEGRAM_API_ID debe ser un entero, se recibió: {api_id_raw!r}")

    # Número de teléfono: argumento CLI > variable de entorno > input interactivo
    phone = (
        request.config.getoption("--phone", default=None)
        or os.getenv("TELEGRAM_PHONE")
    )
    if not phone:
        print("\n")
        phone = input("📱 Introduce el número de teléfono (con prefijo, ej: +34600000000): ").strip()
    if not phone:
        pytest.fail("No se proporcionó número de teléfono.")

    return {
        "api_id": api_id,
        "api_hash": api_hash,
        "phone": phone,
        "force_sms": request.config.getoption("--sms", default=False),
    }


@pytest.fixture(scope="module")
def session_path(tmp_path_factory):
    """Ruta temporal para el archivo de sesión de Telegram."""
    return str(tmp_path_factory.mktemp("sessions") / "integration_test_session")


@pytest.fixture(scope="module")
def logger_stub():
    """Logger mínimo que imprime por stdout para que se vea durante el test."""
    class PrintLogger:
        def info(self, msg):    print(f"  [INFO]  {msg}")
        def warning(self, msg): print(f"  [WARN]  {msg}")
        def error(self, msg):   print(f"  [ERROR] {msg}")
    return PrintLogger()


# ---------------------------------------------------------------------------
# Test de integración
# ---------------------------------------------------------------------------

@pytest.mark.integration
@pytest.mark.asyncio
async def test_real_auth_flow(telegram_credentials, session_path, logger_stub):
    """
    Flujo completo de autenticación real con Telegram:

    1. Crea el cliente con las credenciales reales.
    2. Conecta con Telegram.
    3. Si ya está autenticado (sesión guardada), el test pasa directamente.
    4. Si no, solicita el código de verificación al teléfono.
    5. Espera a que el usuario introduzca el código por consola.
    6. Verifica el código con Telegram.
    7. Confirma que la autenticación fue exitosa.
    """
    creds = telegram_credentials

    client = BSTelegramUserClient(
        api_id=creds["api_id"],
        api_hash=creds["api_hash"],
        phone_number=creds["phone"],
        session_file_path=session_path,
        logger=logger_stub,
        process_messages_endpoint="https://example.com/api/messages",  # no se usa en auth
    )

    # Paso 1: conectar
    await client.connect_client()
    assert client.client.is_connected(), "El cliente debería estar conectado"

    # Paso 2: comprobar si ya está autenticado (sesión previa)
    if await client.is_authenticated():
        print("\n  ✅ Sesión ya autenticada (sesión reutilizada). Test superado.")
        await client.client.disconnect()
        return

    # Paso 3: solicitar código
    force_sms = creds["force_sms"]
    method = "SMS" if force_sms else "app de Telegram"
    print(f"\n  📨 Enviando código de verificación al {creds['phone']} vía {method}...")
    await client.request_verification_code(force_sms=force_sms)
    print("  ✅ Código enviado.")

    # Paso 4: pedir el código al usuario por consola
    print()
    code = input("  🔑 Introduce el código de verificación recibido: ").strip()
    if not code:
        pytest.fail("No se introdujo ningún código de verificación.")

    # Paso 5: verificar
    print(f"  🔄 Verificando código '{code}'...")
    await client.verify_code(code)

    # Paso 6: confirmar autenticación
    assert await client.is_authenticated(), (
        "La autenticación falló: is_authenticated() devolvió False tras verify_code()"
    )

    print(f"  ✅ Autenticación exitosa para {creds['phone']}.")
    await client.client.disconnect()


@pytest.mark.integration
@pytest.mark.asyncio
async def test_sms_code_delivery(telegram_credentials, session_path, logger_stub):
    """
    Verifica que el código de verificación se puede recibir y usar vía SMS.

    Flujo:
    1. Conecta con Telegram.
    2. Solicita el código forzando el envío por SMS (force_sms=True).
    3. Espera a que el usuario introduzca el código recibido por SMS.
    4. Verifica el código y confirma que la autenticación fue exitosa.

    Ejecución:
        zsh run_tests.sh --integration
        zsh run_tests.sh --integration --phone=+34600000000
    """
    creds = telegram_credentials

    client = BSTelegramUserClient(
        api_id=creds["api_id"],
        api_hash=creds["api_hash"],
        phone_number=creds["phone"],
        session_file_path=session_path,
        logger=logger_stub,
        process_messages_endpoint="https://example.com/api/messages",
    )

    # Paso 1: conectar
    await client.connect_client()
    assert client.client.is_connected(), "El cliente debería estar conectado"

    # Paso 2: si ya está autenticado (sesión previa del test anterior) desconectamos
    # la sesión para poder forzar un nuevo envío de código
    if await client.is_authenticated():
        print("\n  ℹ️  Sesión activa detectada. Cerrando sesión para forzar el envío del SMS...")
        await client.client.log_out()
        await client.client.disconnect()
        # Reconectamos con sesión limpia
        client._setup_client()
        await client.connect_client()

    # Paso 3: solicitar código explícitamente por SMS
    print(f"\n  📨 Enviando código de verificación al {creds['phone']} vía SMS (force_sms=True)...")
    await client.request_verification_code(force_sms=True)
    print("  ✅ Solicitud de código SMS enviada.")

    # Paso 4: pedir el código al usuario
    print()
    code = input("  🔑 Introduce el código recibido por SMS: ").strip()
    if not code:
        await client.client.disconnect()
        pytest.fail("No se introdujo ningún código de verificación.")

    # Paso 5: verificar el código
    print(f"  🔄 Verificando código SMS '{code}'...")
    await client.verify_code(code)

    # Paso 6: confirmar autenticación exitosa
    assert await client.is_authenticated(), (
        "La autenticación falló: is_authenticated() devolvió False tras verify_code() con SMS"
    )

    print(f"  ✅ Autenticación vía SMS exitosa para {creds['phone']}.")
    await client.client.disconnect()


