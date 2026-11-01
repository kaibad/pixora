from fastapi import FastAPI

app = FastAPI(title="Pixora")


@app.get("/")
def root():
    return {"message": "Hello from Pixora!"}


@app.get("/health")
def health():
    return {"status": "ok"}