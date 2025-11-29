# bstelegramuser

Telegram client to process channel messages and send them to HTTP endpoints.

## Description
This project provides a simple Telegram user client that listens to messages from specified channels and forwards them to configurable HTTP endpoints. It is designed for integration with other systems, such as bet tracking or notification services.

## Features
- Connects as a Telegram user (not a bot)
- Monitors messages in selected channels
- Sends message data to HTTP endpoints
- Easy to configure and extend

## Requirements
- Python 3.9+
- See `pyproject.toml` for dependencies

## Usage
1. Install dependencies:
   ```sh
   pip install .
   ```
2. Configure your channels and endpoints.
3. Run the client script to start processing messages.

## License
MIT License
