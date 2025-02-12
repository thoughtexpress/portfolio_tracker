import os
import sys
from datetime import datetime
import pytz
from pymongo import MongoClient
from bson import ObjectId, Decimal128
from decimal import Decimal
import logging
import traceback
from logging.handlers import RotatingFileHandler

# Add project root to path
current_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
project_root = os.path.dirname(current_dir)
sys.path.append(project_root)

from portfolio_tracker.config.settings import MONGODB_URI

class TransactionLogger:
    def __init__(self, name):
        self.logger = logging.getLogger(name)
        self.logger.setLevel(logging.DEBUG)
        
        # Create logs directory if it doesn't exist
        log_dir = os.path.join(project_root, 'logs')
        os.makedirs(log_dir, exist_ok=True)
        
        # File handler with rotation
        file_handler = RotatingFileHandler(
            os.path.join(log_dir, f'{name}.log'),
            maxBytes=10*1024*1024,  # 10MB
            backupCount=5
        )
        file_handler.setLevel(logging.DEBUG)
        
        # Console handler
        console_handler = logging.StreamHandler()
        console_handler.setLevel(logging.INFO)
        
        # Create formatters and add it to the handlers
        file_formatter = logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - [%(filename)s:%(lineno)d] - %(message)s'
        )
        console_formatter = logging.Formatter(
            '%(asctime)s - %(levelname)s - %(message)s'
        )
        
        file_handler.setFormatter(file_formatter)
        console_handler.setFormatter(console_formatter)
        
        # Add the handlers to the logger
        self.logger.addHandler(file_handler)
        self.logger.addHandler(console_handler)
    
    def debug(self, msg, *args, **kwargs):
        self.logger.debug(msg, *args, **kwargs)
    
    def info(self, msg, *args, **kwargs):
        self.logger.info(msg, *args, **kwargs)
    
    def warning(self, msg, *args, **kwargs):
        self.logger.warning(msg, *args, **kwargs)
    
    def error(self, msg, *args, **kwargs):
        error_info = traceback.format_exc()
        self.logger.error(f"{msg}\nStacktrace:\n{error_info}", *args, **kwargs)
    
    def critical(self, msg, *args, **kwargs):
        error_info = traceback.format_exc()
        self.logger.critical(f"{msg}\nStacktrace:\n{error_info}", *args, **kwargs)

class TransactionProcessor:
    def __init__(self):
        self.client = MongoClient(MONGODB_URI)
        self.db = self.client.portfolio_tracker
        self.MASTER_PORTFOLIO = "IND Stock Portfolio"
        self.logger = TransactionLogger('transaction_processor')
    
    def parse_date(self, date_str):
        """Parse date string to datetime object"""
        try:
            # Try parsing common date formats
            for fmt in ['%Y-%m-%d', '%d-%m-%Y', '%d/%m/%Y', '%Y/%m/%d']:
                try:
                    return datetime.strptime(date_str, fmt).replace(tzinfo=pytz.UTC)
                except ValueError:
                    continue
            raise ValueError(f"Unable to parse date: {date_str}")
        except Exception as e:
            self.logger.error(f"Error parsing date {date_str}: {str(e)}")
            raise
        
    def process_transaction(self, transaction_data):
        """Process a transaction by updating existing portfolio holdings"""
        try:
            self.logger.info(f"Processing transaction for {transaction_data['symbol']}")
            self.logger.debug(f"Transaction data: {transaction_data}")
            
            # Validate portfolio exists
            portfolio = self.db.portfolios.find_one({"name": transaction_data['portfolio']})
            if not portfolio:
                error_msg = f"Portfolio not found: {transaction_data['portfolio']}"
                self.logger.error(error_msg)
                raise ValueError(error_msg)

            # Check if this is an INR portfolio that needs master sync
            needs_master_sync = self.is_inr_portfolio(transaction_data['portfolio'])
            if needs_master_sync:
                master_portfolio = self.db.portfolios.find_one({"name": self.MASTER_PORTFOLIO})
                if not master_portfolio:
                    self.logger.error(f"Master portfolio '{self.MASTER_PORTFOLIO}' not found")
                    raise ValueError(f"Master portfolio '{self.MASTER_PORTFOLIO}' not found")

            # Extract base symbol and exchange code
            if '.' in transaction_data['symbol']:
                base_symbol, exchange_suffix = transaction_data['symbol'].split('.')
                exchange_code = 'NSE' if exchange_suffix == 'NS' else exchange_suffix
            else:
                base_symbol = transaction_data['symbol']
                exchange_code = 'NSE'
            
            self.logger.debug(f"Parsed symbol: {base_symbol}, exchange: {exchange_code}")

            # Process transaction for main portfolio
            self._process_portfolio_transaction(
                portfolio, base_symbol, exchange_code, transaction_data
            )

            # Sync with master portfolio if needed
            if needs_master_sync:
                self.logger.info(f"Syncing transaction to master portfolio for {base_symbol}")
                self._process_portfolio_transaction(
                    master_portfolio, base_symbol, exchange_code, transaction_data
                )

            return True

        except Exception as e:
            self.logger.error(f"Error processing transaction: {str(e)}")
            raise

    def _process_portfolio_transaction(self, portfolio, base_symbol, exchange_code, transaction_data):
        """Process transaction for a specific portfolio"""
        try:
            # Find existing holding
            holding = next(
                (h for h in portfolio['holdings'] 
                 if h['stock_symbol'] == base_symbol and h['exchange_code'] == exchange_code),
                None
            )
            
            if not holding:
                error_msg = (f"No existing holding found for {base_symbol} ({exchange_code}) "
                            f"in portfolio {portfolio['name']}")
                self.logger.error(error_msg)
                raise ValueError(error_msg)

            # Calculate values
            quantity = Decimal(str(transaction_data['quantity']))
            price = Decimal(str(transaction_data['price']))
            total = quantity * price
            
            current_qty = Decimal(str(holding['quantity'].to_decimal()))
            current_value = Decimal(str(holding['current_value'].to_decimal()))
            current_avg_price = Decimal(str(holding['average_buy_price'].to_decimal()))
            
            # Calculate P/L for the transaction
            if transaction_data['type'].upper() == 'SELL':
                # Calculate realized P/L for this transaction
                realized_pl = (price - current_avg_price) * quantity
                pl_percentage = ((price - current_avg_price) / current_avg_price) * Decimal('100')
                
                # Update holding quantities
                new_qty = current_qty - quantity
                if new_qty < 0:
                    raise ValueError(f"Insufficient quantity for {base_symbol}")
                
                new_value = new_qty * current_avg_price
                if new_value < 0:
                    new_value = Decimal('0')
                    
                # Calculate unrealized P/L for remaining position
                unrealized_pl = (price - current_avg_price) * new_qty if new_qty > 0 else Decimal('0')
                
            else:  # BUY
                realized_pl = Decimal('0')
                pl_percentage = Decimal('0')
                
                new_qty = current_qty + quantity
                new_avg_price = ((current_qty * current_avg_price) + (quantity * price)) / new_qty
                new_value = new_qty * new_avg_price
                
                # Calculate unrealized P/L for entire position
                unrealized_pl = (price - new_avg_price) * new_qty

            # Record the transaction with P/L
            transaction_record = {
                'portfolio_id': portfolio['_id'],
                'stock_symbol': base_symbol,
                'exchange_code': exchange_code,
                'transaction_type': transaction_data['type'].upper(),
                'quantity': Decimal128(str(quantity)),
                'price': Decimal128(str(price)),
                'timestamp': datetime.now(pytz.UTC),
                'total_amount': Decimal128(str(total)),
                'currency': holding['currency'],
                'realized_pl': Decimal128(str(realized_pl)),
                'pl_percentage': Decimal128(str(pl_percentage)),
                'status': 'PENDING',
                'created_at': datetime.now(pytz.UTC),
                'updated_at': datetime.now(pytz.UTC)
            }

            result = self.db.transactions.insert_one(transaction_record)
            
            try:
                # Update holding fields
                update_fields = {
                    "holdings.$.quantity": Decimal128(str(new_qty)),
                    "holdings.$.current_value": Decimal128(str(new_value)),
                    "holdings.$.unrealized_pl": Decimal128(str(unrealized_pl)),
                    "holdings.$.last_updated": datetime.now(pytz.UTC)
                }
                
                if transaction_data['type'].upper() == 'BUY':
                    update_fields["holdings.$.average_buy_price"] = Decimal128(str(new_avg_price))
                else:  # SELL
                    # Update total realized P/L
                    current_total_pl = Decimal(str(holding.get('total_realized_pl', Decimal128('0')).to_decimal()))
                    update_fields["holdings.$.total_realized_pl"] = Decimal128(str(current_total_pl + realized_pl))
                
                # Calculate current P/L percentage
                if new_qty > 0:
                    current_pl_percentage = (unrealized_pl / new_value) * Decimal('100')
                    update_fields["holdings.$.pl_percentage"] = Decimal128(str(current_pl_percentage))
                
                # Update holding
                self.db.portfolios.update_one(
                    {
                        "_id": portfolio['_id'],
                        "holdings": {
                            "$elemMatch": {
                                "stock_symbol": base_symbol,
                                "exchange_code": exchange_code
                            }
                        }
                    },
                    {"$set": update_fields}
                )
                
                # Update portfolio totals
                if transaction_data['type'].upper() == 'SELL':
                    new_total_value = max(Decimal('0'), Decimal(str(portfolio['total_value'].to_decimal())) - total)
                    new_cash_balance = Decimal(str(portfolio['cash_balance'].to_decimal())) + total
                else:  # BUY
                    new_total_value = Decimal(str(portfolio['total_value'].to_decimal())) + total
                    new_cash_balance = Decimal(str(portfolio['cash_balance'].to_decimal())) - total
                
                new_total_value = max(Decimal('0'), new_total_value)
                
                self.db.portfolios.update_one(
                    {"_id": portfolio['_id']},
                    {
                        "$set": {
                            "total_value": Decimal128(str(new_total_value)),
                            "cash_balance": Decimal128(str(new_cash_balance)),
                            "updated_at": datetime.now(pytz.UTC)
                        }
                    }
                )
                
                # Update transaction status
                self.db.transactions.update_one(
                    {'_id': result.inserted_id},
                    {'$set': {'status': 'COMPLETED', 'updated_at': datetime.now(pytz.UTC)}}
                )
                
                self.logger.info(f"Successfully processed transaction for {base_symbol} in {portfolio['name']}")
                
            except Exception as e:
                self.db.transactions.update_one(
                    {'_id': result.inserted_id},
                    {'$set': {'status': 'FAILED', 'updated_at': datetime.now(pytz.UTC)}}
                )
                raise
                
        except Exception as e:
            self.logger.error(f"Error processing portfolio transaction: {str(e)}")
            raise

    def is_inr_portfolio(self, portfolio_name):
        """Check if portfolio is an INR portfolio"""
        try:
            portfolio = self.db.portfolios.find_one({"name": portfolio_name})
            is_inr = portfolio and portfolio.get('currency') == 'INR' and portfolio.get('name') != self.MASTER_PORTFOLIO
            self.logger.debug(f"Portfolio {portfolio_name} INR status: {is_inr}")
            return is_inr
        except Exception as e:
            self.logger.error(f"Error checking INR portfolio status: {str(e)}")
            raise

def main():
    processor = TransactionProcessor()
    
    # Get CSV path from command line argument
    if len(sys.argv) != 2:
        print("Usage: python transaction_processor.py <path_to_csv>")
        sys.exit(1)
    
    csv_path = sys.argv[1]
    
    try:
        results = processor.process_csv(csv_path)
        print(f"Processing complete:")
        print(f"Successful transactions: {results['success']}")
        print(f"Failed transactions: {results['failed']}")
        if results['errors']:
            print("\nErrors:")
            for error in results['errors']:
                print(error)
    except Exception as e:
        print(f"Error processing transactions: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main() 