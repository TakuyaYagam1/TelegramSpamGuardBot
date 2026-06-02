from dotenv import load_dotenv
import os

load_dotenv()

BOT_TOKEN: str = os.environ["BOT_TOKEN"]
ADMIN_ID: int = int(os.environ["ADMIN_ID"])
ACTION_MODE: str = os.getenv("ACTION_MODE", "notify_admin")
