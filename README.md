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