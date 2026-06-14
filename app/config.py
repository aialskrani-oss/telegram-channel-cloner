import os
from dataclasses import dataclass
from typing import Optional


@dataclass
class Config:
    api_id: int
    api_hash: str
    session_string: Optional[str]
    source_channel: str
    destination_channel: str
    db_path: str
    batch_size: int
    delay_between_messages: float
    delay_between_batches: float
    max_retries: int
    retry_delay: float

    @classmethod
    def from_env(cls) -> "Config":
        api_id_str = os.getenv("API_ID", "")
        api_hash = os.getenv("API_HASH", "")
        session_string = os.getenv("SESSION_STRING", None)
        source_channel = os.getenv("SOURCE_CHANNEL", "")
        destination_channel = os.getenv("DESTINATION_CHANNEL", "")
        db_path = os.getenv("DB_PATH", "/data/cloner.db")
        batch_size = int(os.getenv("BATCH_SIZE", "50"))
        delay_between_messages = float(os.getenv("DELAY_BETWEEN_MESSAGES", "0.5"))
        delay_between_batches = float(os.getenv("DELAY_BETWEEN_BATCHES", "2.0"))
        max_retries = int(os.getenv("MAX_RETRIES", "5"))
        retry_delay = float(os.getenv("RETRY_DELAY", "10.0"))

        missing = []
        if not api_id_str:
            missing.append("API_ID")
        if not api_hash:
            missing.append("API_HASH")
        if not source_channel:
            missing.append("SOURCE_CHANNEL")
        if not destination_channel:
            missing.append("DESTINATION_CHANNEL")

        if missing:
            raise ValueError(
                f"المتغيرات البيئية المطلوبة غير موجودة: {', '.join(missing)}\n"
                "يرجى تعيينها في ملف .env أو في متغيرات البيئة."
            )

        try:
            api_id = int(api_id_str)
        except ValueError:
            raise ValueError(f"API_ID يجب أن يكون رقماً صحيحاً، القيمة الحالية: {api_id_str!r}")

        return cls(
            api_id=api_id,
            api_hash=api_hash,
            session_string=session_string if session_string else None,
            source_channel=source_channel,
            destination_channel=destination_channel,
            db_path=db_path,
            batch_size=batch_size,
            delay_between_messages=delay_between_messages,
            delay_between_batches=delay_between_batches,
            max_retries=max_retries,
            retry_delay=retry_delay,
        )
