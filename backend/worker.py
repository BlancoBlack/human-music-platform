from dotenv import load_dotenv
from rq import Queue, SpawnWorker

from app.core.queue import redis_conn

load_dotenv()

# Run from backend/: ./.venv/bin/python worker.py (same .venv as the API; do not use global Python).


def main() -> None:
    print("Worker starting...")

    default_queue = Queue("default", connection=redis_conn)
    print("Worker connected to Redis...")

    worker = SpawnWorker([default_queue], connection=redis_conn)
    worker.work()


if __name__ == "__main__":
    main()

