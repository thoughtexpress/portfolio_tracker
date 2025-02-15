from pydantic import BaseModel, Field
from typing import List, Optional
from datetime import datetime
from uuid import UUID
from decimal import Decimal

class Transaction(BaseModel):
    date: datetime
    type: str  # "BUY" or "SELL"
    quantity: Decimal
    price: Decimal

class PortfolioHolding(BaseModel):
    stock_symbol: str = Field(max_length=20)
    exchange_code: str = Field(max_length=10)
    quantity: Decimal = Field(ge=0)
    average_buy_price: Decimal = Field(ge=0)
    current_value: Decimal = Field(ge=0)
    currency: str = Field(max_length=3)
    last_updated: datetime
    buy_date: datetime
    transactions: List[Transaction] = []

class PortfolioCreate(BaseModel):
    user_id: str
    name: str = Field(max_length=100)
    base_currency: str = "INR"

class Portfolio(BaseModel):
    id: UUID
    user_id: str
    name: str
    holdings: List[PortfolioHolding] = []
    total_value: Decimal = Decimal('0')
    cash_balance: Decimal = Decimal('0')
    base_currency: str
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True
        json_encoders = {
            Decimal: str,
            UUID: str
        }