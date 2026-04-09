from pydantic import BaseModel

class StreamEvent(BaseModel):
    user_id: int
    song_id: int
    duration: int