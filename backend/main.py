from fastapi import FastAPI

from api.router import api_router

app = FastAPI(
    title="Koreader Reader API",
    version="0.1.0",
)

app.include_router(api_router)


@app.get("/health", tags=["system"])
def health_check() -> dict[str, str]:
    return {"status": "ok"}
