"""REST API endpoints."""
import json
from datetime import datetime
from pathlib import Path
from fastapi import APIRouter, Depends, HTTPException, Header, UploadFile, File, BackgroundTasks
from fastapi.responses import FileResponse, JSONResponse
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import get_db
from app.models import Batch, Invoice, Supplier, TradeName, ExportLog
from app.services import (file_service, preprocessing, ocr_service,
                           validation_service, duplicate_service,
                           supplier_service, excel_service, odoo_service)
import anthropic, asyncio, tempfile

router = APIRouter(prefix="/api/v1")

def _check_key(x_api_key: str = Header(None)):
    if x_api_key != settings.API_KEY:
        raise HTTPException(403, "Invalid API Key")

# ── Upload ────────────────────────────────────────────────────
@router.post("/upload", dependencies=[Depends(_check_key)])
async def upload(background_tasks: BackgroundTasks,
                 file: UploadFile = File(...),
                 db: AsyncSession = Depends(get_db)):
    allowed = {".pdf", ".jpg", ".jpeg", ".png"}
    suffix = Path(file.filename).suffix.lower()
    if suffix not in allowed:
        raise HTTPException(400, "نوع الملف غير مدعوم")

    data = await file.read()
    if len(data) > settings.MAX_UPLOAD_MB * 1024 * 1024:
        raise HTTPException(400, "حجم الملف كبير جداً")

    file_hash = file_service.compute_hash(data)
    # Check duplicate file
    r = await db.execute(select(Batch).where(Batch.file_hash == file_hash))
    existing = r.scalars().first()
    if existing:
        return {"batch_id": existing.id, "duplicate_file": True,
                "message": "هذا الملف تم رفعه مسبقاً"}

    batch_id, path = file_service.save_upload(data, file.filename)
    batch = Batch(id=batch_id, filename=file.filename, file_hash=file_hash)
    db.add(batch); await db.commit()

    background_tasks.add_task(process_batch, batch_id, path)
    return {"batch_id": batch_id, "duplicate_file": False}

async def process_batch(batch_id: str, file_path: Path):
    from app.database import AsyncSessionLocal
    async with AsyncSessionLocal() as db:
        tmp_dir = Path(f"/tmp/zatca_{batch_id}")
        tmp_dir.mkdir(exist_ok=True)
        try:
            r = await db.execute(select(Batch).where(Batch.id == batch_id))
            batch = r.scalars().first()
            batch.status = "PROCESSING"; await db.commit()

            pages = await preprocessing.to_page_images(file_path, tmp_dir)
            batch.page_count = len(pages); await db.commit()

            client = anthropic.AsyncAnthropic(api_key=settings.ANTHROPIC_API_KEY)
            sem = asyncio.Semaphore(settings.MAX_CONCURRENT_PAGES)
            tasks = [ocr_service.extract_page(client, sem, p, i)
                     for i, p in enumerate(pages, 1)]
            results = await asyncio.gather(*tasks)

            for data in results:
                from app.services.qr_service import decode_qr, check_consistency
                qr = decode_qr(pages[data["page_number"]-1])
                qr_consistent, qr_notes = check_consistency(data, qr)
                if qr.get("qr_parsed"):
                    qr["qr_consistent"] = qr_consistent
                    if qr_notes:
                        data["notes"] = (data.get("notes") or "") + " | " + " | ".join(qr_notes)

                val = validation_service.validate(data)

                # Supplier memory
                sup_id = tn_id = None
                if data.get("vat_number") and data.get("supplier_name"):
                    try:
                        sup = await supplier_service.get_or_create_supplier(
                            db, data["vat_number"])
                        tn = await supplier_service.get_or_create_trade_name(
                            db, sup.id,
                            data.get("trade_name") or data["supplier_name"],
                            data.get("commercial_reg"), batch_id)
                        sup_id = sup.id; tn_id = tn.id
                    except Exception:
                        pass

                # Fingerprint + duplicate check
                fp = duplicate_service.make_fingerprint(
                    data.get("vat_number",""),
                    data.get("trade_name") or data.get("supplier_name",""),
                    data.get("invoice_number",""),
                    data.get("invoice_date",""))
                dup = await duplicate_service.check_duplicate(
                    db, fp, data.get("total_amount"))

                blocked = None
                if dup["is_duplicate"]: blocked = "فاتورة مكررة"
                elif val["requires_manual_review"]: blocked = "تحتاج مراجعة يدوية"
                elif not val["vat_number_valid"]: blocked = "رقم ضريبي غير صالح"
                elif not val["math_valid"]: blocked = "خطأ حسابي"

                inv = Invoice(
                    batch_id=batch_id, page_number=data["page_number"],
                    supplier_id=sup_id, trade_name_id=tn_id,
                    supplier_name=data.get("supplier_name"),
                    trade_name=data.get("trade_name") or data.get("supplier_name"),
                    vat_number=data.get("vat_number"),
                    invoice_number=data.get("invoice_number"),
                    invoice_date=data.get("invoice_date"),
                    amount_before_vat=data.get("amount_before_vat"),
                    vat_amount=data.get("vat_amount"),
                    total_amount=data.get("total_amount"),
                    classification=data.get("classification","invalid"),
                    confidence=data.get("confidence",0.0),
                    notes=data.get("notes"),
                    **{k: qr.get(k) for k in ["qr_present","qr_parsed","qr_raw",
                       "qr_seller_name","qr_vat_number","qr_timestamp",
                       "qr_total","qr_vat"]},
                    qr_consistent=qr.get("qr_consistent"),
                    **val,
                    duplicate_fingerprint=fp,
                    **dup,
                    export_status="NOT_EXPORTED",
                    blocked_reason=blocked,
                )
                db.add(inv); await db.flush()
                if tn_id and not dup["is_duplicate"] and data.get("total_amount"):
                    await supplier_service.update_totals(
                        db, tn_id, data["total_amount"])

            batch.status = "REVIEWED"; await db.commit()
        except Exception as e:
            r2 = await db.execute(select(Batch).where(Batch.id == batch_id))
            b = r2.scalars().first()
            if b: b.status = "UPLOADED"; b.notes = str(e)
            await db.commit()
        finally:
            file_service.cleanup(file_path)
            file_service.cleanup_dir(tmp_dir)

# ── Batches ───────────────────────────────────────────────────
@router.get("/batches")
async def list_batches(db: AsyncSession = Depends(get_db),
                       page: int = 1, size: int = 20):
    q = select(Batch).order_by(Batch.upload_time.desc()).offset((page-1)*size).limit(size)
    r = await db.execute(q); rows = r.scalars().all()
    return [_batch_dict(b) for b in rows]

@router.get("/batches/{batch_id}")
async def get_batch(batch_id: str, db: AsyncSession = Depends(get_db)):
    r = await db.execute(select(Batch).where(Batch.id == batch_id))
    b = r.scalars().first()
    if not b: raise HTTPException(404)
    return _batch_dict(b)

@router.get("/batches/{batch_id}/invoices")
async def batch_invoices(batch_id: str, db: AsyncSession = Depends(get_db)):
    r = await db.execute(select(Invoice).where(Invoice.batch_id == batch_id)
                         .order_by(Invoice.page_number))
    return [_inv_dict(i) for i in r.scalars().all()]

# ── Invoice update ────────────────────────────────────────────
@router.put("/invoices/{inv_id}", dependencies=[Depends(_check_key)])
async def update_invoice(inv_id: int, body: dict,
                          db: AsyncSession = Depends(get_db)):
    r = await db.execute(select(Invoice).where(Invoice.id == inv_id))
    inv = r.scalars().first()
    if not inv: raise HTTPException(404)
    editable = ["supplier_name","vat_number","trade_name","invoice_number",
                "invoice_date","amount_before_vat","vat_amount","total_amount","notes"]
    for f in editable:
        if f in body: setattr(inv, f, body[f])
    # re-validate
    val = validation_service.validate(_inv_dict(inv))
    for k,v in val.items(): setattr(inv, k, v)
    await db.commit()
    return _inv_dict(inv)

# ── Excel ─────────────────────────────────────────────────────
@router.get("/batches/{batch_id}/excel")
async def export_excel(batch_id: str, db: AsyncSession = Depends(get_db)):
    r = await db.execute(select(Invoice).where(Invoice.batch_id == batch_id)
                         .order_by(Invoice.page_number))
    invs = r.scalars().all()
    if not invs: raise HTTPException(404)
    out = Path(f"exports/{batch_id}.xlsx")
    excel_service.generate(invs, batch_id, out)
    rb = await db.execute(select(Batch).where(Batch.id == batch_id))
    b = rb.scalars().first()
    if b:
        b.status = "EXPORTED"; b.excel_exported_at = datetime.utcnow()
        await db.commit()
    return FileResponse(str(out), media_type=
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        filename=f"invoices_{batch_id}.xlsx")

# ── Odoo payload ──────────────────────────────────────────────
@router.get("/batches/{batch_id}/odoo-payload")
async def odoo_payload(batch_id: str, db: AsyncSession = Depends(get_db)):
    r = await db.execute(select(Invoice).where(Invoice.batch_id == batch_id))
    invs = r.scalars().all()
    return [odoo_service.build_payload(i) for i in invs if not i.is_duplicate]

# ── Push to Odoo ──────────────────────────────────────────────
@router.post("/batches/{batch_id}/push-odoo", dependencies=[Depends(_check_key)])
async def push_odoo(batch_id: str, db: AsyncSession = Depends(get_db)):
    r = await db.execute(select(Invoice).where(Invoice.batch_id == batch_id))
    invs = r.scalars().all()
    results = []
    for inv in invs:
        if inv.blocked_reason:
            results.append({"id": inv.id, "skipped": True, "reason": inv.blocked_reason})
            continue
        res = await odoo_service.push_invoice(inv)
        if res["success"]:
            inv.export_status = "EXPORTED"; inv.odoo_bill_id = res.get("odoo_bill_id")
            inv.last_sync_time = datetime.utcnow(); inv.error_message = None
        else:
            inv.export_status = "ERROR"; inv.error_message = res.get("error")
            inv.last_sync_time = datetime.utcnow()
        log = ExportLog(invoice_id=inv.id, status=inv.export_status,
                        error_message=inv.error_message,
                        payload=json.dumps(res.get("payload",{})))
        db.add(log)
        results.append({"id": inv.id, "status": inv.export_status})
    rb = await db.execute(select(Batch).where(Batch.id == batch_id))
    b = rb.scalars().first()
    if b: b.status = "PUSHED_ODOO"; b.odoo_pushed_at = datetime.utcnow()
    await db.commit()
    return results

# ── Exports / Tracking ────────────────────────────────────────
@router.get("/exports")
async def exports(status: str = None, db: AsyncSession = Depends(get_db)):
    q = select(Invoice)
    if status: q = q.where(Invoice.export_status == status)
    q = q.order_by(Invoice.last_sync_time.desc())
    r = await db.execute(q)
    return [_inv_dict(i) for i in r.scalars().all()]

@router.post("/exports/{inv_id}/retry", dependencies=[Depends(_check_key)])
async def retry_export(inv_id: int, db: AsyncSession = Depends(get_db)):
    r = await db.execute(select(Invoice).where(Invoice.id == inv_id))
    inv = r.scalars().first()
    if not inv: raise HTTPException(404)
    if inv.blocked_reason:
        raise HTTPException(400, inv.blocked_reason)
    res = await odoo_service.push_invoice(inv)
    inv.export_status = "EXPORTED" if res["success"] else "ERROR"
    inv.error_message = res.get("error"); inv.last_sync_time = datetime.utcnow()
    log = ExportLog(invoice_id=inv.id, status=inv.export_status,
                    error_message=inv.error_message,
                    payload=json.dumps(res.get("payload",{})))
    db.add(log); await db.commit()
    return {"status": inv.export_status}

# ── Suppliers ─────────────────────────────────────────────────
@router.get("/suppliers")
async def list_suppliers(db: AsyncSession = Depends(get_db)):
    r = await db.execute(select(Supplier))
    sups = r.scalars().all()
    out = []
    for s in sups:
        r2 = await db.execute(select(TradeName).where(TradeName.supplier_id == s.id))
        tns = r2.scalars().all()
        out.append({"id": s.id, "vat_number": s.vat_number,
                    "trade_names_count": len(tns),
                    "total_invoices": sum(t.total_invoices or 0 for t in tns),
                    "total_amount": sum(t.total_amount_sar or 0 for t in tns),
                    "last_seen": max((t.last_seen_batch for t in tns), default=None)})
    return out

@router.get("/suppliers/{vat_number}")
async def supplier_detail(vat_number: str, db: AsyncSession = Depends(get_db)):
    r = await db.execute(select(Supplier).where(Supplier.vat_number == vat_number))
    sup = r.scalars().first()
    if not sup: raise HTTPException(404)
    r2 = await db.execute(select(TradeName).where(TradeName.supplier_id == sup.id))
    tns = r2.scalars().all()
    r3 = await db.execute(select(Invoice).where(Invoice.supplier_id == sup.id)
                          .order_by(Invoice.invoice_date.desc()))
    invs = r3.scalars().all()
    return {"supplier": {"id": sup.id, "vat_number": sup.vat_number},
            "trade_names": [{"id":t.id,"name":t.trade_name,"commercial_reg":t.commercial_reg,
                              "odoo_vendor_id":t.odoo_vendor_id,
                              "total_invoices":t.total_invoices,
                              "total_amount":t.total_amount_sar} for t in tns],
            "invoices": [_inv_dict(i) for i in invs]}

# ── Helpers ───────────────────────────────────────────────────
def _batch_dict(b):
    return {"id":b.id,"filename":b.filename,"upload_time":str(b.upload_time),
            "page_count":b.page_count,"status":b.status,
            "excel_exported_at":str(b.excel_exported_at) if b.excel_exported_at else None,
            "odoo_pushed_at":str(b.odoo_pushed_at) if b.odoo_pushed_at else None,
            "notes":b.notes}

def _inv_dict(i):
    return {c.key: getattr(i, c.key)
            for c in i.__table__.columns}
