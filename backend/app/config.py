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
    highergov_relevance_threshold: int = 60
    highergov_auto_qualify_threshold: int = 80
    s3_bucket: str = ""
    s3_access_key: str = ""
    s3_secret_key: str = ""
    s3_endpoint: str = ""
    voyage_api_key: str = ""
    voyage_model: str = "voyage-3-large"
    # OpenAI embeddings (text-embedding-3-small, 1536-dim)
    openai_api_key: str = ""
    openai_embedding_model: str = "text-embedding-3-small"
    # Pinecone vector store
    pinecone_api_key: str = ""
    pinecone_index_name: str = "rfp-blackbox"
    pinecone_cloud: str = "aws"
    pinecone_region: str = "us-east-1"
    max_concurrent_api_calls: int = 4
    claude_model: str = "claude-sonnet-4-6"

    model_config = {"env_file": ".env", "extra": "ignore"}


settings = Settings()
