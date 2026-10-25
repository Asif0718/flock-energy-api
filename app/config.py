import os
from dataclasses import dataclass, field
from urllib.parse import urlsplit

from dotenv import load_dotenv


@dataclass(frozen=True)
class Settings:
    base_url: str = "https://urja-ops.flockenergy.tech"
    email: str = ""
    password: str = field(default="", repr=False)
    timeout: float = 15.0

    def __post_init__(self):
        url = urlsplit(self.base_url)
        if url.scheme not in ("http", "https") or not url.netloc or url.username or url.password or url.query or url.fragment or url.path not in ("", "/"):
            raise ValueError("URJA_BASE_URL must be an HTTP(S) origin without credentials")
        if not 0 < self.timeout <= 120:
            raise ValueError("URJA_TIMEOUT must be between 0 and 120 seconds")

    @classmethod
    def from_env(cls):
        load_dotenv()
        return cls(
            base_url=os.getenv("URJA_BASE_URL", cls.base_url).rstrip("/"),
            email=os.getenv("URJA_EMAIL", ""),
            password=os.getenv("URJA_PASSWORD", ""),
            timeout=float(os.getenv("URJA_TIMEOUT", "15")),
        )
