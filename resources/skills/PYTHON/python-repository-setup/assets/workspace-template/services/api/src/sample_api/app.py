from fastapi import FastAPI

from sample_shared import greeting

app = FastAPI(title="Sample API")


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/")
def root() -> dict[str, str]:
    return {"message": greeting()}
