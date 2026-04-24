"""Supplier memory — find or create supplier + trade_name."""
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.models import Supplier, TradeName

async def get_or_create_supplier(db: AsyncSession, vat_number: str) -> Supplier:
    q = select(Supplier).where(Supplier.vat_number == vat_number)
    r = await db.execute(q)
    sup = r.scalars().first()
    if not sup:
        sup = Supplier(vat_number=vat_number)
        db.add(sup)
        await db.flush()
    return sup

async def get_or_create_trade_name(db: AsyncSession, supplier_id: int,
                                    trade_name: str, commercial_reg: str | None,
                                    batch_id: str) -> TradeName:
    q = select(TradeName).where(
        TradeName.supplier_id == supplier_id,
        TradeName.trade_name == trade_name)
    r = await db.execute(q)
    tn = r.scalars().first()
    if not tn:
        tn = TradeName(supplier_id=supplier_id, trade_name=trade_name,
                       commercial_reg=commercial_reg,
                       first_seen_batch=batch_id, last_seen_batch=batch_id)
        db.add(tn)
        await db.flush()
    else:
        tn.last_seen_batch = batch_id
        if commercial_reg and not tn.commercial_reg:
            tn.commercial_reg = commercial_reg
    return tn

async def update_totals(db: AsyncSession, trade_name_id: int,
                         amount: float):
    q = select(TradeName).where(TradeName.id == trade_name_id)
    r = await db.execute(q)
    tn = r.scalars().first()
    if tn:
        tn.total_invoices   = (tn.total_invoices or 0) + 1
        tn.total_amount_sar = (tn.total_amount_sar or 0.0) + (amount or 0.0)
