"""Fan Chat AI API."""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI(title="Fan Chat AI SaaS", version="1.0.0")

app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_credentials=True, allow_methods=["*"], allow_headers=["*"])

@app.get("/")
def root():
    return {"service": "Fan Chat AI SaaS", "version": "1.0.0"}

@app.get("/healthz")
def health():
    return {"status": "ok"}
