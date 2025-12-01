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
Instala el paquete en modo editable (útil durante desarrollo):

```sh
pip install -e .
```

Uso
---
Ejemplo mínimo de uso (reemplaza los placeholders por tus valores reales). Este ejemplo muestra el flujo asincrónico que inicia el cliente, añade un canal y empieza a escuchar mensajes.

```py
import asyncio
from bstelegramuser import BSTelegramUserClient

async def main():
    telegram_client = BSTelegramUserClient(
        api_id=123456,  # Reemplaza por tu API ID (entero)
        api_hash="YOUR_API_HASH",  # Reemplaza por tu API hash
        phone_number="+YOUR_PHONE_NUMBER",  # Reemplaza por tu número con prefijo internacional
        session_file_path="path/to/session.session",  # Ruta al archivo de sesión
        logger=None,  # Reemplaza con una instancia válida de logger (por ejemplo, BSLogger si la tienes)
        process_messages_endpoint="http://localhost/process-pick-message"
    )

    telegram_client.add_channel_to_listen("test")
    await telegram_client.start_listening_channels()

asyncio.run(main())
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
