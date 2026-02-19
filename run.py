#!/usr/bin/env python3
"""
Core Banking System Entry Point

Starts the FastAPI server on port 8090 with the core banking system.
"""

import sys
import os
from pathlib import Path

# Add the project root to Python path
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

from core_banking.api import run_server


if __name__ == "__main__":
    print("🏦 Starting Core Banking System...")
    print("📊 Double-entry bookkeeping enabled")
    print("🔒 Audit trail active")
    print("💰 All financial calculations use Decimal precision")
    print("🌐 API available at: http://localhost:8090")
    print("📚 Documentation at: http://localhost:8090/docs")
    print()
    
    try:
        # Start the server
        run_server(
            host="0.0.0.0",
            port=8090,
            debug=False  # Set to True for development
        )
    except KeyboardInterrupt:
        print("\n👋 Shutting down Core Banking System...")
    except Exception as e:
        print(f"❌ Error starting server: {e}")
        sys.exit(1)