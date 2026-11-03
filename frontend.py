import base64
import os
import urllib.parse

import requests
import streamlit as st

API_URL = os.getenv("API_URL", "http://localhost:8000")

# keep these in sync with the limits in app.py
MAX_IMAGE_MB = 10
MAX_VIDEO_MB = 100
IMAGE_TYPES = ["png", "jpg", "jpeg", "webp"]
VIDEO_TYPES = ["mp4", "mov", "webm"]

st.set_page_config(page_title="Pixora", page_icon="📸", layout="wide")

# ---------- session state ----------
st.session_state.setdefault("token", None)
st.session_state.setdefault("user", None)
st.session_state.setdefault("flash", None)         # (level, message) shown once
st.session_state.setdefault("uploader_key", 0)     # bump to reset the upload form


# ---------- helpers ----------
def get_headers():
    if st.session_state.token:
        return {"Authorization": f"Bearer {st.session_state.token}"}
    return {}


def logout():
    st.session_state.token = None
    st.session_state.user = None


def set_flash(level, message):
    st.session_state.flash = (level, message)


def show_flash():
    if st.session_state.flash:
        level, message = st.session_state.flash
        getattr(st, level)(message)
        st.session_state.flash = None


def api(method, path, **kwargs):
    """Call the backend. Returns a Response, or None if the server is unreachable."""
    kwargs.setdefault("timeout", 30)
    try:
        response = requests.request(
            method, f"{API_URL}{path}", headers=get_headers(), **kwargs
        )
    except requests.RequestException:
        st.error("Can't reach the server. Is the backend running?")
        return None

    # token expired or invalid -> back to the login screen
    if response.status_code == 401 and st.session_state.token:
        logout()
        set_flash("warning", "Session expired. Please log in again.")
        st.rerun()
    return response


def error_detail(response, default):
    """Turn FastAPI / fastapi-users error bodies into a readable string."""
    try:
        detail = response.json().get("detail", default)
    except ValueError:
        return default
    if isinstance(detail, list):                      # 422 validation errors
        return "; ".join(str(d.get("msg", d)) for d in detail)
    if isinstance(detail, dict):                      # e.g. REGISTER_INVALID_PASSWORD
        return detail.get("reason") or detail.get("code") or default
    return str(detail)


# ---------- auth ----------
def do_login(email, password):
    response = api("POST", "/auth/jwt/login", data={"username": email, "password": password})
    if response is None:
        return
    if response.status_code != 200:
        st.error("Invalid email or password!")
        return

    st.session_state.token = response.json()["access_token"]
    me = api("GET", "/users/me")
    if me is not None and me.status_code == 200:
        st.session_state.user = me.json()
        st.rerun()
    else:
        logout()
        st.error("Failed to load your profile")


def login_page():
    st.title("🚀 Welcome to Pixora")
    show_flash()

    # a form lets the user press Enter to submit
    with st.form("auth_form"):
        email = st.text_input("Email")
        password = st.text_input("Password", type="password")
        col1, col2 = st.columns(2)
        login_clicked = col1.form_submit_button("Login", type="primary")
        signup_clicked = col2.form_submit_button("Sign Up")

    if (login_clicked or signup_clicked) and not (email and password):
        st.info("Enter your email and password above")
        return

    if login_clicked:
        do_login(email, password)

    if signup_clicked:
        response = api("POST", "/auth/register", json={"email": email, "password": password})
        if response is None:
            return
        if response.status_code == 201:
            do_login(email, password)             # log the new user straight in
        else:
            st.error(f"Registration failed: {error_detail(response, 'Registration failed')}")


# ---------- upload ----------
def upload_page():
    st.title("📸 Share Something")
    show_flash()

    n = st.session_state.uploader_key
    uploaded_file = st.file_uploader(
        "Choose media", type=IMAGE_TYPES + VIDEO_TYPES, key=f"uploader_{n}"
    )
    caption = st.text_area("Caption:", placeholder="What's on your mind?", key=f"caption_{n}")

    if not uploaded_file:
        return

    is_video = (uploaded_file.type or "").startswith("video/")
    limit_mb = MAX_VIDEO_MB if is_video else MAX_IMAGE_MB
    size_mb = uploaded_file.size / (1024 * 1024)

    if size_mb > limit_mb:
        st.error(f"File is {size_mb:.1f} MB. The limit for {'videos' if is_video else 'images'} is {limit_mb} MB.")
        return

    preview, _ = st.columns([1, 2])
    with preview:
        if is_video:
            st.video(uploaded_file)
        else:
            st.image(uploaded_file)

    if st.button("Share", type="primary"):
        with st.spinner("Uploading..."):
            response = api(
                "POST",
                "/upload",
                files={"file": (uploaded_file.name, uploaded_file.getvalue(), uploaded_file.type)},
                data={"caption": caption},
                timeout=300,                       # videos can take a while
            )

        if response is None:
            return
        if response.status_code == 200:
            set_flash("success", "Posted!")
            st.session_state.uploader_key += 1     # clears the uploader and caption
            st.rerun()
        else:
            st.error(f"Upload failed: {error_detail(response, 'Unknown error')}")


# ---------- feed ----------
def encode_text_for_overlay(text):
    """ImageKit wants overlay text base64-encoded, then URL-encoded."""
    b64 = base64.b64encode(text.encode("utf-8")).decode("utf-8")
    return urllib.parse.quote(b64, safe="")        # safe="" also encodes "/" in base64


def create_transformed_url(original_url, transformation="", caption=None):
    """Insert an ImageKit tr: segment, optionally with a caption text overlay."""
    parts = original_url.split("/")
    if len(parts) < 5:                             # not the expected ImageKit URL shape
        return original_url

    base_url = "/".join(parts[:4])                 # https://ik.imagekit.io/<your_id>
    file_path = "/".join(parts[4:])

    if caption:
        overlay = (
            f"l-text,ie-{encode_text_for_overlay(caption[:150])},"
            "w-560,lx-20,ly-N20,fs-24,co-white,bg-000000A0,pa-10,l-end"
        )
        # chain with ":" so the image is resized first, then the overlay is drawn
        transformation = f"{transformation}:{overlay}" if transformation else overlay

    if not transformation:
        return original_url
    return f"{base_url}/tr:{transformation}/{file_path}"


def feed_page():
    st.title("🏠 Feed")
    show_flash()

    response = api("GET", "/feed")
    if response is None:
        return
    if response.status_code != 200:
        st.error("Failed to load feed")
        return

    posts = response.json()["posts"]
    if not posts:
        st.info("No posts yet! Be the first to share something.")
        return

    for post in posts:
        st.markdown("---")

        # header: who posted, when, and a delete button for the owner
        col1, col2 = st.columns([4, 1])
        with col1:
            st.markdown(f"**{post['email']}** • {post['created_at'][:10]}")
        with col2:
            if post.get("is_owner", False):
                if st.button("🗑️", key=f"delete_{post['id']}", help="Delete post"):
                    result = api("DELETE", f"/posts/{post['id']}")
                    if result is not None and result.status_code == 200:
                        set_flash("success", "Post deleted!")
                        st.rerun()
                    elif result is not None:
                        st.error(f"Failed to delete post: {error_detail(result, 'Unknown error')}")

        caption = post.get("caption") or ""
        media, _ = st.columns([2, 1])
        with media:
            if post["file_type"] == "image":
                st.image(create_transformed_url(post["url"], "w-600", caption))
            else:
                st.video(create_transformed_url(post["url"], "w-640,h-360,cm-pad_resize,bg-blurred"))
                if caption:
                    st.caption(caption)


# ---------- main ----------
if st.session_state.user is None:
    login_page()
else:
    st.sidebar.title(f"👋 Hi {st.session_state.user['email']}!")

    if st.sidebar.button("Logout"):
        logout()
        st.rerun()

    st.sidebar.markdown("---")
    page = st.sidebar.radio("Navigate:", ["🏠 Feed", "📸 Upload"])

    if page == "🏠 Feed":
        feed_page()
    else:
        upload_page()