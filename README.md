## References

- https://imagekit.io/docs/integration/python#what-the-sdk-does
- https://imagekit.io/docs/transformations


```
Upload → ImageKit stores the file → returns url + file_id
              ↓
Database saves: caption, url, file_id, type, time
              ↓
/feed reads the DB → returns captions + urls
              ↓
Frontend shows the media straight from the ImageKit url

```

```bash

python -c "import secrets; print(secrets.token_hex(32))"

```

uv run python -c "import sqlite3; c = sqlite3.connect('test.db'); print(c.execute('select id, email, is_active, is_verified from user').fetchall())"