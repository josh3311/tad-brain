"""Minimal auto-invoicing core: Invoice data model, total calculation,
aggregation, and simple text reporting.
"""

import sys
from dataclasses import dataclass, field
from typing import List


@dataclass
class LineItem:
    description: str
    quantity: float
    unit_price: float


@dataclass
class Invoice:
    customer: str
    tax_rate: float
    items: List[LineItem] = field(default_factory=list)
    subtotal: float = 0.0
    tax_amount: float = 0.0
    total: float = 0.0


def calculate_totals(inv: Invoice) -> None:
    # Compute subtotal, tax, and grand total from line items.
    inv.subtotal = sum(line.quantity * line.unit_price for line in inv.items)
    inv.tax_amount = inv.subtotal * inv.tax_rate
    inv.total = inv.subtotal + inv.tax_amount


class InvoiceBook:
    # Storage and aggregation layer for multiple invoices.
    def __init__(self) -> None:
        self.invoices: List[Invoice] = []

    def add(self, inv: Invoice) -> None:
        self.invoices.append(inv)

    def summary(self) -> dict:
        # Return aggregated metrics across all stored invoices.
        return {
            "count": len(self.invoices),
            "subtotal": sum(i.subtotal for i in self.invoices),
            "tax_amount": sum(i.tax_amount for i in self.invoices),
            "total": sum(i.total for i in self.invoices),
        }


def format_report(book: InvoiceBook) -> str:
    # Generate a plain-text summary report from an InvoiceBook.
    agg = book.summary()
    lines = [
        "Invoice Summary Report",
        "=" * 22,
        f"Invoices: {agg['count']}",
        f"Subtotal: {agg['subtotal']:.2f}",
        f"Tax:      {agg['tax_amount']:.2f}",
        f"Total:    {agg['total']:.2f}",
    ]
    return "\n".join(lines)


def _run_tests() -> int:
    # Test 1: single item, zero tax.
    i1 = Invoice(
        customer="Acme",
        tax_rate=0.0,
        items=[LineItem("Bolt", 10, 1.50)]
    )
    calculate_totals(i1)
    assert i1.subtotal == 15.0
    assert i1.tax_amount == 0.0
    assert i1.total == 15.0

    # Test 2: multiple items with 8% tax.
    i2 = Invoice(
        customer="Wayne",
        tax_rate=0.08,
        items=[
            LineItem("Cape", 1, 100.0),
            LineItem("Mask", 2, 25.0)
        ]
    )
    calculate_totals(i2)
    assert i2.subtotal == 150.0
    assert i2.tax_amount == 12.0
    assert i2.total == 162.0

    # Test 3: InvoiceBook aggregation.
    book = InvoiceBook()
    empty = book.summary()
    assert empty == {"count": 0, "subtotal": 0.0, "tax_amount": 0.0, "total": 0.0}

    book.add(i1)
    book.add(i2)
    s = book.summary()
    assert s["count"] == 2
    assert s["subtotal"] == 165.0
    assert s["tax_amount"] == 12.0
    assert s["total"] == 177.0

    # Test 4: text report on empty book.
    empty_book = InvoiceBook()
    rep_empty = format_report(empty_book)
    assert "Invoices: 0" in rep_empty
    assert "Subtotal: 0.00" in rep_empty
    assert "Tax:      0.00" in rep_empty
    assert "Total:    0.00" in rep_empty

    # Test 5: text report on populated book.
    rep = format_report(book)
    assert "Invoices: 2" in rep
    assert "Subtotal: 165.00" in rep
    assert "Tax:      12.00" in rep
    assert "Total:    177.00" in rep

    return 0


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--test":
        sys.exit(_run_tests())
    else:
        # CLI demo: build a tiny book and print report.
        demo_book = InvoiceBook()
        demo_inv = Invoice(
            customer="Demo Corp",
            tax_rate=0.10,
            items=[
                LineItem("Widget", 5, 20.0),
                LineItem("Gadget", 2, 15.0),
            ],
        )
        calculate_totals(demo_inv)
        demo_book.add(demo_inv)
        print(format_report(demo_book))