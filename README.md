# bstelegramuser

A Python library that wraps [Telethon](https://github.com/LonamiWebs/Telethon) to provide a clean, high-level Telegram **user-client** — designed to listen to channel/chat messages and forward them to an HTTP endpoint for further processing.

---

## Features

- 🔐 **Full authentication flow** — request, resend, and verify Telegram verification codes programmatically (no interactive prompt required).
- 📡 **Channel listener** — subscribe to one or more channels/chats and receive new messages via async callbacks.
- 🌐 **HTTP forwarding** — automatically posts every incoming message to a configurable endpoint using a non-blocking `asyncio.to_thread` call.
- 🔍 **Dialog discovery** — list, search, and resolve dialogs by name or type (channel, supergroup, group, user, bot).
- 🗂️ **Session persistence** — Telethon session files keep the user authenticated across restarts.
- 🔄 **Async context manager** support for clean resource management.

---

## Requirements

- Python ≥ 3.13
- A [Telegram API ID and hash](https://my.telegram.org/apps)
- Dependencies (installed automatically):
  - `telethon >= 1.34.0`
  - `requests >= 2.31.0`
  - `bsutils` (internal package)

---

## Installation

```bash
pip install git+https://github.com/betsheet/bstelegramuser.git
```

Or, for development:

```bash
git clone https://github.com/betsheet/bstelegramuser.git
cd bstelegramuser
pip install -e ".[dev]"
```

---

## Quick Start

### 1. Obtain Telegram API credentials

Go to [https://my.telegram.org/apps](https://my.telegram.org/apps), create an application and note your **API ID** and **API Hash**.

### 2. Authenticate (first run)

On the first run the session file does not exist yet, so you need to go through the verification code flow:

```python
import asyncio
from bstelegramuser import BSTelegramUserClient
from bsutils.logger.bslogger import BSLogger

API_ID    = 12345678
API_HASH  = "your_api_hash"
PHONE     = "+34600000000"
SESSION   = "sessions/myuser.session"
ENDPOINT  = "https://my-backend.example.com/api/picks"

logger = BSLogger("myapp")

async def authenticate():
    client = BSTelegramUserClient(
        api_id=API_ID,
        api_hash=API_HASH,
        phone_number=PHONE,
        session_file_path=SESSION,
        logger=logger,
        process_messages_endpoint=ENDPOINT,
    )

    await client.connect_client()

    # Request the verification code (sent to the Telegram app by default)
    await client.request_verification_code()

    code = input("Enter the verification code: ")
    await client.verify_code(code)

    print("Authenticated! Session saved to", SESSION)
    await client.disconnect_client()

asyncio.run(authenticate())
```

> **Tip:** once authenticated the session file is reused on every subsequent run — no code is required again.

---

## Listening to Channels

```python
import asyncio
from bstelegramuser import BSTelegramUserClient
from bsutils.logger.bslogger import BSLogger

async def main():
    client = BSTelegramUserClient(
        api_id=12345678,
        api_hash="your_api_hash",
        phone_number="+34600000000",
        session_file_path="sessions/myuser.session",
        logger=BSLogger("myapp"),
        process_messages_endpoint="https://my-backend.example.com/api/picks",
    )

    await client.connect_client()

    # Add one or more channels to listen (username with or without '@')
    client.add_channel_to_listen("@my_channel")
    client.add_channel_to_listen("another_channel")

    # This blocks until disconnected, forwarding every new message to the endpoint
    await client.start_listening_channels()

asyncio.run(main())
```

Each new message is automatically serialised as a `BSTelegramPickMessage` and sent via `POST` to `process_messages_endpoint`.

---

## Interactive Mode (CLI / scripts)

If you prefer to let Telethon handle the full auth flow interactively (it will prompt for the code via `input()`), use the interactive helpers:

```python
import asyncio
from bstelegramuser import BSTelegramUserClient
from bsutils.logger.bslogger import BSLogger

async def main():
    async with BSTelegramUserClient(
        api_id=12345678,
        api_hash="your_api_hash",
        phone_number="+34600000000",
        session_file_path="sessions/myuser.session",
        logger=BSLogger("myapp"),
        process_messages_endpoint="https://my-backend.example.com/api/picks",
    ) as client:
        client.add_channel_to_listen("@my_channel")
        await client.interactive_start_listening_channels()

asyncio.run(main())
```

> ⚠️ `interactive_start_listening_channels` relies on `input()` for the verification code, so it is **not suitable for web applications or headless services**.

---

## Resending the Verification Code via SMS

If the code was sent to the Telegram app and you need it via SMS instead:

```python
await client.request_verification_code()          # sent to Telegram app
await client.resend_verification_code_via_sms()   # resend via SMS
code = input("Enter the SMS code: ")
await client.verify_code(code)
```

---

## Dialog Discovery

### List all dialogs

```python
from bsutils.telegram.util import TelegramDialogType

dialogs = await client.get_user_dialogs([TelegramDialogType.CHANNEL])
for d in dialogs:
    print(d["name"], d["username"], d["type"])
# {'id': 123, 'name': 'My Channel', 'username': 'mychannel', 'type': 'channel'}
```

`entity_types` accepts any combination of:

| Value | Matches |
|---|---|
| `TelegramDialogType.CHANNEL` | channels, supergroups, gigagroups |
| `TelegramDialogType.USER` | users and bots |
| `TelegramDialogType.CHAT` | basic groups |

### Resolve a username by name

```python
username = await client.get_dialog_username_by_name("My Private Channel")
# Returns 'myprivatechannel' (without '@'), or None if no public username
```

### Retrieve the last N messages

```python
messages = await client.get_messages_from_dialog("@my_channel", n=10)
for msg in messages:
  print(msg.id, msg.message)
```

The `chat` parameter accepts:
- `"@username"` or `"username"` — resolved directly.
- A full channel name (e.g. `"My Private Channel"`) — resolved via `get_dialog_username_by_name()`.

---

## Managing Channels at Runtime

```python
# Add a channel
added = client.add_channel_to_listen("@sports_news")  # True if newly added

# Remove a channel
removed = client.remove_channel_to_listen("@sports_news")  # True if found and removed

# Inspect current list
channels = client.get_listening_channels()  # returns a copy of the list
```

---

## API Reference

### `BSTelegramUserClient(api_id, api_hash, phone_number, session_file_path, logger, process_messages_endpoint)`

| Parameter | Type | Description |
|---|---|---|
| `api_id` | `int` | Telegram application API ID. |
| `api_hash` | `str` | Telegram application API hash. |
| `phone_number` | `str` | Phone number associated with the Telegram account (e.g. `"+34600000000"`). |
| `session_file_path` | `str` | Path to the Telethon session file (created automatically on first auth). |
| `logger` | `BSLogger` | Logger instance used for all internal messages. |
| `process_messages_endpoint` | `str` | Full HTTP(S) URL where incoming messages are `POST`ed. |

### Methods

| Method | Signature | Description |
|---|---|---|
| `connect_client` | `async () → None` | Connects the Telethon client. Must be called before any other async method. |
| `disconnect_client` | `async () → None` | Gracefully disconnects the client. |
| `request_verification_code` | `async (force_sms=False) → None` | Sends the verification code to the Telegram app (or SMS if `force_sms=True`). |
| `resend_verification_code_via_sms` | `async () → None` | Resends the code via SMS. Requires a prior call to `request_verification_code`. |
| `verify_code` | `async (code: str) → None` | Completes the sign-in with the received code. |
| `is_authenticated` | `async () → bool` | Returns `True` if the user is currently authorised. |
| `add_channel_to_listen` | `(channel_username: str) → bool` | Adds a channel to the listener list. Returns `True` if newly added. |
| `remove_channel_to_listen` | `(channel_username: str) → bool` | Removes a channel from the listener list. Returns `True` if found. |
| `get_listening_channels` | `() → list[str]` | Returns a copy of the current listener list. |
| `start_listening_channels` | `async () → None` | Registers listeners and blocks until disconnected. Requires prior auth. |
| `interactive_start_listening_channels` | `async () → None` | Full interactive flow (prompts for verification code via `input()`). |
| `get_user_dialogs` | `async (entity_types) → list[dict]` | Returns filtered dialogs for the authenticated user. |
| `get_dialog_username_by_name` | `async (channel_name, entity_types=None) → str \| None` | Resolves a dialog's `@username` by its display name. |
| `get_last_n_messages` | `async (chat, n) → list` | Returns the last `n` messages from a channel or chat. |

---

## Error Handling

| Exception | When |
|---|---|
| `ValueError` | Invalid or missing parameters (empty strings, non-positive integers, invalid URL, etc.). |
| `RuntimeError` | Client not initialised, not connected, or not authenticated. |
| `LookupError` | Dialog not found by name in `get_dialog_username_by_name`. |
| `requests.exceptions.Timeout` | HTTP endpoint did not respond within 30 seconds. |
| `requests.exceptions.ConnectionError` | HTTP endpoint is unreachable. |
| `requests.exceptions.RequestException` | Any other HTTP error when forwarding a message. |

---

## Notes

- **Non-blocking HTTP:** the `POST` to `process_messages_endpoint` is executed via `asyncio.to_thread`, so it never blocks the Telethon event loop.
- **Session reuse:** Telethon stores auth state in the session file. Delete it to force re-authentication.
- **Multiple channels:** you can call `add_channel_to_listen` multiple times before starting the listener loop.
- **`from_telegram_chat_id`:** currently set to `""` — future versions may populate it automatically from the event source.

---

## License

MIT — see [LICENSE](LICENSE) for details.

