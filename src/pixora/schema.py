from pydantic import BaseModel

class PostCreate(BaseModel):
    title: str
    content: str
    # published: bool = True

class PostResponse(BaseModel):
    title: str
    content: str
    # published: bool