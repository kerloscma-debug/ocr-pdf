"""Validate extracted invoice data."""

TOL = 0.05
VAT_RATE = 0.15

def validate(inv: dict) -> dict:
    notes = list(filter(None, [inv.get("notes")]))
    requires_review = False

    vat_num_valid = (
        bool(inv.get("vat_number")) and
        str(inv.get("vat_number", "")).isdigit() and
        len(str(inv.get("vat_number", ""))) == 15
    )
    if not vat_num_valid:
        notes.append("رقم ضريبي غير صالح")
        requires_review = True

    b = inv.get("amount_before_vat")
    v = inv.get("vat_amount")
    t = inv.get("total_amount")

    math_valid = False
    vat_rate_valid = False

    if all(x is not None for x in [b, v, t]):
        math_valid = abs((b + v) - t) <= TOL
        if not math_valid:
            notes.append(f"خطأ حسابي: {b} + {v} ≠ {t}")
            requires_review = True
        if b and b > 0:
            rate = v / b
            vat_rate_valid = abs(rate - VAT_RATE) <= 0.01
            if not vat_rate_valid:
                notes.append(f"نسبة الضريبة {rate*100:.1f}% ≠ 15%")
                requires_review = True
    else:
        notes.append("مبالغ ناقصة")
        requires_review = True

    if (inv.get("confidence") or 0) < 0.4:
        requires_review = True
        notes.append("جودة صورة منخفضة")

    return {
        "vat_number_valid":     vat_num_valid,
        "math_valid":           math_valid,
        "vat_rate_valid":       vat_rate_valid,
        "requires_manual_review": requires_review,
        "notes":                " | ".join(notes) if notes else None,
    }

def blocked_reason(inv_row) -> str | None:
    reasons = []
    if inv_row.is_duplicate:
        reasons.append("فاتورة مكررة")
    if inv_row.requires_manual_review:
        reasons.append("تحتاج مراجعة يدوية")
    if not inv_row.vat_number_valid:
        reasons.append("رقم ضريبي غير صالح")
    if not inv_row.math_valid:
        reasons.append("خطأ حسابي")
    return " | ".join(reasons) if reasons else None
