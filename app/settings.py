from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    database_url: str = "sqlite:///./audit_hq.sqlite"
    auth_user: str = "admin"
    auth_password: str = "admin"
    session_secret: str = "dev-secret-change-me"
    raw_data_path: Path = Path("./data")
    # Kho đệm trích xuất xem trước — PHẢI nằm ngoài `raw_data_path` (thư mục đó là
    # liên kết tới dữ liệu khách) và trong nhánh đã gitignore.
    preview_cache_path: Path = Path("./db-data/preview-cache")
    preview_cache_max_bytes: int = 2 * 1024 * 1024 * 1024
    # Thời gian tối đa một request xem trước ĐƯỢC PHÉP chờ lượt trích xuất. Mọi
    # file trong kho trừ một file đều trích xuất dưới 10 giây, nên 12 giây đủ để
    # chúng xong trong đúng một request; file 71,3 MB mất 164,6 giây thì hết hạn
    # chờ và trả về trạng thái đang trích xuất để lưới hỏi lại (biên Cloudflare
    # là 100 giây).
    preview_wait_seconds: float = 12.0


settings = Settings()
