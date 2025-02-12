import os
import sys
import pandas as pd
import streamlit as st
from datetime import datetime
import pytz
from io import StringIO
import yfinance as yf
from pymongo import MongoClient
from decimal import Decimal
from bson.decimal128 import Decimal128
import asyncio

# Add project root to path
current_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
project_root = os.path.dirname(current_dir)
sys.path.append(project_root)

from portfolio_tracker.scripts.transaction_processor import TransactionProcessor
from portfolio_tracker.utils.logger import setup_logger
from portfolio_tracker.scripts.seed_data import seed_database, seed_stock
from portfolio_tracker.scripts.fetch_historical_data import update_historical_data
from portfolio_tracker.database.stock_operations import get_all_stock_symbols
from portfolio_tracker.config.settings import MONGODB_URI

logger = setup_logger('transactions_page')

def validate_csv(df):
    """Validate CSV structure and data"""
    required_columns = ['date', 'symbol', 'quantity', 'price', 'type', 'portfolio', 'user']
    
    # Check required columns
    missing_columns = [col for col in required_columns if col not in df.columns]
    if missing_columns:
        return False, f"Missing required columns: {', '.join(missing_columns)}"
    
    # Validate data types
    try:
        df['date'] = pd.to_datetime(df['date'])
        df['quantity'] = pd.to_numeric(df['quantity'])
        df['price'] = pd.to_numeric(df['price'])
    except Exception as e:
        return False, f"Data type validation failed: {str(e)}"
    
    # Validate transaction types
    valid_types = ['buy', 'sell', 'dividend']
    invalid_types = df[~df['type'].isin(valid_types)]['type'].unique()
    if len(invalid_types) > 0:
        return False, f"Invalid transaction types found: {', '.join(invalid_types)}"
    
    return True, "Validation successful"

def format_transaction_preview(df):
    """Format DataFrame for preview"""
    preview_df = df.copy()
    preview_df['date'] = preview_df['date'].dt.strftime('%Y-%m-%d')
    preview_df['quantity'] = preview_df['quantity'].map('{:,.2f}'.format)
    preview_df['price'] = preview_df['price'].map('₹{:,.2f}'.format)
    return preview_df

def get_stock_info_from_yfinance(symbol):
    """Fetch comprehensive stock information from YFinance"""
    try:
        # Remove .NS suffix if present for lookup
        lookup_symbol = symbol.replace('.NS', '')
        ticker = yf.Ticker(f"{lookup_symbol}.NS")
        info = ticker.info
        
        if not info:
            return None
            
        # Get current price
        current_price = info.get('regularMarketPrice')
        if not current_price:
            return None
            
        # Format stock info to match seed_data.py expectations
        stock_info = {
            'symbol': lookup_symbol,
            'exchange_code': 'NSE',  # Explicitly set NSE for Indian stocks
            'name': info.get('longName', ''),
            'current_price': Decimal128(str(current_price)),
            'last_updated': datetime.now(pytz.UTC),
            'currency': 'INR',  # Set INR for NSE stocks
            'sector': info.get('sector', ''),
            'isin': info.get('isin', ''),
            'attributes': {
                'market_cap': Decimal128(str(info.get('marketCap', 0))),
                'pe_ratio': Decimal128(str(info.get('trailingPE', 0))),
                'dividend_yield': Decimal128(str(info.get('dividendYield', 0) * 100 if info.get('dividendYield') else 0)),
                '52_week_high': Decimal128(str(info.get('fiftyTwoWeekHigh', 0))),
                '52_week_low': Decimal128(str(info.get('fiftyTwoWeekLow', 0))),
                'face_value': Decimal128('1')  # Default face value for Indian stocks
            }
        }
        
        # Validate required fields
        required_fields = ['symbol', 'exchange_code', 'name', 'current_price', 'last_updated', 'currency']
        for field in required_fields:
            if not stock_info.get(field):
                logger.error(f"Missing required field {field} for {symbol}")
                return None
                
        return stock_info
        
    except Exception as e:
        logger.error(f"Error fetching info for {symbol}: {str(e)}")
        return None

async def add_new_stock_to_collections(symbol):
    """Add a new stock to stocks collection and fetch its historical data"""
    try:
        # 1. Get stock info from YFinance
        stock_info = get_stock_info_from_yfinance(symbol)
        if not stock_info:
            return False, f"Could not fetch info for {symbol}"

        # 2. Add to stocks collection
        success = seed_stock(stock_info)
        if not success:
            return False, f"Failed to add {symbol} to stocks collection"

        # 3. Fetch historical data for the new stock
        try:
            await update_historical_data(symbols=[symbol])
            logger.info(f"Historical data fetched for {symbol}")
        except Exception as e:
            logger.warning(f"Warning: Historical data fetch failed for {symbol}: {e}")
            # Continue anyway as the stock is added

        return True, f"Added {symbol}: {stock_info['name']}"

    except Exception as e:
        logger.error(f"Error adding new stock {symbol}: {e}")
        return False, str(e)

def add_new_stocks(df):
    """Add new stocks to database if they don't exist"""
    try:
        client = MongoClient(MONGODB_URI)
        db = client.portfolio_tracker
        
        # Get existing stocks from database
        existing_stocks = set(db.stocks.distinct('symbol'))
        
        # Get unique symbols from transactions
        transaction_symbols = {s.replace('.NS', '') for s in df['symbol'].unique()}
        
        # Find new symbols
        new_symbols = transaction_symbols - existing_stocks
        
        if not new_symbols:
            return True, "No new stocks to add"
            
        # Add new stocks
        results = []
        for symbol in new_symbols:
            # Show progress in Streamlit
            st.text(f"Processing new stock: {symbol}")
            
            success, message = asyncio.run(add_new_stock_to_collections(symbol))
            if success:
                results.append(f"✅ {message}")
            else:
                results.append(f"❌ Failed to add {symbol}: {message}")
                return False, f"Failed to add required stock: {symbol}"
        
        return True, "\n".join(results)
        
    except Exception as e:
        logger.error(f"Error adding new stocks: {str(e)}")
        return False, f"Error adding new stocks: {str(e)}"

def add_stock_mapping(stock_info):
    """Add new stock mapping and seed stock data"""
    try:
        client = MongoClient(MONGODB_URI)
        db = client.portfolio_tracker
        
        # Add to mappings
        mapping = {
            'yfinance_symbol': stock_info['symbol'],
            'display_name': stock_info['name'],
            'upstox_code': stock_info.get('upstox_code', stock_info['symbol']),
            'isin': stock_info.get('isin', ''),
            'nse_code': stock_info['symbol'],
            'status': 'active',
            'last_updated': datetime.now(pytz.UTC)
        }
        
        db.stock_mappings.insert_one(mapping)
        
        # Fetch complete info from yfinance and seed
        yf_info = get_stock_info_from_yfinance(stock_info['symbol'])
        if yf_info:
            seed_stock(yf_info)
            return True, "Stock added successfully"
        else:
            return False, "Could not fetch stock info from YFinance"
            
    except Exception as e:
        return False, f"Error adding stock: {str(e)}"

def main():
    st.title("Transaction Manager")
    
    # Initialize session state
    if 'transaction_data' not in st.session_state:
        st.session_state.transaction_data = None
    if 'validation_message' not in st.session_state:
        st.session_state.validation_message = None
    if 'processing_complete' not in st.session_state:
        st.session_state.processing_complete = False
    
    # File upload section
    st.header("Upload Transactions")
    uploaded_file = st.file_uploader("Choose a CSV file", type='csv')
    
    if uploaded_file is not None:
        try:
            # Read and validate CSV
            content = uploaded_file.read().decode('utf-8')
            df = pd.read_csv(StringIO(content))
            is_valid, message = validate_csv(df)
            
            if is_valid:
                # Check and add new stocks first
                with st.spinner("Checking for new stocks..."):
                    success, stock_message = add_new_stocks(df)
                    
                    if success:
                        st.session_state.transaction_data = df
                        st.session_state.validation_message = "✅ File validation successful"
                        if "No new stocks to add" not in stock_message:
                            st.success("New stocks added successfully:")
                            st.text(stock_message)
                    else:
                        st.error(stock_message)
                        st.session_state.transaction_data = None
                        return  # Stop processing if adding stocks failed
            else:
                st.session_state.validation_message = f"❌ Validation failed: {message}"
                st.session_state.transaction_data = None
            
        except Exception as e:
            st.session_state.validation_message = f"❌ Error reading file: {str(e)}"
            st.session_state.transaction_data = None
    
    # Display validation message
    if st.session_state.validation_message:
        if "successful" in st.session_state.validation_message:
            st.success(st.session_state.validation_message)
        else:
            st.error(st.session_state.validation_message)
    
    # Preview and process section
    if st.session_state.transaction_data is not None:
        st.header("Transaction Preview")
        preview_df = format_transaction_preview(st.session_state.transaction_data)
        st.dataframe(preview_df, use_container_width=True)
        
        # Process transactions button
        if st.button("Process Transactions"):
            try:
                processor = TransactionProcessor()
                
                # Create progress bar
                progress_bar = st.progress(0)
                status_text = st.empty()
                
                # Process each transaction
                total_rows = len(st.session_state.transaction_data)
                results = {
                    'success': 0,
                    'failed': 0,
                    'errors': []
                }
                
                for idx, row in st.session_state.transaction_data.iterrows():
                    try:
                        # Update progress
                        progress = (idx + 1) / total_rows
                        progress_bar.progress(progress)
                        status_text.text(f"Processing transaction {idx + 1} of {total_rows}")
                        
                        # Process transaction
                        transaction = row.to_dict()
                        processor.process_transaction(transaction)
                        results['success'] += 1
                        
                    except Exception as e:
                        results['failed'] += 1
                        results['errors'].append(f"Error in row {idx + 1}: {str(e)}")
                
                # Display results
                st.session_state.processing_complete = True
                
                if results['success'] > 0:
                    st.success(f"Successfully processed {results['success']} transactions")
                    
                    # Update historical data
                    with st.spinner('Updating historical data...'):
                        try:
                            update_historical_data()
                            st.success("Historical data updated successfully")
                        except Exception as e:
                            st.warning(f"Warning: Could not update historical data: {str(e)}")
                
                if results['failed'] > 0:
                    st.error(f"Failed to process {results['failed']} transactions")
                    st.write("Errors:")
                    for error in results['errors']:
                        st.write(f"- {error}")
                
            except Exception as e:
                st.error(f"Error processing transactions: {str(e)}")
    
    # Display sample CSV format
    with st.expander("View Sample CSV Format"):
        st.write("""
        Your CSV file should have the following columns:
        - date (YYYY-MM-DD)
        - symbol (e.g., RELIANCE.NS)
        - quantity (number)
        - price (number)
        - type (buy/sell/dividend)
        - portfolio (portfolio name)
        - user (username)
        - brokerage (optional)
        - notes (optional)
        """)
        
        sample_data = """date,symbol,quantity,price,type,portfolio,user,brokerage,notes
2024-01-15,RELIANCE.NS,10,2500.50,buy,Self Buy IND stocks,john_doe,20.00,Initial purchase
2024-02-01,RELIANCE.NS,5,2600.00,sell,Self Buy IND stocks,john_doe,20.00,Partial profit booking"""
        
        st.code(sample_data, language='csv')

if __name__ == "__main__":
    main() 