from datetime import datetime


def log(message: str) -> None:
    print(f"[{datetime.utcnow().isoformat()}] {message}")


def error(message: str) -> None:
    print(f"[ERROR {datetime.utcnow().isoformat()}] {message}")
