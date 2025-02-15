from pydantic import BaseModel
from decimal import Decimal
from typing import List
from datetime import datetime

class PortfolioHolding(BaseModel):
    stock_symbol: str
    exchange_code: str
    quantity: Decimal
    average_buy_price: Decimal
    current_value: Decimal
    currency: str
    last_updated: datetime

    class Config:
        json_encoders = {
            Decimal: str
        }

class PortfolioCreate(BaseModel):
    user_id: str
    name: str
    base_currency: str = "USD"

class Portfolio(BaseModel):
    id: str
    user_id: str
    name: str
    holdings: List[PortfolioHolding]
    total_value: Decimal
    cash_balance: Decimal
    base_currency: str
    exchange_rates: dict
    created_at: datetime
    updated_at: datetime 