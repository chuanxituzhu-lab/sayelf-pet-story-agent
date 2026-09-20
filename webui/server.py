"""Local sayelf-pet-story-agent WebUI server with QR, billing and brand assets.

The server is intentionally local-first. QR payloads, generated assets, brand
files, credits and the small status registries stay on this machine. The
frontend never sends visitor or exhibitor data to an external service.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import secrets
import shutil
import subprocess
import time
import threading
import uuid
from datetime import datetime, timezone
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from io import BytesIO
from pathlib import Path
from urllib.parse import parse_qs, quote, urlsplit

from PIL import Image, ImageDraw, ImageOps
from reportlab.graphics.barcode.qr import QrCodeWidget
from reportlab.lib.pagesizes import A4
from reportlab.lib.utils import ImageReader
from reportlab.pdfgen import canvas


ROOT = Path(__file__).resolve().parent
ASSET_DIR = ROOT / ".local" / "qr_assets"
REGISTRY_PATH = ROOT / ".local" / "qr_registry.json"
GENERATION_DIR = ROOT / ".local" / "generated_videos"
GENERATION_REGISTRY_PATH = ROOT / ".local" / "generation_registry.json"
USAGE_PATH = ROOT / ".local" / "generation_usage.json"
BRAND_DIR = ROOT / ".local" / "brand_assets"
BRAND_REGISTRY_PATH = ROOT / ".local" / "brand_registry.json"
BILLING_PATH = ROOT / ".local" / "billing_registry.json"
QR_SECRET = os.environ.get("SAYELF_PET_STORY_AGENT_QR_SECRET", "sayelf-pet-story-agent-local-development-secret").encode("utf-8")
MAX_GENERATION_BODY = 16 * 1024 * 1024
MAX_ADMIN_BODY = 24 * 1024 * 1024
MAX_IMAGE_BYTES = 5 * 1024 * 1024
MAX_BRAND_ASSET_BYTES = 8 * 1024 * 1024
MAX_IMAGES_PER_REQUEST = 2
FREE_VIDEO_LIMIT = 1
FREE_IMAGE_LIMIT = 2
MAX_REQUEST_VIDEO_COUNT = 3
MAX_REQUEST_IMAGE_COUNT = 8
DEFAULT_MODEL_ID = "local-fast"
MODEL_CATALOG = {
    "local-fast": {"name": "快速模型", "provider": "local-demo-renderer", "video_credits": 4, "image_credits": 1},
    "local-cinematic": {"name": "电影模型", "provider": "local-demo-renderer", "video_credits": 8, "image_credits": 2},
}
STATE_LOCK = threading.RLock()

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


def load_json_object(path: Path) -> dict:
    if not path.exists():
        return {}
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
        return value if isinstance(value, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


GENERATION_REGISTRY = load_json_object(GENERATION_REGISTRY_PATH)
USAGE_REGISTRY = load_json_object(USAGE_PATH)
BRAND_REGISTRY = load_json_object(BRAND_REGISTRY_PATH)
BILLING_REGISTRY = load_json_object(BILLING_PATH)


def save_registry() -> None:
    REGISTRY_PATH.parent.mkdir(parents=True, exist_ok=True)
    REGISTRY_PATH.write_text(json.dumps(REGISTRY, ensure_ascii=False, indent=2), encoding="utf-8")


def save_json_object(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")


def quota_day() -> str:
    return datetime.now().astimezone().date().isoformat()


def model_config(model_id: str) -> dict:
    return MODEL_CATALOG.get(model_id) or MODEL_CATALOG[DEFAULT_MODEL_ID]


def public_model_catalog() -> list[dict]:
    return [{"id": key, **value} for key, value in MODEL_CATALOG.items()]


def billing_account(account_key: str) -> dict:
    key = account_key.strip()[:128] or "booth:A17"
    item = BILLING_REGISTRY.get(key)
    if not isinstance(item, dict):
        item = {"credits": 0, "updated_at": utc_now()}
        BILLING_REGISTRY[key] = item
    item["credits"] = max(0, int(item.get("credits", 0)))
    return item


def billing_snapshot(account_key: str) -> dict:
    with STATE_LOCK:
        item = billing_account(account_key)
        return {"account_key": account_key, "credits": int(item.get("credits", 0)), "updated_at": item.get("updated_at", utc_now())}


def usage_for(visitor_id: str) -> dict:
    key = visitor_id.strip()[:128] or "anonymous"
    day = quota_day()
    item = USAGE_REGISTRY.get(key)
    if not isinstance(item, dict) or item.get("day") != day:
        item = {"day": day, "free_video_used": 0, "free_image_used": 0, "paid_video_used": 0, "paid_image_used": 0, "video_count": 0, "image_count": 0, "requests": {}}
        USAGE_REGISTRY[key] = item
    item.setdefault("free_video_used", min(FREE_VIDEO_LIMIT, int(item.get("video_count", 0))))
    item.setdefault("free_image_used", min(FREE_IMAGE_LIMIT, int(item.get("image_count", 0))))
    item.setdefault("paid_video_used", max(0, int(item.get("video_count", 0)) - int(item.get("free_video_used", 0))))
    item.setdefault("paid_image_used", max(0, int(item.get("image_count", 0)) - int(item.get("free_image_used", 0))))
    item.setdefault("video_count", int(item.get("free_video_used", 0)) + int(item.get("paid_video_used", 0)))
    item.setdefault("image_count", int(item.get("free_image_used", 0)) + int(item.get("paid_image_used", 0)))
    item.setdefault("requests", {})
    return item


def quota_snapshot(visitor_id: str, account_key: str = "booth:A17") -> dict:
    with STATE_LOCK:
        item = usage_for(visitor_id)
        billing = billing_account(account_key)
        return {
            "day": item["day"],
            "video_limit": FREE_VIDEO_LIMIT,
            "videos_used": int(item.get("video_count", 0)),
            "videos_remaining": max(0, FREE_VIDEO_LIMIT - int(item.get("free_video_used", 0))),
            "free_videos_used": int(item.get("free_video_used", 0)),
            "free_videos_remaining": max(0, FREE_VIDEO_LIMIT - int(item.get("free_video_used", 0))),
            "image_limit": FREE_IMAGE_LIMIT,
            "images_used": int(item.get("image_count", 0)),
            "images_remaining": max(0, FREE_IMAGE_LIMIT - int(item.get("free_image_used", 0))),
            "free_images_used": int(item.get("free_image_used", 0)),
            "free_images_remaining": max(0, FREE_IMAGE_LIMIT - int(item.get("free_image_used", 0))),
            "credits": int(billing.get("credits", 0)),
        }


def reserve_generation(visitor_id: str, video_count: int, image_count: int, model_id: str, account_key: str, idempotency_key: str) -> tuple[dict | None, dict | None, dict | None]:
    with STATE_LOCK:
        item = usage_for(visitor_id)
        existing = item["requests"].get(idempotency_key)
        if existing:
            return existing, None, None
        model_id = model_id if model_id in MODEL_CATALOG else DEFAULT_MODEL_ID
        model = model_config(model_id)
        free_video = min(video_count, max(0, FREE_VIDEO_LIMIT - int(item.get("free_video_used", 0))))
        free_image = min(image_count, max(0, FREE_IMAGE_LIMIT - int(item.get("free_image_used", 0))))
        paid_video = video_count - free_video
        paid_image = image_count - free_image
        required_credits = paid_video * int(model["video_credits"]) + paid_image * int(model["image_credits"])
        billing = billing_account(account_key)
        if int(billing.get("credits", 0)) < required_credits:
            return None, {
                "error": "INSUFFICIENT_CREDITS",
                "required_credits": required_credits,
                "credits": int(billing.get("credits", 0)),
                "model_id": model_id,
                "quota": quota_snapshot(visitor_id, account_key),
            }, None
        item["free_video_used"] = int(item.get("free_video_used", 0)) + free_video
        item["free_image_used"] = int(item.get("free_image_used", 0)) + free_image
        item["paid_video_used"] = int(item.get("paid_video_used", 0)) + paid_video
        item["paid_image_used"] = int(item.get("paid_image_used", 0)) + paid_image
        item["video_count"] = int(item.get("video_count", 0)) + video_count
        item["image_count"] = int(item.get("image_count", 0)) + image_count
        billing["credits"] = int(billing.get("credits", 0)) - required_credits
        billing["updated_at"] = utc_now()
        save_json_object(USAGE_PATH, USAGE_REGISTRY)
        save_json_object(BILLING_PATH, BILLING_REGISTRY)
        reservation = {"free_video": free_video, "free_image": free_image, "paid_video": paid_video, "paid_image": paid_image, "credits": required_credits, "model_id": model_id, "account_key": account_key}
        return None, None, reservation


def reserve_quota(visitor_id: str, image_count: int, idempotency_key: str) -> tuple[dict | None, dict | None]:
    existing, error, _ = reserve_generation(visitor_id, 1, image_count, DEFAULT_MODEL_ID, "booth:A17", idempotency_key)
    return existing, error


def release_generation(visitor_id: str, reservation: dict) -> None:
    with STATE_LOCK:
        item = usage_for(visitor_id)
        item["free_video_used"] = max(0, int(item.get("free_video_used", 0)) - int(reservation.get("free_video", 0)))
        item["free_image_used"] = max(0, int(item.get("free_image_used", 0)) - int(reservation.get("free_image", 0)))
        item["paid_video_used"] = max(0, int(item.get("paid_video_used", 0)) - int(reservation.get("paid_video", 0)))
        item["paid_image_used"] = max(0, int(item.get("paid_image_used", 0)) - int(reservation.get("paid_image", 0)))
        item["video_count"] = max(0, int(item.get("video_count", 0)) - int(reservation.get("free_video", 0)) - int(reservation.get("paid_video", 0)))
        item["image_count"] = max(0, int(item.get("image_count", 0)) - int(reservation.get("free_image", 0)) - int(reservation.get("paid_image", 0)))
        billing = billing_account(str(reservation.get("account_key", "booth:A17")))
        billing["credits"] = int(billing.get("credits", 0)) + int(reservation.get("credits", 0))
        billing["updated_at"] = utc_now()
        save_json_object(USAGE_PATH, USAGE_REGISTRY)
        save_json_object(BILLING_PATH, BILLING_REGISTRY)


def remember_generation(visitor_id: str, idempotency_key: str, response: dict) -> None:
    with STATE_LOCK:
        item = usage_for(visitor_id)
        item["requests"][idempotency_key] = response
        save_json_object(USAGE_PATH, USAGE_REGISTRY)


def decode_image_item(item: object, max_bytes: int = MAX_IMAGE_BYTES) -> tuple[str, bytes]:
    if not isinstance(item, dict):
        raise ValueError("INVALID_IMAGE")
    data_url = str(item.get("data_url", ""))
    if not data_url.startswith("data:image/") or "," not in data_url:
        raise ValueError("INVALID_IMAGE")
    header, encoded = data_url.split(",", 1)
    mime_type = header[5:].split(";", 1)[0].lower()
    if mime_type not in {"image/jpeg", "image/png", "image/webp"}:
        raise ValueError("UNSUPPORTED_IMAGE")
    try:
        raw = base64.b64decode(encoded, validate=True)
        with Image.open(BytesIO(raw)) as image:
            image.verify()
    except (ValueError, OSError):
        raise ValueError("INVALID_IMAGE") from None
    if len(raw) > max_bytes:
        raise ValueError("IMAGE_TOO_LARGE")
    return mime_type, raw


def brand_asset_path(file_name: str) -> Path | None:
    if not file_name:
        return None
    path = BRAND_DIR / Path(file_name).name
    return path if path.exists() and path.parent == BRAND_DIR else None


def brand_for_booth(booth_code: str) -> dict | None:
    matches = [item for item in BRAND_REGISTRY.values() if isinstance(item, dict) and item.get("booth_code") == booth_code]
    return max(matches, key=lambda item: str(item.get("created_at", "")), default=None)


def apply_brand_layer(frame: Image.Image, brand: dict | None) -> Image.Image:
    if not brand:
        return frame
    canvas = frame.convert("RGBA")
    width, height = canvas.size
    logo_path = brand_asset_path(str(brand.get("logo_file", "")))
    board_path = brand_asset_path(str(brand.get("board_file", "")))
    if logo_path:
        with Image.open(logo_path) as source:
            logo = ImageOps.contain(source.convert("RGBA"), (max(80, int(width * 0.24)), max(60, int(height * 0.16))))
        canvas.alpha_composite(logo, (width - logo.width - 24, 24))
    if board_path:
        with Image.open(board_path) as source:
            board = ImageOps.contain(source.convert("RGBA"), (max(160, int(width * 0.82)), max(100, int(height * 0.26))))
        canvas.alpha_composite(board, ((width - board.width) // 2, height - board.height - 26))
    return canvas.convert("RGB")


def make_demo_video(video_id: str, image_payloads: list[bytes], aspect_ratio: str, brand: dict | None = None) -> tuple[str, str]:
    GENERATION_DIR.mkdir(parents=True, exist_ok=True)
    width, height = (720, 1280) if aspect_ratio == "9:16" else (1280, 720)
    frame = Image.new("RGB", (width, height), (11, 18, 32))
    draw = ImageDraw.Draw(frame)
    if image_payloads:
        tile_width = width // len(image_payloads)
        for index, raw in enumerate(image_payloads):
            with Image.open(BytesIO(raw)) as source:
                image = ImageOps.contain(source.convert("RGB"), (tile_width - 24, height - 110))
            left = index * tile_width + (tile_width - image.width) // 2
            top = 60 + (height - 110 - image.height) // 2
            frame.paste(image, (left, top))
            draw.rectangle((index * tile_width + 8, 8, (index + 1) * tile_width - 8, height - 8), outline=(153, 246, 198), width=3)
    else:
        draw.ellipse((width // 2 - 90, height // 2 - 90, width // 2 + 90, height // 2 + 90), outline=(153, 246, 198), width=8)
    draw.text((24, 22), "sayelf-pet-story-agent / local demo video", fill=(220, 229, 240))
    frame = apply_brand_layer(frame, brand)
    frame_path = GENERATION_DIR / f"{video_id}.png"
    video_path = GENERATION_DIR / f"{video_id}.mp4"
    frame.save(frame_path, format="PNG")
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        raise RuntimeError("VIDEO_RENDER_UNAVAILABLE")
    result = subprocess.run(
        [ffmpeg, "-y", "-loop", "1", "-i", str(frame_path), "-t", "3", "-r", "24", "-c:v", "libx264", "-preset", "veryfast", "-crf", "18", "-pix_fmt", "yuv420p", "-movflags", "faststart", str(video_path)],
        capture_output=True,
        text=True,
        timeout=30,
    )
    if result.returncode != 0 or not video_path.exists():
        raise RuntimeError("VIDEO_RENDER_FAILED")
    return video_path.name, frame_path.name


def make_demo_image_assets(video_id: str, frame_file: str, image_count: int) -> list[str]:
    source_path = GENERATION_DIR / Path(frame_file).name
    if not source_path.exists():
        return []
    with Image.open(source_path) as source:
        image = source.convert("RGB")
        files = []
        for index in range(image_count):
            output_name = f"{video_id}-image-{index + 1}.png"
            image.save(GENERATION_DIR / output_name, format="PNG", optimize=True)
            files.append(output_name)
        return files


def public_generation(record: dict) -> dict:
    video_urls = [f"/api/videos/{record['generation_id']}?index={index}" for index in range(len(record.get("video_files", [])))]
    download_urls = [f"/api/videos/{record['generation_id']}?index={index}&download=1" for index in range(len(record.get("video_files", [])))]
    image_urls = [f"/api/generated-images/{record['generation_id']}/{index}" for index in range(len(record.get("image_files", [])))]
    return {
        "generation_id": record["generation_id"],
        "status": record["status"],
        "provider": record["provider"],
        "model_id": record["model_id"],
        "video_url": video_urls[0] if video_urls else "",
        "download_url": download_urls[0] if download_urls else "",
        "video_urls": video_urls,
        "download_urls": download_urls,
        "image_urls": image_urls,
        "created_at": record["created_at"],
        "image_count": record["image_count"],
        "video_count": record["video_count"],
        "credits_charged": record["credits_charged"],
    }


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
        "brand_id": record.get("brand_id"),
        "model_id": record.get("model_id", DEFAULT_MODEL_ID),
        "brand_ready": bool(record.get("brand_id")),
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
        if parsed.path == "/api/generation/quota":
            query = parse_qs(parsed.query)
            visitor_id = query.get("visitor_id", ["anonymous"])[0]
            booth_code = query.get("booth_code", ["A17"])[0]
            self.send_json(quota_snapshot(visitor_id, "booth:" + booth_code))
            return
        if parsed.path == "/api/billing/account":
            query = parse_qs(parsed.query)
            booth_code = query.get("booth_code", ["A17"])[0]
            account = billing_snapshot("booth:" + booth_code)
            account["model_catalog"] = public_model_catalog()
            self.send_json(account)
            return
        if parsed.path == "/api/qr/options":
            options = dict(PILOT_OPTIONS)
            options["models"] = public_model_catalog()
            self.send_json(options)
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
        if len(parts) == 3 and parts[:2] == ["api", "videos"]:
            record = GENERATION_REGISTRY.get(parts[2])
            if not isinstance(record, dict):
                self.send_json({"error": "VIDEO_NOT_FOUND"}, 404)
                return
            files = record.get("video_files") or [record.get("video_file", "")]
            try:
                index = max(0, min(int(parse_qs(parsed.query).get("index", ["0"])[0]), len(files) - 1))
            except (TypeError, ValueError):
                index = 0
            video_path = GENERATION_DIR / Path(str(files[index])).name
            if not video_path.exists() or video_path.parent != GENERATION_DIR:
                self.send_json({"error": "VIDEO_ASSET_NOT_FOUND"}, 404)
                return
            download_name = video_path.name if parse_qs(parsed.query).get("download", [""])[0] == "1" else None
            self.send_bytes(video_path.read_bytes(), "video/mp4", download_name)
            return
        if len(parts) == 4 and parts[:2] == ["api", "generated-images"]:
            record = GENERATION_REGISTRY.get(parts[2])
            if not isinstance(record, dict):
                self.send_json({"error": "IMAGE_NOT_FOUND"}, 404)
                return
            try:
                image_path = GENERATION_DIR / Path(str(record.get("image_files", [])[int(parts[3])])).name
            except (IndexError, TypeError, ValueError):
                self.send_json({"error": "IMAGE_NOT_FOUND"}, 404)
                return
            if not image_path.exists() or image_path.parent != GENERATION_DIR:
                self.send_json({"error": "IMAGE_ASSET_NOT_FOUND"}, 404)
                return
            self.send_bytes(image_path.read_bytes(), "image/png")
            return
        super().do_GET()

    def do_POST(self) -> None:
        parsed = urlsplit(self.path)
        if parsed.path == "/api/billing/grant":
            if int(self.headers.get("Content-Length", "0")) > MAX_ADMIN_BODY:
                self.send_json({"error": "PAYLOAD_TOO_LARGE"}, 413)
                return
            body = self.read_json()
            booth_code = str(body.get("booth_code", "")).strip()[:32]
            try:
                credits = int(body.get("credits", 0))
            except (TypeError, ValueError):
                self.send_json({"error": "INVALID_CREDITS"}, 400)
                return
            if not booth_code or credits <= 0 or credits > 100000:
                self.send_json({"error": "INVALID_CREDITS"}, 400)
                return
            with STATE_LOCK:
                account = billing_account("booth:" + booth_code)
                account["credits"] = int(account.get("credits", 0)) + credits
                account["updated_at"] = utc_now()
                save_json_object(BILLING_PATH, BILLING_REGISTRY)
                self.send_json(billing_snapshot("booth:" + booth_code), 201)
            return
        if parsed.path == "/api/generation/submit":
            content_length = int(self.headers.get("Content-Length", "0"))
            if content_length > MAX_GENERATION_BODY:
                self.send_json({"error": "PAYLOAD_TOO_LARGE"}, 413)
                return
            body = self.read_json()
            visitor_id = str(body.get("visitor_id", "")).strip()[:128] or "anonymous"
            input_text = str(body.get("input_text", "")).strip()[:4000]
            booth_code = str(body.get("booth_code", "A17")).strip()[:32] or "A17"
            account_key = "booth:" + booth_code
            raw_images = body.get("images", [])
            if not isinstance(raw_images, list):
                self.send_json({"error": "INVALID_IMAGES"}, 400)
                return
            if len(raw_images) > MAX_IMAGES_PER_REQUEST:
                self.send_json({"error": "IMAGE_LIMIT", "image_limit": MAX_IMAGES_PER_REQUEST}, 400)
                return
            if not input_text and not raw_images:
                self.send_json({"error": "EMPTY_INPUT"}, 400)
                return
            try:
                image_payloads = [decode_image_item(item)[1] for item in raw_images]
            except ValueError as error:
                self.send_json({"error": str(error)}, 400)
                return
            try:
                video_count = int(body.get("video_count", 1))
                image_count = int(body.get("image_count", 2))
            except (TypeError, ValueError):
                self.send_json({"error": "INVALID_OUTPUT_COUNT"}, 400)
                return
            if video_count < 1 or video_count > MAX_REQUEST_VIDEO_COUNT or image_count < 0 or image_count > MAX_REQUEST_IMAGE_COUNT:
                self.send_json({"error": "INVALID_OUTPUT_COUNT", "video_limit": MAX_REQUEST_VIDEO_COUNT, "image_limit": MAX_REQUEST_IMAGE_COUNT}, 400)
                return
            idempotency_key = str(body.get("idempotency_key", "")).strip()[:128] or uuid.uuid4().hex
            brand = brand_for_booth(booth_code)
            model_id = str(body.get("model_id", "")).strip() or str((brand or {}).get("model_id", DEFAULT_MODEL_ID))
            if model_id not in MODEL_CATALOG:
                self.send_json({"error": "MODEL_NOT_FOUND"}, 400)
                return
            existing, error, reservation = reserve_generation(visitor_id, video_count, image_count, model_id, account_key, idempotency_key)
            if existing:
                existing = dict(existing)
                existing["quota"] = quota_snapshot(visitor_id, account_key)
                self.send_json(existing)
                return
            if error:
                self.send_json(error, 402 if error.get("error") == "INSUFFICIENT_CREDITS" else 429)
                return
            try:
                generation_id = "video-" + uuid.uuid4().hex[:12]
                video_files = []
                frame_file = ""
                for index in range(video_count):
                    video_file, frame_file = make_demo_video(f"{generation_id}-v{index + 1}", image_payloads, str(body.get("aspect_ratio", "9:16")), brand)
                    video_files.append(video_file)
                image_files = make_demo_image_assets(generation_id, frame_file, image_count)
                record = {
                    "generation_id": generation_id,
                    "status": "READY",
                    "provider": model_config(model_id)["provider"],
                    "model_id": model_id,
                    "created_at": utc_now(),
                    "image_count": image_count,
                    "video_count": video_count,
                    "credits_charged": reservation["credits"],
                    "video_files": video_files,
                    "image_files": image_files,
                }
                GENERATION_REGISTRY[generation_id] = record
                save_json_object(GENERATION_REGISTRY_PATH, GENERATION_REGISTRY)
                response = public_generation(record)
                response["quota"] = quota_snapshot(visitor_id, account_key)
                response["billing"] = billing_snapshot(account_key)
                response["returned_to_user"] = True
                remember_generation(visitor_id, idempotency_key, response)
                self.send_json(response, 201)
            except RuntimeError as error:
                release_generation(visitor_id, reservation)
                self.send_json({"error": str(error), "message": "LOCAL_VIDEO_FAILED"}, 503)
            except Exception:
                release_generation(visitor_id, reservation)
                self.send_json({"error": "GENERATION_FAILED"}, 500)
            return
        if parsed.path != "/api/qr/generate":
            self.send_json({"error": "NOT_FOUND"}, 404)
            return
        if int(self.headers.get("Content-Length", "0")) > MAX_ADMIN_BODY:
            self.send_json({"error": "PAYLOAD_TOO_LARGE"}, 413)
            return
        body = self.read_json()
        event = find_option("events", "id", str(body.get("event_id", "")))
        exhibitor = find_option("exhibitors", "id", str(body.get("exhibitor_id", "")))
        booth = next((item for item in PILOT_OPTIONS["booths"] if item["code"] == str(body.get("booth_code", "")) and item["exhibitor_id"] == str(body.get("exhibitor_id", ""))), None)
        campaign = find_option("campaigns", "id", str(body.get("campaign_id", "")))
        if not event or not exhibitor or not booth or not campaign or exhibitor["event_id"] != event["id"] or campaign["event_id"] != event["id"]:
            self.send_json({"error": "INVALID_SELECTION"}, 400)
            return
        model_id = str(body.get("model_id", DEFAULT_MODEL_ID)).strip() or DEFAULT_MODEL_ID
        if model_id not in MODEL_CATALOG:
            self.send_json({"error": "MODEL_NOT_FOUND"}, 400)
            return
        brand_id = None
        brand = {"booth_code": booth["code"], "model_id": model_id, "created_at": utc_now()}
        for kind, body_key in (("logo", "brand_logo"), ("board", "brand_board")):
            raw_asset = body.get(body_key)
            if not raw_asset:
                continue
            try:
                mime_type, raw = decode_image_item(raw_asset, MAX_BRAND_ASSET_BYTES)
            except ValueError as error:
                self.send_json({"error": "INVALID_BRAND_" + kind.upper(), "detail": str(error)}, 400)
                return
            if brand_id is None:
                brand_id = "brand-" + uuid.uuid4().hex[:12]
            extension = {"image/jpeg": "jpg", "image/png": "png", "image/webp": "webp"}[mime_type]
            file_name = f"{brand_id}-{kind}.{extension}"
            BRAND_DIR.mkdir(parents=True, exist_ok=True)
            (BRAND_DIR / file_name).write_bytes(raw)
            brand[kind + "_file"] = file_name
        if brand_id:
            brand["id"] = brand_id
            BRAND_REGISTRY[brand_id] = brand
            save_json_object(BRAND_REGISTRY_PATH, BRAND_REGISTRY)
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
            "brand_id": brand_id,
            "model_id": model_id,
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
