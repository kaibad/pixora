from fastapi import FastAPI,HTTPException, File, UploadFile, Form, Depends
from pixora.schema import PostCreate, PostResponse, PostResponse
from pixora.db import  Post, create_db_and_tables, get_async_session
from sqlalchemy.ext.asyncio import AsyncSession
from contextlib import asynccontextmanager
from sqlalchemy import select

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Create the database and tables on startup
    await create_db_and_tables()
    yield
    # Perform any cleanup tasks on shutdown if needed

app = FastAPI(title="Pixora", lifespan=lifespan)


@app.get("/")
def root():
    return {"message": "Hello from Pixora!"}


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/upload")
async def upload_file(
    file: UploadFile = File(...),
    caption: str = Form(...),
    # this is a dependency that will provide a session for each request. dependency injection is a way to provide dependencies to a function or class without having to create them manually. in this case, we are using the get_async_session function to provide a session for each request. the session will be used to interact with the database.
    session: AsyncSession = Depends(get_async_session)
):
    post = Post(
        caption=caption,
        url="dummy url",
        file_type="image",
        file_name="dummy name"
    )
    session.add(post)
    await session.commit()
    await session.refresh(post)
    return {post}



@app.get("/feed")
async def get_feed(
    session: AsyncSession = Depends(get_async_session)
):
    result = await session.execute(select(Post).order_by(Post.created_at.desc()))
    posts = [row[0] for row in result.fetchall()]

    posts_data = []
    for post in posts:
        posts_data.append(
            {
                "id": str(post.id),
                "caption": post.caption,
                "url": post.url,
                "file_type": post.file_type,
                "file_name": post.file_name,
                "created_at": post.created_at.isoformat(),
            }
        )

    return {"posts": posts_data}