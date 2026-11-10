import os
from dataclasses import dataclass
from pathlib import Path


@dataclass
class Settings:
    email: str | None
    password: str | None
    auth_token: str | None
    country_code: str
    api_version: str
    token_file: Path | None


def load_dotenv(path: str | Path = ".env") -> None:
    env_path = Path(path)
    if not env_path.exists():
        return
    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        os.environ.setdefault(key, value)


def from_env() -> Settings:
    load_dotenv()
    token_file = os.environ.get("PICNIC_TOKEN_FILE", ".picnic_token")
    return Settings(
        email=os.environ.get("PICNIC_EMAIL"),
        password=os.environ.get("PICNIC_PASSWORD"),
        auth_token=os.environ.get("PICNIC_AUTH_TOKEN"),
        country_code=os.environ.get("PICNIC_COUNTRY_CODE", "NL"),
        api_version=os.environ.get("PICNIC_API_VERSION", "15"),
        token_file=Path(token_file) if token_file else None,
    )
