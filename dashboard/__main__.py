#!/usr/bin/env python3
"""Main entry point for Nexum Dashboard"""

import uvicorn
import sys
import os
from pathlib import Path

# Add parent to path so core_banking package is importable
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dashboard.app import create_app

def main():
    """Start the dashboard server"""
    app = create_app()
    
    print("🏦 Nexum Core Banking Dashboard")
    print("💻 Starting on http://localhost:8893")
    print("📊 Dashboard: http://localhost:8893/")
    print("🔌 API docs: http://localhost:8893/docs")
    print("🛑 Press Ctrl+C to stop")
    
    uvicorn.run(
        app,
        host="127.0.0.1",
        port=8893,
        reload=False,
        access_log=False
    )

if __name__ == "__main__":
    main()