"""One-time interactive login to generate a Telegram session string.

Run this yourself, locally, in your own terminal -- it will ask for your
phone number, the login code Telegram sends you, and (if you have 2FA
enabled) your account password. None of that is sent anywhere except
Telegram's own servers; this script only talks to the Telegram API.

Usage:
    cd checker
    python3 generate_session.py

You'll need a free api_id/api_hash first, from https://my.telegram.org
(Log in -> API development tools -> create an app, any name/platform is fine).

The script prints a session string at the end. Treat it like a password --
it is a full login token for your Telegram account. Save it ONLY as the
GitHub Actions secret TELEGRAM_SESSION_STRING. Never commit it, never paste
it anywhere else, and never share it with anyone (including in chat with an
AI assistant) -- anyone who has it can read your Telegram account.
"""
from telethon.sync import TelegramClient
from telethon.sessions import StringSession


def main():
    api_id = int(input("api_id (from my.telegram.org): ").strip())
    api_hash = input("api_hash (from my.telegram.org): ").strip()

    with TelegramClient(StringSession(), api_id, api_hash) as client:
        client.start()
        session_string = client.session.save()

    print("\n" + "=" * 60)
    print("Session created. Save this as the GitHub Actions secret")
    print("TELEGRAM_SESSION_STRING -- do not paste it anywhere else:")
    print("=" * 60)
    print(session_string)
    print("=" * 60)


if __name__ == "__main__":
    main()
