from collections.abc import AsyncGenerator
import uuid

from sqlalchemy import Column, String, Text, DateTime, ForeignKey
from fastapi_users_db_sqlalchemy.generics import GUID
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker

from sqlalchemy.orm import DeclarativeBase, declarative_base, relationship 
from datetime import datetime
from fastapi_users_db_sqlalchemy import SQLAlchemyUserDatabase, SQLAlchemyBaseUserTableUUID
from fastapi_users_db_sqlalchemy.generics import GUID
from fastapi import Depends



DATABASE_URL = "sqlite+aiosqlite:///./test.db"

# create a declarative base class for the models
class Base(DeclarativeBase):
    pass

class User(SQLAlchemyBaseUserTableUUID,Base):
    posts = relationship(argument="Post",back_populates="user")


# ths is the db model for the posts table
class Post(Base):
    __tablename__ = "posts"

    id = Column(GUID, primary_key=True, default=uuid.uuid4)
    user_id = Column(GUID, ForeignKey("user.id"), nullable=False)
    caption = Column(Text)
    url = Column(String(255), nullable=False)
    file_type = Column(String(50), nullable=False)
    file_name = Column(String(255), nullable=False)
    file_id = Column(String(100), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    user = relationship(argument="User", back_populates="posts")

# ceate the async engine and sessionmaker
# async engine is used to connect to the database asynchronously
# sessionmaker is used to create a new session for each request
engine = create_async_engine(DATABASE_URL, echo=True)
async_session = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)


# create the database and tables
async def create_db_and_tables():
    async with engine.begin() as conn:
        # this is going to find all the models that are defined in the declarative base and create the tables in the database
        await conn.run_sync(Base.metadata.create_all)

# create a dependency that will provide a session for each request
async def get_async_session() -> AsyncGenerator[AsyncSession, None]:
    async with async_session() as session:
        yield session

# user model
async def get_user_db(session: AsyncSession = Depends(get_async_session)):
    yield SQLAlchemyUserDatabase(session, User)