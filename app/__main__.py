"""Entry point so the app starts with `python -m app`, honouring HOST/PORT."""

import uvicorn

from .config import settings


def main() -> None:
    uvicorn.run(
        "app.main:app",
        host=settings.host,
        port=settings.port,
        reload=False,
        log_level="info",
    )


if __name__ == "__main__":
    main()
