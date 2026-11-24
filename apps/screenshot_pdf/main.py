from __future__ import annotations

import multiprocessing
import sys


def main() -> int:
    try:
        from PySide6.QtWidgets import QApplication, QMessageBox
    except ImportError:
        message = 'PySide6 is missing. Close this window and run setup.bat first.'
        if sys.platform == 'win32':
            import ctypes
            ctypes.windll.user32.MessageBoxW(None, message, 'Setup needed', 0x10)
        else:
            print(message)
        return 1
    app = QApplication(sys.argv)
    app.setStyle('Fusion')
    try:
        from app_config import APP_ID
        from settings import setup_logging
        setup_logging(APP_ID)
        from gui import MainWindow
        window = MainWindow()
        window.show()
        return app.exec()
    except Exception as exc:
        import logging
        logging.exception('Application startup failed')
        QMessageBox.critical(None, 'Unable to start', f'{exc}\n\nRun setup.bat and read README.md for dependency setup.')
        return 1


if __name__ == '__main__':
    multiprocessing.freeze_support()
    raise SystemExit(main())
