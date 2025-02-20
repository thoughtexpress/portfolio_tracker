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

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Initialize Flask with correct template and static paths
app = Flask(__name__, 
    template_folder='web/templates',
    static_folder='web/static',
    static_url_path='/static'
)

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
                        'updated_at': datetime.now(timezone.utc)
                    })
                else:
                    # Create new holding
                    holdings.append({
                        'stock_id': stock_id,
                        'quantity': Decimal128(str(quantity)),
                        'average_price': Decimal128(str(price)),
                        'purchase_price': Decimal128(str(price)),  # Added for schema validation
                        'purchase_date': transaction_date,  # Added for schema validation
                        'last_transaction_date': transaction_date,
                        'created_at': datetime.now(timezone.utc),
                        'updated_at': datetime.now(timezone.utc)
                    })
            
            elif transaction['transaction_type'] == 'SELL':
                if not existing_holding:
                    raise ValueError(f"Cannot sell stock {stock_id} - no existing holding found")
                
                current_quantity = float(existing_holding['quantity'].to_decimal())
                new_quantity = current_quantity - quantity
                
                if new_quantity < 0:
                    raise ValueError(f"Insufficient quantity for sale. Available: {current_quantity}, Required: {quantity}")
                
                if new_quantity == 0:
                    # Remove holding if quantity becomes zero
                    holdings = [h for h in holdings if h['stock_id'] != stock_id]
                else:
                    # Update existing holding
                    existing_holding.update({
                        'quantity': Decimal128(str(new_quantity)),
                        'last_transaction_date': transaction_date,
                        'updated_at': datetime.now(timezone.utc)
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

@app.route('/transactions/import/upstox', methods=['POST'])
def import_upstox_transactions():
    """Import transactions from Upstox CSV"""
    try:
        if 'file' not in request.files:
            return jsonify({'error': 'No file provided'}), 400
            
        file = request.files['file']
        portfolio_id = request.form.get('portfolio_id')
        
        if file.filename == '':
            return jsonify({'error': 'No file selected'}), 400

        if not file.filename.endswith('.csv'):
            return jsonify({'error': 'File must be a CSV'}), 400

        # Create upload folder if it doesn't exist
        upload_folder = os.path.join(app.root_path, 'uploads')
        if not os.path.exists(upload_folder):
            os.makedirs(upload_folder)

        # Save file temporarily
        temp_path = os.path.join(upload_folder, secure_filename(file.filename))
        file.save(temp_path)

        try:
            # Import transactions
            importer = UpstoxTransactionImporter(db)
            results = importer.import_transactions(temp_path, portfolio_id)
            
            return jsonify(results)

        finally:
            # Clean up temporary file
            if os.path.exists(temp_path):
                os.remove(temp_path)

    except Exception as e:
        logger.error(f"Error in import_upstox_transactions: {e}")
        logger.error(traceback.format_exc())
        return jsonify({'error': str(e)}), 500

# Update the import template route to include portfolios
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
        # Common replacements
        replacements = {
            'LIMITED': 'LTD',
            'LTD.': 'LTD',
            'INDUSTRIES': 'IND',
            'INDUSTRY': 'IND',
            '&': 'AND',
            '.': '',
            ',': '',
        }
        
        # Convert to uppercase and remove extra spaces
        name = name.upper().strip()
        
        # Apply replacements
        for old, new in replacements.items():
            name = name.replace(old, new)
        
        # Remove common suffixes
        suffixes = [' LTD', ' LIMITED', ' IND']
        for suffix in suffixes:
            if name.endswith(suffix):
                name = name[:-len(suffix)]
        
        # Remove extra whitespace
        return ' '.join(name.split())

    def find_matching_stock(self, company_name, scrip_code):
        """Find matching stock using multiple criteria"""
        try:
            # Clean the input company name
            cleaned_company = self.clean_company_name(company_name)
            
            # Try exact matches first
            stock = self.db.stocks_collection.find_one({
                '$or': [
                    {'identifiers.nse_code': scrip_code},
                    {'identifiers.bse_code': scrip_code}
                ]
            })
            
            if stock:
                logger.info(f"Found stock by scrip code: {scrip_code}")
                return stock

            # Get all stocks and try different matching strategies
            stocks = list(self.db.stocks_collection.find({}))
            best_match = None
            highest_ratio = 0
            
            for stock in stocks:
                # Clean the database stock name
                db_name_clean = self.clean_company_name(stock['display_name'])
                
                # Try different matching techniques
                ratios = [
                    fuzz.ratio(cleaned_company, db_name_clean),  # Simple ratio
                    fuzz.partial_ratio(cleaned_company, db_name_clean),  # Partial ratio
                    fuzz.token_sort_ratio(cleaned_company, db_name_clean),  # Token sort ratio
                    fuzz.token_set_ratio(cleaned_company, db_name_clean)  # Token set ratio
                ]
                
                # Get the highest ratio from all matching techniques
                max_ratio = max(ratios)
                
                if max_ratio > highest_ratio:
                    highest_ratio = max_ratio
                    best_match = stock

                # Log matching attempts for debugging
                logger.debug(f"Matching '{company_name}' with '{stock['display_name']}': {max_ratio}")

            # Use a threshold of 80 for matching
            if highest_ratio >= 80:
                logger.info(f"Found fuzzy match for '{company_name}': '{best_match['display_name']}' with ratio {highest_ratio}")
                return best_match
            
            # If no match found, log the failure
            logger.warning(f"No match found for '{company_name}' (cleaned: '{cleaned_company}')")
            return None

        except Exception as e:
            logger.error(f"Error in find_matching_stock: {e}")
            raise

    def create_name_variations(self, name):
        """Create common variations of company names"""
        variations = {name}
        
        # Add variation without 'LIMITED'/'LTD'
        for suffix in [' LIMITED', ' LTD', ' LTD.']:
            if name.upper().endswith(suffix):
                variations.add(name[:-len(suffix)])
        
        # Add variations with '&' and 'AND'
        if ' & ' in name:
            variations.add(name.replace(' & ', ' AND '))
        if ' AND ' in name:
            variations.add(name.replace(' AND ', ' & '))
        
        # Add variations with 'INDUSTRIES' and 'IND'
        if ' INDUSTRIES ' in name.upper():
            variations.add(name.upper().replace(' INDUSTRIES ', ' IND '))
        if ' IND ' in name.upper():
            variations.add(name.upper().replace(' IND ', ' INDUSTRIES '))
        
        return variations

    def validate_transactions(self, transactions):
        """Validate transactions before processing"""
        validation_results = {
            'valid': [],
            'invalid': [],
            'summary': {
                'total': len(transactions),
                'valid': 0,
                'invalid': 0,
                'errors': {},
                'matches': {}  # Add matches to summary for verification
            }
        }

        for transaction in transactions:
            try:
                # Find matching stock
                stock = self.find_matching_stock(
                    transaction['company_name'],
                    transaction['scrip_code']
                )
                
                if not stock:
                    raise ValueError(f"No matching stock found for {transaction['company_name']} ({transaction['scrip_code']})")

                # Add match information to summary
                validation_results['summary']['matches'][transaction['company_name']] = {
                    'matched_to': stock['display_name'],
                    'scrip_code': transaction['scrip_code']
                }

                # Add stock info to transaction
                transaction['stock_id'] = str(stock['_id'])
                transaction['stock_name'] = stock['display_name']
                validation_results['valid'].append(transaction)
                validation_results['summary']['valid'] += 1

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

if __name__ == '__main__':
    logger.info(f"Starting Flask application...")
    logger.info(f"Template folder: {app.template_folder}")
    logger.info(f"Static folder: {app.static_folder}")
    app.run(debug=True, port=8000) 