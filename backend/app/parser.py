"""
AI Order Parser

Two-tier strategy:
  1. Heuristic parser (regex + table-aware) — always available, deterministic, fast.
  2. LLM parser (optional) — used when USE_LLM=true and an API key is configured.
     Gives the heuristic output as a hint, asks the LLM to refine it.

Outputs a structured SalesOrder with a confidence score per field.
"""
import json
import logging
import re
from dataclasses import dataclass
from datetime import date, datetime
from typing import List, Optional, Tuple

from app.schemas import OrderItem, SalesOrder

log = logging.getLogger("parser")

# ---------------------------------------------------------------------------
# Patterns
# ---------------------------------------------------------------------------
ITEM_CODE_RE = re.compile(r"\b([A-Z][A-Z0-9]{1,5}-?\d{2,8}|SKU\d{3,8}|[A-Z]{2,4}\d{3,8})\b")
QTY_RE = re.compile(r"(?:qty|quantity|qnty)[\s:=-]*([0-9]+(?:\.[0-9]+)?)", re.I)
PRICE_RE = re.compile(r"(?:[$€£₨]|USD|EUR|PKR|GBP)\s*([0-9]{1,3}(?:,[0-9]{3})*(?:\.[0-9]+)?|[0-9]+(?:\.[0-9]+)?)", re.I)
TOTAL_RE = re.compile(r"\btotal[\s:]*[$€£₨]?\s*([0-9,]+(?:\.[0-9]+)?)", re.I)
SUBTOTAL_RE = re.compile(r"\bsub[-\s]?total[\s:]*[$€£₨]?\s*([0-9,]+(?:\.[0-9]+)?)", re.I)
TAX_RE = re.compile(r"\btax[\s:]*[$€£₨]?\s*([0-9,]+(?:\.[0-9]+)?)", re.I)
CUSTOMER_RE = re.compile(r"(?:customer|bill\s*to|sold\s*to|client)[\s:]*([A-Za-z0-9 .,&'\-]{3,80})", re.I)
PO_RE = re.compile(r"(?:\bPO\b|\bP\.O\.?|\bPurchase\s+Order\b)\s*(?:no\.?|number|#)?[\s:#-]*([A-Z0-9-]{3,20})", re.I)
DATE_RE = re.compile(r"\b(\d{4}-\d{2}-\d{2}|\d{1,2}[/-]\d{1,2}[/-]\d{2,4})\b")
CURRENCY_RE = re.compile(r"\b(USD|EUR|GBP|PKR|AED|JPY|INR)\b", re.I)


@dataclass
class _ParsedLine:
    item_code: str
    description: str
    quantity: float
    unit_price: float
    line_total: Optional[float]
    confidence: float


class OrderParser:
    def __init__(self, use_llm: bool = False, llm_api_key: str = "") -> None:
        self.use_llm = bool(use_llm and llm_api_key)
        self.llm_api_key = llm_api_key
        self.last_method: str = "heuristic"

    # -------- Public --------
    def parse(self, text: str) -> SalesOrder:
        if not text or not text.strip():
            self.last_method = "empty"
            return SalesOrder(confidence=0.0)

        heuristic = self._parse_heuristic(text)

        if self.use_llm:
            try:
                refined = self._parse_with_llm(text, heuristic)
                self.last_method = "llm+heuristic"
                return refined
            except Exception as exc:
                log.warning("LLM parse failed, using heuristic: %s", exc)

        self.last_method = "heuristic"
        return heuristic

    # -------- Heuristic --------
    def _parse_heuristic(self, text: str) -> SalesOrder:
        lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
        joined = "\n".join(lines)

        customer = self._first_match(CUSTOMER_RE, joined) or ""
        po = self._first_match(PO_RE, joined) or ""
        order_date = self._extract_date(joined)
        currency = (self._first_match(CURRENCY_RE, joined) or "USD").upper()

        items = self._extract_line_items(lines)

        subtotal = self._first_money(SUBTOTAL_RE, joined) or sum(i.line_total or 0 for i in items)
        tax = self._first_money(TAX_RE, joined) or 0.0
        total = self._first_money(TOTAL_RE, joined) or (subtotal + tax)

        # crude per-field confidence aggregation
        score = 0.0
        score += 0.15 if customer else 0.0
        score += 0.10 if po else 0.0
        score += 0.10 if order_date else 0.0
        score += 0.40 if items else 0.0
        score += 0.15 if total > 0 else 0.0
        score += 0.10 if subtotal > 0 else 0.0

        return SalesOrder(
            customer_name=customer.strip().rstrip(".,"),
            po_number=po,
            order_date=order_date,
            currency=currency,
            items=[OrderItem(
                item_code=i.item_code,
                description=i.description,
                quantity=i.quantity,
                unit_price=i.unit_price,
                line_total=i.line_total,
                confidence=i.confidence,
            ) for i in items],
            subtotal=round(subtotal, 2),
            tax=round(tax, 2),
            total=round(total, 2),
            confidence=round(min(score, 1.0), 3),
        )

    def _extract_line_items(self, lines: List[str]) -> List[_ParsedLine]:
        out: List[_ParsedLine] = []
        for line in lines:
            code_match = ITEM_CODE_RE.search(line)
            if not code_match:
                continue
            numbers = re.findall(r"[\d,]+(?:\.\d+)?", line.replace(code_match.group(0), ""))
            nums = []
            for n in numbers:
                try:
                    nums.append(float(n.replace(",", "")))
                except ValueError:
                    continue
            if len(nums) < 2:
                continue

            # Heuristic: smallest → quantity, then unit price, then line total
            qty = min(nums[:2]) if len(nums) >= 2 else nums[0]
            unit_price = nums[-2] if len(nums) >= 3 else nums[-1]
            line_total = nums[-1] if len(nums) >= 3 else qty * unit_price

            description = re.sub(ITEM_CODE_RE, "", line)
            description = re.sub(r"[\d,$.€£₨]+", "", description).strip(" -|\t")

            out.append(_ParsedLine(
                item_code=code_match.group(0),
                description=description[:120],
                quantity=qty,
                unit_price=unit_price,
                line_total=round(line_total, 2),
                confidence=0.7 if len(nums) >= 3 else 0.5,
            ))
        return out

    # -------- Helpers --------
    @staticmethod
    def _first_match(pattern: re.Pattern, text: str) -> Optional[str]:
        m = pattern.search(text)
        return m.group(1).strip() if m else None

    @staticmethod
    def _first_money(pattern: re.Pattern, text: str) -> float:
        m = pattern.search(text)
        if not m:
            return 0.0
        try:
            return float(m.group(1).replace(",", ""))
        except (ValueError, IndexError):
            return 0.0

    @staticmethod
    def _extract_date(text: str) -> Optional[date]:
        m = DATE_RE.search(text)
        if not m:
            return None
        raw = m.group(1)
        for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%m/%d/%Y", "%d-%m-%Y", "%d/%m/%y", "%m/%d/%y"):
            try:
                return datetime.strptime(raw, fmt).date()
            except ValueError:
                continue
        return None

    # -------- LLM (optional) --------
    def _parse_with_llm(self, text: str, hint: SalesOrder) -> SalesOrder:
        """Refine the heuristic guess via Anthropic Messages API. Best-effort."""
        import httpx

        prompt = (
            "You are an expert at extracting structured sales orders from OCR text.\n"
            "Return STRICT JSON only, matching this schema:\n"
            "{customer_name,customer_id,order_date(YYYY-MM-DD or null),po_number,currency,"
            "items:[{item_code,description,quantity,unit_price,line_total,confidence}],"
            "subtotal,tax,total,notes,confidence}\n\n"
            f"Heuristic guess (verify and improve): {hint.json()}\n\n"
            f"OCR text:\n---\n{text[:8000]}\n---\n"
            "Output JSON only, no markdown."
        )
        resp = httpx.post(
            "https://api.anthropic.com/v1/messages",
            headers={
                "x-api-key": self.llm_api_key,
                "anthropic-version": "2023-06-01",
                "content-type": "application/json",
            },
            json={
                "model": "claude-sonnet-4-5",
                "max_tokens": 2000,
                "messages": [{"role": "user", "content": prompt}],
            },
            timeout=30.0,
        )
        resp.raise_for_status()
        body = resp.json()
        content = body["content"][0]["text"].strip()
        # strip optional code fences
        content = re.sub(r"^```(?:json)?\s*|\s*```$", "", content, flags=re.MULTILINE)
        data = json.loads(content)
        return SalesOrder(**data)
