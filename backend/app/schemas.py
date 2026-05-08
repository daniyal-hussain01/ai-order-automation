"""Pydantic schemas for the API."""
from datetime import date
from typing import List, Optional

from pydantic import BaseModel, Field


class OrderItem(BaseModel):
    item_code: str = Field(..., description="SKU or item code")
    description: Optional[str] = ""
    quantity: float = Field(..., ge=0)
    unit_price: float = Field(..., ge=0)
    line_total: Optional[float] = None
    confidence: float = Field(0.0, ge=0.0, le=1.0)


class SalesOrder(BaseModel):
    customer_name: Optional[str] = ""
    customer_id: Optional[str] = ""
    order_date: Optional[date] = None
    po_number: Optional[str] = ""
    currency: str = "USD"
    items: List[OrderItem] = []
    subtotal: float = 0.0
    tax: float = 0.0
    total: float = 0.0
    notes: Optional[str] = ""
    confidence: float = Field(0.0, ge=0.0, le=1.0)


class UploadResponse(BaseModel):
    order_id: str
    filename: str
    ocr_text: str
    ocr_confidence: float
    processing_ms: int


class ExtractResponse(BaseModel):
    order_id: str
    order: SalesOrder
    parser_method: str
    processing_ms: int


class OrderUpdate(BaseModel):
    order: SalesOrder


class ApprovalResponse(BaseModel):
    order_id: str
    status: str
    external_id: Optional[str] = None
    bravo_mode: str


class HealthResponse(BaseModel):
    status: str
    version: str
    ocr_available: bool
    bravo_mode: str
