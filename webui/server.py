"""Local sayelf-pet-story-agent WebUI server with an exhibitor QR registry.

The server is intentionally local-first. QR payloads, generated assets and the
small status registry stay on this machine. The frontend never sends QR data to
an external QR service.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import secrets
import time
import uuid
from datetime import datetime, timezone
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from io import BytesIO
from pathlib import Path
from urllib.parse import parse_qs, quote, urlsplit

from PIL import Image, ImageDraw
from reportlab.graphics.barcode.qr import QrCodeWidget
from reportlab.lib.pagesizes import A4
from reportlab.lib.utils import ImageReader
from reportlab.pdfgen import canvas


ROOT = Path(__file__).resolve().parent
ASSET_DIR = ROOT / ".local" / "qr_assets"
REGISTRY_PATH = ROOT / ".local" / "qr_registry.json"
QR_SECRET = os.environ.get("SAYELF_PET_STORY_AGENT_QR_SECRET", "sayelf-pet-story-agent-local-development-secret").encode("utf-8")

PILOT_OPTIONS = {
    "events": [{"id": "event-pilot-01", "name": "Pet Expo Pilot 01"}],
    "exhibitors": [{"id": "exhibitor-happypet", "event_id": "event-pilot-01", "name": "HappyPet"}],
    "booths": [{"id": "booth-a17", "event_id": "event-pilot-01", "exhibitor_id": "exhibitor-happypet", "code": "A17", "name": "A17"}],
    "campaigns": [{"id": "campaign-my-pet-movie", "event_id": "event-pilot-01", "name": "My Pet Movie"}],
}


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def load_registry() -> list[dict]:
    if not REGISTRY_PATH.exists():
        return []
    try:
        value = json.loads(REGISTRY_PATH.read_text(encoding="utf-8"))
        return value if isinstance(value, list) else []
    except (OSError, json.JSONDecodeError):
        return []


REGISTRY = load_registry()


def save_registry() -> None:
    REGISTRY_PATH.parent.mkdir(parents=True, exist_ok=True)
    REGISTRY_PATH.write_text(json.dumps(REGISTRY, ensure_ascii=False, indent=2), encoding="utf-8")


def find_option(collection: str, key: str, value: str) -> dict | None:
    return next((item for item in PILOT_OPTIONS[collection] if item.get(key) == value), None)


def sign_join(event_id: str, exhibitor_id: str, booth_code: str, token: str, nonce: str, expires_at: int) -> str:
    message = "|".join([event_id, exhibitor_id, booth_code, token, nonce, str(expires_at)]).encode("utf-8")
    return hmac.new(QR_SECRET, message, hashlib.sha256).hexdigest()


def make_qr_png(payload: str, size: int = 720) -> bytes:
    widget = QrCodeWidget(payload)
    widget.qr.make()
    modules = widget.qr.getModuleCount()
    quiet_zone = 4
    pixels_per_module = max(1, size // (modules + quiet_zone * 2))
    image_size = (modules + quiet_zone * 2) * pixels_per_module
    image = Image.new("RGB", (image_size, image_size), "white")
    draw = ImageDraw.Draw(image)
    for row in range(modules):
        for column in range(modules):
            if widget.qr.isDark(row, column):
                left = (column + quiet_zone) * pixels_per_module
                top = (row + quiet_zone) * pixels_per_module
                draw.rectangle((left, top, left + pixels_per_module - 1, top + pixels_per_module - 1), fill="black")
    output = BytesIO()
    image.save(output, format="PNG", optimize=True)
    return output.getvalue()


def make_qr_pdf(record: dict, png: bytes) -> bytes:
    output = BytesIO()
    page_width, page_height = A4
    pdf = canvas.Canvas(output, pagesize=A4)
    pdf.setTitle(f"sayelf-pet-story-agent QR - {record['booth_code']}")
    pdf.setFillColorRGB(0.04, 0.07, 0.13)
    pdf.rect(0, 0, page_width, page_height, fill=1, stroke=0)
    pdf.setFillColorRGB(0.60, 0.96, 0.78)
    pdf.setFont("Helvetica-Bold", 25)
    pdf.drawString(48, page_height - 72, "sayelf-pet-story-agent")
    pdf.setFillColorRGB(0.92, 0.95, 0.98)
    pdf.setFont("Helvetica-Bold", 20)
    pdf.drawString(48, page_height - 112, record["event_name"])
    pdf.setFont("Helvetica", 16)
    pdf.drawString(48, page_height - 140, f"{record['exhibitor_name']} · Booth {record['booth_code']}")
    qr_size = 310
    pdf.drawImage(ImageReader(BytesIO(png)), (page_width - qr_size) / 2, page_height - 520, qr_size, qr_size, mask="auto")
    pdf.setFillColorRGB(0.60, 0.96, 0.78)
    pdf.setFont("Helvetica-Bold", 19)
    pdf.drawCentredString(page_width / 2, page_height - 565, "Scan to create your pet movie")
    pdf.setFillColorRGB(0.68, 0.74, 0.82)
    pdf.setFont("Helvetica", 11)
    pdf.drawCentredString(page_width / 2, 74, f"Campaign: {record['campaign_name']}")
    pdf.drawCentredString(page_width / 2, 56, f"QR status: {record['status']} · Expires: {record['expires_at']}")
    pdf.save()
    return output.getvalue()


def safe_base_url(raw: str) -> str:
    parsed = urlsplit(raw or "")
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return "http://localhost:8080/"
    return f"{parsed.scheme}://{parsed.netloc}/"


def public_record(record: dict) -> dict:
    status = record["status"]
    expires_epoch = record.get("expires_epoch")
    if expires_epoch is None:
        try:
            expires_epoch = datetime.fromisoformat(record["expires_at"].replace("Z", "+00:00")).timestamp()
        except (KeyError, ValueError):
            expires_epoch = 0
    if status == "ACTIVE" and expires_epoch <= int(time.time()):
        status = "EXPIRED"
    return {
        "id": record["id"],
        "event_id": record["event_id"],
        "event_name": record["event_name"],
        "exhibitor_id": record["exhibitor_id"],
        "exhibitor_name": record["exhibitor_name"],
        "booth_code": record["booth_code"],
        "campaign_name": record["campaign_name"],
        "status": status,
        "created_at": record["created_at"],
        "expires_at": record["expires_at"],
        "png_url": f"/api/qr/{record['id']}/png",
        "pdf_url": f"/api/qr/{record['id']}/pdf",
    }


class SayelfPetStoryAgentHandler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(ROOT), **kwargs)

    def log_message(self, format: str, *args) -> None:
        print(f"[sayelf-pet-story-agent] {format % args}")

    def send_json(self, payload: dict, status: int = 200) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def send_bytes(self, body: bytes, content_type: str, download_name: str | None = None) -> None:
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        if download_name:
            self.send_header("Content-Disposition", f'attachment; filename="{download_name}"')
        self.end_headers()
        self.wfile.write(body)

    def read_json(self) -> dict:
        length = int(self.headers.get("Content-Length", "0"))
        raw = self.rfile.read(length) if length else b"{}"
        try:
            value = json.loads(raw.decode("utf-8"))
            return value if isinstance(value, dict) else {}
        except json.JSONDecodeError:
            return {}

    def do_GET(self) -> None:
        parsed = urlsplit(self.path)
        if parsed.path == "/api/qr/options":
            self.send_json(PILOT_OPTIONS)
            return
        if parsed.path == "/api/qr/status":
            query = parse_qs(parsed.query)
            records = REGISTRY
            if query.get("event_id"):
                records = [item for item in records if item["event_id"] == query["event_id"][0]]
            self.send_json({"items": [public_record(item) for item in reversed(records)]})
            return
        parts = parsed.path.strip("/").split("/")
        if len(parts) == 4 and parts[:2] == ["api", "qr"] and parts[3] in {"png", "pdf"}:
            record = next((item for item in REGISTRY if item["id"] == parts[2]), None)
            if not record:
                self.send_json({"error": "QR_NOT_FOUND"}, 404)
                return
            path = ASSET_DIR / record[f"{parts[3]}_file"]
            if not path.exists():
                self.send_json({"error": "QR_ASSET_NOT_FOUND"}, 404)
                return
            content_type = "image/png" if parts[3] == "png" else "application/pdf"
            self.send_bytes(path.read_bytes(), content_type, path.name)
            return
        super().do_GET()

    def do_POST(self) -> None:
        parsed = urlsplit(self.path)
        if parsed.path != "/api/qr/generate":
            self.send_json({"error": "NOT_FOUND"}, 404)
            return
        body = self.read_json()
        event = find_option("events", "id", str(body.get("event_id", "")))
        exhibitor = find_option("exhibitors", "id", str(body.get("exhibitor_id", "")))
        booth = next((item for item in PILOT_OPTIONS["booths"] if item["code"] == str(body.get("booth_code", "")) and item["exhibitor_id"] == str(body.get("exhibitor_id", ""))), None)
        campaign = find_option("campaigns", "id", str(body.get("campaign_id", "")))
        if not event or not exhibitor or not booth or not campaign or exhibitor["event_id"] != event["id"] or campaign["event_id"] != event["id"]:
            self.send_json({"error": "INVALID_SELECTION"}, 400)
            return
        now = int(time.time())
        expires_at = now + 30 * 24 * 60 * 60
        record_id = "qr-" + uuid.uuid4().hex[:12]
        token = secrets.token_urlsafe(18)
        nonce = secrets.token_urlsafe(12)
        signature = sign_join(event["id"], exhibitor["id"], booth["code"], token, nonce, expires_at)
        base_url = safe_base_url(str(body.get("base_url", "")))
        join_url = f"{base_url}?event={quote(event['id'])}&booth={quote(booth['code'])}&join_token={quote(token)}&nonce={quote(nonce)}&exp={expires_at}&sig={signature}"
        record = {
            "id": record_id,
            "event_id": event["id"],
            "event_name": event["name"],
            "exhibitor_id": exhibitor["id"],
            "exhibitor_name": exhibitor["name"],
            "booth_code": booth["code"],
            "campaign_id": campaign["id"],
            "campaign_name": campaign["name"],
            "status": "ACTIVE",
            "created_at": utc_now(),
            "expires_epoch": expires_at,
            "expires_at": datetime.fromtimestamp(expires_at, timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
            "join_url": join_url,
            "token": token,
            "nonce": nonce,
        }
        png = make_qr_png(join_url)
        pdf = make_qr_pdf(record, png)
        ASSET_DIR.mkdir(parents=True, exist_ok=True)
        png_name = f"{record_id}.png"
        pdf_name = f"{record_id}.pdf"
        (ASSET_DIR / png_name).write_bytes(png)
        (ASSET_DIR / pdf_name).write_bytes(pdf)
        record["png_file"] = png_name
        record["pdf_file"] = pdf_name
        REGISTRY.append(record)
        save_registry()
        response = public_record(record)
        response["join_url"] = join_url
        self.send_json(response, 201)


def main() -> None:
    port = int(os.environ.get("SAYELF_PET_STORY_AGENT_WEBUI_PORT", "8080"))
    server = ThreadingHTTPServer(("127.0.0.1", port), SayelfPetStoryAgentHandler)
    print(f"sayelf-pet-story-agent WebUI: http://localhost:{port}/")
    print("QR registry: local-only")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nsayelf-pet-story-agent WebUI stopped")
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
