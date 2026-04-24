"""Claude Vision API for invoice extraction."""
import asyncio, base64, json, re
from pathlib import Path
import anthropic
from app.config import settings

MODEL = "claude-sonnet-4-20250514"

SYSTEM = """أنت متخصص في استخراج بيانات الفواتير الضريبية السعودية.
حلل الصورة وأرجع JSON فقط بدون أي نص آخر.

{
  "supplier_name": "string|null",
  "trade_name": "string|null",
  "vat_number": "string|null",
  "commercial_reg": "string|null",
  "invoice_number": "string|null",
  "invoice_date": "DD/MM/YYYY|null",
  "amount_before_vat": number|null,
  "vat_amount": number|null,
  "total_amount": number|null,
  "classification": "valid_tax_invoice|simplified_invoice|invalid",
  "confidence": 0.0-1.0,
  "notes": "string|null"
}

قواعد:
- إذا كان المبلغ الإجمالي فقط (فاتورة مبسطة): احسب amount_before_vat = total/1.15، vat_amount = total - before
- ضع confidence منخفض (< 0.4) لو الصورة غير واضحة
- الأرقام float وليست string
- لو مش فاتورة ضريبية: classification = "invalid"
"""

async def extract_page(client: anthropic.AsyncAnthropic,
                       sem: asyncio.Semaphore,
                       img_path: Path,
                       page_num: int) -> dict:
    async with sem:
        img_b64 = base64.standard_b64encode(img_path.read_bytes()).decode()
        try:
            resp = await client.messages.create(
                model=MODEL,
                max_tokens=600,
                system=SYSTEM,
                messages=[{"role": "user", "content": [
                    {"type": "image", "source": {
                        "type": "base64",
                        "media_type": "image/jpeg",
                        "data": img_b64}},
                    {"type": "text",
                     "text": f"استخرج بيانات الصفحة {page_num}. JSON فقط."}
                ]}]
            )
            raw = resp.content[0].text.strip()
            raw = re.sub(r"^```(?:json)?\s*", "", raw)
            raw = re.sub(r"\s*```$", "", raw)
            data = json.loads(raw)
            data["page_number"] = page_num
            return data
        except Exception as e:
            return _empty(page_num, str(e))

def _empty(page_num: int, note: str) -> dict:
    return {"page_number": page_num, "supplier_name": None, "trade_name": None,
            "vat_number": None, "commercial_reg": None, "invoice_number": None,
            "invoice_date": None, "amount_before_vat": None, "vat_amount": None,
            "total_amount": None, "classification": "invalid",
            "confidence": 0.0, "notes": f"خطأ: {note}"}
