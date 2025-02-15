from typing import Optional, List, Dict
import logging
from pymongo import MongoClient
from config.exchanges import EXCHANGE_CONFIGS, ExchangeConfig
from config.settings import MONGODB_URI
from models.stock import Stock
from datetime import datetime
from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase
from config.database import get_database
from bson import ObjectId

def get_database():
    client = MongoClient(MONGODB_URI)
    return client.portfolio_tracker

class StockMasterService:
    def __init__(self):
        self.db = None
        self.collection = None

    async def initialize(self):
        """Initialize database connection"""
        if self.db is None:
            self.db = await get_database()
            self.collection = self.db.master_stocks
            logging.info("StockMasterService initialized")

    async def get_all_stocks(self) -> List[Stock]:
        """Fetch all stocks from the master_stocks collection"""
        try:
            # Convert cursor to list directly
            stocks_data = await self.collection.find({"status": "active"}).to_list(None)
            return [self._map_to_stock_model(stock) for stock in stocks_data]
        except Exception as e:
            logging.error(f"Error fetching stocks: {e}")
            return []

    async def get_stock(self, stock_id: str) -> Optional[Stock]:
        """Fetch a specific stock by ID"""
        try:
            stock = await self.collection.find_one({"_id": ObjectId(stock_id)})
            if stock:
                return self._map_to_stock_model(stock)
            return None
        except Exception as e:
            print(f"Error fetching stock {stock_id}: {e}")
            return None

    async def add_stock(self, stock: Stock) -> Optional[Stock]:
        """Add a new stock to the master list"""
        try:
            result = await self.collection.insert_one({
                "_id": stock.id,
                "symbol": stock.symbol,
                "name": stock.name,
                "exchange_code": stock.exchange_code,
                "created_at": datetime.now()
            })
            if result.inserted_id:
                return stock
            return None
        except Exception as e:
            print(f"Error adding stock: {e}")
            return None

    async def update_stock(self, stock_id: str, stock: Stock) -> Optional[Stock]:
        """Update an existing stock"""
        try:
            result = await self.collection.update_one(
                {"_id": stock_id},
                {"$set": {
                    "symbol": stock.symbol,
                    "name": stock.name,
                    "exchange_code": stock.exchange_code
                }}
            )
            if result.modified_count:
                return stock
            return None
        except Exception as e:
            print(f"Error updating stock: {e}")
            return None

    async def delete_stock(self, stock_id: str) -> bool:
        """Delete a stock from the master list"""
        try:
            result = await self.collection.delete_one({"_id": stock_id})
            return result.deleted_count > 0
        except Exception as e:
            print(f"Error deleting stock: {e}")
            return False

    async def search_stocks(self, query: str) -> List[Stock]:
        """Search stocks by symbol or display name"""
        try:
            # Ensure initialization
            await self.initialize()
            
            search_query = {
                "status": "active",
                "$or": [
                    {"identifiers.nse_code": {"$regex": query, "$options": "i"}},
                    {"display_name": {"$regex": query, "$options": "i"}}
                ]
            }
            
            cursor = self.collection.find(search_query)
            stocks_data = await cursor.to_list(length=None)
            
            stocks = []
            for doc in stocks_data:
                try:
                    stock = Stock(
                        id=str(doc['_id']),
                        symbol=doc['identifiers']['nse_code'],
                        name=doc['display_name'],
                        exchange_code="NSE",
                        created_at=doc['created_at'],
                        status=doc.get('status', 'active'),
                        identifiers=doc['identifiers']
                    )
                    stocks.append(stock)
                except Exception as e:
                    logging.error(f"Error mapping stock document: {e}")
                    continue
            
            return stocks
        except Exception as e:
            logging.error(f"Error searching stocks: {e}")
            return []

    def _map_to_stock_model(self, doc: dict) -> Stock:
        """Map MongoDB document to Stock model"""
        return Stock(
            id=str(doc['_id']),
            symbol=doc['identifiers']['nse_code'],
            name=doc['display_name'],
            exchange_code="NSE",
            created_at=doc['created_at'],
            status=doc['status'],
            identifiers=doc['identifiers']
        )

    async def validate_stock(self, stock_id: str) -> Optional[Stock]:
        """Validate if a stock exists and is active"""
        try:
            stock = await self.collection.find_one({
                "_id": ObjectId(stock_id),
                "status": "active"
            })
            return self._map_to_stock_model(stock) if stock else None
        except Exception as e:
            print(f"Error validating stock {stock_id}: {e}")
            return None

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

    async def verify_database_connection(self) -> bool:
        """Verify database connection and collection existence"""
        try:
            # Ensure initialization
            await self.initialize()
            
            # Count documents in master_stocks
            count = await self.collection.count_documents({})
            logging.info(f"Total stocks in database: {count}")
            
            # Get a sample document
            sample = await self.collection.find_one({})
            if sample:
                logging.info(f"Sample stock document structure: {list(sample.keys())}")
            else:
                logging.warning("No documents found in master_stocks collection")
            
            return True
        except Exception as e:
            logging.error(f"Database verification failed: {e}")
            return False