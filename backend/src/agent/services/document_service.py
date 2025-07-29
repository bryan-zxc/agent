import fitz  # PyMuPDF
import pymupdf4llm
import statistics
import io
import base64
from pathlib import Path
from PIL import Image
from ..models.schemas import (
    ImageContent,
    PDFContent,
    PageContent,
    PDFMetaSummary,
    PDFType,
)


def extract_images_from_page(
    page: fitz.Page, page_number: int, min_tokens: int = 64
):
    images = []
    pixel_limit = min_tokens * 32 * 32
    
    # Get image list from page
    image_list = page.get_images()
    
    for i, img in enumerate(image_list):
        # Get image object
        xref = img[0]
        pix = fitz.Pixmap(page.parent, xref)
        
        # Skip if image is too small
        if pix.width * pix.height < pixel_limit:
            pix = None
            continue
            
        # Convert to PIL Image if not GRAY or RGB
        if pix.n - pix.alpha < 4:  # GRAY or RGB
            img_data = pix.tobytes("png")
            pil_image = Image.open(io.BytesIO(img_data))
            
            image_content = ImageContent(
                image_name=f"pg{str(page_number).zfill(4)}_im_{str(i).zfill(3)}",
                image_width=pix.width,
                image_height=pix.height,
                image_data=base64.b64encode(img_data).decode("utf-8"),
            )
            images.append(image_content)
        
        pix = None  # Free memory
    
    return images


def extract_document_content(pdf_path: str) -> PDFContent:
    # Use pymupdf4llm for markdown extraction with page chunks
    md_pages = pymupdf4llm.to_markdown(pdf_path, page_chunks=True)
    
    # Open document with PyMuPDF for image extraction
    doc = fitz.open(pdf_path)
    pages = []
    
    for i, page in enumerate(doc):
        # Use page label if available, otherwise use page number (1-indexed)
        page_label = page.get_label()
        page_number = page_label if page_label else str(i + 1)
        
        # Get markdown text for this page
        if i < len(md_pages):
            text = md_pages[i]['text']
        else:
            text = ""
        
        # Extract images from the page
        images = extract_images_from_page(page, page_number)

        # Create PageContent object
        page_content = PageContent(page_number=page_number, text=text, images=images)
        pages.append(page_content)

    doc.close()
    return PDFContent(pages=pages)


def create_document_meta_summary(
    document_content: PDFContent,
) -> PDFMetaSummary:
    pages = document_content.pages

    # Calculate basic metrics
    num_pages = len(pages)
    num_images = sum(len(page.images) for page in pages)

    # Calculate text length metrics
    page_text_lengths = [len(page.text) for page in pages]
    total_text_length = sum(page_text_lengths)
    max_page_text_length = max(page_text_lengths) if page_text_lengths else 0

    # Calculate median (handle empty case)
    median_page_text_length = (
        statistics.median(page_text_lengths) if page_text_lengths else 0
    )

    return PDFMetaSummary(
        num_pages=num_pages,
        num_images=num_images,
        total_text_length=total_text_length,
        max_page_text_length=max_page_text_length,
        median_page_text_length=int(median_page_text_length),
    )