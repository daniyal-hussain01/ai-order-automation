"""
Bravo ERP integration client.

Operates in two modes:
  - LIVE  : POSTs to the real Bravo API when BRAVO_API_URL is configured.
  - MOCK  : Locally simulates the API so the demo always works end-to-end.

Both modes share the same interface so the rest of the system is agnostic.
"""
import logging
import uuid
from typing import Dict

import httpx

from app.schemas import SalesOrder

log = logging.getLogger("bravo")


class BravoClient:
    def __init__(self, base_url: str = "", api_key: str = "") -> None:
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key

    def is_live(self) -> bool:
        return bool(self.base_url and self.api_key)

    async def create_sales_order(self, order: SalesOrder) -> Dict:
        if not self.is_live():
            return self._mock_create(order)
        return await self._live_create(order)

    # ---- live ----
    async def _live_create(self, order: SalesOrder) -> Dict:
        url = f"{self.base_url}/api/v1/sales-orders"
        payload = self._to_bravo_payload(order)
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "X-Source": "ai-order-automation",
        }
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.post(url, json=payload, headers=headers)
            resp.raise_for_status()
            data = resp.json()
        return {
            "external_id": data.get("id") or data.get("orderId") or data.get("number"),
            "raw": data,
        }

    # ---- mock ----
    def _mock_create(self, order: SalesOrder) -> Dict:
        external_id = f"BRAVO-{uuid.uuid4().hex[:10].upper()}"
        log.info("[MOCK] Bravo SO created: %s (%d items, total=%.2f %s)",
                 external_id, len(order.items), order.total, order.currency)
        return {"external_id": external_id, "raw": {"mock": True}}

    @staticmethod
    def _to_bravo_payload(order: SalesOrder) -> Dict:
        return {
            "customer": {"name": order.customer_name, "id": order.customer_id or None},
            "poNumber": order.po_number or None,
            "orderDate": order.order_date.isoformat() if order.order_date else None,
            "currency": order.currency,
            "lines": [
                {
                    "itemCode": i.item_code,
                    "description": i.description,
                    "quantity": i.quantity,
                    "unitPrice": i.unit_price,
                    "lineTotal": i.line_total,
                }
                for i in order.items
            ],
            "subtotal": order.subtotal,
            "tax": order.tax,
            "total": order.total,
            "notes": order.notes or None,
        }
