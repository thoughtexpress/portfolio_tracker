# api/dependencies.py
from fastapi import Depends
from portfolio_tracker.database import get_db

async def get_current_user(token: str):
    """Reusable authentication"""
    pass

async def get_portfolio_service(db = Depends(get_db)):
    """Reusable service injection"""
    return PortfolioService(db)