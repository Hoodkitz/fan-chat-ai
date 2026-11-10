"""Fan Chat AI API entry point."""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from apps.core.config import settings
from apps.api.routers import persona, chats, fans, stats

app = FastAPI(title="Fan Chat AI SaaS", version="1.0.0", docs_url="/docs")

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS.split(","),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(persona.router)
app.include_router(chats.router)
app.include_router(fans.router)
app.include_router(stats.router)

@app.get("/")
def root():
    return {"service": "Fan Chat AI SaaS", "version": "1.0.0"}

@app.get("/healthz")
def health():
    return {"status": "ok", "version": "1.0.0"}
