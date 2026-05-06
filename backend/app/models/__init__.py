# backend/app/models/__init__.py

# Import ALL model files here so Base.metadata sees them
from app.models.user import User
from app.models.business import Business
from app.models.customer import Customer
from app.models.vendor import Vendor
from app.models.product import Product
from app.models.sales_invoice import SalesInvoice
from app.models.sales_invoice_item import SalesInvoiceItem
from app.models.purchase_invoice import PurchaseInvoice
from app.models.payment import Payment
from app.models.gst_record import GSTRecord
from app.models.revenue_ledger import RevenueLedger
from app.models.cashflow_forecast import CashflowForecast
from app.models.alert import Alert

__all__ = [
    "User",
    "Business",
    "Customer",
    "Vendor",
    "Product",
    "SalesInvoice",
    "SalesInvoiceItem",
    "PurchaseInvoice",
    "Payment",
    "GSTRecord",
    "RevenueLedger",
    "CashflowForecast",
    "Alert",
]