"""Minimal SMTP wiring core for TAD: .env parser, config model, and MIME builder."""
import dataclasses
import sys
from email.mime.text import MIMEText
from typing import Dict, List


@dataclasses.dataclass(frozen=True)
class SMTPConfig:
    host: str
    port: int
    username: str
    password: str
    use_tls: bool
    from_addr: str

    @classmethod
    def from_mapping(cls, mapping: Dict[str, str]) -> "SMTPConfig":
        return cls(
            host=mapping["SMTP_HOST"],
            port=int(mapping.get("SMTP_PORT", "587")),
            username=mapping["SMTP_USERNAME"],
            password=mapping["SMTP_PASSWORD"],
            use_tls=mapping.get("SMTP_USE_TLS", "true").lower() in ("1", "true", "yes"),
            from_addr=mapping["SMTP_FROM"],
        )

    def validate(self) -> None:
        for field in dataclasses.fields(self):
            val = getattr(self, field.name)
            if val in (None, ""):
                raise ValueError(f"SMTPConfig missing value for {field.name}")


@dataclasses.dataclass(frozen=True)
class Lead:
    name: str
    email: str


def parse_dotenv(content: str) -> Dict[str, str]:
    """Parse KEY=VALUE lines into a dict. Ignores comments and blank lines."""
    env: Dict[str, str] = {}
    for raw in content.splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        env[key] = value
    return env


@dataclasses.dataclass(frozen=True)
class EmailRecord:
    lead: Lead
    subject: str
    ok: bool


class EmailLedger:
    """Storage and aggregation layer for email dispatch attempts."""

    def __init__(self) -> None:
        self._records: List[EmailRecord] = []

    def record(self, lead: Lead, subject: str, ok: bool) -> None:
        self._records.append(EmailRecord(lead=lead, subject=subject, ok=ok))

    def total(self) -> int:
        return len(self._records)

    def successes(self) -> int:
        return sum(1 for r in self._records if r.ok)

    def failures(self) -> int:
        return sum(1 for r in self._records if not r.ok)


def build_mime_text(lead: Lead, subject: str, body: str, from_addr: str) -> MIMEText:
    msg = MIMEText(body)
    msg["Subject"] = subject
    msg["From"] = from_addr
    msg["To"] = lead.email
    return msg


def _run_tests() -> int:
    errors = 0

    # Test parse_dotenv
    env_text = (
        "# comment\n"
        "SMTP_HOST=smtp.example.com\n"
        "SMTP_PORT=465\n"
        "SMTP_USERNAME=user\n"
        "SMTP_PASSWORD=pass\n"
        "SMTP_USE_TLS=yes\n"
        "SMTP_FROM=noreply@example.com\n"
        "\n"
        "BAD_LINE_NO_EQUALS\n"
    )
    parsed = parse_dotenv(env_text)
    if parsed.get("SMTP_HOST") != "smtp.example.com":
        print("FAIL: parse_dotenv host")
        errors += 1
    if parsed.get("SMTP_PORT") != "465":
        print("FAIL: parse_dotenv port")
        errors += 1

    # Test SMTPConfig.from_mapping and validate
    config = SMTPConfig.from_mapping(parsed)
    if config.host != "smtp.example.com" or config.port != 465 or not config.use_tls:
        print("FAIL: SMTPConfig.from_mapping")
        errors += 1
    try:
        bad = dict(parsed)
        bad["SMTP_HOST"] = ""
        bad_config = SMTPConfig.from_mapping(bad)
        bad_config.validate()
        print("FAIL: validate should raise on empty host")
        errors += 1
    except ValueError:
        pass

    # Test EmailLedger
    ledger = EmailLedger()
    lead1 = Lead(name="Alice", email="alice@example.com")
    lead2 = Lead(name="Bob", email="bob@example.com")
    ledger.record(lead1, "Hello", True)
    ledger.record(lead2, "Hi", False)
    if ledger.total() != 2:
        print("FAIL: ledger total")
        errors += 1
    if ledger.successes() != 1:
        print("FAIL: ledger successes")
        errors += 1
    if ledger.failures() != 1:
        print("FAIL: ledger failures")
        errors += 1

    # Test build_mime_text
    msg = build_mime_text(lead1, "Test Subject", "Test body", "from@example.com")
    if msg["To"] != "alice@example.com":
        print("FAIL: mime To")
        errors += 1
    if msg["Subject"] != "Test Subject":
        print("FAIL: mime Subject")
        errors += 1

    if errors:
        print(f"Tests failed: {errors}")
        return 1
    print("All tests passed.")
    return 0


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--test":
        sys.exit(_run_tests())