from pydantic import BaseModel
from datetime import datetime

class Stock(BaseModel):
    id: str
    symbol: str  # maps to identifiers.nse_code
    name: str    # maps to display_name
    exchange_code: str
    created_at: datetime

    class Config:
        from_attributes = True 