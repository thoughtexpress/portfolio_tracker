from fastapi import APIRouter, Depends, HTTPException, Request
from typing import List
from models.portfolio import (
    Portfolio, PortfolioCreate, PortfolioHolding
)
from services.portfolio_service import PortfolioService
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from services.stock_master_service import StockMasterService
from datetime import datetime
from decimal import Decimal
import logging

router = APIRouter()
templates = Jinja2Templates(directory="web/templates")

@router.post("/", response_model=Portfolio)
async def create_portfolio(
    portfolio: PortfolioCreate,
    portfolio_service: PortfolioService = Depends()
):
    # Validate portfolio name
    if not portfolio.name or len(portfolio.name) > 100:
        raise HTTPException(
            status_code=400,
            detail="Portfolio name must be 1-100 characters"
        )

    # Validate holdings
    if not portfolio.holdings:
        raise HTTPException(
            status_code=400,
            detail="Portfolio must have at least one holding"
        )

    for holding in portfolio.holdings:
        # Validate quantity
        if holding.quantity <= Decimal('0'):
            raise HTTPException(
                status_code=400,
                detail="Quantity must be greater than 0"
            )

        # Validate purchase price
        if holding.purchase_price <= Decimal('0'):
            raise HTTPException(
                status_code=400,
                detail="Purchase price must be greater than 0"
            )

        # Validate purchase date
        if holding.purchase_date > datetime.now():
            raise HTTPException(
                status_code=400,
                detail="Purchase date cannot be in the future"
            )

        # Validate stock exists
        stock = await portfolio_service.stock_service.get_stock(holding.stock_id)
        if not stock:
            raise HTTPException(
                status_code=400,
                detail=f"Stock with ID {holding.stock_id} not found"
            )

    # Create portfolio
    try:
        created_portfolio = await portfolio_service.create_portfolio(portfolio)
        return created_portfolio
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Error creating portfolio: {str(e)}"
        )

@router.get("/", response_class=HTMLResponse)
async def list_portfolios(
    request: Request,
    portfolio_service: PortfolioService = Depends()
):
    portfolios = await portfolio_service.get_all_portfolios()
    return templates.TemplateResponse(
        "portfolio/dashboard.html",
        {
            "request": request,
            "portfolios": portfolios
        }
    )

@router.get("/{portfolio_id}", response_class=HTMLResponse)
async def get_portfolio(
    request: Request,
    portfolio_id: str,
    portfolio_service: PortfolioService = Depends()
):
    portfolio = await portfolio_service.get_portfolio(portfolio_id)
    if not portfolio:
        raise HTTPException(status_code=404, detail="Portfolio not found")
    return templates.TemplateResponse(
        "portfolio/detail.html",
        {
            "request": request,
            "portfolio": portfolio
        }
    )

@router.post("/{portfolio_id}/holdings")
async def add_holding(
    portfolio_id: str,
    holding: PortfolioHolding,
    portfolio_service: PortfolioService = Depends()
):
    # Validate holding data
    if holding.quantity <= Decimal('0'):
        raise HTTPException(
            status_code=400,
            detail="Quantity must be greater than 0"
        )

    if holding.purchase_price <= Decimal('0'):
        raise HTTPException(
            status_code=400,
            detail="Purchase price must be greater than 0"
        )

    if holding.purchase_date > datetime.now():
        raise HTTPException(
            status_code=400,
            detail="Purchase date cannot be in the future"
        )

    try:
        return await portfolio_service.add_holding(portfolio_id, holding)
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Error adding holding: {str(e)}"
        )

@router.get("/new", response_class=HTMLResponse)
async def show_create_form(
    request: Request,
    stock_service: StockMasterService = Depends()
):
    try:
        master_stocks = await stock_service.get_all_stocks()
        return templates.TemplateResponse(
            "portfolio/create.html",
            {
                "request": request,
                "master_stocks": master_stocks
            }
        )
    except Exception as e:
        logging.error(f"Error rendering template: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.put("/{portfolio_id}", response_model=Portfolio)
async def update_portfolio(
    portfolio_id: str,
    portfolio: PortfolioCreate,
    portfolio_service: PortfolioService = Depends()
):
    # Validate portfolio name
    if not portfolio.name or len(portfolio.name) > 100:
        raise HTTPException(
            status_code=400,
            detail="Portfolio name must be 1-100 characters"
        )

    try:
        updated_portfolio = await portfolio_service.update_portfolio(portfolio_id, portfolio)
        if not updated_portfolio:
            raise HTTPException(status_code=404, detail="Portfolio not found")
        return updated_portfolio
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Error updating portfolio: {str(e)}"
        )

@router.delete("/{portfolio_id}")
async def delete_portfolio(
    portfolio_id: str,
    portfolio_service: PortfolioService = Depends()
):
    try:
        success = await portfolio_service.delete_portfolio(portfolio_id)
        if not success:
            raise HTTPException(status_code=404, detail="Portfolio not found")
        return {"message": "Portfolio deleted successfully"}
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Error deleting portfolio: {str(e)}"
        ) 