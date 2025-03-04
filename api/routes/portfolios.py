from fastapi import APIRouter, Depends, HTTPException, Request
from typing import List
from models.portfolio import (
    Portfolio, PortfolioCreate, PortfolioHolding
)
from services.portfolio_service import PortfolioService
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from services.stock_master_service import StockMasterService
from datetime import datetime
from decimal import Decimal
import logging
from config.database import get_database

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

@router.get("/portfolios/new", response_class=HTMLResponse)
async def create_portfolio(request: Request):
    """Render the portfolio creation page"""
    try:
        return templates.TemplateResponse(
            "portfolio/create.html",
            {"request": request}
        )
    except Exception as e:
        logging.error(f"Error rendering portfolio creation page: {e}")
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

@router.get("/api/stocks/search")
def search_stocks(
    request: Request,
    query: str,
    stock_service: StockMasterService = Depends()
):
    try:
        stocks = stock_service.search_stocks(query)
        return JSONResponse(content=[
            {
                "id": stock.id,
                "symbol": stock.symbol,
                "name": stock.name,
                "exchange_code": stock.exchange_code
            } for stock in stocks
        ])
    except Exception as e:
        logging.error(f"Search error: {str(e)}")
        return JSONResponse(
            content={"error": str(e)},
            status_code=500
        )

@router.get("/api/stocks/validate/{stock_id}")
async def validate_stock(
    stock_id: str,
    stock_service: StockMasterService = Depends()
):
    stock = await stock_service.validate_stock(stock_id)
    if not stock:
        raise HTTPException(status_code=404, detail="Stock not found or inactive")
    return stock

@router.get("/api/stocks/verify")
async def verify_stocks_database(
    request: Request,
    stock_service: StockMasterService = Depends()
):
    """Verify database connection"""
    try:
        is_connected = await stock_service.verify_connection()
        
        if not is_connected:
            logging.error("Database connection verification failed")
            return JSONResponse(
                content={
                    "status": "error",
                    "message": "Database connection failed",
                    "details": "Could not verify connection to MongoDB"
                },
                status_code=500
            )
        
        return JSONResponse(
            content={
                "status": "success",
                "message": "Database connection verified"
            },
            status_code=200
        )
    except Exception as e:
        logging.error(f"Verification error: {str(e)}")
        return JSONResponse(
            content={
                "status": "error",
                "message": "Database connection failed",
                "details": str(e)
            },
            status_code=500
        )

@router.get("/api/stocks/test-connection")
async def test_database_connection(
    request: Request,
    stock_service: StockMasterService = Depends()
):
    """Test database connection and log details"""
    try:
        is_connected = await stock_service.verify_connection()
        if is_connected:
            return JSONResponse(
                content={
                    "status": "success",
                    "message": "Database connection successful. Check logs for details."
                },
                status_code=200
            )
        else:
            return JSONResponse(
                content={
                    "status": "error",
                    "message": "Database connection failed. Check logs for details."
                },
                status_code=500
            )
    except Exception as e:
        logging.error(f"Connection test failed: {str(e)}")
        return JSONResponse(
            content={
                "status": "error",
                "message": f"Test failed: {str(e)}"
            },
            status_code=500
        )

@router.get("/api/test-db")
async def test_db():
    """Simple endpoint to test database connection"""
    try:
        db = get_database()
        collection = db.master_stocks
        count = await collection.count_documents({})
        sample = await collection.find_one({})
        
        return {
            "status": "success",
            "count": count,
            "sample_id": str(sample['_id']) if sample else None,
            "sample_name": sample['display_name'] if sample else None
        }
    except Exception as e:
        logging.error(f"Database test failed: {e}")
        return {
            "status": "error",
            "error": str(e),
            "type": str(type(e))
        } 