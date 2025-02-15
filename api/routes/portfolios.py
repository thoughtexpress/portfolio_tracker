from fastapi import APIRouter, Depends, HTTPException
from typing import List
from models.portfolio import (
    Portfolio, PortfolioCreate, PortfolioHolding
)
from services.portfolio_service import PortfolioService
from fastapi.responses import HTMLResponse
from fastapi.requests import Request
from services.stock_master_service import StockMasterService
from fastapi.templating import Jinja2Templates

router = APIRouter(prefix="/portfolios")
templates = Jinja2Templates(directory="web/templates")

@router.post("/", response_model=Portfolio)
async def create_portfolio(
    portfolio: PortfolioCreate,
    portfolio_service: PortfolioService = Depends()
):
    return await portfolio_service.create_portfolio(portfolio)

@router.get("/", response_model=List[Portfolio])
async def list_portfolios(
    portfolio_service: PortfolioService = Depends()
):
    return await portfolio_service.get_all_portfolios()

@router.get("/{portfolio_id}", response_model=Portfolio)
async def get_portfolio(
    portfolio_id: str,
    portfolio_service: PortfolioService = Depends()
):
    portfolio = await portfolio_service.get_portfolio(portfolio_id)
    if not portfolio:
        raise HTTPException(status_code=404, detail="Portfolio not found")
    return portfolio

@router.post("/{portfolio_id}/holdings")
async def add_holding(
    portfolio_id: str,
    holding: PortfolioHolding,
    portfolio_service: PortfolioService = Depends()
):
    return await portfolio_service.add_holding(portfolio_id, holding)

@router.get("/new", response_class=HTMLResponse)
async def create_portfolio_form(
    request: Request,
    stock_service: StockMasterService = Depends()
):
    master_stocks = await stock_service.get_all_stocks()
    return templates.TemplateResponse(
        "portfolio/create.html",
        {
            "request": request,
            "master_stocks": master_stocks,
            "user_id": "temp_user"  # We'll implement auth later
        }
    ) 