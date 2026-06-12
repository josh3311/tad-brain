import sys
from dataclasses import dataclass


@dataclass
class RevenueEntry:
    source: str
    amount: float
    status: str  # "paid" or "pending"


def calculate_total_revenue(entries):
    # core logic: sum only realized (paid) revenue
    return sum(e.amount for e in entries if e.status == "paid")


class RevenueTracker:
    # storage and aggregation layer on top of the core model
    def __init__(self):
        self.entries = []

    def add_entry(self, entry):
        self.entries.append(entry)

    def total_paid(self):
        return calculate_total_revenue(self.entries)

    def total_pending(self):
        return sum(e.amount for e in self.entries if e.status == "pending")


def format_report(entries):
    # simple text report summarizing revenue
    paid = calculate_total_revenue(entries)
    pending = sum(e.amount for e in entries if e.status == "pending")
    lines = [
        "Revenue Report",
        "--------------",
        f"Paid:    ${paid:.2f}",
        f"Pending: ${pending:.2f}",
        f"Total:   ${paid + pending:.2f}",
        "",
        "Breakdown:",
    ]
    for e in entries:
        lines.append(f"- {e.source}: ${e.amount:.2f} [{e.status}]")
    if not entries:
        lines.append("(no entries)")
    return "\n".join(lines)


def run_tests():
    # test 1: mixed paid and pending
    entries = [
        RevenueEntry("Consulting", 1000.0, "paid"),
        RevenueEntry("SaaS", 500.0, "pending"),
        RevenueEntry("Training", 250.0, "paid"),
    ]
    result = calculate_total_revenue(entries)
    if result != 1250.0:
        print(f"FAIL: expected 1250.0, got {result}")
        return 1

    # test 2: empty list
    if calculate_total_revenue([]) != 0.0:
        print("FAIL: expected 0.0 for empty list")
        return 1

    # test 3: tracker total paid aggregation
    tracker = RevenueTracker()
    tracker.add_entry(RevenueEntry("Consulting", 1000.0, "paid"))
    tracker.add_entry(RevenueEntry("SaaS", 500.0, "pending"))
    tracker.add_entry(RevenueEntry("Training", 250.0, "paid"))
    if tracker.total_paid() != 1250.0:
        print(f"FAIL tracker total_paid: expected 1250.0, got {tracker.total_paid()}")
        return 1

    # test 4: tracker total pending aggregation
    if tracker.total_pending() != 500.0:
        print(f"FAIL tracker total_pending: expected 500.0, got {tracker.total_pending()}")
        return 1

    # test 5: empty tracker
    empty = RevenueTracker()
    if empty.total_paid() != 0.0 or empty.total_pending() != 0.0:
        print("FAIL: empty tracker expected 0.0")
        return 1

    # test 6: report includes correct totals and entries
    report = format_report(entries)
    if "$1250.00" not in report:
        print("FAIL report missing paid total")
        return 1
    if "$500.00" not in report:
        print("FAIL report missing pending total")
        return 1
    if "$1750.00" not in report:
        print("FAIL report missing grand total")
        return 1
    if "Consulting" not in report:
        print("FAIL report missing entry name")
        return 1

    # test 7: report handles empty entries gracefully
    empty_report = format_report([])
    if "$0.00" not in empty_report:
        print("FAIL empty report missing zero total")
        return 1
    if "(no entries)" not in empty_report:
        print("FAIL empty report missing placeholder")
        return 1

    print("PASS")
    return 0


def main():
    if len(sys.argv) > 1 and sys.argv[1] == "--test":
        sys.exit(run_tests())

    # small CLI demo
    tracker = RevenueTracker()
    tracker.add_entry(RevenueEntry("Consulting", 1000.0, "paid"))
    tracker.add_entry(RevenueEntry("SaaS", 500.0, "pending"))
    tracker.add_entry(RevenueEntry("Training", 250.0, "paid"))
    print(format_report(tracker.entries))


if __name__ == "__main__":
    main()