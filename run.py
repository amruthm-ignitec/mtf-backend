"""Run the API server. Port and host come from .env (PORT, HOST) or defaults 8000, 0.0.0.0."""
import uvicorn

from app.config import get_settings

if __name__ == "__main__":
    s = get_settings()
    uvicorn.run("app.main:app", host=s.host, port=s.port, reload=True)
