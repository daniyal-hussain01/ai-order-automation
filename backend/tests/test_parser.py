"""Unit tests for the heuristic parser. Run with: pytest -q"""
from app.parser import OrderParser


SAMPLE = """
Acme Corporation
Invoice / Sales Order
Customer: Globex Industries Ltd.
PO Number: PO-2025-00417
Date: 2025-04-30
Currency: USD

Item Code      Description           Qty    Unit Price    Line Total
SKU-1001       Widget Type A          10       12.50         125.00
SKU-1002       Widget Type B           5       30.00         150.00
ABC-2210       Premium Bracket         2      199.99         399.98

Subtotal: $674.98
Tax: $54.00
Total: $728.98
"""


def test_parse_extracts_customer_and_po():
    p = OrderParser(use_llm=False)
    order = p.parse(SAMPLE)
    assert "Globex" in (order.customer_name or "")
    assert order.po_number == "PO-2025-00417"


def test_parse_extracts_line_items():
    p = OrderParser(use_llm=False)
    order = p.parse(SAMPLE)
    codes = [i.item_code for i in order.items]
    assert "SKU-1001" in codes
    assert "SKU-1002" in codes
    assert "ABC-2210" in codes
    assert len(order.items) == 3


def test_parse_extracts_totals():
    p = OrderParser(use_llm=False)
    order = p.parse(SAMPLE)
    assert order.total == 728.98
    assert order.tax == 54.00


def test_parse_empty_text():
    p = OrderParser(use_llm=False)
    order = p.parse("")
    assert order.confidence == 0.0
    assert order.items == []


def test_confidence_score():
    p = OrderParser(use_llm=False)
    order = p.parse(SAMPLE)
    assert order.confidence > 0.7
