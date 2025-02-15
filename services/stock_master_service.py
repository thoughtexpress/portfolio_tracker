from typing import Optional, List, Dict
import logging
from pymongo import MongoClient
from config.exchanges import EXCHANGE_CONFIGS, ExchangeConfig
from config.settings import MONGODB_URI

def get_database():
    client = MongoClient(MONGODB_URI)
    return client.portfolio_tracker

class StockMasterService:
    def __init__(self):
        self.db = get_database()
        self.collection = self.db.master_stocks

    async def create_stock_entry(self, stock_data: Dict, exchange_code: str) -> bool:
        """Create stock entry with exchange-specific information"""
        exchange_config = EXCHANGE_CONFIGS.get(exchange_code)
        if not exchange_config:
            raise ValueError(f"Unsupported exchange: {exchange_code}")

        stock_doc = {
            "display_name": stock_data["display_name"],
            "identifiers": {
                "symbol": stock_data["symbol"],
                "isin": stock_data.get("isin"),
                "exchange_codes": {
                    exchange_code: stock_data["symbol"]
                },
                "yfinance_symbol": f"{stock_data['symbol']}{exchange_config.symbol_suffix}"
            },
            "exchange_info": {
                "primary_exchange": exchange_code,
                "listed_exchanges": [exchange_code],
                "country": exchange_config.country,
                "currency": exchange_config.currency
            }
        }
        
        try:
            await self.collection.update_one(
                {"identifiers.isin": stock_data.get("isin")},
                {"$set": stock_doc},
                upsert=True
            )
            return True
        except Exception as e:
            logging.error(f"Error creating stock entry: {str(e)}")
            return False

    async def get_stock_by_symbol(self, symbol: str, exchange: str) -> Optional[Dict]:
        """Get stock by symbol and exchange"""
        return await self.collection.find_one({
            f"identifiers.exchange_codes.{exchange}": symbol
        })

    async def get_exchange_stocks(self, exchange: str) -> List[Dict]:
        """Get all stocks for a specific exchange"""
        return await self.collection.find({
            f"identifiers.exchange_codes.{exchange}": {"$exists": True}
        }).to_list(None)