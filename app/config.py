import os
from dataclasses import dataclass
from typing import Optional


@dataclass
class Config:
    bot_token: str
    source_channel: Optional[str]
    destination_channel: Optional[str]
    db_path: str
    admin_ids: list

    @classmethod
    def from_env(cls) -> "Config":
        token = os.getenv("BOT_TOKEN", "").strip()
        if not token:
            raise ValueError("❌ متغير BOT_TOKEN مفقود! احصل عليه من @BotFather")

        source = os.getenv("SOURCE_CHANNEL", "").strip() or None
        dest = os.getenv("DESTINATION_CHANNEL", "").strip() or None
        db_path = os.getenv("DB_PATH", "/data/cloner.db")
        admin_ids_str = os.getenv("ADMIN_IDS", "")
        admin_ids = [int(x.strip()) for x in admin_ids_str.split(",") if x.strip().lstrip("-").isdigit()]

        return cls(
            bot_token=token,
            source_channel=source,
            destination_channel=dest,
            db_path=db_path,
            admin_ids=admin_ids,
        )
