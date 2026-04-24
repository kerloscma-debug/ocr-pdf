"""ZATCA QR code detection and TLV parsing."""
import struct, base64
from pathlib import Path

def decode_qr(img_path: Path) -> dict:
    result = {"qr_present": False, "qr_parsed": False, "qr_raw": None,
              "qr_seller_name": None, "qr_vat_number": None,
              "qr_timestamp": None, "qr_total": None, "qr_vat": None}
    try:
        from pyzbar.pyzbar import decode
        from PIL import Image
        img = Image.open(img_path)
        codes = decode(img)
        if not codes:
            return result
        raw = codes[0].data.decode("utf-8", errors="ignore")
        result["qr_present"] = True
        result["qr_raw"] = raw
        # Try TLV parse
        tlv = _parse_tlv(codes[0].data)
        if tlv:
            result["qr_parsed"]       = True
            result["qr_seller_name"]  = tlv.get(1)
            result["qr_vat_number"]   = tlv.get(2)
            result["qr_timestamp"]    = tlv.get(3)
            result["qr_total"]        = _to_float(tlv.get(4))
            result["qr_vat"]          = _to_float(tlv.get(5))
    except Exception:
        pass
    return result

def _parse_tlv(data: bytes) -> dict | None:
    try:
        result, i = {}, 0
        while i < len(data):
            tag = data[i]; i += 1
            length = data[i]; i += 1
            value = data[i:i+length].decode("utf-8", errors="ignore"); i += length
            result[tag] = value
        return result if result else None
    except Exception:
        return None

def _to_float(val) -> float | None:
    try:
        return float(val)
    except Exception:
        return None

def check_consistency(invoice: dict, qr: dict) -> tuple[bool, list[str]]:
    if not qr.get("qr_parsed"):
        return False, []
    notes = []
    consistent = True
    tol = 0.05
    if qr.get("qr_vat_number") and invoice.get("vat_number"):
        if qr["qr_vat_number"] != invoice["vat_number"]:
            notes.append("QR VAT number mismatch")
            consistent = False
    if qr.get("qr_total") is not None and invoice.get("total_amount") is not None:
        if abs(qr["qr_total"] - invoice["total_amount"]) > tol:
            notes.append(f"QR total {qr['qr_total']} ≠ invoice {invoice['total_amount']}")
            consistent = False
    if qr.get("qr_vat") is not None and invoice.get("vat_amount") is not None:
        if abs(qr["qr_vat"] - invoice["vat_amount"]) > tol:
            notes.append(f"QR VAT {qr['qr_vat']} ≠ invoice {invoice['vat_amount']}")
            consistent = False
    return consistent, notes
