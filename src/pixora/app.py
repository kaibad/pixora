from fastapi import FastAPI, HTTPException, File, UploadFile, Form, Depends
from fastapi.concurrency import run_in_threadpool
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from contextlib import asynccontextmanager

from pixora.db import Post, create_db_and_tables, get_async_session
from pixora.images import imagekit
import uuid

MAX_IMAGE_SIZE = 10 * 1024 * 1024 # 10 MB
MAX_VIDEO_SIZE = 100 * 1024 * 1024 # 100 MB


@asynccontextmanager
async def lifespan(app: FastAPI):
    await create_db_and_tables()
    yield

app = FastAPI(title="Pixora", lifespan=lifespan)


@app.get("/")
def root():
    return {"message": "Hello from Pixora!"}


@app.get("/health")
def health():
    return {"status": "ok"}


# Upload file endpoint
@app.post("/upload")
async def upload_file(
    file: UploadFile = File(...),
    caption: str = Form(...),
    session: AsyncSession = Depends(get_async_session),
):
    content_type = file.content_type or ""
    if content_type.startswith("image/"):
        file_type, max_size = "image", MAX_IMAGE_SIZE
    elif content_type.startswith("video/"):
        file_type, max_size = "video", MAX_VIDEO_SIZE
    else:
        raise HTTPException(status_code=400, detail="Only image or video files are allowed")

    if file.size is not None and file.size > max_size:
        raise HTTPException(status_code=413, detail=f"{file_type} is too large")

    try:
        #run_in_threadpool runs a normal (blocking) function in a separate thread, so it doesn’t freeze your async server while it waits.
        # BAD: blocks the entire server during the upload
        # result = imagekit.files.upload(file=file.file, file_name=file.filename)
        # GOOD: upload runs in a worker thread, the event loop stays free
        # The syntax is run_in_threadpool(function, *args, **kwargs). Note that you pass the function without parentheses, and the arguments follow it. FastAPI then calls imagekit.files.upload(file=..., file_name=...) in a thread and gives you the result when it’s done, and the await lets other requests run in the meantime.
        result = await run_in_threadpool(
            imagekit.files.upload,
            file=file.file,                     
            file_name=file.filename,
            folder=f"/pixora/{file_type}s",
            tags=["pixora-backend-upload"],
        )
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"ImageKit upload failed: {e}")
    finally:
        await file.close()

    post = Post(
        caption=caption,
        url=result.url,
        file_type=file_type,
        file_name=result.name,
    )
    session.add(post)
    await session.commit()
    await session.refresh(post)

    return {
        "id": str(post.id),
        "caption": post.caption,
        "url": post.url,
        "file_type": post.file_type,
        "file_name": post.file_name,
        "created_at": post.created_at.isoformat(),
    }


# Get feed endpoint
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

# delete post endpoint
@app.delete("/posts/{post_id}")
async def delete_post(
    post_id: str,
    session: AsyncSession = Depends(get_async_session)
):
    try:
        post_uuid = uuid.UUID(post_id)

        result = await session.execute(select(Post).where(Post.id == post_uuid)) 
        post = result.scalars().first()
        if not post:
            raise HTTPException(status_code=404, detail="Post not found")

        await session.delete(post)
        await session.commit()

        return {"success": True, "message": "Post deleted successfully"}

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))