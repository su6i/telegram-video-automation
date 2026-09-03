"""
One-off interactive login that creates the Pyrogram user session
(`hybrid_account.session`) used by scripts/process_and_upload.py.

Run it once, answer the phone-number / login-code prompts, and every later
upload run reuses the session file without asking again.
"""
import argparse
import asyncio
import os
import sys

from dotenv import load_dotenv
from pyrogram import Client

# The repo root has to be on sys.path before anything under src/ is imported —
# running this file as a script puts scripts/ on sys.path, not the root.
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from src.env_resolver import env_path

load_dotenv(env_path())

api_id = os.getenv("API_ID")
api_hash = os.getenv("API_HASH")

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
    parser = argparse.ArgumentParser(description="Interactive Telegram login to save session.")
    parser.parse_args()
    
    if not api_id or not api_hash:
        sys.exit("❌ API_ID / API_HASH missing from .env")
        
    asyncio.run(main())
