"""Make Windows fonts available to Qt's offscreen PDF renderer as well."""
from functools import lru_cache
import os
from pathlib import Path

from PySide6.QtGui import QFont, QFontDatabase, QGuiApplication


@lru_cache(maxsize=1)
def ensure_fonts():
    if os.name == 'nt':
        folder = Path(os.environ.get('WINDIR', os.environ.get('SystemRoot', ''))) / 'Fonts'
        for filename in ('segoeui.ttf', 'segoeuib.ttf', 'Nirmala.ttc', 'Nirmala.ttf', 'NirmalaB.ttf', 'vrinda.ttf', 'mangal.ttf'):
            path = folder / filename
            if path.is_file():
                QFontDatabase.addApplicationFont(str(path))
    if QGuiApplication.instance():
        QGuiApplication.setFont(QFont('Segoe UI', 10) if os.name == 'nt' else
                                QFontDatabase.systemFont(QFontDatabase.SystemFont.GeneralFont))
