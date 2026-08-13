"""
Extraction Utilities — Reusable functions for PDF text + image extraction.

Used by both:
  - extract_pipelinev2.py (batch processing)
  - api/main.py (live upload endpoint)
"""

import os
import base64
import fitz  # PyMuPDF
import boto3
from openai import OpenAI
from dotenv import load_dotenv

load_dotenv()

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

# S3 Configuration
S3_BUCKET_NAME = os.getenv("S3_BUCKET_NAME", "final-project-inmind")
AWS_REGION = os.getenv("AWS_REGION", "eu-north-1")
S3_PREFIX = "images/"  # Folder prefix in the bucket

# Initialize S3 client
s3_client = boto3.client(
    "s3",
    region_name=AWS_REGION,
    aws_access_key_id=os.getenv("AWS_ACCESS_KEY_ID"),
    aws_secret_access_key=os.getenv("AWS_SECRET_ACCESS_KEY"),
)

MIN_IMAGE_WIDTH = 80
MIN_IMAGE_HEIGHT = 80


def caption_image(img_bytes: bytes, page_num: int, img_index: int, manual_name: str) -> str:
    """Send an image to GPT-4o Vision and get a descriptive caption."""
    img_b64 = base64.b64encode(img_bytes).decode("utf-8")

    prompt = f"""You are a technical documentation analyst. This image is extracted from page {page_num} 
of the "{manual_name}" drone user manual.

Describe this image in detail for a text-based search system. Include:
- What the image depicts (diagram, table, chart, photo, icon, etc.)
- All labeled components, buttons, ports, or parts visible
- Any numerical values, measurements, or specifications shown
- Spatial relationships (e.g., "the USB-C port is on the bottom left")
- LED indicator colors/patterns if applicable
- Any arrows, callouts, or annotations

Be factual and thorough. This caption will replace the image in a text-only document used for RAG retrieval.
Write 2-5 sentences."""

    messages = [
        {
            "role": "user",
            "content": [
                {"type": "text", "text": prompt},
                {
                    "type": "image_url",
                    "image_url": {
                        "url": f"data:image/png;base64,{img_b64}",
                        "detail": "high",
                    },
                },
            ],
        }
    ]

    try:
        response = client.chat.completions.create(
            model="gpt-4o",
            messages=messages,
            max_tokens=300,
            temperature=0.2,
        )
        return response.choices[0].message.content.strip()
    except Exception as e:
        return f"[Image caption unavailable: {e}]"


def extract_page_images(page, doc, seen_xrefs: set) -> list:
    """Extract all meaningful images from a PDF page, skipping duplicates."""
    images = []
    image_list = page.get_images(full=True)

    for img_index, img_info in enumerate(image_list):
        xref = img_info[0]

        if xref in seen_xrefs:
            continue

        try:
            base_image = doc.extract_image(xref)
            if base_image is None:
                continue

            img_bytes = base_image["image"]
            width = base_image["width"]
            height = base_image["height"]

            if width < MIN_IMAGE_WIDTH or height < MIN_IMAGE_HEIGHT:
                continue

            ext = base_image["ext"]
            if ext != "png":
                pix = fitz.Pixmap(img_bytes)
                if pix.n > 4:
                    pix = fitz.Pixmap(fitz.csRGB, pix)
                img_bytes = pix.tobytes("png")

            seen_xrefs.add(xref)
            images.append({
                "bytes": img_bytes,
                "width": width,
                "height": height,
                "index": img_index,
                "xref": xref,
            })
        except Exception:
            continue

    return images


def render_page_as_image(page) -> bytes:
    """Render the full page as a PNG image."""
    pix = page.get_pixmap(dpi=150)
    return pix.tobytes("png")


def has_visual_content(page) -> bool:
    """Check if a page has important diagrams that aren't extractable as embedded images."""
    images = page.get_images(full=True)
    if len(images) >= 1:
        return False

    text = page.get_text("text")
    text_lower = text.lower()

    strong_visual_indicators = [
        "status indicator", "front led", "detection range",
        "optimal transmission zone", "mode 1",
    ]

    has_strong_keyword = any(kw in text_lower for kw in strong_visual_indicators)
    drawings = page.get_drawings()
    has_substantial_drawings = len(drawings) > 50

    return has_strong_keyword and has_substantial_drawings


def save_image(img_bytes: bytes, doc_name: str, page_num: int, img_index: int, images_dir: str) -> str:
    """
    Save image to disk under the document's name prefix.
    Returns the relative path from project root.

    Naming: {doc_name}_page{N}_img{I}.png
    This makes deletion easy — just delete all files starting with {doc_name}_
    """
    os.makedirs(images_dir, exist_ok=True)

    # Clean document name for filesystem
    doc_stem = doc_name.replace(".pdf", "").replace(" ", "_")
    filename = f"{doc_stem}_page{page_num}_img{img_index}.png"
    filepath = os.path.join(images_dir, filename)

    with open(filepath, "wb") as f:
        f.write(img_bytes)

    return filepath


def upload_image_to_s3(img_bytes: bytes, doc_name: str, page_num: int, img_index: int) -> str:
    """
    Upload image to S3 and return the public URL.

    Naming: images/{doc_name}_page{N}_img{I}.png
    Returns: https://{bucket}.s3.{region}.amazonaws.com/images/{filename}
    """
    doc_stem = doc_name.replace(".pdf", "").replace(" ", "_")
    filename = f"{doc_stem}_page{page_num}_img{img_index}.png"
    s3_key = f"{S3_PREFIX}{filename}"

    try:
        s3_client.put_object(
            Bucket=S3_BUCKET_NAME,
            Key=s3_key,
            Body=img_bytes,
            ContentType="image/png",
        )

        url = f"https://{S3_BUCKET_NAME}.s3.{AWS_REGION}.amazonaws.com/{s3_key}"
        return url

    except Exception as e:
        print(f"  ⚠ S3 upload failed for {filename}: {e}")
        return ""


def extract_pdf(
    pdf_path: str,
    doc_name: str,
    images_dir: str,
    caption_images: bool = True,
    upload_to_s3: bool = True,
) -> list[dict]:
    """
    Full extraction pipeline for a single PDF.

    Returns a list of page dicts:
    [
        {
            "page": 1,
            "text": "...",       # Extracted text + captions inlined
            "image_paths": [...], # List of saved image file paths
            "image_urls": [...],  # List of S3 URLs (if upload_to_s3=True)
        },
        ...
    ]

    Args:
        pdf_path: Path to the PDF file
        doc_name: Document name (used for image naming)
        images_dir: Directory to save extracted images
        caption_images: Whether to caption images with GPT-4o (expensive but better)
        upload_to_s3: Whether to upload images to S3 and store URLs
    """
    doc = fitz.open(pdf_path)
    pages = []
    seen_xrefs = set()

    for page_num in range(len(doc)):
        page = doc[page_num]
        page_number = page_num + 1

        text = page.get_text("text").strip()

        if len(text) < 50:
            continue

        page_text_parts = [text]
        page_image_paths = []
        page_image_urls = []

        # Extract embedded images
        images = extract_page_images(page, doc, seen_xrefs)

        if images:
            for img in images:
                # Save image to disk
                img_filepath = save_image(
                    img["bytes"], doc_name, page_number, img["index"], images_dir
                )
                page_image_paths.append(img_filepath)

                # Upload to S3
                img_url = ""
                if upload_to_s3:
                    img_url = upload_image_to_s3(
                        img["bytes"], doc_name, page_number, img["index"]
                    )
                    if img_url:
                        page_image_urls.append(img_url)

                # Caption if enabled
                if caption_images:
                    caption = caption_image(img["bytes"], page_number, img["index"], doc_name)
                else:
                    caption = "[Image extracted but not captioned]"

                page_text_parts.append(f"\n[IMAGE on Page {page_number} — {img['width']}x{img['height']}px]")
                page_text_parts.append(f"[IMAGE_PATH]: {img_filepath}")
                if img_url:
                    page_text_parts.append(f"[IMAGE_URL]: {img_url}")
                page_text_parts.append(f"[CAPTION]: {caption}")

        # Full-page renders for vector diagrams
        elif has_visual_content(page) and len(text) > 100:
            page_img_bytes = render_page_as_image(page)
            img_filepath = save_image(
                page_img_bytes, doc_name, page_number, 0, images_dir
            )
            page_image_paths.append(img_filepath)

            # Upload to S3
            img_url = ""
            if upload_to_s3:
                img_url = upload_image_to_s3(
                    page_img_bytes, doc_name, page_number, 0
                )
                if img_url:
                    page_image_urls.append(img_url)

            if caption_images:
                caption = caption_image(page_img_bytes, page_number, 0, doc_name)
            else:
                caption = "[Full page render extracted but not captioned]"

            page_text_parts.append(f"\n[VISUAL CONTENT on Page {page_number} — Full page render]")
            page_text_parts.append(f"[IMAGE_PATH]: {img_filepath}")
            if img_url:
                page_text_parts.append(f"[IMAGE_URL]: {img_url}")
            page_text_parts.append(f"[CAPTION]: {caption}")

        pages.append({
            "page": page_number,
            "text": "\n".join(page_text_parts),
            "image_paths": page_image_paths,
            "image_urls": page_image_urls,
        })

    doc.close()
    return pages
