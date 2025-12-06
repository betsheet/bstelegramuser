# bstelegramuser

Cliente de Telegram que procesa mensajes de canales y los reenvía a endpoints HTTP.

Descripción
-----------
Este proyecto proporciona un cliente de usuario de Telegram que escucha mensajes de canales especificados y los envía a endpoints HTTP configurables. Está pensado para integrarse con otros sistemas, por ejemplo, seguimiento de apuestas o servicios de notificaciones.

Características
---------------
- Conexión como usuario de Telegram (no como bot)
- Monitoreo de mensajes en canales seleccionados
- Envío de datos de mensajes a endpoints HTTP
- Fácil de configurar y extender

Requisitos
----------
- Python 3.9+
- Ver `pyproject.toml` para dependencias

Instalación
----------
Instala el paquete en modo editable:

```sh
pip install -e .
```

Uso
---

### Flujo no interactivo (recomendado para aplicaciones web)

Este flujo permite controlar cada paso de la autenticación y es compatible con aplicaciones web:

```python
import asyncio
from bstelegramuser import BSTelegramUserClient
from bsutils.logger.bslogger import BSLogger


async def main():
    # 1. Crear instancia del cliente
    telegram_client = BSTelegramUserClient(
        api_id=123456,  # Replace with your actual API ID
        api_hash="YOUR_API_HASH",  # Replace with your actual API hash
        phone_number="+1234567890",  # Replace with your phone number
        session_file_path="session.session",
        logger=BSLogger("app.log"),  # Replace with your logger instance
        process_messages_endpoint="https://your-api.com/process-message"
    )

    # 2. Conectar al servidor de Telegram
    await telegram_client.connect_client()

    # 3. Verificar si ya está autenticado
    if not await telegram_client.is_authenticated():
        # 3a. Solicitar código de verificación
        await telegram_client.request_verification_code()
        
        # 3b. Obtener código del usuario (desde formulario web, input, etc.)
        code = input("Enter verification code: ")
        
        # 3c. Verificar el código
        await telegram_client.verify_code(code)

    # 4. Añadir canales a escuchar
    telegram_client.add_channel_to_listen("channel1")
    telegram_client.add_channel_to_listen("channel2")

    # 5. Iniciar escucha
    await telegram_client.start_listening_channels()


asyncio.run(main())
```

### Flujo interactivo (para scripts de terminal)

Para scripts que se ejecutan en terminal, puedes usar el flujo interactivo simplificado:

```python
import asyncio
from bstelegramuser import BSTelegramUserClient
from bsutils.logger.bslogger import BSLogger


async def main():
    telegram_client = BSTelegramUserClient(
        api_id=123456,  # Replace with your actual API ID
        api_hash="YOUR_API_HASH",  # Replace with your actual API hash
        phone_number="+1234567890",  # Replace with your phone number
        session_file_path="session.session",
        logger=BSLogger("app.log"),
        process_messages_endpoint="https://your-api.com/process-message"
    )

    telegram_client.add_channel_to_listen("channel1")
    await telegram_client.interactive_start_listening_channels()


asyncio.run(main())
```

**Nota:** El flujo interactivo usa `input()` para solicitar el código de verificación, por lo que NO es compatible con aplicaciones web.asyncio.run(main())
```

Notas de seguridad
------------------
- No incluyas credenciales reales ni tokens en archivos que subas a repositorios públicos.
- Guarda `session_file_path` y demás secretos en variables de entorno o en mecanismos de secreto adecuados cuando vayas a desplegar.

Contribuciones
--------------
Las contribuciones son bienvenidas. Abre issues o pull requests para mejoras o correcciones.

Licencia
--------
MIT License
