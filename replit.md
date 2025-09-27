# POS System for Kazakhstan Market

## Overview
This is a Point of Sale (POS) system designed specifically for the Kazakhstan market, featuring bilingual support (Kazakh/Russian). The system provides comprehensive retail management functionality including sales processing, inventory management, and reporting.

## Recent Changes (September 27, 2025)
### Security Improvements ✅
- **ADMIN_PASSWORD Security**: Moved admin password from workflow command to secure Replit Secrets
- **Production Debug Mode**: Disabled debug mode for production environment (FLASK_ENV=production)
- **Template Security**: Fixed URL routing issues that could expose internal endpoints

### Code Quality & Architecture Improvements ✅  
- **Eliminated Code Duplication**: Consolidated duplicated functions across modules:
  - `create_default_admin_user` - removed from views/auth.py, kept in app.py
  - `require_role` decorator - consolidated in utils/helpers.py
  - `log_operation` - unified version in utils/helpers.py with proper error handling
  - Language functions (`get_language`, `translate_name`) - centralized in utils/language.py
  - `generate_transaction_number` - single implementation in utils/helpers.py
- **Better Import Structure**: Cleaned up imports and dependencies between modules
- **Configuration Management**: Improved debug mode configuration through environment variables

### Previous Mobile Optimizations
- **Mobile Optimization Complete**: Implemented comprehensive mobile and tablet optimizations for Kazakhstan market
- **Tablet-Optimized POS Interface**: Added responsive design with Bootstrap breakpoints and touch-friendly controls
- **Barcode Scanner Integration**: Added QuaggaJS-based barcode scanning with camera access and product search API
- **Popular Products System**: Implemented backend analytics for tracking popular products based on sales data
- **Quick Access Panel**: Created smart product recommendations panel with 7-day and 30-day popularity metrics
- **Enhanced Database**: Added barcode field to products table with sample Kazakhstan market data
- **API Endpoints**: Created `/api/search-barcode` and `/api/quick-access-products` for mobile functionality
- **Touch-Optimized UI**: Improved button sizes, spacing, and interactions for tablet cashier efficiency
- **Bilingual Mobile Support**: All mobile features support Kazakh/Russian interface switching

## Previous Changes (September 26, 2025)
- Set up the application for Replit environment
- Migrated from SQLite to PostgreSQL database  
- Configured proper Flask application with ProxyFix middleware for Replit
- Installed all Python dependencies using uv package manager
- Created proper workflow configuration for port 5000 with webview output
- Fixed analytics function to handle None query results properly
- Created main.py entry point for Gunicorn deployment
- Configured deployment settings for autoscale production deployment
- Set up static/images directory for file uploads
- Verified all major features work: Dashboard, POS Terminal, Inventory Management

## Architecture
- **Backend**: Flask application with SQLAlchemy ORM
- **Database**: PostgreSQL (Replit-managed)
- **Frontend**: HTML templates with Bootstrap styling
- **Language Support**: Kazakh and Russian (bilingual interface)

## Key Features
- **POS Terminal**: Complete sales transaction processing
- **Inventory Management**: Product catalog with stock tracking
- **Reporting**: Sales analytics and reporting dashboard
- **Kazakhstan-specific**: Tax calculations (12% VAT), currency (₸), local language support

## Project Structure
- `app.py` - Main Flask application with all routes and business logic
- `models.py` - Database models for all entities
- `config.py` - Application configuration
- `templates/` - Jinja2 HTML templates
- `static/` - Static assets (CSS, JS, images)

## Database Configuration
- Uses PostgreSQL via DATABASE_URL environment variable
- Automatic database initialization with sample Kazakhstan market data
- Models include: Products, Categories, Suppliers, Transactions, Payments, etc.

## Deployment
- Configured for Replit autoscale deployment
- Uses Gunicorn WSGI server for production
- Listens on port 5000 for both development and production

## Dependencies
All dependencies are managed through pyproject.toml and include Flask, SQLAlchemy, PostgreSQL driver, and other essential packages.