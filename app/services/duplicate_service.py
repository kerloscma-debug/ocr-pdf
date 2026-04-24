"""Duplicate detection using fingerprint."""
import hashlib
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.models import Invoice
from app.config import settings

def make_fingerprint(vat_number: str, trade_name: str,
                     invoice_number: str, invoice_date: str) -> str:
    key = f"{(vat_number or '').strip()}|{(trade_name or '').strip().lower()}|" \
          f"{(invoice_number or '').strip()}|{(invoice_date or '').strip()}"
    return hashlib.sha256(key.encode()).hexdigest()

async def check_duplicate(db: AsyncSession, fingerprint: str,
                           amount: float | None,
                           current_invoice_id: int | None = None) -> dict:
    q = select(Invoice).where(Invoice.duplicate_fingerprint == fingerprint)
    if current_invoice_id:
        q = q.where(Invoice.id != current_invoice_id)
    result = await db.execute(q)
    existing = result.scalars().first()

    if not existing:
        return {"is_duplicate": False, "duplicate_of_id": None, "duplicate_notes": None}

    tol = settings.DUPLICATE_AMOUNT_TOLERANCE
    note = f"مكرر — موجود في batch {existing.batch_id} صفحة {existing.page_number}"

    if amount is not None and existing.total_amount is not None:
        diff = abs(amount - existing.total_amount)
        if diff > tol:
            note += f" | تحذير: المبلغ مختلف بفارق {diff:.2f} ريال"

    return {"is_duplicate": True, "duplicate_of_id": existing.id, "duplicate_notes": note}
