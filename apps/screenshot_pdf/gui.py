"""The GUI only exchanges small messages with a spawned processing process."""
from __future__ import annotations

import logging
import multiprocessing as mp
from pathlib import Path
import queue
import time

from PySide6.QtCore import QTimer, QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (QCheckBox, QComboBox, QFileDialog, QFormLayout, QGroupBox,
    QHBoxLayout, QLabel, QLineEdit, QMainWindow, QMessageBox, QPlainTextEdit,
    QProgressBar, QPushButton, QScrollArea, QSpinBox, QVBoxLayout, QWidget)

from app_config import APP_ID, APP_TITLE, IS_TRANSCRIBER
from dependencies import check_dependencies
from settings import config_folder, load_settings, save_settings
from storage import clean_stale, create_workspace, prepare_folders, remove_workspace, stop_process_tree
from utils import parse_urls, validate_interval


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        from fonts import ensure_fonts
        ensure_fonts()
        self.setWindowTitle(APP_TITLE)
        self.resize(930, 900)
        self.settings = load_settings(APP_ID)
        self.process = None
        self.roots = {}
        self.result = None
        self.cancel_at = None
        self.close_after = False
        self.context = mp.get_context('spawn')
        root = QWidget()
        layout = QVBoxLayout(root)
        self.setCentralWidget(root)
        heading = QLabel(APP_TITLE)
        heading.setStyleSheet('font-size: 25px; font-weight: 600; color: #1b465e; padding: 6px 0;')
        layout.addWidget(heading)
        intro = QLabel('Local processing • No AI API keys or token charges\n'
                       'Use videos you have permission to download and process.')
        intro.setWordWrap(True)
        layout.addWidget(intro)
        self.options = QWidget()
        fields = QVBoxLayout(self.options)
        fields.setContentsMargins(0, 0, 0, 0)
        fields.addWidget(QLabel('YouTube URLs — one per line'))
        self.urls = QPlainTextEdit()
        self.urls.setPlaceholderText('https://www.youtube.com/watch?v=...\nhttps://youtu.be/...\nhttps://www.youtube.com/shorts/...')
        self.urls.setMinimumHeight(130)
        fields.addWidget(self.urls)
        choices = QFormLayout()
        if IS_TRANSCRIBER:
            self.language = QComboBox()
            for label, code in [('Auto Detect', None), ('English', 'en'), ('Bengali / Bangla', 'bn'), ('Hindi', 'hi')]:
                self.language.addItem(label, code)
            self.language.setCurrentIndex(max(0, self.language.findData(self.settings['language'])))
            self.model = QComboBox()
            for label, code in [('Recommended / Auto', 'auto'), ('tiny', 'tiny'), ('base', 'base'),
                                ('small', 'small'), ('medium', 'medium'), ('large-v3', 'large-v3')]:
                self.model.addItem(label, code)
            self.model.setCurrentIndex(max(0, self.model.findData(self.settings['model'])))
            choices.addRow('Language', self.language)
            choices.addRow('Whisper model', self.model)
            hint = QLabel('Smaller = faster, lower accuracy. Larger = slower, usually more accurate.\n'
                          'Auto uses small. Supported GPUs are used automatically, with CPU fallback.\n'
                          'A model is downloaded once into Download/cache → models.')
            hint.setWordWrap(True)
            choices.addRow(hint)
        else:
            self.interval = QLineEdit(str(self.settings['interval']))
            self.interval.setPlaceholderText('Seconds, for example 0.5 or 10')
            choices.addRow('Screenshot interval (seconds)', self.interval)
            self.quality = QSpinBox()
            self.quality.setRange(2, 12)
            self.quality.setValue(int(self.settings['quality']))
            self.quality.setToolTip('2 = best quality, largest files; 12 = smaller files.')
            choices.addRow('JPEG quality (2 best, 12 smallest)', self.quality)
            self.captions = QCheckBox('Show title and timestamp below each screenshot')
            self.captions.setChecked(bool(self.settings['captions']))
            choices.addRow(self.captions)
        fields.addLayout(choices)
        folders = QGroupBox('Storage locations — any writable drive')
        folder_form = QFormLayout(folders)
        self.folders = {}
        for name, label in [('cache', 'Download / cache'), ('temp', 'Temporary processing'), ('output', 'Final output')]:
            row = QHBoxLayout()
            entry = QLineEdit(str(self.settings[name]))
            button = QPushButton('Browse…')
            button.clicked.connect(lambda checked=False, field=entry: self.pick_folder(field))
            row.addWidget(entry, 1)
            row.addWidget(button)
            folder_form.addRow(label, row)
            self.folders[name] = entry
        fields.addWidget(folders)
        self.keep = QCheckBox('Keep downloaded videos after processing (reuse in either app)')
        self.keep.setChecked(bool(self.settings['keep']))
        fields.addWidget(self.keep)
        reuse = QLabel('To share saved videos, choose the same Download/cache folder in both apps.\n'
                       'Existing saved videos are never deleted when this box is unchecked.')
        reuse.setWordWrap(True)
        fields.addWidget(reuse)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(self.options)
        layout.addWidget(scroll, 3)
        actions = QHBoxLayout()
        self.start = QPushButton('Start')
        self.start.setStyleSheet('background: #226787; color: white; padding: 9px 28px; font-weight: bold;')
        self.start.clicked.connect(self.start_batch)
        self.cancel_button = QPushButton('Cancel')
        self.cancel_button.setEnabled(False)
        self.cancel_button.clicked.connect(self.cancel_batch)
        open_output = QPushButton('Open output folder')
        open_output.clicked.connect(self.open_output)
        actions.addWidget(self.start)
        actions.addWidget(self.cancel_button)
        actions.addStretch()
        actions.addWidget(open_output)
        layout.addLayout(actions)
        self.status = QLabel('Ready')
        self.status.setWordWrap(True)
        layout.addWidget(self.status)
        self.progress = QProgressBar()
        self.progress.setRange(0, 1000)
        layout.addWidget(self.progress)
        self.log = QPlainTextEdit()
        self.log.setReadOnly(True)
        self.log.setMaximumBlockCount(3000)
        self.log.setMinimumHeight(130)
        layout.addWidget(self.log, 1)
        self.timer = QTimer(self)
        self.timer.setInterval(100)
        self.timer.timeout.connect(self.poll)
        QTimer.singleShot(0, self.startup_check)

    def pick_folder(self, field):
        folder = QFileDialog.getExistingDirectory(self, 'Choose folder', field.text())
        if folder:
            field.setText(folder)

    def collect_settings(self):
        settings = dict(self.settings)
        settings.update({key: entry.text().strip() for key, entry in self.folders.items()})
        settings['keep'] = self.keep.isChecked()
        if IS_TRANSCRIBER:
            settings.update(language=self.language.currentData(), model=self.model.currentData())
        else:
            settings.update(interval=self.interval.text(), quality=self.quality.value(), captions=self.captions.isChecked())
        return settings

    def startup_check(self):
        errors, warnings = check_dependencies(IS_TRANSCRIBER)
        for message in errors + warnings:
            self.log.appendPlainText(message)
        self.log.appendPlainText('Settings and logs: ' + str(config_folder(APP_ID)))
        if errors:
            self.status.setText('Setup required — see the messages below and README.md.')

    def open_output(self):
        folder = Path(self.folders['output'].text()).expanduser()
        if folder.is_dir():
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(folder.resolve())))
        else:
            QMessageBox.information(self, 'Output folder', 'This folder will be created when processing starts.')

    def start_batch(self):
        try:
            videos, duplicates, invalid = parse_urls(self.urls.toPlainText())
            if not videos:
                raise ValueError('Paste at least one valid individual YouTube video URL. Playlist-only links are not supported.')
            errors, warnings = check_dependencies(IS_TRANSCRIBER)
            if errors:
                raise ValueError('\n\n'.join(errors))
            settings = self.collect_settings()
            if not IS_TRANSCRIBER:
                validate_interval(settings['interval'])
            warnings.extend(prepare_folders(settings))
            self.log.clear()
            for raw in duplicates:
                self.log.appendPlainText('DUPLICATE, skipped: ' + raw)
            for raw in invalid:
                self.log.appendPlainText('INVALID URL, skipped: ' + raw)
            for warning in warnings:
                self.log.appendPlainText('WARNING: ' + warning)
            for key in ('cache', 'temp', 'output'):
                clean_stale(Path(settings[key]))
            save_settings(APP_ID, settings)
            self.settings = settings
            for key in ('cache', 'temp', 'output'):
                self.roots[key] = str(create_workspace(Path(settings[key])))
            self.events = self.context.Queue()
            self.cancel_event = self.context.Event()
            from batch import run_batch
            self.process = self.context.Process(target=run_batch,
                args=(settings, videos, self.cancel_event, self.events, self.roots))
            self.result = None
            self.cancel_at = None
            self.invalid = invalid
            self.duplicates = duplicates
            self.videos = videos
            self.process.start()
            self.options.setEnabled(False)
            self.start.setEnabled(False)
            self.cancel_button.setEnabled(True)
            self.progress.setValue(0)
            self.status.setText('Starting local processing…')
            self.timer.start()
        except Exception as exc:
            logging.exception('Could not start batch')
            self.cleanup()
            self.process = None
            QMessageBox.warning(self, 'Cannot start', str(exc))

    def cancel_batch(self):
        if self.process and self.cancel_at is None:
            self.cancel_event.set()
            self.cancel_at = time.monotonic()
            self.cancel_button.setEnabled(False)
            self.status.setText('Cancelling… completed output files will be preserved.')

    def poll(self):
        for _ in range(250):
            try:
                kind, value = self.events.get_nowait()
            except queue.Empty:
                break
            if kind == 'log':
                self.log.appendPlainText(str(value))
            elif kind == 'status' and self.cancel_at is None:
                self.status.setText(str(value))
            elif kind == 'progress':
                self.progress.setValue(value)
            elif kind in ('done', 'fatal'):
                self.result = (kind, value)
        if self.cancel_at and self.process.is_alive() and time.monotonic() - self.cancel_at > 8:
            stop_process_tree(self.process)
        if self.process.is_alive():
            return
        self.process.join(timeout=0.1)
        # Queue feeder has flushed when the process exits; collect the last result.
        while True:
            try:
                kind, value = self.events.get_nowait()
            except queue.Empty:
                break
            if kind in ('done', 'fatal'):
                self.result = (kind, value)
            elif kind == 'log':
                self.log.appendPlainText(str(value))
        self.timer.stop()
        self.cleanup()
        self.events.close()
        self.events.join_thread()
        self.process.close()
        self.process = None
        self.options.setEnabled(True)
        self.start.setEnabled(True)
        self.cancel_button.setEnabled(False)
        self.show_result()
        if self.close_after:
            self.close()

    def cleanup(self):
        for root in self.roots.values():
            remove_workspace(Path(root))
        self.roots = {}

    def show_result(self):
        if not self.result:
            message = ('Cancelled. No combined output was saved for this run.' if self.cancel_at else
                       'The processing worker stopped unexpectedly. See the worker logfile. Previously saved outputs are intact.')
        elif self.result[0] == 'fatal':
            message = 'Processing stopped: ' + str(self.result[1])
        else:
            result = self.result[1]
            good = sum(row['status'] == 'SUCCESS' for row in result['results'])
            bad = sum(row['status'] == 'FAILED' for row in result['results'])
            message = ('Cancelled.' if result['cancelled'] else 'Completed.' if not bad else 'Completed with errors.')
            message += f'\nSuccessful: {good} • Failed: {bad} • Not processed: {len(self.videos) - good - bad}'
            message += f'\nInvalid links skipped: {len(self.invalid)} • Duplicates skipped: {len(self.duplicates)}'
            if 'screenshots' in result:
                message += f'\nScreenshots: {result["screenshots"]:,}'
            message += f'\nElapsed: {result["elapsed"] / 60:.1f} minutes'
            message += '\nOutput: ' + (result['output'] or 'No combined output saved for this cancelled run.')
            for row in result['results']:
                self.log.appendPlainText(f'{row["status"]}: {row["url"]}' + (' — ' + row['reason'] if row.get('reason') else ''))
            if not result['cancelled']:
                self.progress.setValue(1000)
        self.status.setText(message)
        self.log.appendPlainText('\n' + message)

    def closeEvent(self, event):
        if self.process:
            self.close_after = True
            self.cancel_batch()
            event.ignore()
            return
        try:
            save_settings(APP_ID, self.collect_settings())
        except OSError as exc:
            logging.warning('Could not save settings: %s', exc)
        event.accept()
