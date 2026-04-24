from sqlalchemy import (Column, Integer, String, Float, Boolean,
                        DateTime, ForeignKey, Text, func)
from sqlalchemy.orm import relationship
from app.database import Base

class Supplier(Base):
    __tablename__ = "suppliers"
    id         = Column(Integer, primary_key=True)
    vat_number = Column(String(15), unique=True, nullable=False, index=True)
    created_at = Column(DateTime, default=func.now())
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())
    trade_names = relationship("TradeName", back_populates="supplier")

class TradeName(Base):
    __tablename__ = "trade_names"
    id               = Column(Integer, primary_key=True)
    supplier_id      = Column(Integer, ForeignKey("suppliers.id"), nullable=False)
    trade_name       = Column(String(255), nullable=False, index=True)
    commercial_reg   = Column(String(50))
    odoo_vendor_id   = Column(Integer)
    first_seen_batch = Column(String(36))
    last_seen_batch  = Column(String(36))
    total_invoices   = Column(Integer, default=0)
    total_amount_sar = Column(Float, default=0.0)
    created_at       = Column(DateTime, default=func.now())
    supplier         = relationship("Supplier", back_populates="trade_names")
    invoices         = relationship("Invoice", back_populates="trade_name_rel")

class Batch(Base):
    __tablename__ = "batches"
    id               = Column(String(36), primary_key=True)
    filename         = Column(String(255))
    file_hash        = Column(String(64), unique=True, index=True)
    upload_time      = Column(DateTime, default=func.now())
    page_count       = Column(Integer, default=0)
    status           = Column(String(20), default="UPLOADED")
    excel_exported_at = Column(DateTime)
    odoo_pushed_at   = Column(DateTime)
    pushed_by        = Column(String(100))
    notes            = Column(Text)
    invoices         = relationship("Invoice", back_populates="batch")

class Invoice(Base):
    __tablename__ = "invoices"
    id                   = Column(Integer, primary_key=True)
    batch_id             = Column(String(36), ForeignKey("batches.id"))
    supplier_id          = Column(Integer, ForeignKey("suppliers.id"))
    trade_name_id        = Column(Integer, ForeignKey("trade_names.id"))
    page_number          = Column(Integer)
    supplier_name        = Column(String(255))
    vat_number           = Column(String(15))
    trade_name           = Column(String(255))
    invoice_number       = Column(String(100))
    invoice_date         = Column(String(20))
    amount_before_vat    = Column(Float)
    vat_amount           = Column(Float)
    total_amount         = Column(Float)
    classification       = Column(String(30))
    confidence           = Column(Float)
    notes                = Column(Text)
    # QR
    qr_present           = Column(Boolean, default=False)
    qr_parsed            = Column(Boolean, default=False)
    qr_raw               = Column(Text)
    qr_seller_name       = Column(String(255))
    qr_vat_number        = Column(String(15))
    qr_timestamp         = Column(String(50))
    qr_total             = Column(Float)
    qr_vat               = Column(Float)
    qr_consistent        = Column(Boolean)
    # Validation
    vat_number_valid     = Column(Boolean)
    math_valid           = Column(Boolean)
    vat_rate_valid       = Column(Boolean)
    requires_manual_review = Column(Boolean, default=False)
    # Duplicate
    duplicate_fingerprint = Column(String(64), index=True)
    is_duplicate         = Column(Boolean, default=False)
    duplicate_of_id      = Column(Integer, ForeignKey("invoices.id"))
    duplicate_notes      = Column(Text)
    # Odoo
    export_status        = Column(String(20), default="NOT_EXPORTED")
    blocked_reason       = Column(Text)
    odoo_bill_id         = Column(Integer)
    last_sync_time       = Column(DateTime)
    error_message        = Column(Text)
    # Relations
    batch         = relationship("Batch", back_populates="invoices")
    trade_name_rel = relationship("TradeName", back_populates="invoices")

class ExportLog(Base):
    __tablename__ = "export_logs"
    id            = Column(Integer, primary_key=True)
    invoice_id    = Column(Integer, ForeignKey("invoices.id"))
    status        = Column(String(20))
    error_message = Column(Text)
    last_sync_time = Column(DateTime, default=func.now())
    payload       = Column(Text)
