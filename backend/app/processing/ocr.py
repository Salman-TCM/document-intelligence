import pytesseract
from PIL import Image, ImageFilter, ImageOps

MIN_WIDTH = 1600
# psm 4 reads the page as a single column, which keeps table rows on one line.
# The default (psm 3) tends to split the right-hand amount column off on its own.
# Chosen by comparing psm 3/4/6 on the eval set (see eval/report.md).
TESSERACT_CONFIG = "--psm 4"


def prepare(image: Image.Image) -> Image.Image:
    """Clean up a scan or photo so Tesseract has an easier job."""
    image = ImageOps.exif_transpose(image).convert("L")
    image = image.filter(ImageFilter.MedianFilter(3))  # removes speckle noise; do it before upscaling
    if image.width < MIN_WIDTH:
        scale = MIN_WIDTH / image.width
        image = image.resize((MIN_WIDTH, int(image.height * scale)), Image.LANCZOS)
    return image


def ocr_image(image: Image.Image) -> str:
    return pytesseract.image_to_string(prepare(image), config=TESSERACT_CONFIG)
