from pydantic import BaseModel
from datetime import datetime
from typing import Dict, Optional

class Stock(BaseModel):
    id: str
    symbol: str
    name: str
    exchange_code: str = "NSE"
    created_at: datetime
    status: str = "active"
    identifiers: Dict[str, str] = {}
    trading_codes: Optional[Dict[str, str]] = None
    last_price: Optional[float] = None
    price_updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True 