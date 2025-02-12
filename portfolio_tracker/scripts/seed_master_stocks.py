import pandas as pd
import yfinance as yf
from pymongo import MongoClient
from datetime import datetime
import pytz
import logging
from tqdm import tqdm
import sys
import os
from fuzzywuzzy import fuzz

# Add project root to path
current_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(os.path.dirname(current_dir))
sys.path.append(project_root)

from portfolio_tracker.config.settings import MONGODB_URI
from portfolio_tracker.utils.logger import setup_logger

logger = setup_logger('import_stock_mappings')

def get_yfinance_info(identifier, isin=None):
    """Try to find stock info using any available identifier"""
    try:
        # Try direct lookup
        ticker = yf.Ticker(f"{identifier}.NS")
        info = ticker.info
        
        # Verify ISIN if provided
        if isin and info and info.get('isin') != isin:
            return None
            
        return info
        
    except Exception as e:
        logger.error(f"Error fetching YFinance info for {identifier}: {str(e)}")
        return None

def get_stock_info_from_name(transaction_code):
    """Try to find stock info using transaction code"""
    try:
        # Remove common suffixes and clean the name
        search_name = transaction_code.replace(' LIMITED', '').replace(' LTD', '').strip()
        search_name = search_name.split('(')[0].strip()  # Remove anything in parentheses
        
        # Try direct lookup with common variations
        variations = [
            search_name,
            search_name.replace(' ', ''),  # No spaces
            search_name.split()[0]  # First word only
        ]
        
        for name in variations:
            try:
                ticker = yf.Ticker(f"{name}.NS")
                info = ticker.info
                if info and 'symbol' in info:
                    logger.info(f"Found match for {transaction_code}: {info.get('longName', '')}")
                    return info
            except Exception as e:
                continue
                
        logger.warning(f"No YFinance match found for {transaction_code}")
        return None
        
    except Exception as e:
        logger.error(f"Error fetching YFinance info for {transaction_code}: {str(e)}")
        return None

def clean_mapping_data(mapping):
    """Clean and validate mapping data before MongoDB insertion"""
    # Convert NaN/None to empty strings for string fields
    string_fields = [
        'display_name', 
        'company_ticker', 
        'isin', 
        'yfinance_symbol',
        'upstox_holdings_code',
        'upstox_transaction_code'
    ]
    
    cleaned_mapping = {}
    for key, value in mapping.items():
        if key in string_fields:
            # Convert NaN, None, or non-string values to empty string
            cleaned_mapping[key] = str(value) if pd.notna(value) else ''
        else:
            cleaned_mapping[key] = value
    
    return cleaned_mapping

def import_mappings(csv_file, incomplete_data=False):
    """Import stock mappings from CSV and enrich with YFinance data"""
    client = None
    try:
        # Read CSV with explicit encoding handling
        try:
            df = pd.read_csv(csv_file, encoding='utf-8')
        except UnicodeDecodeError:
            df = pd.read_csv(csv_file, encoding='latin1')
            
        logger.info(f"Found {len(df)} stocks in CSV")
        
        # Connect to MongoDB
        client = MongoClient(MONGODB_URI)
        db = client.portfolio_tracker
        
        results = {
            'success': 0,
            'failed': 0,
            'errors': []
        }
        
        # Process each stock
        for _, row in tqdm(df.iterrows(), total=len(df)):
            try:
                if incomplete_data:
                    # Verify we have the transaction code
                    if not pd.notna(row.get('upstox_transaction_code')):
                        raise ValueError("Missing upstox_transaction_code")
                    
                    transaction_code = str(row['upstox_transaction_code']).strip()
                    logger.info(f"Processing {transaction_code}")
                    
                    # Try to get info from YFinance
                    yf_info = get_stock_info_from_name(transaction_code)
                    
                    if not yf_info:
                        raise ValueError(f"Could not find stock info for {transaction_code}")
                    
                    # Create mapping from YFinance data
                    mapping = {
                        'display_name': yf_info.get('longName', ''),
                        'company_ticker': yf_info.get('symbol', '').replace('.NS', ''),
                        'isin': yf_info.get('isin', ''),
                        'yfinance_symbol': yf_info.get('symbol', '').replace('.NS', ''),
                        'upstox_transaction_code': transaction_code,
                        'upstox_holdings_code': row.get('upstox_holdings_code', ''),
                        'status': 'active',
                        'last_updated': datetime.now(pytz.UTC)
                    }
                    
                    # Log the mapping for debugging
                    logger.info(f"Created mapping for {transaction_code}: {mapping}")
                else:
                    # Original logic for complete data
                    mapping = {
                        'isin': row.get('isin', ''),
                        'display_name': row.get('display_name', ''),
                        'company_ticker': row.get('company_ticker', ''),
                        'yfinance_symbol': str(row.get('yfinance_symbol', '')).replace('.NS', ''),
                        'upstox_holdings_code': row.get('upstox_holdings_code', ''),
                        'upstox_transaction_code': row.get('upstox_transaction_code', ''),
                        'status': 'active',
                        'last_updated': datetime.now(pytz.UTC)
                    }
                
                # Clean and validate the mapping data
                cleaned_mapping = clean_mapping_data(mapping)
                
                # Validate required fields
                missing_fields = []
                if not cleaned_mapping.get('display_name'):
                    missing_fields.append('display_name')
                if not cleaned_mapping.get('company_ticker'):
                    missing_fields.append('company_ticker')
                if not cleaned_mapping.get('isin'):
                    missing_fields.append('isin')
                
                if missing_fields:
                    raise ValueError(f"Missing required fields: {', '.join(missing_fields)}")
                
                # Add or update mapping
                db.stock_mappings.update_one(
                    {'isin': cleaned_mapping['isin']},
                    {'$set': cleaned_mapping},
                    upsert=True
                )
                
                results['success'] += 1
                logger.info(f"Added/Updated mapping for {cleaned_mapping['display_name']}")
                
            except Exception as e:
                results['failed'] += 1
                error_msg = f"Error processing {row.get('upstox_transaction_code', 'unknown stock')}: {str(e)}"
                results['errors'].append(error_msg)
                logger.error(error_msg)
        
        # Print summary
        print("\nImport Summary:")
        print(f"Successfully processed: {results['success']}")
        print(f"Failed: {results['failed']}")
        if results['errors']:
            print("\nErrors:")
            for error in results['errors']:
                print(f"- {error}")
        
        return results['success'] > 0
        
    except Exception as e:
        logger.error(f"Error importing mappings: {str(e)}")
        return False
    
    finally:
        if client:
            client.close()

def find_stock_by_identifier(identifier):
    """Find stock mapping using any identifier (ISIN, company_ticker, yfinance_symbol)"""
    try:
        client = MongoClient(MONGODB_URI)
        db = client.portfolio_tracker
        
        # Try different fields
        mapping = db.stock_mappings.find_one({
            '$or': [
                {'isin': identifier},
                {'company_ticker': identifier},
                {'yfinance_symbol': identifier},
                {'nse_code': identifier}
            ]
        })
        
        return mapping
        
    except Exception as e:
        logger.error(f"Error finding stock: {str(e)}")
        return None
    
    finally:
        client.close()

def find_similar_stocks(transaction_code, threshold=80):
    """Find similar stocks in existing mappings using fuzzy matching"""
    try:
        # Connect to MongoDB
        client = MongoClient(MONGODB_URI)
        db = client.portfolio_tracker
        
        # Get all existing mappings
        existing_mappings = list(db.stock_mappings.find({}, {
            'display_name': 1, 
            'upstox_transaction_code': 1,
            'company_ticker': 1,
            'isin': 1
        }))
        
        # Clean the transaction code
        clean_name = transaction_code.replace(' LIMITED', '').replace(' LTD', '').strip()
        clean_name = clean_name.split('(')[0].strip()
        
        # Find matches
        matches = []
        for mapping in existing_mappings:
            # Compare with display_name
            if mapping.get('display_name'):
                ratio = fuzz.ratio(clean_name.lower(), mapping['display_name'].lower())
                if ratio >= threshold:
                    matches.append({
                        'ratio': ratio,
                        'mapping': mapping
                    })
            
            # Compare with upstox_transaction_code
            if mapping.get('upstox_transaction_code'):
                ratio = fuzz.ratio(clean_name.lower(), mapping['upstox_transaction_code'].lower())
                if ratio >= threshold:
                    matches.append({
                        'ratio': ratio,
                        'mapping': mapping
                    })
        
        # Sort by match ratio and remove duplicates
        matches.sort(key=lambda x: x['ratio'], reverse=True)
        seen = set()
        unique_matches = []
        for match in matches:
            isin = match['mapping']['isin']
            if isin not in seen:
                seen.add(isin)
                unique_matches.append(match)
        
        return unique_matches
        
    except Exception as e:
        logger.error(f"Error finding similar stocks: {str(e)}")
        return []
        
    finally:
        if client:
            client.close()

if __name__ == "__main__":
    # Example usage for incomplete data
    csv_file = "data/sample_csv/new_stocks_to_add_With_upstox_transaction_info.csv"
    success = import_mappings(csv_file, incomplete_data=True)
    sys.exit(0 if success else 1) 