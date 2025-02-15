from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from api.routes import portfolios
from config.settings import PROJECT_NAME, DEBUG
from services.portfolio_service import PortfolioService
from services.stock_master_service import StockMasterService
from fastapi.responses import HTMLResponse

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

# Portfolio service
portfolio_service = PortfolioService()

# Stock service
stock_service = StockMasterService()

# Root route
@app.get("/", response_class=HTMLResponse)
async def root(request: Request):
    return templates.TemplateResponse(
        "portfolio/dashboard.html", 
        {
            "request": request,
            "portfolios": []
        }
    )

# Create Portfolio Form Route - MUST BE BEFORE ROUTER INCLUSION
@app.get("/portfolios/new", response_class=HTMLResponse)
async def new_portfolio(request: Request):
    try:
        stocks = await stock_service.get_all_stocks()
        return templates.TemplateResponse(
            "portfolio/create.html",
            {
                "request": request,
                "master_stocks": stocks
            }
        )
    except Exception as e:
        print(f"Error: {e}")  # For debugging
        return {"detail": str(e)}

# Include portfolio routes
app.include_router(
    portfolios.router,
    prefix="/portfolios",
    tags=["portfolios"]
) 