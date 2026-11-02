from pydantic import BaseModel
import uuid
from fastapi_users import schemas

class PostCreate(BaseModel):
    title: str
    content: str
    # published: bool = True

class PostResponse(BaseModel):
    title: str
    content: str
    # published: bool


class UserRead(schemas.BaseUser[uuid.UUID]):
    pass


class UserCreate(schemas.BaseUserCreate):
    pass


class UserUpdate(schemas.BaseUserUpdate):
    pass