from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from app.routes import issues

BASE_DIR = Path(__file__).resolve().parent

templates = Jinja2Templates(directory=BASE_DIR / "templates")


def create_app() -> FastAPI:
    app = FastAPI(title="Klaidų klasifikavimo ir prioritizavimo sistema")
    app.mount("/static", StaticFiles(directory=BASE_DIR / "static"), name="static")

    app.include_router(issues.router)

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/", response_class=HTMLResponse)
    def index(request: Request) -> HTMLResponse:
        return templates.TemplateResponse(request, "index.html")

    return app


app = create_app()
