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
    stock_id: str
    quantity: Decimal = Field(gt=0)
    purchase_price: Decimal = Field(gt=0)
    purchase_date: datetime

class PortfolioCreate(BaseModel):
    name: str = Field(max_length=100)
    base_currency: str = "USD"

class Portfolio(BaseModel):
    id: str
    user_id: str
    name: str
    holdings: List[PortfolioHolding] = []
    base_currency: str
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True
        json_encoders = {
            Decimal: str,
            UUID: str
        }