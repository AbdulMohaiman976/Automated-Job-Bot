from pathlib import Path
import os
from dotenv import load_dotenv

# Explicitly load .env from the project root
BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(dotenv_path=BASE_DIR / ".env", override=True)


def _clear_blackhole_proxy_env() -> None:
    """
    Some environments inject a dummy proxy such as 127.0.0.1:9, which breaks
    Apify/API traffic. Remove only that placeholder so direct connections work.
    """
    proxy_keys = (
        "HTTP_PROXY",
        "HTTPS_PROXY",
        "ALL_PROXY",
        "http_proxy",
        "https_proxy",
        "all_proxy",
        "GIT_HTTP_PROXY",
        "GIT_HTTPS_PROXY",
    )

    for key in proxy_keys:
        value = os.environ.get(key)
        if value and "127.0.0.1:9" in value:
            os.environ.pop(key, None)


_clear_blackhole_proxy_env()

CANDIDATE_EMAIL = os.getenv("CANDIDATE_EMAIL", "candidate@example.com")
APIFY_TOKEN = os.getenv("APIFY_TOKEN")
JOB_KEYWORDS = os.getenv("JOB_KEYWORDS", "Data Engineer")
JOB_LOCATION = os.getenv("JOB_LOCATION", "United States")
REMOTE_ONLY = True
MAX_AGE_DAYS = 1
OUTPUT_DIR = Path("./data")

APIFY_MAX_RETRIES = int(os.getenv("APIFY_MAX_RETRIES", 3))
APIFY_TIMEOUT_SECONDS = int(os.getenv("APIFY_TIMEOUT_SECONDS", 300))
APIFY_MAX_CONCURRENCY = int(os.getenv("APIFY_MAX_CONCURRENCY", 5))
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
GROQ_API_KEY = os.getenv("GROQ_API_KEY")

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/129.0.0.0 Safari/537.36"
)
