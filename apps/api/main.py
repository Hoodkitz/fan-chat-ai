"""Fan Chat AI API."""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from apps.api.routers.persona import router as persona_router
from apps.api.routers.chat import router as chat_router

app = FastAPI(title="Fan Chat AI SaaS", version="1.0.0")

app.include_router(persona_router)

app.include_router(chat_router)

app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_credentials=True, allow_methods=["*"], allow_headers=["*"])

@app.get("/")
def root():
    return {"service": "Fan Chat AI SaaS", "version": "1.0.0"}

@app.get("/healthz")
def health():
    return {"status": "ok"}
