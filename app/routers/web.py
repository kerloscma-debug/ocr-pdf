"""Web (Jinja2) routes."""
import secrets
from fastapi import APIRouter, Request, Depends, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import get_db
from app.models import Batch, Invoice, Supplier, TradeName

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")

def _basic_auth(request: Request):
    if not settings.BASIC_AUTH_USER:
        return True
    auth = request.headers.get("Authorization","")
    if not auth.startswith("Basic "):
        return False
    import base64
    try:
        user, pw = base64.b64decode(auth[6:]).decode().split(":",1)
        return (secrets.compare_digest(user, settings.BASIC_AUTH_USER) and
                secrets.compare_digest(pw, settings.BASIC_AUTH_PASS))
    except Exception:
        return False

def _require_auth(request: Request):
    if not _basic_auth(request):
        from fastapi.responses import Response
        raise HTTPException(status_code=401, headers={"WWW-Authenticate": "Basic"})

@router.get("/", response_class=HTMLResponse)
async def index(request: Request):
    return RedirectResponse("/upload")

@router.get("/upload", response_class=HTMLResponse)
async def upload_page(request: Request):
    _require_auth(request)
    return templates.TemplateResponse("upload.html", {"request": request,
        "api_key": settings.API_KEY})

@router.get("/batches", response_class=HTMLResponse)
async def batches_page(request: Request, db: AsyncSession = Depends(get_db)):
    _require_auth(request)
    r = await db.execute(select(Batch).order_by(Batch.upload_time.desc()))
    batches = r.scalars().all()
    # Add duplicate count per batch
    batch_list = []
    for b in batches:
        dup_r = await db.execute(
            select(func.count()).where(Invoice.batch_id == b.id,
                                       Invoice.is_duplicate == True))
        dup_count = dup_r.scalar()
        batch_list.append({"batch": b, "dup_count": dup_count})
    return templates.TemplateResponse("batches.html",
        {"request": request, "batch_list": batch_list})

@router.get("/batches/{batch_id}", response_class=HTMLResponse)
async def review_page(request: Request, batch_id: str,
                      db: AsyncSession = Depends(get_db)):
    _require_auth(request)
    r = await db.execute(select(Batch).where(Batch.id == batch_id))
    batch = r.scalars().first()
    if not batch: raise HTTPException(404)
    r2 = await db.execute(select(Invoice).where(Invoice.batch_id == batch_id)
                          .order_by(Invoice.page_number))
    invoices = r2.scalars().all()
    return templates.TemplateResponse("review.html",
        {"request": request, "batch": batch, "invoices": invoices,
         "api_key": settings.API_KEY})

@router.get("/exports", response_class=HTMLResponse)
async def exports_page(request: Request, status: str = None,
                        db: AsyncSession = Depends(get_db)):
    _require_auth(request)
    q = select(Invoice, Batch).join(Batch, Invoice.batch_id == Batch.id)
    if status: q = q.where(Invoice.export_status == status)
    q = q.order_by(Invoice.last_sync_time.desc())
    r = await db.execute(q)
    rows = r.all()
    return templates.TemplateResponse("exports.html",
        {"request": request, "rows": rows, "filter_status": status,
         "api_key": settings.API_KEY,
         "odoo_enabled": settings.ODOO_ENABLED})

@router.get("/suppliers", response_class=HTMLResponse)
async def suppliers_page(request: Request, db: AsyncSession = Depends(get_db)):
    _require_auth(request)
    r = await db.execute(select(Supplier))
    sups = r.scalars().all()
    sup_data = []
    for s in sups:
        r2 = await db.execute(select(TradeName).where(TradeName.supplier_id == s.id))
        tns = r2.scalars().all()
        sup_data.append({
            "supplier": s,
            "trade_names": tns,
            "total_invoices": sum(t.total_invoices or 0 for t in tns),
            "total_amount":   sum(t.total_amount_sar or 0 for t in tns),
        })
    return templates.TemplateResponse("suppliers.html",
        {"request": request, "sup_data": sup_data})

@router.get("/suppliers/{vat_number}", response_class=HTMLResponse)
async def supplier_detail_page(request: Request, vat_number: str,
                                db: AsyncSession = Depends(get_db)):
    _require_auth(request)
    r = await db.execute(select(Supplier).where(Supplier.vat_number == vat_number))
    sup = r.scalars().first()
    if not sup: raise HTTPException(404)
    r2 = await db.execute(select(TradeName).where(TradeName.supplier_id == sup.id))
    tns = r2.scalars().all()
    r3 = await db.execute(select(Invoice).where(Invoice.supplier_id == sup.id)
                          .order_by(Invoice.invoice_date.desc()))
    invs = r3.scalars().all()
    return templates.TemplateResponse("supplier_detail.html",
        {"request": request, "sup": sup, "trade_names": tns, "invoices": invs})
