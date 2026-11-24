"""A small streaming PDF 1.4 writer: JPEG bytes are copied, never recompressed.

Only object offsets and page IDs remain in memory. Qt renders Unicode labels one
page at a time, including Windows font fallback and Bengali/Devanagari shaping.
"""
from __future__ import annotations

from io import BytesIO
from pathlib import Path
import shutil

from PIL import Image
from PySide6.QtCore import QBuffer, QIODevice, QRectF
from PySide6.QtGui import QColor, QFont, QImage, QPainter, QTextDocument
from html import escape
from fonts import ensure_fonts

WIDTH, HEIGHT = 841.89, 595.28  # A4 landscape, in points


def text_image(lines: list[str], width: int, height: int, size: int = 24) -> bytes:
    ensure_fonts()
    image = QImage(width, height, QImage.Format.Format_RGB32)
    image.fill(QColor('white'))
    document = QTextDocument()
    document.setDefaultFont(text_font(size))
    document.setTextWidth(width - 60)
    document.setHtml('<br><br>'.join(escape(line) for line in lines))
    while document.size().height() > height - 50 and size > 7:
        size -= 1
        document.setDefaultFont(text_font(size))
    painter = QPainter(image)
    painter.translate(30, 25)
    document.drawContents(painter, QRectF(0, 0, width - 60, height - 50))
    painter.end()
    buffer = QBuffer()
    buffer.open(QIODevice.OpenModeFlag.WriteOnly)
    if not image.save(buffer, 'JPEG', 95):
        raise RuntimeError('Could not render a PDF label.')
    return bytes(buffer.data())


class StreamingPDF:
    def __init__(self, path: Path):
        self.file = path.open('w+b')
        self.file.write(b'%PDF-1.4\n%\xe2\xe3\xcf\xd3\n')
        self.offsets: list[int | None] = [None, None, None]
        self.pages: list[int] = []

    def checkpoint(self):
        return self.file.tell(), len(self.offsets), len(self.pages)

    def rollback(self, checkpoint):
        position, objects, pages = checkpoint
        self.file.seek(position)
        self.file.truncate()
        del self.offsets[objects:]
        del self.pages[pages:]

    def _begin(self, number: int | None = None) -> int:
        if number is None:
            number = len(self.offsets)
            self.offsets.append(None)
        self.offsets[number] = self.file.tell()
        self.file.write(f'{number} 0 obj\n'.encode('ascii'))
        return number

    def _object(self, body: bytes, number: int | None = None) -> int:
        index = self._begin(number)
        self.file.write(body + b'\nendobj\n')
        return index

    def _image(self, source: Path | bytes) -> tuple[int, int, int]:
        stream = source.open('rb') if isinstance(source, Path) else BytesIO(source)
        with stream:
            with Image.open(stream) as header:
                width, height = header.size
                if header.format != 'JPEG' or header.mode != 'RGB':
                    raise ValueError('PDF images must be RGB JPEGs.')
            # Pillow closes a supplied stream only in special cases; reopen to be explicit.
        stream = source.open('rb') if isinstance(source, Path) else BytesIO(source)
        with stream:
            stream.seek(0, 2)
            length = stream.tell()
            stream.seek(0)
            number = self._begin()
            self.file.write((f'<< /Type /XObject /Subtype /Image /Width {width} /Height {height} '
                f'/ColorSpace /DeviceRGB /BitsPerComponent 8 /Filter /DCTDecode /Length {length} >>\nstream\n').encode('ascii'))
            shutil.copyfileobj(stream, self.file, length=1024 * 1024)
            self.file.write(b'\nendstream\nendobj\n')
        return number, width, height

    def add_page(self, image: Path | bytes, caption: str = '') -> None:
        number, width, height = self._image(image)
        available_h = HEIGHT - (74 if caption else 36)
        scale = min((WIDTH - 36) / width, available_h / height)
        w, h = width * scale, height * scale
        x, y = (WIDTH - w) / 2, (74 if caption else 36) / 2 + (available_h - h) / 2
        if caption:
            y += 18
        commands = f'q {w:.3f} 0 0 {h:.3f} {x:.3f} {y:.3f} cm /Im0 Do Q\n'
        resources = f'/Im0 {number} 0 R'
        if caption:
            label, _, _ = self._image(text_image([caption], 1684, 100, 19))
            resources += f' /Im1 {label} 0 R'
            commands += f'q {WIDTH - 36:.3f} 0 0 46 18 6 cm /Im1 Do Q\n'
        content = commands.encode('ascii')
        content_id = self._object(f'<< /Length {len(content)} >>\nstream\n'.encode() + content + b'endstream')
        page = self._object((f'<< /Type /Page /Parent 2 0 R /MediaBox [0 0 {WIDTH} {HEIGHT}] '
            f'/Resources << /XObject << {resources} >> >> /Contents {content_id} 0 R >>').encode('ascii'))
        self.pages.append(page)

    def title_page(self, number: int, info: dict, url: str):
        from utils import timestamp
        duration = timestamp(float(info['duration'])) if info.get('duration') else 'Unknown'
        self.add_page(text_image([f'Video {number}', str(info.get('title', 'Untitled')), url,
                                  f'Duration: {duration}'], 1684, 1190, 35))

    def error_page(self, number: int, url: str, reason: str):
        self.add_page(text_image([f'Video {number} — failed', url, reason[:1800]], 1684, 1190, 28))

    def finish(self):
        self._object(b'<< /Type /Catalog /Pages 2 0 R >>', 1)
        kids = ' '.join(f'{page} 0 R' for page in self.pages)
        self._object(f'<< /Type /Pages /Count {len(self.pages)} /Kids [{kids}] >>'.encode('ascii'), 2)
        start = self.file.tell()
        self.file.write(f'xref\n0 {len(self.offsets)}\n0000000000 65535 f \n'.encode('ascii'))
        for offset in self.offsets[1:]:
            if offset is None or offset >= 10**10:
                raise ValueError('PDF exceeded the supported size.')
            self.file.write(f'{offset:010d} 00000 n \n'.encode('ascii'))
        self.file.write((f'trailer\n<< /Size {len(self.offsets)} /Root 1 0 R >>\n'
                         f'startxref\n{start}\n%%EOF\n').encode('ascii'))
        self.file.flush()

    def close(self):
        self.file.close()


def text_font(size):
    from PySide6.QtGui import QGuiApplication
    font = QFont(QGuiApplication.font())
    font.setPointSize(size)
    return font
