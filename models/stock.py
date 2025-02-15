from pydantic import BaseModel
from datetime import datetime
from typing import Optional, Dict

class Stock(BaseModel):
    id: str
    symbol: str  # maps to identifiers.nse_code
    name: str    # maps to display_name
    exchange_code: str
    created_at: datetime
    status: str
    identifiers: Dict[str, str]
    trading_codes: Optional[Dict[str, str]] = None
    last_price: Optional[float] = None
    price_updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True 