from pathlib import Path
from urllib.parse import quote

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from app import config
from app.auth import CsrfError, LoginRequired
from app.routes import annotations, auth, dashboard, issues, reports

BASE_DIR = Path(__file__).resolve().parent

templates = Jinja2Templates(directory=BASE_DIR / "templates")


def create_app() -> FastAPI:
    app = FastAPI(title="Klaidų klasifikavimo ir prioritizavimo sistema")
    app.mount("/static", StaticFiles(directory=BASE_DIR / "static"), name="static")

    app.include_router(issues.router)
    app.include_router(reports.router)
    app.include_router(auth.router)
    app.include_router(dashboard.router)
    app.include_router(annotations.router)

    @app.exception_handler(LoginRequired)
    def redirect_to_login(request: Request, exc: LoginRequired) -> RedirectResponse:
        # Po prisijungimo grąžinama į tą patį puslapį (tik GET užklausoms).
        target = "/dashboard"
        if request.method == "GET":
            target = request.url.path
            if request.url.query:
                target += "?" + request.url.query
        return RedirectResponse(f"/login?next={quote(target, safe='')}", status_code=303)

    @app.exception_handler(CsrfError)
    def csrf_error(request: Request, exc: CsrfError) -> HTMLResponse:
        context = {
            "title": "Veiksmas atmestas",
            "message": "Saugos žymė (CSRF) neteisinga arba pasenusi. "
            "Grįžkite atgal, atnaujinkite puslapį ir bandykite dar kartą.",
        }
        return templates.TemplateResponse(request, "error.html", context, status_code=403)

    @app.middleware("http")
    async def security_headers(request: Request, call_next) -> Response:
        response = await call_next(request)
        response.headers.setdefault("X-Frame-Options", "DENY")
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        if response.headers.get("content-type", "").startswith("text/html"):
            # Po atsijungimo naršyklė neturi rodyti vidinių puslapių iš talpyklos.
            response.headers.setdefault("Cache-Control", "no-store")
        return response

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/", response_class=HTMLResponse)
    def index(request: Request) -> HTMLResponse:
        return templates.TemplateResponse(request, "index.html")

    return app


# Vietinis `.env` failas (jei yra); realūs aplinkos kintamieji turi pirmenybę.
config.load_env_file(config.PROJECT_DIR / ".env")
app = create_app()
