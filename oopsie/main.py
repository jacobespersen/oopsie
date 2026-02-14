"""FastAPI app entry point."""

from fastapi import FastAPI

from oopsie.config import Settings

settings = Settings()
app = FastAPI(title="Oopsie", description="AI-powered error fix service")


@app.get("/health")
def health():
    """Health check for the API."""
    return {"status": "ok"}
