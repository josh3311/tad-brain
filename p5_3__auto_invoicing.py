"""Minimal auto invoicing core: data model and total calculation."""

import sys
from dataclasses import dataclass, field
from decimal import Decimal
from typing import List


@dataclass
class LineItem:
    description: str
    quantity: Decimal
    unit_price: Decimal


@dataclass
class Invoice:
    invoice_id: str
    customer: str
    tax_rate: Decimal = Decimal("0.00")
    lines: List[LineItem] = field(default_factory=list)

    def calculate_totals(self):
        subtotal = Decimal("0.00")
        for line in self.lines:
            subtotal += line.quantity * line.unit_price
        tax = (subtotal * self.tax_rate).quantize(Decimal("0.01"))
        total = (subtotal + tax).quantize(Decimal("0.01"))
        return subtotal.quantize(Decimal("0.01")), tax, total


@dataclass
class InvoiceStore:
    _invoices: List[Invoice] = field(default_factory=list)

    def add(self, invoice: Invoice) -> None:
        self._invoices.append(invoice)

    def get(self, invoice_id: str) -> Invoice:
        for inv in self._invoices:
            if inv.invoice_id == invoice_id:
                return inv
        raise KeyError(invoice_id)

    def summary(self):
        total_subtotal = Decimal("0.00")
        total_tax = Decimal("0.00")
        grand_total = Decimal("0.00")
        for inv in self._invoices:
            s, t, tot = inv.calculate_totals()
            total_subtotal += s
            total_tax += t
            grand_total += tot
        return {
            "count": len(self._invoices),
            "total_subtotal": total_subtotal.quantize(Decimal("0.01")),
            "total_tax": total_tax.quantize(Decimal("0.01")),
            "total": grand_total.quantize(Decimal("0.01")),
        }


def _run_tests():
    # test 1: no tax
    inv1 = Invoice(
        invoice_id="INV-001",
        customer="Acme Corp",
        lines=[
            LineItem("Widget", Decimal("2"), Decimal("10.00")),
            LineItem("Gadget", Decimal("1"), Decimal("5.50")),
        ],
    )
    sub1, tax1, tot1 = inv1.calculate_totals()
    assert sub1 == Decimal("25.50"), f"subtotal mismatch: {sub1}"
    assert tax1 == Decimal("0.00"), f"tax mismatch: {tax1}"
    assert tot1 == Decimal("25.50"), f"total mismatch: {tot1}"

    # test 2: 10 percent tax
    inv2 = Invoice(
        invoice_id="INV-002",
        customer="Beta LLC",
        tax_rate=Decimal("0.10"),
        lines=[LineItem("Service", Decimal("3"), Decimal("100.00"))],
    )
    sub2, tax2, tot2 = inv2.calculate_totals()
    assert sub2 == Decimal("300.00"), f"subtotal mismatch: {sub2}"
    assert tax2 == Decimal("30.00"), f"tax mismatch: {tax2}"
    assert tot2 == Decimal("330.00"), f"total mismatch: {tot2}"

    # test 3: storage and aggregation
    store = InvoiceStore()
    store.add(inv1)
    store.add(inv2)

    retrieved = store.get("INV-001")
    assert retrieved.invoice_id == "INV-001"
    assert retrieved.customer == "Acme Corp"

    summary = store.summary()
    assert summary["count"] == 2
    assert summary["total_subtotal"] == Decimal("325.50")
    assert summary["total_tax"] == Decimal("30.00")
    assert summary["total"] == Decimal("355.50")

    # test missing invoice raises KeyError
    try:
        store.get("INV-999")
        assert False, "Expected KeyError for missing invoice"
    except KeyError:
        pass

    # test empty store summary
    empty_store = InvoiceStore()
    empty_summary = empty_store.summary()
    assert empty_summary["count"] == 0
    assert empty_summary["total_subtotal"] == Decimal("0.00")
    assert empty_summary["total_tax"] == Decimal("0.00")
    assert empty_summary["total"] == Decimal("0.00")

    print("All tests passed.")
    return 0


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--test":
        try:
            sys.exit(_run_tests())
        except AssertionError as exc:
            print(f"Test failed: {exc}")
            sys.exit(1)
    print("Usage: python module.py --test")