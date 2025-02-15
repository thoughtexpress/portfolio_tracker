from decimal import Decimal
from typing import Dict, List
from datetime import datetime
from uuid import uuid4
from models.portfolio import Portfolio, PortfolioCreate, PortfolioHolding
from services.currency_service import CurrencyService
from services.stock_master_service import StockMasterService

class PortfolioService:
    def __init__(self):
        self.db = get_database()
        self.collection = self.db.portfolios
        self.currency_service = CurrencyService()
        self.stock_service = StockMasterService()

    async def create_portfolio(self, portfolio: PortfolioCreate) -> Portfolio:
        portfolio_dict = {
            "id": str(uuid4()),
            **portfolio.dict(),
            "holdings": [],
            "total_value": "0",
            "cash_balance": "0",
            "created_at": datetime.utcnow(),
            "updated_at": datetime.utcnow()
        }
        await self.collection.insert_one(portfolio_dict)
        return Portfolio(**portfolio_dict)

    async def get_all_portfolios(self) -> List[Portfolio]:
        portfolios = await self.collection.find().to_list(None)
        return [Portfolio(**p) for p in portfolios]

    async def get_portfolio_value(self, portfolio_id: str) -> Dict:
        """Get portfolio value with currency conversion"""
        portfolio = await self.get_portfolio(portfolio_id)
        total_value = Decimal('0')
        holdings_value = []

        for holding in portfolio.holdings:
            stock = await self.stock_service.get_stock_by_symbol(
                holding.stock_id, 
                holding.exchange
            )
            
            # Get current price in stock's native currency
            current_price = await self.get_current_price(
                stock['identifiers']['yfinance_symbol']
            )
            
            # Convert to portfolio's base currency
            if stock['exchange_info']['currency'] != portfolio.base_currency:
                exchange_rate = await self.currency_service.get_exchange_rate(
                    stock['exchange_info']['currency'],
                    portfolio.base_currency
                )
                value = holding.quantity * current_price * exchange_rate
            else:
                value = holding.quantity * current_price
                
            holdings_value.append({
                "stock": stock['display_name'],
                "value": value,
                "currency": portfolio.base_currency
            })
            total_value += value

        return {
            "total_value": total_value,
            "currency": portfolio.base_currency,
            "holdings": holdings_value
        }