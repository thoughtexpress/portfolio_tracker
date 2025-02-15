from typing import Dict, List, Set
import yfinance as yf
from datetime import datetime
import pytz
import logging
import pandas as pd
import requests

from config.settings import MONGODB_URI
#from scripts.setup.create_master_stocks import StockMaster

class StockMasterMaintenance:
    def __init__(self, stock_master: StockMaster):
        self.stock_master = stock_master
        self.logger = logging.getLogger(__name__)

    def get_current_nse_stocks(self) -> Set[str]:
        """Fetch current NSE stock list"""
        try:
            # Get NSE stocks from NSE website
            url = "https://archives.nseindia.com/content/equities/EQUITY_L.csv"
            df = pd.read_csv(url)
            
            # Extract symbols and clean them
            nse_stocks = set(df['SYMBOL'].str.strip())
            self.logger.info(f"Found {len(nse_stocks)} stocks from NSE")
            
            return nse_stocks
            
        except Exception as e:
            self.logger.error(f"Error fetching NSE stocks: {e}")
            # Fallback method using yfinance if NSE website fails
            try:
                # You might need to adjust this based on available data
                tickers = yf.Tickers("^NSEI")  # NSE Index
                # This is a placeholder - you'll need to implement proper NSE stock fetching
                self.logger.warning("Using fallback method to fetch NSE stocks")
                return set()
            except Exception as e2:
                self.logger.error(f"Fallback method also failed: {e2}")
                return set()

    def get_stock_details(self, symbol: str) -> Dict:
        """Fetch detailed stock info from YFinance"""
        try:
            self.logger.info(f"Fetching details for {symbol}")
            ticker = yf.Ticker(f"{symbol}.NS")
            info = ticker.info
            
            if not info:
                self.logger.warning(f"No info found for {symbol}")
                return {}
                
            return {
                "display_name": info.get("longName", symbol),
                "nse_code": symbol,
                "yfinance_symbol": f"{symbol}.NS",
                "isin": info.get("isin", ""),
                "upstox_symbol": symbol,  # Usually same as NSE code
                "upstox_transaction_code": info.get("longName", symbol),  # Default to long name
                "upstox_holdings_code": symbol  # Usually same as NSE code
            }
        except Exception as e:
            self.logger.error(f"Error fetching details for {symbol}: {e}")
            return {}

    def detect_changes(self, current_stocks: Set[str]) -> Dict[str, List[str]]:
        """Detect new listings and delistings"""
        existing_stocks = {stock["identifiers"]["nse_code"] 
                         for stock in self.stock_master.get_all_active_stocks()}
        
        return {
            "new_listings": list(current_stocks - existing_stocks),
            "delistings": list(existing_stocks - current_stocks)
        }

    def detect_name_changes(self, symbol: str, new_info: Dict) -> bool:
        """Detect if stock name has changed"""
        existing_stock = self.stock_master.find_stock(symbol)
        if not existing_stock:
            return False

        current_name = existing_stock["display_name"]
        new_name = new_info["display_name"]
        
        return current_name != new_name

    def update_stocks(self):
        """Main update routine"""
        try:
            # Get current NSE stocks
            current_stocks = self.get_current_nse_stocks()
            changes = self.detect_changes(current_stocks)

            # Handle new listings
            for symbol in changes["new_listings"]:
                stock_info = self.get_stock_details(symbol)
                if stock_info:
                    self.stock_master.create_stock_entry(stock_info)
                    self.logger.info(f"Added new stock: {symbol}")

            # Handle delistings
            for symbol in changes["delistings"]:
                self.stock_master.update_status(symbol, "delisted")
                self.logger.info(f"Marked as delisted: {symbol}")

            # Check for name changes in existing stocks
            for symbol in current_stocks:
                new_info = self.get_stock_details(symbol)
                if new_info and self.detect_name_changes(symbol, new_info):
                    self.stock_master.add_name_variant(
                        symbol,
                        new_info["display_name"],
                        "yfinance_update"
                    )
                    self.logger.info(f"Updated name for {symbol}")

        except Exception as e:
            self.logger.error(f"Error in update routine: {e}")

def main():
    """Main entry point for the script."""
    # Set up logging
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    logger = logging.getLogger(__name__)
    
    logger.info("Starting stock master maintenance...")
    
    stock_master = StockMaster(MONGODB_URI)
    maintenance = StockMasterMaintenance(stock_master)
    
    try:
        maintenance.update_stocks()
        logger.info("Stock master maintenance completed successfully")
    except Exception as e:
        logger.error(f"Error during maintenance: {e}")
    finally:
        stock_master.close()

if __name__ == "__main__":
    main()