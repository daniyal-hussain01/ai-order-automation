"""OCR engine — wraps Tesseract for images and pdf2image for PDFs."""
import io
import logging
import shutil
from dataclasses import dataclass
from typing import Optional

from PIL import Image

from app.config import settings

log = logging.getLogger("ocr")


@dataclass
class OCRResult:
    text: str
    confidence: float  # 0.0 - 1.0


class OCREngine:
    def __init__(self) -> None:
        try:
            import pytesseract  # noqa: F401
            self._pytesseract = pytesseract
            if shutil.which(settings.TESSERACT_CMD):
                pytesseract.pytesseract.tesseract_cmd = settings.TESSERACT_CMD
            self._ok = True
        except Exception as exc:
            log.warning("pytesseract unavailable: %s", exc)
            self._pytesseract = None
            self._ok = False

    def available(self) -> bool:
        return self._ok and shutil.which(settings.TESSERACT_CMD) is not None

    def run(self, content: bytes, mime_type: Optional[str] = None) -> OCRResult:
        """Run OCR on image bytes or PDF bytes; returns OCRResult."""
        if mime_type == "application/pdf":
            return self._ocr_pdf(content)
        return self._ocr_image(content)

    def _ocr_image(self, content: bytes) -> OCRResult:
        img = Image.open(io.BytesIO(content))
        if img.mode != "RGB":
            img = img.convert("RGB")
        return self._tesseract(img)

    def _ocr_pdf(self, content: bytes) -> OCRResult:
        try:
            from pdf2image import convert_from_bytes
        except Exception as exc:
            raise RuntimeError(f"pdf2image not installed: {exc}") from exc

        pages = convert_from_bytes(content, dpi=200, fmt="png")
        if not pages:
            return OCRResult(text="", confidence=0.0)

        texts, confs = [], []
        for page in pages:
            r = self._tesseract(page)
            texts.append(r.text)
            confs.append(r.confidence)
        return OCRResult(
            text="\n\n".join(texts),
            confidence=sum(confs) / max(len(confs), 1),
        )

    def _tesseract(self, img: Image.Image) -> OCRResult:
        if not self._ok:
            # Graceful fallback: return empty so the pipeline still demos
            return OCRResult(text="", confidence=0.0)

        try:
            data = self._pytesseract.image_to_data(
                img, lang=settings.OCR_LANG,
                output_type=self._pytesseract.Output.DICT,
            )
            # Reconstruct text preserving line breaks using tesseract's block/par/line
            # numbers. Without this, all words collapse onto one line and downstream
            # line-by-line parsers (e.g. line-item extraction) only see the first match.
            lines: dict = {}
            order: list = []
            for i, w in enumerate(data.get("text", [])):
                if not w or not w.strip():
                    continue
                key = (
                    data.get("block_num", [0])[i],
                    data.get("par_num", [0])[i],
                    data.get("line_num", [0])[i],
                )
                if key not in lines:
                    lines[key] = []
                    order.append(key)
                lines[key].append(w)
            text = "\n".join(" ".join(lines[k]) for k in order)
            # tesseract confidences in [0,100], -1 means missing
            nums = [float(c) for c in data.get("conf", []) if c not in ("-1", -1, "", None)]
            conf = (sum(nums) / len(nums) / 100.0) if nums else 0.0
            return OCRResult(text=text, confidence=round(conf, 3))
        except Exception as exc:
            log.exception("Tesseract failed")
            return OCRResult(text="", confidence=0.0)
