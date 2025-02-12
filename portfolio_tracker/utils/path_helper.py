import os
import sys

def setup_project_path():
    """Add project root to Python path for consistent imports"""
    # Get the portfolio_tracker directory path
    current_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    project_root = os.path.dirname(current_dir)
    
    # Add both project root and portfolio_tracker directory to path
    if project_root not in sys.path:
        sys.path.insert(0, project_root)
    if current_dir not in sys.path:
        sys.path.insert(0, current_dir) 