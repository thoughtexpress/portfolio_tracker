import streamlit as st
import pandas as pd
from datetime import datetime
import os
import sys

# Add project root to path (more robust path resolution)
current_dir = os.path.dirname(os.path.abspath(__file__))
scripts_dir = os.path.dirname(current_dir)  # scripts folder
project_root = os.path.dirname(os.path.dirname(scripts_dir))  # portfolio_tracker root
sys.path.insert(0, project_root)  # Insert at beginning of path

# Now import your modules
from portfolio_tracker.config.settings import MONGODB_URI
from portfolio_tracker.utils.logger import setup_logger
from portfolio_tracker.scripts.import_stock_mappings import import_mappings, find_similar_stocks

logger = setup_logger('stock_mappings_manager')

def render_stock_mappings_page():
    st.title("Stock Mappings Manager")
    
    # File uploader
    uploaded_file = st.file_uploader("Upload CSV file", type=['csv'])
    
    col1, col2 = st.columns(2)
    
    with col1:
        incomplete_data = st.checkbox(
            "Incomplete Data (Use YFinance)",
            help="Enable if CSV only contains transaction codes"
        )
        
        interactive_mode = st.checkbox(
            "Interactive Mode",
            help="Manually verify matches"
        )
    
    with col2:
        threshold = st.slider(
            "Matching Threshold",
            min_value=0,
            max_value=100,
            value=80,
            help="Similarity threshold for matching existing stocks"
        )
    
    if uploaded_file is not None:
        if st.button("Process File"):
            try:
                # Save uploaded file temporarily
                temp_file = f"temp_{uploaded_file.name}"
                with open(temp_file, "wb") as f:
                    f.write(uploaded_file.getvalue())
                
                with st.spinner("Processing file..."):
                    if interactive_mode:
                        # For interactive mode, we need to handle user input
                        df = pd.read_csv(temp_file)
                        progress_bar = st.progress(0)
                        
                        for idx, row in df.iterrows():
                            progress = (idx + 1) / len(df)
                            progress_bar.progress(progress)
                            
                            if incomplete_data and pd.notna(row.get('upstox_transaction_code')):
                                similar_stocks = find_similar_stocks(
                                    row['upstox_transaction_code'],
                                    threshold=threshold
                                )
                                
                                if similar_stocks:
                                    st.write(f"Processing: {row['upstox_transaction_code']}")
                                    st.write("Found similar stocks:")
                                    
                                    options = ["Use YFinance"] + [
                                        f"{match['mapping']['display_name']} (Match: {match['ratio']}%)"
                                        for match in similar_stocks[:5]
                                    ]
                                    
                                    choice = st.selectbox(
                                        "Select matching stock",
                                        options,
                                        key=f"select_{idx}"
                                    )
                                    
                                    if st.button("Confirm", key=f"confirm_{idx}"):
                                        continue
                    
                    else:
                        # Non-interactive mode - use only incomplete_data parameter
                        success = import_mappings(
                            temp_file,
                            incomplete_data=incomplete_data
                        )
                        
                        if success:
                            st.success("Successfully processed file!")
                        else:
                            st.error("Error processing file")
                
                # Clean up
                os.remove(temp_file)
                
            except Exception as e:
                st.error(f"Error processing file: {str(e)}")
                logger.error(f"Error processing file: {str(e)}")

def main():
    render_stock_mappings_page()

if __name__ == "__main__":
    main() 