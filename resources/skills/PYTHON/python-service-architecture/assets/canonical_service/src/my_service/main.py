"""Executable entry point."""

import uvicorn

from my_service.bootstrap.app import create_app

if __name__ == "__main__":
    uvicorn.run(create_app())
