from flask import Flask, request, jsonify, render_template, url_for
from pymongo import MongoClient
from bson import ObjectId
from bson.decimal128 import Decimal128
from datetime import datetime, timezone, timedelta
from decimal import Decimal
import logging
import traceback
from pathlib import Path
from werkzeug.utils import secure_filename
import csv
import io
import pandas as pd
import os
from math import ceil
from fuzzywuzzy import fuzz
from bson.json_util import dumps, loads
import json

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

class CustomJSONEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, Decimal128):
            return float(obj.to_decimal())
        if isinstance(obj, ObjectId):
            return str(obj)
        if isinstance(obj, datetime):
            return obj.isoformat()
        return super().default(obj)

# Initialize Flask
app = Flask(__name__, 
           template_folder='web/templates',
           static_folder='web/static')

# Set the custom JSON encoder
app.json_encoder = CustomJSONEncoder

# MongoDB connection
MONGODB_URL = "mongodb://localhost:27017"
DATABASE_NAME = "portfolio_tracker"

try:
    client = MongoClient(MONGODB_URL)
    db = client[DATABASE_NAME]
    stocks_collection = db.master_stocks
    portfolios_collection = db.portfolios
    logger.info(f"Connected to MongoDB. Found {stocks_collection.count_documents({})} stocks")
except Exception as e:
    logger.error(f"MongoDB connection failed: {e}")
    raise

# Routes
@app.route('/')
def home():
    """Home page with recent transactions"""
    try:
        # Fetch recent transactions
        recent_transactions = list(db.transactions.find()
                                 .sort('date', -1)
                                 .limit(5))

        # Fetch related data
        stock_ids = {t['stock_id'] for t in recent_transactions}
        portfolio_ids = {t['portfolio_id'] for t in recent_transactions if t.get('portfolio_id')}
        
        stocks = {str(s['_id']): s for s in db.stocks_collection.find({'_id': {'$in': list(map(ObjectId, stock_ids))}})}
        portfolios = {str(p['_id']): p for p in db.portfolios.find({'_id': {'$in': list(map(ObjectId, portfolio_ids))}})}
        
        # Enrich transaction data
        for transaction in recent_transactions:
            transaction['_id'] = str(transaction['_id'])
            stock = stocks.get(transaction['stock_id'], {})
            transaction['stock_name'] = stock.get('display_name', 'Unknown Stock')
            
            if transaction.get('portfolio_id'):
                portfolio = portfolios.get(transaction['portfolio_id'], {})
                transaction['portfolio_name'] = portfolio.get('name', 'Unknown Portfolio')

        return render_template('home.html', recent_transactions=recent_transactions)
    except Exception as e:
        logger.error(f"Error rendering home page: {e}")
        logger.error(traceback.format_exc())
        return jsonify({'error': 'Failed to render home page'}), 500

@app.route('/portfolios/new', methods=['GET'])
def new_portfolio():
    """Render portfolio creation page"""
    try:
        logger.info("Rendering portfolio creation page")
        return render_template('portfolio/create.html')
    except Exception as e:
        logger.error(f"Error rendering portfolio creation page: {e}")
        logger.error(traceback.format_exc())
        return jsonify({'error': 'Failed to render portfolio creation page'}), 500

@app.route('/portfolios/api/stocks/search')
def search_stocks():
    """Search stocks API endpoint"""
    try:
        query = request.args.get('query', '')
        logger.info(f"Searching stocks with query: {query}")
        
        if not query:
            return jsonify([])

        search_query = {
            "status": "active",
            "$or": [
                {"identifiers.nse_code": {"$regex": query, "$options": "i"}},
                {"display_name": {"$regex": query, "$options": "i"}}
            ]
        }

        stocks = list(stocks_collection.find(search_query))
        logger.info(f"Found {len(stocks)} matching stocks")
        
        # Log first document structure for debugging
        if stocks:
            logger.info(f"Sample document structure: {stocks[0]}")
        
        results = []
        for stock in stocks:
            try:
                # Safely access nested fields with get()
                identifiers = stock.get('identifiers', {})
                result = {
                    "id": str(stock['_id']),
                    "symbol": identifiers.get('nse_code', ''),  # Use get() with default value
                    "name": stock.get('display_name', ''),
                    "exchange_code": "NSE"
                }
                results.append(result)
            except Exception as e:
                logger.error(f"Error processing stock document: {e}")
                logger.error(f"Problematic document: {stock}")
                continue

        return jsonify(results)

    except Exception as e:
        logger.error(f"Search error: {e}")
        return jsonify({"error": str(e)}), 500

# Debug route to check template existence
@app.route('/check-template')
def check_template():
    """Debug endpoint to check template existence"""
    template_path = Path(app.template_folder) / 'portfolio' / 'create.html'
    return {
        'template_folder': app.template_folder,
        'template_exists': template_path.exists(),
        'full_path': str(template_path.absolute())
    }

@app.route('/portfolios/create', methods=['POST'])
def create_portfolio():
    """Create a new portfolio"""
    try:
        # Log the incoming request
        logger.info("Received portfolio creation request")
        
        if not request.is_json:
            logger.error("Request does not contain JSON data")
            return jsonify({'error': 'Content-Type must be application/json'}), 400

        data = request.json
        logger.info(f"Received portfolio data: {data}")

        # Validate required fields
        required_fields = ['name', 'user_id', 'base_currency', 'holdings']
        for field in required_fields:
            if field not in data:
                logger.error(f"Missing required field: {field}")
                return jsonify({'error': f"Missing required field: {field}"}), 400

        # Validate holdings data
        if not data['holdings']:
            logger.error("Portfolio must have at least one holding")
            return jsonify({'error': "Portfolio must have at least one holding"}), 400

        for holding in data['holdings']:
            required_holding_fields = ['stock_id', 'quantity', 'purchase_price', 'purchase_date']
            for field in required_holding_fields:
                if field not in holding:
                    logger.error(f"Missing required holding field: {field}")
                    return jsonify({'error': f"Missing required holding field: {field}"}), 400

        # Create portfolio document with proper MongoDB types
        try:
            current_time = datetime.now(timezone.utc)
            portfolio = {
                'id': str(ObjectId()),
                'user_id': data['user_id'],
                'name': data['name'],
                'base_currency': data['base_currency'],
                'holdings': [{
                    'stock_id': h['stock_id'],
                    'quantity': Decimal128(str(h['quantity'])),  # Convert to Decimal128
                    'purchase_price': Decimal128(str(h['purchase_price'])),  # Convert to Decimal128
                    'purchase_date': datetime.strptime(h['purchase_date'], '%Y-%m-%d').replace(tzinfo=timezone.utc)
                } for h in data['holdings']],
                'created_at': current_time,
                'updated_at': current_time
            }
            
            logger.info(f"Prepared portfolio document: {portfolio}")
            
        except ValueError as e:
            logger.error(f"Data conversion error: {e}")
            return jsonify({'error': f"Invalid data format: {str(e)}"}), 400

        # Insert into database
        try:
            result = portfolios_collection.insert_one(portfolio)
            logger.info(f"Created portfolio with ID: {result.inserted_id}")
            
            return jsonify({
                'success': True,
                'message': 'Portfolio created successfully',
                'portfolio_id': str(result.inserted_id)
            })
        except Exception as e:
            logger.error(f"Database insertion error: {e}")
            logger.error(traceback.format_exc())
            return jsonify({'error': 'Failed to save portfolio to database'}), 500

    except Exception as e:
        logger.error(f"Unexpected error in create_portfolio: {e}")
        logger.error(traceback.format_exc())
        return jsonify({'error': 'Internal server error'}), 500

@app.route('/portfolios')
def list_portfolios():
    """Display list of portfolios"""
    try:
        logger.info("Fetching portfolios list")
        
        # Fetch all portfolios from the database
        portfolios = list(portfolios_collection.find())
        logger.info(f"Found {len(portfolios)} portfolios")

        # Create a set of all stock IDs
        stock_ids = set()
        for portfolio in portfolios:
            for holding in portfolio.get('holdings', []):
                stock_ids.add(holding['stock_id'])

        # Fetch all required stocks in one query
        stocks = {
            str(stock['_id']): {
                'symbol': stock.get('identifiers', {}).get('nse_code', ''),
                'name': stock.get('display_name', '')
            }
            for stock in stocks_collection.find({'_id': {'$in': list(map(ObjectId, stock_ids))}})
        }

        # Convert ObjectId to string and add stock details
        for portfolio in portfolios:
            portfolio['_id'] = str(portfolio['_id'])
            for holding in portfolio.get('holdings', []):
                if 'quantity' in holding:
                    holding['quantity'] = float(holding['quantity'].to_decimal())
                if 'purchase_price' in holding:
                    holding['purchase_price'] = float(holding['purchase_price'].to_decimal())
                # Add stock details to holding
                stock_info = stocks.get(holding['stock_id'], {})
                holding['stock_symbol'] = stock_info.get('symbol', 'Unknown')
                holding['stock_name'] = stock_info.get('name', 'Unknown Stock')

        return render_template(
            'portfolio/list.html',
            portfolios=portfolios
        )
    except Exception as e:
        logger.error(f"Error fetching portfolios: {e}")
        logger.error(traceback.format_exc())
        return jsonify({'error': 'Failed to fetch portfolios'}), 500

@app.route('/portfolios/<portfolio_id>/edit', methods=['GET', 'POST'])
def edit_portfolio(portfolio_id):
    """Edit portfolio page"""
    try:
        if request.method == 'GET':
            logger.info(f"Fetching portfolio with ID: {portfolio_id}")
            
            # Fetch the portfolio
            portfolio = portfolios_collection.find_one({'_id': ObjectId(portfolio_id)})
            if not portfolio:
                logger.error(f"Portfolio not found: {portfolio_id}")
                return jsonify({'error': 'Portfolio not found'}), 404

            # Convert ObjectId to string
            portfolio['_id'] = str(portfolio['_id'])
            
            # Log holdings for debugging
            logger.info(f"Portfolio holdings before processing: {portfolio.get('holdings', [])}")
            
            # Create a list of ObjectIds for stock lookup
            stock_ids = [ObjectId(holding['stock_id']) for holding in portfolio.get('holdings', [])]
            logger.info(f"Looking up stocks with IDs: {stock_ids}")
            
            # Fetch all required stocks in one query
            stocks_cursor = stocks_collection.find({'_id': {'$in': stock_ids}})
            stocks = {}
            for stock in stocks_cursor:
                stock_id = str(stock['_id'])
                stocks[stock_id] = {
                    'symbol': stock.get('identifiers', {}).get('nse_code', ''),
                    'name': stock.get('display_name', '')
                }
                logger.info(f"Found stock: {stock_id} -> {stocks[stock_id]}")
            
            # Convert Decimal128 to float and add stock details for display
            for holding in portfolio.get('holdings', []):
                if 'quantity' in holding:
                    holding['quantity'] = float(holding['quantity'].to_decimal())
                if 'purchase_price' in holding:
                    holding['purchase_price'] = float(holding['purchase_price'].to_decimal())
                
                # Add stock details from our fetched stocks
                stock_info = stocks.get(holding['stock_id'])
                if stock_info:
                    holding['stock_symbol'] = stock_info['symbol']
                    holding['stock_name'] = stock_info['name']
                    logger.info(f"Mapped holding {holding['stock_id']} to stock: {stock_info}")
                else:
                    logger.error(f"No stock found for ID: {holding['stock_id']}")
                    holding['stock_symbol'] = 'Unknown'
                    holding['stock_name'] = 'Stock Not Found'

            logger.info(f"Final portfolio data: {portfolio}")
            return render_template('portfolio/edit.html', portfolio=portfolio)
        
        elif request.method == 'POST':
            data = request.json
            logger.info(f"Received edit data: {data}")

            # Validate required fields
            required_fields = ['name', 'user_id', 'base_currency', 'holdings']
            for field in required_fields:
                if field not in data:
                    return jsonify({'error': f"Missing required field: {field}"}), 400

            # Update portfolio with proper MongoDB types
            try:
                updated_portfolio = {
                    'name': data['name'],
                    'user_id': data['user_id'],
                    'base_currency': data['base_currency'],
                    'holdings': [{
                        'stock_id': h['stock_id'],
                        'quantity': Decimal128(str(h['quantity'])),
                        'purchase_price': Decimal128(str(h['purchase_price'])),
                        'purchase_date': datetime.strptime(h['purchase_date'], '%Y-%m-%d').replace(tzinfo=timezone.utc)
                    } for h in data['holdings']],
                    'updated_at': datetime.now(timezone.utc)
                }

                result = portfolios_collection.update_one(
                    {'_id': ObjectId(portfolio_id)},
                    {'$set': updated_portfolio}
                )

                if result.modified_count == 0:
                    return jsonify({'error': 'Portfolio not found or no changes made'}), 404

                return jsonify({
                    'success': True,
                    'message': 'Portfolio updated successfully'
                })

            except ValueError as e:
                logger.error(f"Data conversion error: {e}")
                return jsonify({'error': f"Invalid data format: {str(e)}"}), 400

    except Exception as e:
        logger.error(f"Error in edit_portfolio: {e}")
        logger.error(traceback.format_exc())
        return jsonify({'error': 'Internal server error'}), 500

@app.route('/transactions')
def list_transactions():
    try:
        # Get filter parameters
        portfolio_id = request.args.get('portfolio')
        date_range = request.args.get('dateRange')
        transaction_type = request.args.get('type')
        status = request.args.get('status')
        page = int(request.args.get('page', 1))
        per_page = 20

        # Build query
        query = {}
        if portfolio_id:
            query['portfolio_id'] = portfolio_id
        if transaction_type:
            query['transaction_type'] = transaction_type
        if status:
            query['status'] = status
        if date_range:
            days = int(date_range)
            query['date'] = {
                '$gte': datetime.now(timezone.utc) - timedelta(days=days)
            }

        # Get total count for pagination
        total_count = db.transactions.count_documents(query)
        total_pages = ceil(total_count / per_page)

        # Fetch transactions with pagination
        transactions = list(db.transactions.find(query)
                          .sort('date', -1)
                          .skip((page - 1) * per_page)
                          .limit(per_page))

        # Fetch related data
        stock_ids = {t['stock_id'] for t in transactions}
        portfolio_ids = {t['portfolio_id'] for t in transactions if t.get('portfolio_id')}
        
        stocks = {str(s['_id']): s for s in db.stocks_collection.find({'_id': {'$in': list(map(ObjectId, stock_ids))}})}
        portfolios = {str(p['_id']): p for p in db.portfolios.find({'_id': {'$in': list(map(ObjectId, portfolio_ids))}})}
        
        # Enrich transaction data
        for transaction in transactions:
            transaction['_id'] = str(transaction['_id'])
            stock = stocks.get(transaction['stock_id'], {})
            transaction['stock_name'] = stock.get('display_name', 'Unknown Stock')
            transaction['stock_symbol'] = stock.get('identifiers', {}).get('nse_code', '')
            
            if transaction.get('portfolio_id'):
                portfolio = portfolios.get(transaction['portfolio_id'], {})
                transaction['portfolio_name'] = portfolio.get('name', 'Unknown Portfolio')

            # Convert Decimal128 to float for template rendering
            transaction['quantity'] = float(transaction['quantity'].to_decimal())
            transaction['price'] = float(transaction['price'].to_decimal())
            transaction['total_value'] = transaction['quantity'] * transaction['price']

            # Convert charges if they exist
            if 'charges' in transaction:
                charges = transaction['charges']
                transaction['charges'] = {
                    'brokerage': float(charges.get('brokerage', Decimal128('0')).to_decimal()),
                    'gst': float(charges.get('gst', Decimal128('0')).to_decimal()),
                    'stt': float(charges.get('stt', Decimal128('0')).to_decimal()),
                    'stamp_duty': float(charges.get('stamp_duty', Decimal128('0')).to_decimal()),
                    'exchange_charges': float(charges.get('exchange_charges', Decimal128('0')).to_decimal()),
                    'sebi_charges': float(charges.get('sebi_charges', Decimal128('0')).to_decimal())
                }

        # Get all portfolios for filter dropdown
        all_portfolios = list(db.portfolios.find({}, {'name': 1}))

        return render_template('transactions/list.html',
                             transactions=transactions,
                             portfolios=all_portfolios,
                             page=page,
                             total_pages=total_pages,
                             max=max,
                             min=min)

    except Exception as e:
        logger.error(f"Error in list_transactions: {e}")
        logger.error(traceback.format_exc())
        return jsonify({'error': 'Failed to load transactions'}), 500

@app.route('/transactions/new', methods=['GET', 'POST'])
def new_transaction():
    """Create new transaction"""
    try:
        if request.method == 'GET':
            portfolios = list(db.portfolios.find())
            brokers = list(db.brokers.find({'status': 'ACTIVE'}))
            return render_template('transactions/create.html', 
                                portfolios=portfolios,
                                brokers=brokers)
        
        elif request.method == 'POST':
            data = request.json
            
            # Validate required fields
            required_fields = ['portfolio_id', 'stock_id', 'transaction_type', 
                             'quantity', 'price', 'date', 'broker']
            for field in required_fields:
                if field not in data:
                    return jsonify({'error': f'Missing required field: {field}'}), 400

            # Create transaction document
            transaction = {
                'id': str(ObjectId()),
                'portfolio_id': data['portfolio_id'],
                'stock_id': data['stock_id'],
                'transaction_type': data['transaction_type'],
                'quantity': Decimal128(str(data['quantity'])),
                'price': Decimal128(str(data['price'])),
                'date': datetime.strptime(data['date'], '%Y-%m-%d').replace(tzinfo=timezone.utc),
                'broker': {
                    'name': data['broker']['name'],
                    'transaction_id': data['broker'].get('transaction_id', '')
                },
                'status': 'COMPLETED',
                'charges': {
                    'brokerage': Decimal128(str(data['charges'].get('brokerage', 0))),
                    'gst': Decimal128(str(data['charges'].get('gst', 0))),
                    'stt': Decimal128(str(data['charges'].get('stt', 0))),
                    'stamp_duty': Decimal128(str(data['charges'].get('stamp_duty', 0))),
                    'exchange_charges': Decimal128(str(data['charges'].get('exchange_charges', 0))),
                    'sebi_charges': Decimal128(str(data['charges'].get('sebi_charges', 0)))
                },
                'notes': data.get('notes', ''),
                'created_at': datetime.now(timezone.utc),
                'updated_at': datetime.now(timezone.utc)
            }

            # Insert transaction
            result = db.transactions.insert_one(transaction)
            
            # Update portfolio holdings
            portfolio_manager = PortfolioManager(db)
            try:
                portfolio_manager.process_transaction(transaction)
            except Exception as e:
                logger.error(f"Error processing transaction: {e}")
                # Log error but continue with the response
                return jsonify({
                    'success': True,
                    'transaction_id': str(result.inserted_id),
                    'warning': 'Transaction saved but portfolio update failed'
                })

            return jsonify({
                'success': True,
                'transaction_id': str(result.inserted_id)
            })

    except Exception as e:
        logger.error(f"Error in new_transaction: {e}")
        return jsonify({'error': str(e)}), 500

class PortfolioManager:
    def __init__(self, db):
        self.db = db

    def update_portfolio_holdings(self, portfolio_id, transaction):
        """Update portfolio holdings based on a transaction"""
        try:
            portfolio = self.db.portfolios.find_one({'_id': ObjectId(portfolio_id)})
            if not portfolio:
                raise ValueError(f"Portfolio not found: {portfolio_id}")

            # Fetch stock details first
            stock = self.db.stocks_collection.find_one({'_id': ObjectId(transaction['stock_id'])})
            if not stock:
                raise ValueError(f"Stock not found: {transaction['stock_id']}")

            holdings = portfolio.get('holdings', [])
            stock_id = transaction['stock_id']
            quantity = float(transaction['quantity'].to_decimal())
            price = float(transaction['price'].to_decimal())
            transaction_date = transaction['date']
            
            # Find existing holding for this stock
            existing_holding = next(
                (h for h in holdings if h['stock_id'] == stock_id),
                None
            )

            if transaction['transaction_type'] == 'BUY':
                if existing_holding:
                    # Update existing holding
                    new_quantity = float(existing_holding['quantity'].to_decimal()) + quantity
                    total_value = (float(existing_holding['quantity'].to_decimal()) * 
                                 float(existing_holding['average_price'].to_decimal()) +
                                 quantity * price)
                    new_avg_price = total_value / new_quantity
                    
                    existing_holding.update({
                        'quantity': Decimal128(str(new_quantity)),
                        'average_price': Decimal128(str(new_avg_price)),
                        'last_transaction_date': transaction_date,
                        'updated_at': datetime.now(timezone.utc),
                        'stock_name': stock['display_name'],  # Add stock details
                        'stock_symbol': stock.get('identifiers', {}).get('nse_code', '')
                    })
                else:
                    # Create new holding
                    holdings.append({
                        'stock_id': stock_id,
                        'stock_name': stock['display_name'],  # Add stock details
                        'stock_symbol': stock.get('identifiers', {}).get('nse_code', ''),
                        'quantity': Decimal128(str(quantity)),
                        'average_price': Decimal128(str(price)),
                        'purchase_price': Decimal128(str(price)),
                        'purchase_date': transaction_date,
                        'last_transaction_date': transaction_date,
                        'created_at': datetime.now(timezone.utc),
                        'updated_at': datetime.now(timezone.utc)
                    })
            
            elif transaction['transaction_type'] == 'SELL':
                if not existing_holding:
                    # For first-time sells, create a holding with negative quantity
                    holdings.append({
                        'stock_id': stock_id,
                        'stock_name': stock['display_name'],  # Add stock details
                        'stock_symbol': stock.get('identifiers', {}).get('nse_code', ''),
                        'quantity': Decimal128(str(-quantity)),
                        'average_price': Decimal128(str(price)),
                        'purchase_price': Decimal128(str(price)),
                        'purchase_date': transaction_date,
                        'last_transaction_date': transaction_date,
                        'created_at': datetime.now(timezone.utc),
                        'updated_at': datetime.now(timezone.utc),
                        'notes': 'Historical position - started tracking with sell transaction'
                    })
                else:
                    current_quantity = float(existing_holding['quantity'].to_decimal())
                    new_quantity = current_quantity - quantity
                    
                    if new_quantity == 0:
                        # Remove holding if quantity becomes zero
                        holdings = [h for h in holdings if h['stock_id'] != stock_id]
                    else:
                        # Update existing holding
                        existing_holding.update({
                            'quantity': Decimal128(str(new_quantity)),
                            'last_transaction_date': transaction_date,
                            'updated_at': datetime.now(timezone.utc),
                            'stock_name': stock['display_name'],  # Add stock details
                            'stock_symbol': stock.get('identifiers', {}).get('nse_code', '')
                        })

            # Update portfolio
            self.db.portfolios.update_one(
                {'_id': ObjectId(portfolio_id)},
                {
                    '$set': {
                        'holdings': holdings,
                        'updated_at': datetime.now(timezone.utc)
                    }
                }
            )

            return True

        except Exception as e:
            logger.error(f"Error updating portfolio holdings: {e}")
            raise

    def process_transaction(self, transaction):
        """Process a transaction and update portfolio holdings"""
        try:
            if not transaction.get('portfolio_id'):
                return False

            return self.update_portfolio_holdings(
                transaction['portfolio_id'],
                transaction
            )

        except Exception as e:
            logger.error(f"Error processing transaction: {e}")
            raise

def clean_price(price_str):
    """Clean price string by removing '?' and commas"""
    if isinstance(price_str, str):
        # Remove the '?' symbol and commas
        return float(price_str.replace('?', '').replace(',', ''))
    return float(price_str)

@app.route('/transactions/import/upstox', methods=['POST'])
def import_upstox_transactions():
    try:
        if 'file' not in request.files:
            return jsonify({'error': 'No file provided'}), 400
            
        file = request.files['file']
        portfolio_id = request.form.get('portfolio_id')
        
        if file.filename == '':
            return jsonify({'error': 'No file selected'}), 400

        # Handle both CSV and Excel files
        if file.filename.endswith(('.xlsx', '.xls')):
            df = pd.read_excel(file)
        elif file.filename.endswith('.csv'):
            file_content = file.read().decode('utf-8')
            df = pd.read_csv(io.StringIO(file_content))
        else:
            return jsonify({'error': 'File must be CSV or Excel'}), 400

        # Convert DataFrame to list of transactions
        transactions = []
        for _, row in df.iterrows():
            try:
                transaction = {
                    'company_name': str(row['Company']),
                    'scrip_code': str(row['Scrip Code']),
                    'transaction_type': 'BUY' if str(row['Side']).upper() == 'BUY' else 'SELL',
                    'quantity': float(row['Quantity']),
                    'price': clean_price(row['Price']),
                    'date': datetime.strptime(str(row['Date']), '%d-%m-%Y').replace(tzinfo=timezone.utc),
                    'broker_transaction_id': str(row['Trade Num'])
                }
                transactions.append(transaction)
            except Exception as e:
                logger.error(f"Error processing row: {row}")
                logger.error(f"Error details: {e}")
                continue

        if not transactions:
            return jsonify({'error': 'No valid transactions found in file'}), 400

        # Store all transactions in temp collection first
        transaction_ids = []
        for transaction in transactions:
            # Create a complete transaction document that satisfies the schema
            temp_transaction = {
                'id': str(ObjectId()),
                'company_name': transaction['company_name'],
                'scrip_code': transaction['scrip_code'],
                'transaction_type': transaction['transaction_type'],
                'quantity': transaction['quantity'],
                'price': transaction['price'],
                'date': transaction['date'],
                'broker': {
                    'name': 'UPSTOX',
                    'transaction_id': transaction.get('broker_transaction_id', '')
                },
                'status': 'PENDING',
                'created_at': datetime.now(timezone.utc),
                'updated_at': datetime.now(timezone.utc),
                'stock_id': None  # Will be updated after mapping
            }
            
            db.temp_transactions.insert_one(temp_transaction)
            transaction_ids.append(temp_transaction['id'])

        # Process and find potential matches
        importer = UpstoxTransactionImporter(db)
        validation_results = importer.validate_transactions(transactions)
        
        # Always show mapping page for verification
        unmatched_data = []
        for item in validation_results.get('unmatched', []) + validation_results.get('valid', []):
            if isinstance(item, dict):
                transaction = item.get('transaction', {})
                potential_matches = item.get('potential_matches', [])
                if transaction:
                    unmatched_data.append({
                        'transaction': transaction,
                        'potential_matches': potential_matches or []  # Ensure list exists
                    })

        # Return JSON response for AJAX request
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return jsonify({
                'success': True,
                'redirect': url_for('view_stock_mapping',  # Updated function name
                                  transaction_ids=transaction_ids,
                                  portfolio_id=portfolio_id)
            })
        
        # Regular form submit - return template
        return render_template(
            'transactions/map_stocks.html',
            unmatched_transactions=unmatched_data,
            transaction_ids=transaction_ids,
            portfolio_id=portfolio_id,
            total_transactions=len(transactions),
            unmatched_count=len(unmatched_data)
        )
        
    except Exception as e:
        logger.error(f"Error importing transactions: {e}")
        logger.error(traceback.format_exc())
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return jsonify({'error': str(e)}), 500
        return render_template('error.html', error=str(e)), 500

@app.route('/transactions/import', methods=['GET'])
def import_transactions():
    """Render import page"""
    try:
        portfolios = list(db.portfolios.find({}, {'name': 1}))
        return render_template('transactions/import.html', portfolios=portfolios)
    except Exception as e:
        logger.error(f"Error rendering import page: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/transactions/assign-portfolio', methods=['POST'])
def assign_portfolio():
    try:
        data = request.json
        portfolio_id = data.get('portfolio_id')
        transaction_ids = data.get('transaction_ids', [])

        if not portfolio_id or not transaction_ids:
            return jsonify({'error': 'Portfolio ID and transaction IDs are required'}), 400

        portfolio_manager = PortfolioManager(db)
        successful_count = 0
        
        # Move transactions from temp collection to main collection
        temp_transactions = list(db.temp_transactions.find({
            'id': {'$in': transaction_ids}
        }))

        for transaction in temp_transactions:
            try:
                transaction['portfolio_id'] = portfolio_id
                transaction['status'] = 'COMPLETED'
                transaction['updated_at'] = datetime.now(timezone.utc)
                
                # Remove _id before insertion
                transaction.pop('_id', None)
                
                # Insert into main transactions collection
                db.transactions.insert_one(transaction)
                
                # Update portfolio holdings
                portfolio_manager.process_transaction(transaction)
                
                # Remove from temp collection
                db.temp_transactions.delete_one({'id': transaction['id']})
                
                successful_count += 1
                
            except Exception as e:
                logger.error(f"Error processing transaction {transaction['id']}: {e}")
                # Log error and continue with next transaction

        return jsonify({
            'message': f'Successfully assigned {successful_count} transactions to portfolio',
            'count': successful_count
        })

    except Exception as e:
        logger.error(f"Error in assign_portfolio: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/brokers', methods=['GET', 'POST'])
def manage_brokers():
    if request.method == 'POST':
        data = request.json
        broker = {
            'name': data['name'],
            'api_settings': {
                'api_key': data.get('api_key', ''),
                'api_secret': data.get('api_secret', ''),
                'base_url': data.get('base_url', '')
            },
            'charge_structure': {
                'brokerage_percentage': Decimal128(str(data.get('brokerage_percentage', 0))),
                'gst_percentage': Decimal128(str(data.get('gst_percentage', 0.18))),
                'stt_percentage': Decimal128(str(data.get('stt_percentage', 0.001))),
                'stamp_duty_percentage': Decimal128(str(data.get('stamp_duty_percentage', 0.00015))),
                'exchange_charges_percentage': Decimal128(str(data.get('exchange_charges_percentage', 0.0000345))),
                'sebi_charges_percentage': Decimal128(str(data.get('sebi_charges_percentage', 0.0000001)))
            },
            'status': 'ACTIVE'
        }
        
        db.brokers.insert_one(broker)
        return jsonify({'message': 'Broker added successfully'})
        
    brokers = list(db.brokers.find())
    return render_template('brokers/list.html', brokers=brokers)

@app.route('/brokers/<broker_id>', methods=['PUT', 'DELETE'])
def manage_broker(broker_id):
    if request.method == 'DELETE':
        db.brokers.delete_one({'_id': ObjectId(broker_id)})
        return jsonify({'message': 'Broker deleted successfully'})
    
    data = request.json
    db.brokers.update_one(
        {'_id': ObjectId(broker_id)},
        {'$set': data}
    )
    return jsonify({'message': 'Broker updated successfully'})

class UpstoxTransactionImporter:
    def __init__(self, db):
        self.db = db
        self.portfolio_manager = PortfolioManager(db)

    def clean_company_name(self, name):
        """Clean company name for better matching"""
        if not name:
            return ""
            
        # Common replacements
        replacements = {
            ' LIMITED': ' LTD',
            ' LTD.': ' LTD',
            ' INDUSTRIES': ' IND',
            ' INDUSTRY': ' IND',
            '&': 'AND',
            '.': '',
            ',': '',
            '-': ' ',
            '  ': ' '  # Remove double spaces
        }
        
        # Convert to uppercase and remove extra spaces
        name = name.upper().strip()
        
        # Apply replacements
        for old, new in replacements.items():
            name = name.replace(old, new)
        
        # Remove common suffixes if they exist as whole words
        suffixes = [' LTD', ' LIMITED', ' IND', ' INDUSTRIES', ' PRIVATE', ' PVT']
        for suffix in suffixes:
            if name.endswith(suffix):
                name = name[:-len(suffix)]
        
        # Remove extra whitespace and return
        return ' '.join(name.split())

    def find_matching_stock(self, company_name, scrip_code):
        """Find matching stock using multiple criteria"""
        try:
            logger.info(f"Searching for stock: {company_name} ({scrip_code})")
            
            # Clean the input company name
            cleaned_company = self.clean_company_name(company_name)
            logger.info(f"Cleaned company name: {cleaned_company}")
            
            # Try exact matches first with scrip code
            stock = self.db.stocks_collection.find_one({
                '$or': [
                    {'identifiers.nse_code': scrip_code},
                    {'identifiers.bse_code': scrip_code}
                ]
            })
            
            if stock:
                logger.info(f"Found stock by scrip code: {scrip_code}")
                return stock

            # Get all stocks for fuzzy matching
            stocks = list(self.db.stocks_collection.find())
            best_match = None
            highest_ratio = 0
            
            for stock in stocks:
                # Clean the database stock name
                db_name = stock.get('display_name', '')
                db_name_clean = self.clean_company_name(db_name)
                
                # Try different matching techniques
                ratios = [
                    fuzz.ratio(cleaned_company, db_name_clean),
                    fuzz.partial_ratio(cleaned_company, db_name_clean),
                    fuzz.token_sort_ratio(cleaned_company, db_name_clean),
                    fuzz.token_set_ratio(cleaned_company, db_name_clean)
                ]
                
                # Get the highest ratio from all matching techniques
                max_ratio = max(ratios)
                
                # Log matching attempts for debugging
                logger.debug(f"Matching '{cleaned_company}' with '{db_name_clean}': {max_ratio}")
                
                if max_ratio > highest_ratio:
                    highest_ratio = max_ratio
                    best_match = stock
                    logger.info(f"New best match: '{db_name}' with ratio {max_ratio}")

            # Use a threshold of 80 for matching
            if highest_ratio >= 80:
                logger.info(f"Found fuzzy match: '{best_match['display_name']}' with ratio {highest_ratio}")
                return best_match
            
            # If no match found, log the failure
            logger.warning(f"No match found for '{company_name}' (cleaned: '{cleaned_company}')")
            
            # Instead of returning None, raise an exception
            raise ValueError(f"No matching stock found for {company_name} ({scrip_code})")

        except Exception as e:
            logger.error(f"Error in find_matching_stock: {e}")
            raise

    def find_potential_matches(self, company_name, scrip_code, limit=5):
        """Find potential stock matches from database and return top 5 with match scores"""
        try:
            cleaned_company = self.clean_company_name(company_name)
            potential_matches = []
            
            # Get all stocks from database without status filter first
            database_stocks = list(db.stocks_collection.find(
                {},  # Remove status filter
                {
                    'display_name': 1,
                    'identifiers.nse_code': 1,
                    '_id': 1,
                    'status': 1  # Add status to check what we have
                }
            ))
            
            logger.info(f"Found {len(database_stocks)} total stocks in database")
            if len(database_stocks) > 0:
                # Log a sample stock to see the structure
                logger.info(f"Sample stock: {database_stocks[0]}")
            else:
                logger.error("No stocks found in database!")
            
            for stock in database_stocks:
                db_name = stock.get('display_name', '')
                db_symbol = stock.get('identifiers', {}).get('nse_code', '')
                db_name_clean = self.clean_company_name(db_name)
                
                # Calculate different match ratios
                name_ratio = fuzz.ratio(cleaned_company, db_name_clean)
                partial_ratio = fuzz.partial_ratio(cleaned_company, db_name_clean)
                sort_ratio = fuzz.token_sort_ratio(cleaned_company, db_name_clean)
                set_ratio = fuzz.token_set_ratio(cleaned_company, db_name_clean)
                
                # Get the highest ratio
                max_ratio = max(name_ratio, partial_ratio, sort_ratio, set_ratio)
                
                # Log all potential matches for debugging
                logger.debug(f"Comparing '{cleaned_company}' with '{db_name_clean}': {max_ratio}%")
                
                # If ratio is above threshold, add to potential matches
                if max_ratio > 50:  # Adjust threshold as needed
                    match_info = {
                        'id': str(stock['_id']),
                        'name': f"{stock['display_name']} ({db_symbol}) - {max_ratio}% match",
                        'display_name': stock['display_name'],
                        'symbol': db_symbol,
                        'score': max_ratio
                    }
                    potential_matches.append(match_info)
                    logger.info(f"Found match: {match_info['name']} with score {max_ratio}")
            
            # Sort by match score and get top matches
            sorted_matches = sorted(
                potential_matches,
                key=lambda x: x['score'],
                reverse=True
            )[:limit]
            
            logger.info(f"Top {len(sorted_matches)} matches for '{company_name}': {sorted_matches}")
            
            return sorted_matches
            
        except Exception as e:
            logger.error(f"Error finding potential matches: {e}")
            logger.error(traceback.format_exc())
            return []

    def validate_transactions(self, transactions):
        """Validate transactions and identify unmatched stocks"""
        validation_results = {
            'valid': [],
            'unmatched': [],
            'invalid': [],
            'summary': {
                'total': len(transactions),
                'valid': 0,
                'unmatched': 0,
                'invalid': 0,
                'errors': {},
                'matches': {}
            }
        }

        for transaction in transactions:
            try:
                # Try exact match first
                stock = self.find_matching_stock(
                    transaction['company_name'],
                    transaction['scrip_code']
                )
                
                if stock:
                    # Process matched stock
                    transaction['stock_id'] = str(stock['_id'])
                    transaction['stock_name'] = stock['display_name']
                    validation_results['valid'].append(transaction)
                    validation_results['summary']['valid'] += 1
                else:
                    # Find potential matches
                    potential_matches = self.find_potential_matches(
                        transaction['company_name'],
                        transaction['scrip_code']
                    )
                    
                    # Add to unmatched with potential matches
                    validation_results['unmatched'].append({
                        'transaction': transaction,
                        'potential_matches': potential_matches
                    })
                    validation_results['summary']['unmatched'] += 1

            except Exception as e:
                error_msg = str(e)
                validation_results['invalid'].append({
                    'transaction': transaction,
                    'error': error_msg
                })
                validation_results['summary']['invalid'] += 1
                validation_results['summary']['errors'][error_msg] = \
                    validation_results['summary']['errors'].get(error_msg, 0) + 1

        return validation_results

    def import_transactions(self, file_path, portfolio_id=None):
        try:
            # Read CSV file
            df = pd.read_csv(file_path)
            
            # Prepare transactions list
            transactions = []
            for _, row in df.iterrows():
                price = self.clean_amount(row['Price'])
                transaction = {
                    'company_name': row['Company'],
                    'scrip_code': str(row['Scrip Code']),
                    'transaction_type': 'BUY' if row['Side'].upper() == 'BUY' else 'SELL',
                    'quantity': float(row['Quantity']),
                    'price': price,
                    'date': datetime.strptime(row['Date'], '%d-%m-%Y').replace(tzinfo=timezone.utc),
                    'broker_transaction_id': str(row['Trade Num']),
                    'charges': {
                        'brokerage': Decimal128('0'),
                        'gst': Decimal128('0'),
                        'stt': Decimal128('0'),
                        'stamp_duty': Decimal128('0'),
                        'exchange_charges': Decimal128('0'),
                        'sebi_charges': Decimal128('0')
                    }
                }
                transactions.append(transaction)

            # Validate transactions
            validation_results = self.validate_transactions(transactions)
            
            if not validation_results['valid']:
                return {
                    'success': False,
                    'message': 'No valid transactions found',
                    'summary': validation_results['summary'],
                    'invalid_transactions': validation_results['invalid']
                }

            # Process valid transactions
            processed_results = {
                'success': True,
                'processed': 0,
                'failed': 0,
                'errors': [],
                'summary': validation_results['summary']
            }

            for transaction in validation_results['valid']:
                try:
                    # Create transaction document with all required fields
                    transaction_doc = {
                        'id': str(ObjectId()),
                        'portfolio_id': portfolio_id,
                        'stock_id': transaction['stock_id'],
                        'transaction_type': transaction['transaction_type'],
                        'quantity': Decimal128(str(transaction['quantity'])),
                        'price': Decimal128(str(transaction['price'])),
                        'date': transaction['date'],
                        'broker': {
                            'name': 'UPSTOX',
                            'transaction_id': transaction['broker_transaction_id']
                        },
                        'charges': transaction['charges'],
                        'status': 'COMPLETED' if portfolio_id else 'PENDING',
                        'created_at': datetime.now(timezone.utc),
                        'updated_at': datetime.now(timezone.utc)
                    }

                    # Insert transaction
                    if portfolio_id:
                        self.db.transactions.insert_one(transaction_doc)
                        self.portfolio_manager.process_transaction(transaction_doc)
                    else:
                        self.db.temp_transactions.insert_one(transaction_doc)
                    
                    processed_results['processed'] += 1

                except Exception as e:
                    processed_results['failed'] += 1
                    processed_results['errors'].append({
                        'transaction': transaction,
                        'error': str(e)
                    })
                    logger.error(f"Error processing transaction for {transaction['company_name']}: {e}")

            return processed_results

        except Exception as e:
            logger.error(f"Error importing transactions: {e}")
            raise

    def clean_amount(self, amount):
        if isinstance(amount, str):
            # Remove the '?' symbol and commas, then convert to float
            return float(amount.replace('?', '').replace(',', ''))
        return float(amount)

@app.route('/transactions/import/map-stocks', methods=['POST'])
def map_stocks():
    """Handle stock mapping for unmatched transactions"""
    try:
        data = request.json
        mappings = data.get('mappings', [])
        temp_transaction_ids = data.get('transaction_ids', [])
        
        # Update temporary transactions with mapped stocks
        for mapping in mappings:
            db.temp_transactions.update_many(
                {'company_name': mapping['company_name']},
                {'$set': {
                    'stock_id': mapping['selected_stock_id'],
                    'stock_name': mapping['selected_stock_name']
                }}
            )
        
        return jsonify({
            'success': True,
            'message': f'Successfully mapped {len(mappings)} stocks'
        })
        
    except Exception as e:
        logger.error(f"Error mapping stocks: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/transactions/import/confirm', methods=['POST'])
def confirm_import():
    """Confirm and process mapped transactions"""
    try:
        data = request.json
        logger.info(f"Received confirmation data: {data}")  # Debug log
        
        portfolio_id = data.get('portfolio_id')
        mappings = data.get('mappings', [])
        
        if not portfolio_id or not mappings:
            logger.error("Missing required data")  # Debug log
            return jsonify({'error': 'Missing required data'}), 400

        # Process transactions
        processed = 0
        errors = []
        portfolio_manager = PortfolioManager(db)
        
        for mapping in mappings:
            try:
                # Get transaction from temp collection
                temp_transaction = db.temp_transactions.find_one({
                    'id': mapping.get('transaction_id')  # Use transaction_id from mapping
                })
                
                if not temp_transaction:
                    logger.error(f"Transaction not found: {mapping.get('transaction_id')}")
                    continue

                # Create final transaction document
                transaction = {
                    'portfolio_id': portfolio_id,
                    'stock_id': mapping.get('selected_stock_id'),
                    'transaction_type': temp_transaction['transaction_type'],
                    'quantity': Decimal128(str(temp_transaction['quantity'])),
                    'price': Decimal128(str(temp_transaction['price'])),
                    'date': temp_transaction['date'],
                    'status': 'COMPLETED',
                    'broker': temp_transaction['broker'],
                    'created_at': datetime.now(timezone.utc),
                    'updated_at': datetime.now(timezone.utc)
                }

                # Validate required fields
                if not all([transaction['stock_id'], transaction['portfolio_id']]):
                    raise ValueError("Missing stock_id or portfolio_id")

                # Insert into main collection
                result = db.transactions.insert_one(transaction)
                
                # Update portfolio
                if result.inserted_id:
                    portfolio_manager.process_transaction(transaction)
                    processed += 1
                    # Remove from temp collection
                    db.temp_transactions.delete_one({'_id': temp_transaction['_id']})
                
            except Exception as e:
                logger.error(f"Error processing mapping: {e}")
                errors.append({
                    'transaction_id': mapping.get('transaction_id'),
                    'error': str(e)
                })
        
        if processed == 0:
            return jsonify({'error': 'No transactions were processed', 'details': errors}), 400

        return jsonify({
            'success': True,
            'processed': processed,
            'errors': errors
        })
        
    except Exception as e:
        logger.error(f"Error confirming import: {e}")
        logger.error(traceback.format_exc())
        return jsonify({'error': str(e)}), 500

def process_matched_transactions(transactions, portfolio_id):
    """Process transactions that have been matched to stocks"""
    try:
        processed = 0
        errors = []
        portfolio_manager = PortfolioManager(db)

        for transaction in transactions:
            try:
                # Create transaction document
                transaction_doc = {
                    'id': str(ObjectId()),
                    'portfolio_id': portfolio_id,
                    'stock_id': transaction['stock_id'],
                    'transaction_type': transaction['transaction_type'],
                    'quantity': Decimal128(str(transaction['quantity'])),
                    'price': Decimal128(str(transaction['price'])),
                    'date': transaction['date'],
                    'status': 'COMPLETED',
                    'broker': {'name': 'UPSTOX', 'transaction_id': transaction.get('broker_transaction_id', '')},
                    'charges': transaction.get('charges', {}),
                    'created_at': datetime.now(timezone.utc),
                    'updated_at': datetime.now(timezone.utc)
                }

                # Insert and process
                db.transactions.insert_one(transaction_doc)
                portfolio_manager.process_transaction(transaction_doc)
                processed += 1

            except Exception as e:
                errors.append({'transaction': transaction, 'error': str(e)})

        return jsonify({
            'success': True,
            'processed': processed,
            'errors': errors
        })

    except Exception as e:
        logger.error(f"Error processing transactions: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/transactions/view-stock-mapping', methods=['GET'])
def view_stock_mapping():
    """Display stock mapping page"""
    try:
        transaction_ids = request.args.getlist('transaction_ids')
        portfolio_id = request.args.get('portfolio_id')

        if not transaction_ids or not portfolio_id:
            return jsonify({'error': 'Missing required parameters'}), 400

        # Fetch transactions from temp collection
        temp_transactions = list(db.temp_transactions.find({
            'id': {'$in': transaction_ids}
        }))

        # Get potential matches for each transaction
        importer = UpstoxTransactionImporter(db)
        unmatched_data = []
        
        for transaction in temp_transactions:
            potential_matches = importer.find_potential_matches(
                transaction['company_name'],
                transaction['scrip_code']
            )
            
            logger.info(f"Potential matches for {transaction['company_name']}: {potential_matches}")
            
            unmatched_data.append({
                'transaction': transaction,
                'potential_matches': potential_matches
            })

        return render_template(
            'transactions/map_stocks.html',
            unmatched_transactions=unmatched_data,
            transaction_ids=transaction_ids,
            portfolio_id=portfolio_id,
            total_transactions=len(temp_transactions),
            unmatched_count=len(unmatched_data)
        )

    except Exception as e:
        logger.error(f"Error displaying stock mapping page: {e}")
        logger.error(traceback.format_exc())
        return jsonify({'error': str(e)}), 500

if __name__ == '__main__':
    logger.info(f"Starting Flask application...")
    logger.info(f"Template folder: {app.template_folder}")
    logger.info(f"Static folder: {app.static_folder}")
    app.run(debug=True, port=8000) 