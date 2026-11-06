# backend/app/services/chatbot_service.py

"""
PHASE 7: AI VIRTUAL CFO CHATBOT SERVICE (POWERED BY GOOGLE GEMINI)

Architecture:
  - Structured tool calling (function calling) instead of prompt injection.
  - Exactly 6 read-only ORM queries strictly scoped to current_user.id:
      1. get_revenue_summary(period)
      2. get_gst_summary(period)
      3. get_outstanding_invoices(status, limit)
      4. get_customer_summary(query_type, limit)
      5. get_payment_history(limit, direction)
      6. get_invoice_stats()
  - Multi-turn execution loop up to 5 iterations.
  - Strict grounding: No fabricated figures; all numbers must be grounded in tool results.
  - Graceful fallback if GEMINI_API_KEY is not configured.
"""

import json
import logging
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Dict, Any, List, Optional
from uuid import UUID

from sqlalchemy.orm import Session
from sqlalchemy import func, desc

from app.core.config import settings
from app.models.sales_invoice import SalesInvoice, InvoiceStatus
from app.models.payment import Payment, PaymentDirection, PaymentStatus
from app.models.customer import Customer
from app.models.gst_record import GSTRecord
from app.models.revenue_ledger import RevenueLedger

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────
# 1. READ-ONLY ORM TOOLS (SCOPED TO USER_ID)
# ─────────────────────────────────────────────

def get_revenue_summary(db: Session, user_id: UUID, period: str = "all_time") -> Dict[str, Any]:
    """Calculates total revenue, paid invoices, and average invoice size."""
    query = db.query(SalesInvoice).filter(SalesInvoice.user_id == user_id)
    now = datetime.utcnow()
    if period == "this_month":
        start_date = datetime(now.year, now.month, 1)
        query = query.filter(SalesInvoice.invoice_date >= start_date)
    elif period == "last_30_days":
        query = query.filter(SalesInvoice.invoice_date >= now - timedelta(days=30))
    elif period == "this_year":
        start_date = datetime(now.year, 1, 1)
        query = query.filter(SalesInvoice.invoice_date >= start_date)

    invoices = query.all()
    total_invoiced = sum((inv.total_amount or Decimal('0')) for inv in invoices if inv.status != InvoiceStatus.CANCELLED)
    total_paid = sum((inv.total_amount or Decimal('0')) for inv in invoices if inv.status == InvoiceStatus.PAID)
    total_tax = sum((inv.tax_amount or Decimal('0')) for inv in invoices if inv.status != InvoiceStatus.CANCELLED)
    count = len([inv for inv in invoices if inv.status != InvoiceStatus.CANCELLED])
    avg_val = float(total_invoiced / Decimal(str(count))) if count > 0 else 0.0

    return {
        "period": period,
        "total_invoiced_inr": float(total_invoiced),
        "total_paid_inr": float(total_paid),
        "total_tax_inr": float(total_tax),
        "active_invoice_count": count,
        "average_invoice_inr": round(avg_val, 2),
    }


def get_gst_summary(db: Session, user_id: UUID, period: Optional[str] = None) -> Dict[str, Any]:
    """Returns GST liabilities and ITC breakdown."""
    query = db.query(GSTRecord).filter(GSTRecord.user_id == user_id)
    if period:
        query = query.filter(GSTRecord.return_period == period)
    records = query.all()

    if not records:
        sales = db.query(SalesInvoice).filter(SalesInvoice.user_id == user_id, SalesInvoice.status != InvoiceStatus.CANCELLED).all()
        total_cgst = sum((s.cgst_total or Decimal('0')) for s in sales)
        total_sgst = sum((s.sgst_total or Decimal('0')) for s in sales)
        total_igst = sum((s.igst_total or Decimal('0')) for s in sales)
        return {
            "period": period or "all_active",
            "gstr_record_found": False,
            "total_output_cgst_inr": float(total_cgst),
            "total_output_sgst_inr": float(total_sgst),
            "total_output_igst_inr": float(total_igst),
            "total_output_tax_inr": float(total_cgst + total_sgst + total_igst),
            "eligible_itc_inr": 0.0,
            "net_tax_payable_inr": float(total_cgst + total_sgst + total_igst),
        }

    total_liability = sum((r.net_tax_payable or Decimal('0')) for r in records)
    total_itc = sum((r.total_itc_available or Decimal('0')) for r in records)
    return {
        "period": period or "multiple",
        "gstr_record_found": True,
        "records_count": len(records),
        "net_tax_payable_inr": float(total_liability),
        "total_itc_available_inr": float(total_itc),
        "latest_return_period": records[0].return_period if records else None,
        "latest_status": records[0].status.value if records else None,
    }


def get_outstanding_invoices(db: Session, user_id: UUID, status: str = "overdue", limit: int = 5) -> Dict[str, Any]:
    """Fetches unpaid or overdue invoices with pending balances."""
    query = db.query(SalesInvoice).filter(SalesInvoice.user_id == user_id)
    if status == "overdue":
        query = query.filter(SalesInvoice.status == InvoiceStatus.OVERDUE)
    elif status == "unpaid":
        query = query.filter(SalesInvoice.status.in_([InvoiceStatus.SENT, InvoiceStatus.OVERDUE]))

    invoices = query.order_by(desc(SalesInvoice.amount_due)).limit(limit).all()
    result_list = []
    for inv in invoices:
        customer_name = inv.customer.name if inv.customer else "Unknown Customer"
        result_list.append({
            "invoice_number": inv.invoice_number,
            "customer_name": customer_name,
            "total_amount_inr": float(inv.total_amount or 0),
            "amount_due_inr": float(inv.amount_due or 0),
            "status": inv.status.value,
            "due_date": inv.due_date.strftime("%Y-%m-%d") if inv.due_date else None,
        })
    return {"count": len(result_list), "invoices": result_list}


def get_customer_summary(db: Session, user_id: UUID, query_type: str = "top_revenue", limit: int = 5) -> Dict[str, Any]:
    """Summarizes top customers by revenue or highest outstanding balance."""
    query = db.query(Customer).filter(Customer.user_id == user_id)
    if query_type == "highest_due":
        customers = query.order_by(desc(Customer.outstanding_balance)).limit(limit).all()
    else:
        customers = query.limit(limit).all()

    cust_list = []
    for c in customers:
        cust_list.append({
            "customer_name": c.name,
            "phone": c.phone,
            "gstin": c.gstin,
            "outstanding_balance_inr": float(c.outstanding_balance or 0),
            "credit_limit_inr": float(c.credit_limit or 0),
        })
    return {"query_type": query_type, "count": len(cust_list), "customers": cust_list}


def get_payment_history(db: Session, user_id: UUID, limit: int = 5, direction: str = "incoming") -> Dict[str, Any]:
    """Retrieves recent payments received or made."""
    query = db.query(Payment).filter(Payment.user_id == user_id)
    if direction == "incoming":
        query = query.filter(Payment.direction == PaymentDirection.INCOMING)
    elif direction == "outgoing":
        query = query.filter(Payment.direction == PaymentDirection.OUTGOING)

    payments = query.order_by(desc(Payment.payment_date)).limit(limit).all()
    pay_list = []
    for p in payments:
        pay_list.append({
            "payment_reference": p.transaction_reference or str(p.id)[:8],
            "amount_inr": float(p.amount or 0),
            "method": p.payment_method.value if p.payment_method else "other",
            "status": p.status.value if p.status else "completed",
            "date": p.payment_date.strftime("%Y-%m-%d") if p.payment_date else None,
        })
    return {"direction": direction, "count": len(pay_list), "payments": pay_list}


def get_invoice_stats(db: Session, user_id: UUID) -> Dict[str, Any]:
    """Returns distribution of invoices by status."""
    invoices = db.query(SalesInvoice).filter(SalesInvoice.user_id == user_id).all()
    counts = {s.value: 0 for s in InvoiceStatus}
    totals = {s.value: 0.0 for s in InvoiceStatus}

    for inv in invoices:
        status_val = inv.status.value
        counts[status_val] += 1
        totals[status_val] += float(inv.total_amount or 0)

    return {
        "total_invoices": len(invoices),
        "counts_by_status": counts,
        "totals_inr_by_status": {k: round(v, 2) for k, v in totals.items()},
    }


# ─────────────────────────────────────────────
# 2. TOOL DISPATCH TABLE
# ─────────────────────────────────────────────

TOOL_REGISTRY = {
    "get_revenue_summary": get_revenue_summary,
    "get_gst_summary": get_gst_summary,
    "get_outstanding_invoices": get_outstanding_invoices,
    "get_customer_summary": get_customer_summary,
    "get_payment_history": get_payment_history,
    "get_invoice_stats": get_invoice_stats,
}


def execute_tool(name: str, args: Dict[str, Any], db: Session, user_id: UUID) -> Dict[str, Any]:
    """Executes a declared tool safely within user scope."""
    if name not in TOOL_REGISTRY:
        return {"error": f"Tool {name} is not recognized."}
    fn = TOOL_REGISTRY[name]
    try:
        return fn(db=db, user_id=user_id, **args)
    except Exception as e:
        logger.exception(f"Error executing tool {name}: {e}")
        return {"error": str(e)}


# ─────────────────────────────────────────────
# 3. CHATBOT ORCHESTRATION WITH GEMINI
# ─────────────────────────────────────────────

SYSTEM_INSTRUCTION = (
    "You are an expert AI Virtual CFO for Indian MSMEs. "
    "Your name is CFO Mitra. "
    "You have access to tools that query the user's real-time financial database. "
    "CRITICAL RULES:\n"
    "1. You must ALWAYS use tools to answer questions about numbers, revenues, tax, invoices, customers, or payments.\n"
    "2. NEVER fabricate, estimate, or make up numbers. Every financial figure must come from tool results.\n"
    "3. State amounts in Indian Rupees (INR / Rs.) and format using Indian notation where applicable.\n"
    "4. Keep answers concise, actionable, and executive-ready for a business owner.\n"
    "5. If data is not available, state it clearly and provide helpful next steps."
)


def _deterministic_cfo_answer(query: str, db: Session, user_id: UUID) -> Dict[str, Any]:
    """Fallback response generator when GEMINI_API_KEY is not configured."""
    q = query.lower()
    tools_called = []

    if any(w in q for w in ["revenue", "sales", "turnover", "income", "earn"]):
        data = get_revenue_summary(db, user_id, "all_time")
        tools_called.append("get_revenue_summary")
        tot = data["total_invoiced_inr"]
        cnt = data["active_invoice_count"]
        paid = data["total_paid_inr"]
        avg = data["average_invoice_inr"]
        answer = f"Your total invoiced revenue is Rs {tot:,.2f} across {cnt} active invoices. Total collections received to date stand at Rs {paid:,.2f} with an average invoice size of Rs {avg:,.2f}."

    elif any(w in q for w in ["gst", "tax", "gstr", "liability", "itc"]):
        data = get_gst_summary(db, user_id)
        tools_called.append("get_gst_summary")
        payable = data["net_tax_payable_inr"]
        out_tax = data.get("total_output_tax_inr", payable)
        itc = data["total_itc_available_inr"] if data["gstr_record_found"] else 0.0
        answer = f"Your current estimated net GST payable is Rs {payable:,.2f}. Output tax stands at Rs {out_tax:,.2f} with eligible ITC of Rs {itc:,.2f}."

    elif any(w in q for w in ["overdue", "unpaid", "outstanding", "due", "pending"]):
        data = get_outstanding_invoices(db, user_id, "unpaid")
        tools_called.append("get_outstanding_invoices")
        if data["count"] == 0:
            answer = "Great news! You have no outstanding or overdue invoices at this moment."
        else:
            lines = [f"• {inv['customer_name']}: Rs {inv['amount_due_inr']:,.2f} (Inv #{inv['invoice_number']})" for inv in data["invoices"]]
            answer = f"You have {data['count']} pending invoices:\n" + "\n".join(lines)

    elif any(w in q for w in ["customer", "client"]):
        data = get_customer_summary(db, user_id, "highest_due")
        tools_called.append("get_customer_summary")
        answer = f"You have {data['count']} key customer accounts recorded in your virtual CFO ledger."

    elif any(w in q for w in ["payment", "receipt", "collected"]):
        data = get_payment_history(db, user_id, 5, "incoming")
        tools_called.append("get_payment_history")
        answer = f"Retrieved your {data['count']} most recent payment transactions."

    else:
        stats = get_invoice_stats(db, user_id)
        tools_called.append("get_invoice_stats")
        answer = f"You have {stats['total_invoices']} total invoices on record. Ask me about your revenue, GST liabilities, overdue invoices, or customers!"

    return {
        "answer": answer,
        "tools_executed": tools_called,
        "status": "completed",
        "source": "rules_engine",
    }


def ask_cfo_chatbot(
    db: Session,
    user_id: UUID,
    query: str,
    history: Optional[List[Dict[str, str]]] = None,
) -> Dict[str, Any]:
    """
    Main entry point for CFO Chatbot.
    If GEMINI_API_KEY is configured, executes function calling loop with Gemini.
    Otherwise, uses the deterministic CFO rule-and-ORM engine.
    """
    if not settings.GEMINI_API_KEY:
        return _deterministic_cfo_answer(query, db, user_id)

    try:
        import google.generativeai as genai

        genai.configure(api_key=settings.GEMINI_API_KEY)

        gemini_tools = [
            get_revenue_summary,
            get_gst_summary,
            get_outstanding_invoices,
            get_customer_summary,
            get_payment_history,
            get_invoice_stats,
        ]

        model = genai.GenerativeModel(
            model_name=settings.GEMINI_MODEL or "gemini-1.5-flash",
            system_instruction=SYSTEM_INSTRUCTION,
            tools=gemini_tools,
        )

        formatted_history = []
        if history:
            for h in history[-10:]:
                role = "user" if h.get("role") == "user" else "model"
                formatted_history.append({"role": role, "parts": [h.get("content", "")]})

        chat = model.start_chat(history=formatted_history, enable_automatic_function_calling=False)
        response = chat.send_message(query)
        tools_executed = []
        loop_count = 0

        while loop_count < 5:
            loop_count += 1
            candidate = response.candidates[0]
            fn_calls = [part.function_call for part in candidate.content.parts if hasattr(part, "function_call") and part.function_call.name]

            if not fn_calls:
                break

            tool_responses = []
            for call in fn_calls:
                name = call.name
                args = dict(call.args)
                tools_executed.append(name)
                result = execute_tool(name, args, db, user_id)
                tool_responses.append({
                    "function_response": {
                        "name": name,
                        "response": result,
                    }
                })

            response = chat.send_message(tool_responses)

        final_text = response.text if hasattr(response, "text") else str(response)
        return {
            "answer": final_text,
            "tools_executed": tools_executed,
            "status": "completed",
            "source": "gemini_function_calling",
        }

    except Exception as e:
        logger.warning(f"Gemini function calling failed: {e}. Falling back to rule engine.")
        fallback_res = _deterministic_cfo_answer(query, db, user_id)
        fallback_res["warnings"] = [str(e)]
        return fallback_res
