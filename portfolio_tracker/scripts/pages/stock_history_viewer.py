import os
import sys
from datetime import datetime, timedelta
import pytz
import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from pymongo import MongoClient

# Add project root to path
current_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
project_root = os.path.dirname(current_dir)
sys.path.append(project_root)

from portfolio_tracker.config.settings import MONGODB_URI
from portfolio_tracker.utils.logger import setup_logger

logger = setup_logger('stock_history_viewer')

class StockHistoryViewer:
    def __init__(self):
        self.client = MongoClient(MONGODB_URI)
        self.db = self.client.portfolio_tracker
        self.time_periods = {
            "1 Day": 1,
            "2 Days": 2,
            "1 Week": 7,
            "1 Month": 30,
            "3 Months": 90,
            "6 Months": 180,
            "1 Year": 365,
            "3 Years": 1095,
            "5 Years": 1825,
            "10 Years": 3650,
            "Since Inception": None
        }
        
    def get_all_stocks(self):
        """Get all available stocks"""
        return list(self.db.stocks.find({}, {"symbol": 1, "name": 1, "_id": 0}))
        
    def get_stock_data(self, symbol, days=None):
        """Get historical data for a stock"""
        try:
            end_date = datetime.now(pytz.UTC)
            if days:
                start_date = end_date - timedelta(days=days)
            else:
                # For "Since Inception", get the earliest available data
                earliest_record = self.db.historical_prices.find_one(
                    {"symbol": {"$in": [symbol, f"{symbol}.NS"]}},  # Check both formats
                    sort=[("date", 1)]
                )
                if earliest_record:
                    start_date = earliest_record['date']
                else:
                    return pd.DataFrame()
            
            # Query historical prices with both symbol formats
            historical_prices = list(self.db.historical_prices.find(
                {
                    "symbol": {"$in": [symbol, f"{symbol}.NS"]},  # Check both formats
                    "date": {"$gte": start_date, "$lte": end_date}
                }
            ).sort("date", 1))
            
            if not historical_prices:
                return pd.DataFrame()
            
            # Convert to DataFrame
            df = pd.DataFrame(historical_prices)
            df['date'] = pd.to_datetime(df['date'])
            
            # Convert Decimal128 to float
            numeric_columns = ['open', 'high', 'low', 'close', 'volume']
            for col in numeric_columns:
                df[col] = df[col].astype(str).astype(float)
            
            return df
            
        except Exception as e:
            logger.error(f"Error getting stock data for {symbol}: {e}")
            return pd.DataFrame()

    def create_stock_chart(self, df, symbol, chart_types):
        """Create interactive chart for a single stock"""
        try:
            # Determine if volume is needed
            show_volume = 'Volume' in chart_types
            total_rows = 2 if show_volume else 1
            
            # Create subplots
            fig = make_subplots(
                rows=total_rows,
                cols=1,
                shared_xaxes=True,
                vertical_spacing=0.05,
                row_heights=[0.7, 0.3] if show_volume else [1]
            )
            
            # Add price data
            if 'Price' in chart_types:
                fig.add_trace(
                    go.Scatter(
                        x=df['date'],
                        y=df['close'],
                        name="Price",
                        line=dict(color='#1f77b4'),
                        hovertemplate="<b>Date:</b> %{x}<br>" +
                                    "<b>Price:</b> ₹%{y:.2f}<br>" +
                                    "<extra></extra>"
                    ),
                    row=1, col=1
                )
            
            if 'Candlestick' in chart_types:
                fig.add_trace(
                    go.Candlestick(
                        x=df['date'],
                        open=df['open'],
                        high=df['high'],
                        low=df['low'],
                        close=df['close'],
                        name="Candlestick",
                        increasing_line_color='#2ca02c',
                        decreasing_line_color='#d62728'
                    ),
                    row=1, col=1
                )
            
            # Add volume data if selected
            if show_volume:
                fig.add_trace(
                    go.Bar(
                        x=df['date'],
                        y=df['volume'],
                        name="Volume",
                        marker_color='#1f77b4',
                        opacity=0.5,
                        hovertemplate="<b>Date:</b> %{x}<br>" +
                                    "<b>Volume:</b> %{y:,.0f}<br>" +
                                    "<extra></extra>"
                    ),
                    row=2, col=1
                )
            
            # Update layout
            fig.update_layout(
                title=f"{symbol} Stock History",
                height=600,
                showlegend=True,
                legend=dict(
                    yanchor="top",
                    y=0.99,
                    xanchor="left",
                    x=0.01
                ),
                margin=dict(l=50, r=50, t=50, b=50),
                xaxis_rangeslider_visible=False
            )
            
            # Update y-axes labels
            fig.update_yaxes(title_text="Price (₹)", row=1, col=1)
            if show_volume:
                fig.update_yaxes(title_text="Volume", row=2, col=1)
            
            return fig
            
        except Exception as e:
            logger.error(f"Error creating stock chart: {e}")
            return None

    def calculate_metrics(self, df):
        """Calculate various metrics for the stock"""
        try:
            metrics = {}
            
            # Get latest price
            latest_price = df['close'].iloc[-1]
            
            # 1 day change
            if len(df) > 1:
                prev_day = df['close'].iloc[-2]
                metrics['1d_change'] = latest_price - prev_day
                metrics['1d_change_pct'] = (metrics['1d_change'] / prev_day) * 100
            else:
                metrics['1d_change'] = 0
                metrics['1d_change_pct'] = 0
            
            # 1 week change
            week_ago_idx = -6 if len(df) > 5 else 0
            week_ago_price = df['close'].iloc[week_ago_idx]
            metrics['1w_change'] = latest_price - week_ago_price
            metrics['1w_change_pct'] = (metrics['1w_change'] / week_ago_price) * 100
            
            # 52 week change
            year_data = df.tail(252)  # Approximately 252 trading days in a year
            if not year_data.empty:
                year_ago_price = year_data['close'].iloc[0]
                metrics['52w_change'] = latest_price - year_ago_price
                metrics['52w_change_pct'] = (metrics['52w_change'] / year_ago_price) * 100
                metrics['52w_high'] = year_data['high'].max()
                metrics['52w_low'] = year_data['low'].min()
            else:
                metrics['52w_change'] = 0
                metrics['52w_change_pct'] = 0
                metrics['52w_high'] = latest_price
                metrics['52w_low'] = latest_price
            
            # All-time profit/loss
            first_price = df['close'].iloc[0]
            metrics['total_change'] = latest_price - first_price
            metrics['total_change_pct'] = (metrics['total_change'] / first_price) * 100
            
            return metrics
            
        except Exception as e:
            logger.error(f"Error calculating metrics: {e}")
            return None

def main():
    st.set_page_config(
        page_title="Stock History Viewer",
        layout="wide"  # Restore wide layout
    )
    
    # Add navigation
    st.sidebar.title("Navigation")
    pages = {
        "Portfolio Dashboard": "portfolio_dashboard",
        "Stock Anomaly Dashboard": "stock_anomaly_dashboard",
        "Stock History Viewer": "stock_history_viewer"
    }
    
    for page_name, page_script in pages.items():
        if st.sidebar.button(page_name):
            st.switch_page(f"pages/{page_script}.py")
    
    st.title("Stock History Viewer")
    
    viewer = StockHistoryViewer()
    all_stocks = viewer.get_all_stocks()
    
    # Initialize session state for tracking stocks
    if 'num_stocks' not in st.session_state:
        st.session_state.num_stocks = 1
    
    # Add stock button
    if st.button("Add Another Stock View"):
        st.session_state.num_stocks += 1
    
    # Display stock viewers
    for i in range(st.session_state.num_stocks):
        st.markdown(f"### Stock {i+1}")
        
        # Create three columns for stock selection, time period, and chart types
        col1, col2, col3 = st.columns([2, 1, 2])
        
        with col1:
            stock = st.selectbox(
                "Select Stock",
                options=[None] + [f"{s['symbol']} - {s['name']}" for s in all_stocks],
                key=f"stock_{i}"
            )
        
        if stock:
            symbol = stock.split(" - ")[0]
            
            with col2:
                period = st.selectbox(
                    "Time Period",
                    options=list(viewer.time_periods.keys()),
                    key=f"period_{i}"
                )
            
            with col3:
                chart_types = st.multiselect(
                    "Chart Types",
                    options=["Price", "Candlestick", "Volume"],
                    default=["Price"],
                    key=f"chart_type_{i}"
                )
            
            # Get and display data
            days = viewer.time_periods[period]
            df = viewer.get_stock_data(symbol, days)
            
            if not df.empty:
                # Create container with custom width for chart and metrics
                container = st.container()
                with container:
                    # Create two columns with specific width ratio
                    chart_col, metrics_col = st.columns([0.7, 0.3])
                    
                    with chart_col:
                        fig = viewer.create_stock_chart(df, symbol, chart_types)
                        if fig:
                            # Update figure layout to fit the column
                            fig.update_layout(
                                height=600,
                                margin=dict(l=40, r=40, t=40, b=40)
                            )
                            st.plotly_chart(fig, use_container_width=True)  # Use container width
                        else:
                            st.error("Error creating chart")
                    
                    with metrics_col:
                        metrics = viewer.calculate_metrics(df)
                        if metrics:
                            st.markdown("### Key Metrics")
                            
                            # Get latest price from the DataFrame
                            latest_price = df['close'].iloc[-1]
                            
                            # Create two columns for metrics
                            left_metrics, right_metrics = st.columns(2)
                            
                            with left_metrics:
                                # Latest Price
                                st.metric("Current Price", f"₹{latest_price:,.2f}")
                                
                                # 1 Day Change
                                st.metric(
                                    "1 Day Change",
                                    f"₹{metrics['1d_change']:,.2f}",
                                    f"{metrics['1d_change_pct']:,.2f}%",
                                    delta_color="normal"
                                )
                                
                                # 1 Week Change
                                st.metric(
                                    "1 Week Change",
                                    f"₹{metrics['1w_change']:,.2f}",
                                    f"{metrics['1w_change_pct']:,.2f}%",
                                    delta_color="normal"
                                )
                                
                                # 52 Week High
                                st.metric("52 Week High", f"₹{metrics['52w_high']:,.2f}")
                            
                            with right_metrics:
                                # Total Change
                                st.metric(
                                    "Total Change",
                                    f"₹{metrics['total_change']:,.2f}",
                                    f"{metrics['total_change_pct']:,.2f}%",
                                    delta_color="normal"
                                )
                                
                                # 52 Week Change
                                st.metric(
                                    "52 Week Change",
                                    f"₹{metrics['52w_change']:,.2f}",
                                    f"{metrics['52w_change_pct']:,.2f}%",
                                    delta_color="normal"
                                )
                                
                                # 52 Week Low
                                st.metric("52 Week Low", f"₹{metrics['52w_low']:,.2f}")
                                
                                # Add some spacing to align with left column
                                st.write("")
                            
                            # Add date range context at the bottom
                            st.caption(
                                f"Data from {df['date'].iloc[0].strftime('%Y-%m-%d')} "
                                f"to {df['date'].iloc[-1].strftime('%Y-%m-%d')}"
                            )
            else:
                st.warning(f"No data available for {symbol} in selected time period")
        
        st.markdown("---")  # Add separator between stocks

if __name__ == "__main__":
    main() 