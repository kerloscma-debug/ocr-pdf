"""Odoo integration — draft bills only."""
import json
from datetime import datetime
from app.config import settings

def build_payload(inv) -> dict:
    return {
        "supplier": {"name": inv.supplier_name, "vat_number": inv.vat_number,
                     "trade_name": inv.trade_name},
        "bill": {
            "invoice_number": inv.invoice_number,
            "invoice_date":   inv.invoice_date,
            "amount_before_vat": inv.amount_before_vat,
            "vat_amount":     inv.vat_amount,
            "total_amount":   inv.total_amount,
            "currency": "SAR", "tax_rate": 15,
            "source_batch_id":    inv.batch_id,
            "source_page_number": inv.page_number,
        },
        "validation": {
            "approved": False,
            "requires_manual_review": inv.requires_manual_review,
            "notes": inv.notes or "",
        }
    }

async def push_invoice(inv) -> dict:
    """Push single invoice to Odoo (or simulate)."""
    payload = build_payload(inv)
    if not settings.ODOO_ENABLED:
        return {"success": True, "simulated": True,
                "payload": payload, "odoo_bill_id": None}
    try:
        import xmlrpc.client
        common = xmlrpc.client.ServerProxy(f"{settings.ODOO_URL}/xmlrpc/2/common")
        uid = common.authenticate(settings.ODOO_DB, settings.ODOO_USERNAME,
                                  settings.ODOO_PASSWORD, {})
        models = xmlrpc.client.ServerProxy(f"{settings.ODOO_URL}/xmlrpc/2/object")
        # find or create partner
        partner_ids = models.execute_kw(
            settings.ODOO_DB, uid, settings.ODOO_PASSWORD,
            "res.partner", "search",
            [[["vat", "=", inv.vat_number]]])
        if partner_ids:
            partner_id = partner_ids[0]
        else:
            partner_id = models.execute_kw(
                settings.ODOO_DB, uid, settings.ODOO_PASSWORD,
                "res.partner", "create",
                [{"name": inv.trade_name or inv.supplier_name,
                  "vat": inv.vat_number, "is_company": True}])
        # create draft bill
        bill_id = models.execute_kw(
            settings.ODOO_DB, uid, settings.ODOO_PASSWORD,
            "account.move", "create", [{
                "move_type": "in_invoice",
                "partner_id": partner_id,
                "ref": inv.invoice_number,
                "invoice_date": inv.invoice_date,
                "state": "draft",
            }])
        return {"success": True, "odoo_bill_id": bill_id, "payload": payload}
    except Exception as e:
        return {"success": False, "error": str(e), "payload": payload}
