"""Entry point for the Trading Terminal."""

import uvicorn

from core.app import create_app

app = create_app()

if __name__ == "__main__":
    uvicorn.run("run:app", host="127.0.0.1", port=8000, reload=True)
