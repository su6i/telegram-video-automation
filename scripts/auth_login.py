import os
import pathlib
import sys

from dotenv import load_dotenv
from pyrogram import Client

# The repo root has to be on sys.path before anything under src/ is imported —
# running this file as a script puts scripts/ on sys.path, not the root.
REPO = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from src.env_resolver import env_path

# Load from root .env
load_dotenv(env_path())

api_id = os.getenv("API_ID")
api_hash = os.getenv("API_HASH")

if not api_id or not api_hash:
    print("❌ Error: API_ID or API_HASH found in .env file.")
    exit(1)

print("🔐 Starting Pyrogram Login...")
print("Please enter your phone number when prompted (e.g., +98912...)")
print("Then enter the code you receive on Telegram.")

app = Client("hybrid_account", api_id=api_id, api_hash=api_hash)

print("🚀 Attempting to connect...")
app.start()

me = app.get_me()
print("✅ Login Successful!")
print(f"👤 User: {me.first_name} {me.last_name or ''} (@{me.username})")
print(f"📱 Phone: {me.phone_number}")

app.stop()
print("👋 Session saved. You can now use the scraper tools.")
