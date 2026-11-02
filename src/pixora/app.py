from fastapi import FastAPI, HTTPException, File, UploadFile, Form, Depends
from fastapi.concurrency import run_in_threadpool
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from contextlib import asynccontextmanager

from pixora.db import Post, create_db_and_tables, get_async_session
from pixora.images import imagekit
import uuid

from pixora.users import fastapi_users, auth_backend, current_active_user
from pixora.schema import UserRead, UserCreate, UserUpdate
from pixora.db import User

from sqlalchemy.orm import selectinload

MAX_IMAGE_SIZE = 10 * 1024 * 1024 # 10 MB
MAX_VIDEO_SIZE = 100 * 1024 * 1024 # 100 MB


@asynccontextmanager
async def lifespan(app: FastAPI):
    await create_db_and_tables()
    yield

app = FastAPI(title="Pixora", lifespan=lifespan)

app.include_router(
    fastapi_users.get_auth_router(auth_backend), prefix="/auth/jwt", tags=["auth"]
)
app.include_router(
    fastapi_users.get_register_router(UserRead, UserCreate), prefix="/auth", tags=["auth"]
)
app.include_router(
    fastapi_users.get_reset_password_router(), prefix="/auth", tags=["auth"]
)
app.include_router(
    fastapi_users.get_verify_router(UserRead), prefix="/auth", tags=["auth"]
)
app.include_router(
    fastapi_users.get_users_router(UserRead, UserUpdate), prefix="/users", tags=["users"]
)


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
    user: User = Depends(current_active_user),
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
        user_id=user.id,  
        caption=caption,
        url=result.url,
        file_type=file_type,
        file_name=result.name,
        file_id=result.file_id,  
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
    user: User = Depends(current_active_user),
    session: AsyncSession = Depends(get_async_session),
):
    result = await session.execute(
        select(Post).options(selectinload(Post.user)).order_by(Post.created_at.desc())
    )
    posts = result.scalars().all()

    return {
        "posts": [
            {
                "id": str(p.id),
                "user_id": str(p.user_id),
                "caption": p.caption,
                "url": p.url,
                "file_type": p.file_type,
                "file_name": p.file_name,
                "created_at": p.created_at.isoformat(),
                "email": p.user.email,
                "is_owner": p.user_id == user.id,
                "email": p.user.email
            }
            for p in posts
        ]
    }

# delete post endpoint
@app.delete("/posts/{post_id}")
async def delete_post(
    post_id: uuid.UUID,
    user: User = Depends(current_active_user),
    session: AsyncSession = Depends(get_async_session),
):
    post = await session.get(Post, post_id)
    if post is None:
        raise HTTPException(status_code=404, detail="Post not found")
    if post.user_id != user.id:
        raise HTTPException(status_code=403, detail="Not your post")

    # delete from ImageKit first; if it fails, the DB row stays so you can retry
    if post.file_id:
        try:
            await run_in_threadpool(imagekit.files.delete, post.file_id)
        except Exception as e:
            raise HTTPException(status_code=502, detail=f"ImageKit delete failed: {e}")

    await session.delete(post)
    await session.commit()

    return {"success": True, "message": "Post deleted successfully"}