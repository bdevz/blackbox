from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    database_url: str = "postgresql://blackbox:blackbox@localhost:5432/blackbox"
    redis_url: str = "redis://localhost:6379/0"
    anthropic_api_key: str = ""
    coda_api_token: str = ""
    coda_doc_id: str = "dSt8mkiTmO7"
    hubspot_api_key: str = ""
    hubspot_portal_id: str = "243046792"
    slack_bot_token: str = ""
    slack_interview_channel: str = "C088YP1M732"
    slack_general_channel: str = "C07AYH29X4L"
    highergov_api_key: str = ""
    s3_bucket: str = ""
    s3_access_key: str = ""
    s3_secret_key: str = ""
    s3_endpoint: str = ""

    model_config = {"env_file": ".env", "extra": "ignore"}


settings = Settings()
