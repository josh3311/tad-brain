"""
TAD — Delivery Engine v1.0
Phase 5 — Package and send products to clients

Takes a built product package and delivers it to the client.
- Zips the product folder
- Sends via email with professional message
- Logs delivery to memory/delivery_log.json
- Notifies Finance Agent to send invoice
"""

import json
import os
import re
import smtplib
import sys
import zipfile
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.base import MIMEBase
from email import encoders
from pathlib import Path
from datetime import datetime
from openai import OpenAI
from dotenv import load_dotenv

load_dotenv()

ROOT       = Path(__file__).parent
MEMORY     = ROOT / "memory"
SKILLS_DIR = ROOT / "skills"

if str(SKILLS_DIR) not in sys.path:
    sys.path.insert(0, str(SKILLS_DIR))

client = OpenAI(
    api_key=os.getenv("KIMI_API_KEY", ""),
    base_url="https://api.moonshot.ai/v1",
)
MODEL = "kimi-k2.6"

# Email config from .env
SMTP_HOST     = os.getenv("SMTP_HOST", "smtp.gmail.com")
SMTP_PORT     = int(os.getenv("SMTP_PORT", "587"))
SMTP_USER     = os.getenv("SMTP_USER", "")
SMTP_PASSWORD = os.getenv("SMTP_PASSWORD", "")
FROM_NAME     = os.getenv("FROM_NAME", "TAD AI")


# ── Logging ───────────────────────────────────────────────────────────────────

def _log(msg: str):
    entry = {"ts": datetime.now().isoformat(), "msg": msg}
    MEMORY.mkdir(exist_ok=True)
    with open(MEMORY / "delivery_log.jsonl", "a", encoding="utf-8") as f:
        f.write(json.dumps(entry) + "\n")
    print(f"[Delivery] {msg}")


# ── Package zipper ────────────────────────────────────────────────────────────

def zip_package(package_path: str) -> Path:
    """Zip a product package folder for delivery."""
    pkg     = Path(package_path)
    zip_out = pkg.parent / f"{pkg.name}.zip"

    with zipfile.ZipFile(zip_out, "w", zipfile.ZIP_DEFLATED) as zf:
        for file in pkg.rglob("*"):
            if file.is_file():
                zf.write(file, file.relative_to(pkg.parent))

    _log(f"Zipped: {zip_out.name} ({zip_out.stat().st_size // 1024}KB)")
    return zip_out


# ── Delivery email generator ──────────────────────────────────────────────────

def generate_delivery_email(product_spec: dict, client_name: str) -> dict:
    """Generate a professional delivery email for the client."""
    prompt = f"""Write a professional product delivery email.

CLIENT: {client_name}
PRODUCT: {product_spec.get('display_name', 'Your AI Solution')}
DESCRIPTION: {product_spec.get('description', '')}
SETUP STEPS: {json.dumps(product_spec.get('setup_steps', []))}
PRICE: {product_spec.get('price_suggestion', '')}

Write a warm, professional email that:
- Thanks them for their business
- Explains what is attached
- Gives 3 simple setup steps
- Offers support
- Mentions the invoice is coming separately

Keep it under 200 words. Friendly but professional.

Return ONLY JSON:
{{
  "subject": "email subject line",
  "body": "full email body text"
}}"""

    try:
        resp = client.chat.completions.create(
            model=MODEL,
            messages=[{"role": "user", "content": prompt}],
            temperature=1,
            max_tokens=400,
        )
        raw   = resp.choices[0].message.content or "{}"
        clean = re.sub(r"```json|```", "", raw).strip()
        return json.loads(clean)
    except Exception as e:
        _log(f"Email generation error: {e}")
        return {
            "subject": f"Your {product_spec.get('display_name', 'AI Solution')} is Ready",
            "body": f"Hi {client_name},\n\nYour product is attached and ready to use.\n\nPlease find the setup instructions in the README.md file included.\n\nReply to this email if you need any help.\n\nBest,\nTAD AI Team",
        }


# ── Email sender ──────────────────────────────────────────────────────────────

def send_email(to_email: str, subject: str, body: str,
               attachment_path: Path = None) -> bool:
    """Send email with optional attachment."""
    if not SMTP_USER or not SMTP_PASSWORD:
        _log("SMTP not configured — saving email to memory/pending_emails.json")
        _save_pending_email(to_email, subject, body, attachment_path)
        return False

    try:
        msg = MIMEMultipart()
        msg["From"]    = f"{FROM_NAME} <{SMTP_USER}>"
        msg["To"]      = to_email
        msg["Subject"] = subject
        msg.attach(MIMEText(body, "plain"))

        if attachment_path and attachment_path.exists():
            with open(attachment_path, "rb") as f:
                part = MIMEBase("application", "octet-stream")
                part.set_payload(f.read())
            encoders.encode_base64(part)
            part.add_header(
                "Content-Disposition",
                f"attachment; filename={attachment_path.name}"
            )
            msg.attach(part)

        with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as server:
            server.starttls()
            server.login(SMTP_USER, SMTP_PASSWORD)
            server.send_message(msg)

        _log(f"Email sent to {to_email}: {subject}")
        return True

    except Exception as e:
        _log(f"Email send error: {e}")
        _save_pending_email(to_email, subject, body, attachment_path)
        return False


def _save_pending_email(to: str, subject: str, body: str, attachment=None):
    """Save unsent email to pending queue."""
    pending_path = MEMORY / "pending_emails.json"
    data = {"emails": []}
    if pending_path.exists():
        try:
            data = json.loads(pending_path.read_text(encoding="utf-8"))
        except Exception:
            pass
    data["emails"].append({
        "to":         to,
        "subject":    subject,
        "body":       body,
        "attachment": str(attachment) if attachment else None,
        "queued_at":  datetime.now().isoformat(),
        "status":     "pending",
    })
    pending_path.write_text(json.dumps(data, indent=2), encoding="utf-8")
    _log(f"Email queued for later: {subject}")


# ── Main delivery function ────────────────────────────────────────────────────

def deliver_product(package_path: str, client_email: str,
                    client_name: str, product_spec: dict = None) -> dict:
    """
    Full delivery pipeline.
    Zip → generate email → send → log → notify finance.
    Returns delivery result.
    """
    _log(f"=== Delivering to {client_name} ({client_email}) ===")

    # Load spec if not provided
    if not product_spec:
        spec_path = Path(package_path) / "product_spec.json"
        if spec_path.exists():
            product_spec = json.loads(spec_path.read_text(encoding="utf-8"))
        else:
            product_spec = {"display_name": "AI Solution", "description": ""}

    # Zip the package
    zip_path = zip_package(package_path)

    # Generate email
    email_content = generate_delivery_email(product_spec, client_name)

    # Send email
    sent = send_email(
        to_email=client_email,
        subject=email_content.get("subject", "Your product is ready"),
        body=email_content.get("body", ""),
        attachment_path=zip_path,
    )

    # Log delivery
    delivery = {
        "client_name":  client_name,
        "client_email": client_email,
        "product":      product_spec.get("display_name", ""),
        "package_path": package_path,
        "zip_path":     str(zip_path),
        "email_sent":   sent,
        "delivered_at": datetime.now().isoformat(),
        "status":       "delivered" if sent else "queued",
    }

    log_path = MEMORY / "delivery_log.json"
    data     = {"deliveries": []}
    if log_path.exists():
        try:
            data = json.loads(log_path.read_text(encoding="utf-8"))
        except Exception:
            pass
    data["deliveries"].append(delivery)
    log_path.write_text(json.dumps(data, indent=2), encoding="utf-8")

    # Notify Finance Agent
    try:
        from finance_agent import handle_closed_deal
        deal = {
            "lead":    {"name": client_name, "contact": client_email},
            "value":   float(re.sub(r"[^0-9.]", "", product_spec.get("price_suggestion", "297").split("/")[0]) or 297),
            "product": product_spec.get("display_name", ""),
        }
        handle_closed_deal(deal)
        _log("Finance Agent notified — invoice will be sent")
    except Exception as e:
        _log(f"Finance notification error: {e}")

    _log(f"=== Delivery complete: {delivery['status']} ===")
    return delivery


def get_delivery_history() -> list:
    log_path = MEMORY / "delivery_log.json"
    if not log_path.exists():
        return []
    try:
        return json.loads(log_path.read_text(encoding="utf-8")).get("deliveries", [])
    except Exception:
        return []


# ── Standalone test ───────────────────────────────────────────────────────────

if __name__ == "__main__":
    print("TAD Delivery Engine — Test Mode")
    print("=" * 40)

    # Check for built products
    products_log = MEMORY / "products_built.json"
    if products_log.exists():
        data     = json.loads(products_log.read_text(encoding="utf-8"))
        products = data.get("products", [])
        if products:
            latest = products[-1]
            print(f"Latest product: {latest.get('name')}")
            print(f"Package path: {latest.get('package')}")

            email = input("\nClient email to deliver to: ").strip()
            name  = input("Client name: ").strip()

            if email and name:
                result = deliver_product(
                    package_path=latest.get("package"),
                    client_email=email,
                    client_name=name,
                    product_spec=latest.get("spec"),
                )
                print(f"\nDelivery status: {result.get('status')}")
                print(f"Email sent: {result.get('email_sent')}")
            else:
                print("No email provided — skipping send test")
        else:
            print("No products built yet. Run tad_product_builder.py first.")
    else:
        print("No products built yet. Run tad_product_builder.py first.")
