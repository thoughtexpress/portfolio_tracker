from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from api.routes import portfolios
from config.settings import API_V1_PREFIX, PROJECT_NAME, DEBUG
from services.portfolio_service import PortfolioService

app = FastAPI(
    title=PROJECT_NAME,
    debug=DEBUG
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Adjust in production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount static files
app.mount("/static", StaticFiles(directory="web/static"), name="static")

# Templates
templates = Jinja2Templates(directory="web/templates")

# Include routers
app.include_router(portfolios.router, prefix=API_V1_PREFIX)

# Web routes
@app.get("/")
async def home(request):
    portfolio_service = PortfolioService()
    portfolios = await portfolio_service.get_all_portfolios()
    return templates.TemplateResponse(
        "portfolio/dashboard.html", 
        {"request": request, "portfolios": portfolios}
    ) 