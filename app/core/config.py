from typing import Dict, List
from pydantic_settings import BaseSettings
from pathlib import Path
from pydantic import Field, field_validator
import json


class Settings(BaseSettings):
    DATABASE_URL: str
    OPENAI_API_KEY: str
    REDIS_URL: str

    class Config:
        env_file = Path(__file__).parent.parent.parent / ".env"
        env_file_encoding = "utf-8"
        case_sensitive = True
        extra = "allow"


# Initialize settings
settings = Settings()
