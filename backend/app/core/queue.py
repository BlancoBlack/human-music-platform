import redis
from rq import Queue

redis_conn = redis.Redis(host="localhost", port=6379)
queue = Queue("default", connection=redis_conn)


def get_queue() -> Queue:
    return queue

