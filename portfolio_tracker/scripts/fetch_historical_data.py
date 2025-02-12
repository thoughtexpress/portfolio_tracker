import os
import sys
from datetime import datetime, timedelta
import pytz
from decimal import Decimal
import pandas as pd
import yfinance as yf
from pymongo import MongoClient
from bson.decimal128 import Decimal128
from tqdm import tqdm
import time

# Add the project root directory to Python path
current_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(os.path.dirname(current_dir))
sys.path.append(project_root)

from portfolio_tracker.models.historical_price import HistoricalPrice
from portfolio_tracker.config.settings import MONGODB_URI
from portfolio_tracker.utils.logger import setup_logger

logger = setup_logger('stock_fetcher')

class StockDataFetcher:
    def __init__(self):
        self.client = MongoClient(MONGODB_URI)
        self.db = self.client.portfolio_tracker
        self.historical_price = HistoricalPrice()

    def safe_decimal128(self, value):
        """Safely convert any numeric value to Decimal128"""
        try:
            if isinstance(value, Decimal128):
                return value
            if isinstance(value, (Decimal, float, int)):
                return Decimal128(str(value))
            if isinstance(value, str):
                return Decimal128(value)
            return Decimal128('0')
        except Exception as e:
            logger.error(f"Error converting value to Decimal128: {value}, {e}")
            return Decimal128('0')

    def get_current_price(self, symbol, exchange):
        """Fetch current price using yfinance"""
        try:
            if exchange == "NSE" and not symbol.endswith('.NS'):
                symbol = f"{symbol}.NS"
                
            stock = yf.Ticker(symbol)
            info = stock.info
            price = info.get('regularMarketPrice', 0)
            return self.safe_decimal128(price)
        except Exception as e:
            logger.error(f"Error fetching current price for {symbol}: {e}")
            return self.safe_decimal128('0')

    def get_last_update_date(self, symbol, exchange_code):
        """Get the last date for which we have data for a stock"""
        try:
            query_symbol = symbol
            if exchange_code == "NSE" and not symbol.endswith('.NS'):
                query_symbol = f"{symbol}.NS"

            last_record = self.db.historical_prices.find_one(
                {"symbol": query_symbol},
                sort=[("date", -1)]
            )
            
            if last_record and 'date' in last_record:
                # Ensure the date is timezone-aware
                last_date = last_record['date']
                if last_date.tzinfo is None:
                    last_date = pytz.UTC.localize(last_date)
                return last_date
            return None
        except Exception as e:
            logger.error(f"Error getting last update date for {symbol}: {e}")
            return None

    def is_new_stock(self, symbol, exchange_code):
        """Check if this is a new stock not in our database"""
        query_symbol = symbol
        if exchange_code == "NSE" and not symbol.endswith('.NS'):
            query_symbol = f"{symbol}.NS"

        return self.db.historical_prices.count_documents({"symbol": query_symbol}) == 0

    def get_stock_inception_date(self, symbol, exchange):
        """Get the earliest available date for a new stock"""
        try:
            if exchange == "NSE" and not symbol.endswith('.NS'):
                symbol = f"{symbol}.NS"
            
            stock = yf.Ticker(symbol)
            hist = stock.history(period="max", interval="1d")
            
            if hist.empty:
                logger.warning(f"No historical data found for {symbol}")
                return datetime.now(pytz.UTC) - timedelta(days=365)
                
            earliest_date = hist.index[0].to_pydatetime()
            logger.info(f"Found inception date for {symbol}: {earliest_date.date()}")
            
            return pytz.UTC.localize(earliest_date) if earliest_date.tzinfo is None else earliest_date
            
        except Exception as e:
            logger.error(f"Error getting inception date for {symbol}: {e}")
            return datetime.now(pytz.UTC) - timedelta(days=365)

    def fetch_stock_data(self, symbol, exchange_code, start_date, end_date):
        """Fetch historical data for a stock using yfinance"""
        try:
            # Ensure dates are timezone-aware
            if start_date.tzinfo is None:
                start_date = pytz.UTC.localize(start_date)
            if end_date.tzinfo is None:
                end_date = pytz.UTC.localize(end_date)

            query_symbol = symbol
            if exchange_code == "NSE" and not symbol.endswith('.NS'):
                query_symbol = f"{symbol}.NS"

            logger.info(f"Fetching data for {query_symbol} from {start_date.date()} to {end_date.date()}")
            
            stock = yf.Ticker(query_symbol)
            df = stock.history(start=start_date, end=end_date)
            
            prices_data = []
            for index, row in df.iterrows():
                # Ensure the index datetime is timezone-aware
                date = index.to_pydatetime()
                if date.tzinfo is None:
                    date = pytz.UTC.localize(date)

                price_data = {
                    "symbol": query_symbol,
                    "exchange_code": exchange_code,
                    "date": date,
                    "open": self.safe_decimal128(row['Open']),
                    "high": self.safe_decimal128(row['High']),
                    "low": self.safe_decimal128(row['Low']),
                    "close": self.safe_decimal128(row['Close']),
                    "volume": self.safe_decimal128(row['Volume']),
                    "source": "yfinance"
                }
                prices_data.append(price_data)
            
            return prices_data
            
        except Exception as e:
            logger.error(f"Error fetching stock data for {symbol}: {e}")
            return None

    def update_stock_data(self, symbol, exchange_code):
        """Update stock data, fetching only the delta since last update"""
        try:
            end_date = datetime.now(pytz.UTC)  # Already timezone-aware
            
            if self.is_new_stock(symbol, exchange_code):
                logger.info(f"New stock detected: {symbol}")
                start_date = self.get_stock_inception_date(symbol, exchange_code)
                if start_date.tzinfo is None:
                    start_date = pytz.UTC.localize(start_date)
            else:
                last_update = self.get_last_update_date(symbol, exchange_code)
                if not last_update:
                    logger.error(f"No last update date found for existing stock: {symbol}")
                    return False
                
                # Ensure last_update is timezone-aware
                if last_update.tzinfo is None:
                    last_update = pytz.UTC.localize(last_update)
                
                start_date = last_update + timedelta(days=1)
                
                if start_date >= end_date:
                    logger.info(f"Data already up to date for {symbol}")
                    return True

            prices = self.fetch_stock_data(symbol, exchange_code, start_date, end_date)
            
            if not prices:
                return False

            # Add creation timestamp
            now = datetime.now(pytz.UTC)  # Already timezone-aware
            prices = [dict(**price, created_at=now) for price in prices]

            if prices:
                batch_size = 1000
                for i in range(0, len(prices), batch_size):
                    batch = prices[i:i + batch_size]
                    self.historical_price.insert_prices(batch)
                
                logger.info(f"Updated {len(prices)} records for {symbol}")
                return True

            return True

        except Exception as e:
            logger.error(f"Error updating data for {symbol}: {e}")
            logger.exception(e)  # Log full stack trace
            return False

def main():
    fetcher = StockDataFetcher()
    
    # Get stocks from CSV or database
    csv_path = 'data/stocks.csv'
    if os.path.exists(csv_path):
        logger.info("Loading stocks from CSV...")
        df = pd.read_csv(csv_path)
        stocks = df.to_dict('records')
    else:
        logger.info("Getting stocks from database...")
        stocks = list(fetcher.db.stocks.find({}, {
            "symbol": 1, 
            "exchange_code": 1, 
            "_id": 0
        }))
    
    if not stocks:
        logger.warning("No stocks found to update")
        return

    logger.info(f"Processing {len(stocks)} stocks")
    
    for stock in tqdm(stocks, desc="Processing stocks"):
        symbol = stock['symbol']
        exchange = stock.get('exchange_code') or stock.get('exchange')
        
        fetcher.update_stock_data(symbol, exchange)
        time.sleep(1)  # Rate limiting between stocks

def update_historical_data():
    """Update historical price data for all stocks in portfolio"""
    try:
        client = MongoClient(MONGODB_URI)
        db = client.portfolio_tracker
        
        # Get all unique symbols from portfolios
        symbols = db.stocks.distinct('symbol')
        
        # Get yesterday's date as end date
        end_date = datetime.now()
        start_date = end_date - timedelta(days=7)  # Get 7 days of data
        
        for symbol in symbols:
            try:
                # Add .NS suffix for NSE stocks
                ticker_symbol = f"{symbol}.NS"
                ticker = yf.Ticker(ticker_symbol)
                
                # Fetch historical data
                hist = ticker.history(start=start_date, end=end_date)
                
                if not hist.empty:
                    # Convert index to datetime and prepare data for MongoDB
                    for date, row in hist.iterrows():
                        price_data = {
                            'symbol': symbol,
                            'date': date.to_pydatetime(),
                            'open': float(row['Open']),
                            'high': float(row['High']),
                            'low': float(row['Low']),
                            'close': float(row['Close']),
                            'volume': int(row['Volume'])
                        }
                        
                        # Upsert price data
                        db.historical_prices.update_one(
                            {'symbol': symbol, 'date': price_data['date']},
                            {'$set': price_data},
                            upsert=True
                        )
                        
            except Exception as e:
                logger.error(f"Error updating data for {symbol}: {str(e)}")
                continue
                
        client.close()
        return True
        
    except Exception as e:
        logger.error(f"Error in update_historical_data: {str(e)}")
        return False

if __name__ == "__main__":
    main() 