from pathlib import Path
from urllib.parse import quote

from fastapi import Depends, FastAPI, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from app import config
from app.auth import CsrfError, Forbidden, LoginRateLimiter, LoginRequired, Session, get_current_session
from app.routes import account, admin_users, annotations, auth, dashboard, developer, issues, reports

BASE_DIR = Path(__file__).resolve().parent

templates = Jinja2Templates(directory=BASE_DIR / "templates")


def create_app() -> FastAPI:
    app = FastAPI(title="Klaidų klasifikavimo ir prioritizavimo sistema")
    app.state.login_limiter = LoginRateLimiter()  # atskiras kiekvienai programos instancijai
    app.mount("/static", StaticFiles(directory=BASE_DIR / "static"), name="static")

    app.include_router(issues.router)
    app.include_router(reports.router)
    app.include_router(auth.router)
    app.include_router(dashboard.router)
    app.include_router(annotations.router)
    app.include_router(account.router)
    app.include_router(developer.router)
    app.include_router(admin_users.router)

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

    @app.exception_handler(Forbidden)
    def forbidden(request: Request, exc: Forbidden) -> HTMLResponse:
        context = {
            "title": "Prieiga uždrausta",
            "message": "Jūsų paskyros rolė neleidžia atidaryti šio puslapio arba atlikti šio veiksmo.",
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
    def index(request: Request, session: Session | None = Depends(get_current_session)) -> HTMLResponse:
        return templates.TemplateResponse(request, "index.html", {"session": session})

    return app


# Vietinis `.env` failas (jei yra); realūs aplinkos kintamieji turi pirmenybę.
config.load_env_file(config.PROJECT_DIR / ".env")
app = create_app()
