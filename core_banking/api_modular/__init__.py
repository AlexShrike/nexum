"""
Core Banking API Application Factory
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .customers import router as customers_router
from .accounts import router as accounts_router
from .transactions import router as transactions_router
from .loans import router as loans_router
from .credit import router as credit_router
from .products import router as products_router
from .collections import router as collections_router
from .reporting import router as reporting_router
from .workflows import router as workflows_router
from .rbac import router as rbac_router
from .custom_fields import router as custom_fields_router
from .kafka import router as kafka_router
from .admin import router as admin_router


def create_app() -> FastAPI:
    """Create and configure the FastAPI application"""
    app = FastAPI(
        title="Core Banking System API",
        description="Production-grade core banking system with double-entry bookkeeping",
        version="1.0.0",
        docs_url="/docs",
        redoc_url="/redoc"
    )

    # Add CORS middleware
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],  # Configure appropriately for production
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    
    # Include routers
    app.include_router(customers_router, prefix="/customers", tags=["Customers"])
    app.include_router(accounts_router, prefix="/accounts", tags=["Accounts"])
    app.include_router(transactions_router, prefix="/transactions", tags=["Transactions"])
    app.include_router(loans_router, prefix="/loans", tags=["Loans"])
    app.include_router(credit_router, prefix="/credit", tags=["Credit"])
    app.include_router(products_router, prefix="/products", tags=["Products"])
    app.include_router(collections_router, prefix="/collections", tags=["Collections"])
    app.include_router(reporting_router, prefix="/reports", tags=["Reports"])
    app.include_router(workflows_router, prefix="/workflows", tags=["Workflows"])
    app.include_router(rbac_router, prefix="/rbac", tags=["RBAC"])
    app.include_router(custom_fields_router, prefix="/custom-fields", tags=["Custom Fields"])
    app.include_router(kafka_router, prefix="/kafka", tags=["Kafka"])
    app.include_router(admin_router, prefix="/admin", tags=["Admin"])
    
    # Health check endpoint
    @app.get("/health")
    async def health_check():
        """Health check endpoint"""
        return {
            "status": "healthy",
            "service": "core_banking_api",
            "version": "1.0.0"
        }

    # Root endpoint
    @app.get("/")
    async def get_api_info():
        """Get API information"""
        return {
            "name": "Core Banking System API",
            "version": "1.0.0",
            "description": "Production-grade core banking system",
            "endpoints": {
                "docs": "/docs",
                "health": "/health",
                "customers": "/customers",
                "accounts": "/accounts", 
                "transactions": "/transactions",
                "credit": "/credit",
                "loans": "/loans",
                "products": "/products",
                "collections": "/collections",
                "reports": "/reports",
                "workflows": "/workflows",
                "rbac": "/rbac",
                "custom-fields": "/custom-fields",
                "kafka": "/kafka",
                "admin": "/admin",
            }
        }
    
    return app


# Create the app instance for backward compatibility
app = create_app()