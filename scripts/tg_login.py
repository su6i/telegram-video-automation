"""
One-off interactive login that creates the Pyrogram user session
(`hybrid_account.session`) used by scripts/process_and_upload.py.

Run it once, answer the phone-number / login-code prompts, and every later
upload run reuses the session file without asking again.
"""
import asyncio
import os
import sys

from dotenv import load_dotenv
from src.env_resolver import env_path
from pyrogram import Client

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
load_dotenv(env_path())

api_id = os.getenv("API_ID")
api_hash = os.getenv("API_HASH")

if not api_id or not api_hash:
    sys.exit("❌ API_ID / API_HASH missing from .env")


async def main():
    app = Client("hybrid_account", api_id=int(api_id), api_hash=api_hash, workdir=ROOT)
    print("🚨 Enter your PHONE NUMBER (e.g. +49...), NOT a bot token.\n")
    async with app:
        me = await app.get_me()
        if me.is_bot:
            sys.exit("❌ That is a bot account. Delete the session and log in with your phone.")
        print(f"\n✅ Logged in as: {me.first_name} (@{me.username or 'no-username'}, id={me.id})")
        print(f"💾 Session saved: {os.path.join(ROOT, 'hybrid_account.session')}")


if __name__ == "__main__":
    asyncio.run(main())
