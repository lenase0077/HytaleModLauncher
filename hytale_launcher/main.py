from __future__ import annotations

import math
import sys
import webbrowser
from dataclasses import dataclass, field
from pathlib import Path

from PyQt6.QtCore import (
    QByteArray,
    QEasingCurve,
    QObject,
    QPropertyAnimation,
    QRunnable,
    Qt,
    QThreadPool,
    QTimer,
    QUrl,
    pyqtSignal,
    pyqtSlot,
)
from PyQt6.QtGui import (
    QColor,
    QCursor,
    QImage,
    QPainter,
    QPixmap,
    QResizeEvent,
    QIcon,
)
from PyQt6.QtNetwork import QNetworkAccessManager, QNetworkReply, QNetworkRequest
from PyQt6.QtWidgets import (
    QApplication,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from hytale_launcher import assets_manager, config_store, lockfile_store, i18n
from hytale_launcher.curseforge_client import CurseForgeClient, SEARCH_PAGE_SIZE
from hytale_launcher.mod_installer import ModInstaller
from hytale_launcher.models import Category, FingerprintMatch, Mod, ModFile
from hytale_launcher.scanner import compute_fingerprint, scan_unmanaged
from hytale_launcher.theme import THEMES, Palette, generate_qss

# ── API ───────────────────────────────────────────────────────────────────────
CURSEFORGE_API_KEY = "$2a$10$M2pSZI9Ntw2K4fTSTPvU7uy8NfeMnAQQ/x9R0C0DpJ/6J5icPIg8W"


# ── Helpers ───────────────────────────────────────────────────────────────────
def _ellipsize(value: str, limit: int) -> str:
    clean = " ".join(value.split())
    if len(clean) <= limit:
        return clean
    return clean[: max(0, limit - 3)].rstrip() + "..."


def _btn(parent: QWidget, text: str, obj: str = "", width: int | None = None, icon: str | None = None) -> QPushButton:
    b = QPushButton(text, parent)
    if obj:
        b.setObjectName(obj)
    if width:
        b.setFixedWidth(width)
    if icon:
        b.setIcon(assets_manager.get_icon(icon))
    b.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
    return b


# ── Data ──────────────────────────────────────────────────────────────────────
@dataclass(frozen=True)
class SortOption:
    label_key: str; field: int; order: str
    def __str__(self) -> str: return i18n.tr(self.label_key)


@dataclass(frozen=True)
class CategoryOption:
    id: int | None; name: str
    def __str__(self) -> str: return self.name


@dataclass
class ScanResult:
    recognized: list[tuple[Path, ModFile, str]]
    unrecognized: list[Path]


@dataclass
class CheckResult:
    updates: dict[int, ModFile] = field(default_factory=dict)


# ── Worker signals ────────────────────────────────────────────────────────────
class WorkerSignals(QObject):
    result = pyqtSignal(object)
    error  = pyqtSignal(str)
    status = pyqtSignal(str)


# ── Workers ───────────────────────────────────────────────────────────────────
class SearchWorker(QRunnable):
    def __init__(self, client, query, cat_id, sort_field, sort_order, page):
        super().__init__()
        self.signals = WorkerSignals()
        self._c, self._q, self._cid = client, query, cat_id
        self._sf, self._so, self._p = sort_field, sort_order, page

    @pyqtSlot()
    def run(self):
        try:
            self.signals.result.emit(
                self._c.search_mods(self._q, self._p, self._cid, self._sf, self._so))
        except Exception as e:
            self.signals.error.emit(str(e))


class CategoryWorker(QRunnable):
    def __init__(self, client):
        super().__init__()
        self.signals = WorkerSignals()
        self._c = client

    @pyqtSlot()
    def run(self):
        try:
            self.signals.result.emit(self._c.get_mod_categories())
        except Exception as e:
            self.signals.error.emit(str(e))


class FetchFilesWorker(QRunnable):
    def __init__(self, client, mod):
        super().__init__()
        self.signals = WorkerSignals()
        self._c, self._m = client, mod

    @pyqtSlot()
    def run(self):
        try:
            self.signals.result.emit(self._c.get_files_for_mod(self._m.id))
        except Exception as e:
            self.signals.error.emit(str(e))


class InstallWorker(QRunnable):
    def __init__(self, client, mod, mods_dir, selected_file):
        super().__init__()
        self.signals = WorkerSignals()
        self._c, self._m, self._d, self._f = client, mod, mods_dir, selected_file

    @pyqtSlot()
    def run(self):
        try:
            plan  = self._c.resolve_install_plan(self._f)
            ids   = sorted({f.mod_id for f in plan})
            by_id = self._c.get_mods_by_ids(ids)
            ModInstaller(self._c).install_all(
                plan, by_id, self._d,
                lambda l: self.signals.status.emit(l),
            )
            self.signals.result.emit(None)
        except Exception as e:
            self.signals.error.emit(str(e))


class ScanWorker(QRunnable):
    def __init__(self, client: CurseForgeClient, mods_dir: Path):
        super().__init__()
        self.signals = WorkerSignals()
        self._client = client
        self._dir    = mods_dir

    @pyqtSlot()
    def run(self):
        try:
            lf        = lockfile_store.load(self._dir)
            unmanaged = scan_unmanaged(self._dir, lf)
            if not unmanaged:
                self.signals.result.emit(ScanResult([], []))
                return

            self.signals.status.emit(i18n.tr("scan_fp", len(unmanaged)))
            fp_map: dict[int, Path] = {}
            failed: list[Path]      = []
            for path in unmanaged:
                try:
                    fp_map[compute_fingerprint(path)] = path
                except Exception:
                    failed.append(path)

            recognized: list[tuple[Path, ModFile, str]] = []
            matched_fps: set[int] = set()

            if fp_map:
                self.signals.status.emit(i18n.tr("scan_api"))
                try:
                    matches = self._client.get_mods_by_fingerprints(list(fp_map.keys()))
                    if matches:
                        mod_ids   = list({m.mod_id for m in matches if m.mod_id})
                        mods_by_id = self._client.get_mods_by_ids(mod_ids) if mod_ids else {}
                        for m in matches:
                            path      = fp_map.get(m.fingerprint)
                            if path is None:
                                continue
                            mod_obj   = mods_by_id.get(m.mod_id)
                            mod_name  = mod_obj.name if mod_obj else ""
                            recognized.append((path, m.file, mod_name))
                            matched_fps.add(m.fingerprint)
                except Exception:
                    pass

            unrecognized = [p for fp, p in fp_map.items() if fp not in matched_fps] + failed
            self.signals.result.emit(ScanResult(recognized, unrecognized))
        except Exception as e:
            self.signals.error.emit(str(e))


class CheckUpdatesWorker(QRunnable):
    def __init__(self, client: CurseForgeClient, refs: list[lockfile_store.InstalledModRef]):
        super().__init__()
        self.signals = WorkerSignals()
        self._client = client
        self._refs   = [r for r in refs if r.mod_id > 0]

    @pyqtSlot()
    def run(self):
        try:
            result = CheckResult()
            total  = len(self._refs)
            for i, ref in enumerate(self._refs, 1):
                self.signals.status.emit(
                    i18n.tr("chk_item", i, total, ref.mod_name or ref.file_name)
                )
                latest = self._client.get_latest_file_for_mod(ref.mod_id)
                if latest and latest.id > ref.file_id:
                    result.updates[ref.mod_id] = latest
            self.signals.result.emit(result)
        except Exception as e:
            self.signals.error.emit(str(e))


class UpdateOneWorker(QRunnable):
    def __init__(self, client: CurseForgeClient, mod_id: int, mod_name: str,
                 new_file: ModFile, mods_dir: Path):
        super().__init__()
        self.signals   = WorkerSignals()
        self._client   = client
        self._mod_id   = mod_id
        self._mod_name = mod_name
        self._file     = new_file
        self._dir      = mods_dir

    @pyqtSlot()
    def run(self):
        try:
            plan     = self._client.resolve_install_plan(self._file)
            ids      = sorted({f.mod_id for f in plan})
            by_id    = self._client.get_mods_by_ids(ids)
            ModInstaller(self._client).install_all(
                plan, by_id, self._dir,
                lambda l: self.signals.status.emit(l),
            )
            self.signals.result.emit(self._mod_id)
        except Exception as e:
            self.signals.error.emit(str(e))


# ── Toggle switch ─────────────────────────────────────────────────────────────
class ToggleSwitch(QWidget):
    toggled = pyqtSignal(bool)

    def __init__(self, checked: bool = True, parent: QWidget | None = None):
        super().__init__(parent)
        self._checked   = checked
        self._thumb_pos = 22.0 if checked else 2.0
        self.setFixedSize(46, 24)
        self.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self._anim = QPropertyAnimation(self, b"_thumb_x", self)
        self._anim.setDuration(150)
        self._anim.setEasingCurve(QEasingCurve.Type.OutCubic)

    def _get_thumb(self) -> float: return self._thumb_pos
    def _set_thumb(self, v: float):
        self._thumb_pos = v; self.update()

    _thumb_x = property(_get_thumb, _set_thumb)

    def isChecked(self) -> bool: return self._checked

    def setChecked(self, val: bool):
        self._checked = val
        self._anim.setStartValue(self._thumb_pos)
        self._anim.setEndValue(22.0 if val else 2.0)
        self._anim.start()

    def mousePressEvent(self, _):
        self.setChecked(not self._checked)
        self.toggled.emit(self._checked)

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        
        # Read colors dynamically from current theme via main app
        app = QApplication.instance()
        main_win = app.activeWindow()
        green_color = "#10B981"
        text3_color = "#475569"
        text_color  = "#FFFFFF"
        if hasattr(main_win, "get_palette"):
            pal = main_win.get_palette()
            green_color = pal.green
            text3_color = pal.text3
            text_color  = pal.text

        clr = QColor(green_color) if self._checked else QColor(text3_color)
        clr.setAlpha(200)
        p.setBrush(clr)
        p.setPen(Qt.PenStyle.NoPen)
        p.drawRoundedRect(0, 4, 46, 16, 8, 8)
        p.setBrush(QColor(text_color))
        p.drawEllipse(int(self._thumb_pos), 2, 20, 20)
        p.end()


# ── Installed mod row ─────────────────────────────────────────────────────────
class InstalledModRow(QFrame):
    toggle_requested = pyqtSignal(int, bool)
    remove_requested = pyqtSignal(int)
    update_requested = pyqtSignal(int, object)

    def __init__(self, ref: lockfile_store.InstalledModRef,
                 palette: Palette,
                 update_file: ModFile | None = None,
                 parent: QWidget | None = None):
        super().__init__(parent)
        self.ref         = ref
        self.update_file = update_file
        self.palette     = palette
        self.setObjectName("modRow")
        self.setMinimumHeight(72)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self._build()

    def _build(self):
        lo = QHBoxLayout(self)
        lo.setContentsMargins(16, 12, 16, 12)
        lo.setSpacing(12)

        dot = QLabel("●")
        dot.setObjectName("enabledDot" if self.ref.enabled else "disabledDot")
        dot.setFixedWidth(18)
        lo.addWidget(dot)

        info = QVBoxLayout()
        info.setSpacing(3)

        name_row = QHBoxLayout()
        name_row.setSpacing(6)
        name_text = self.ref.mod_name or f"Mod #{self.ref.mod_id}"
        name = QLabel(_ellipsize(name_text, 50))
        name.setObjectName("rowName")
        name_row.addWidget(name)

        if not self.ref.is_managed or self.ref.mod_id == 0:
            ext = QLabel(i18n.tr("row_ext"))
            ext.setStyleSheet(
                f"background-color:rgba(71,85,105,0.2); color:{self.palette.text3};"
                f"border:1px solid rgba(71,85,105,0.3); border-radius:5px;"
                f"padding:1px 6px; font-size:8pt; font-weight:600;"
            )
            name_row.addWidget(ext)

        if self.update_file:
            upd = QLabel(i18n.tr("row_upd_badge"))
            upd.setStyleSheet(
                f"background-color:rgba(129,140,248,0.15); color:{self.palette.purple};"
                f"border:1px solid rgba(129,140,248,0.3); border-radius:5px;"
                f"padding:1px 6px; font-size:8pt; font-weight:700;"
            )
            name_row.addWidget(upd)

        name_row.addStretch()
        info.addLayout(name_row)

        file_lbl = QLabel(self.ref.file_name or "—")
        file_lbl.setObjectName("rowFile")
        info.addWidget(file_lbl)
        lo.addLayout(info, stretch=1)

        # Status badge
        status_txt = i18n.tr("row_active") if self.ref.enabled else i18n.tr("row_inactive")
        status = QLabel(status_txt)
        status.setAlignment(Qt.AlignmentFlag.AlignCenter)
        status.setFixedWidth(85)
        if self.ref.enabled:
            status.setStyleSheet(
                f"background:rgba(16,185,129,0.15); color:{self.palette.green};"
                f"border:1px solid rgba(16,185,129,0.3); border-radius:6px;"
                f"padding:2px 8px; font-size:8pt; font-weight:700;"
            )
        else:
            status.setStyleSheet(
                f"background:rgba(71,85,105,0.2); color:{self.palette.text3};"
                f"border:1px solid rgba(71,85,105,0.3); border-radius:6px;"
                f"padding:2px 8px; font-size:8pt; font-weight:700;"
            )
        lo.addWidget(status)

        if self.update_file:
            upd_btn = _btn(self, i18n.tr("row_upd_btn"), icon="circle-arrow-up")
            upd_btn.setStyleSheet(
                f"background-color:rgba(129,140,248,0.12); color:{self.palette.purple};"
                f"border:1px solid rgba(129,140,248,0.3); border-radius:6px;"
                f"padding:4px 10px; font-weight:700; font-size:8pt;"
            )
            upd_btn.clicked.connect(
                lambda: self.update_requested.emit(self.ref.mod_id, self.update_file)
            )
            lo.addWidget(upd_btn)

        toggle = ToggleSwitch(checked=self.ref.enabled)
        toggle.toggled.connect(
            lambda val, mid=self.ref.mod_id: self.toggle_requested.emit(mid, val)
        )
        lo.addWidget(toggle)

        rem = _btn(self, i18n.tr("card_remove"), width=95, icon="trash-2")
        rem.setStyleSheet(
            f"background-color: {self.palette.red}; color: #FFFFFF;"
            f"border: 1px solid {self.palette.red}; border-radius: 8px;"
            f"padding: 6px 12px; font-weight: 700;"
        )
        rem.clicked.connect(lambda: self.remove_requested.emit(self.ref.mod_id))
        lo.addWidget(rem)


# ── Installed panel ───────────────────────────────────────────────────────────
class InstalledPanel(QWidget):
    refresh_needed = pyqtSignal()
    status_message = pyqtSignal(str)

    def __init__(self, get_mods_dir, client: CurseForgeClient,
                 pool: QThreadPool, parent: QWidget | None = None):
        super().__init__(parent)
        self.setObjectName("installedPanel")
        self._get_dir    = get_mods_dir
        self._client     = client
        self._pool       = pool
        self._update_map: dict[int, ModFile] = {}
        self._busy       = False
        self._build()

    def _build(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        hdr = QWidget()
        hdr.setObjectName("installedHeader")
        hlo = QVBoxLayout(hdr)
        hlo.setContentsMargins(24, 14, 24, 14)
        hlo.setSpacing(4)
        title_row = QHBoxLayout()
        self._title = QLabel(i18n.tr("tab_installed"))
        self._title.setObjectName("installedTitle")
        title_row.addWidget(self._title)
        title_row.addStretch()
        self._count_badge = QLabel("")
        self._count_badge.setObjectName("badgeLabel")
        title_row.addWidget(self._count_badge)
        hlo.addLayout(title_row)
        sub = QLabel(i18n.tr("inst_subtitle"))
        sub.setObjectName("installedSubtitle")
        hlo.addWidget(sub)
        root.addWidget(hdr)

        bar = QWidget()
        bar.setObjectName("actionBar")
        blo = QHBoxLayout(bar)
        blo.setContentsMargins(24, 8, 24, 8)
        blo.setSpacing(8)
        self._scan_btn = _btn(bar, i18n.tr("inst_scan"), icon="refresh-cw")
        self._scan_btn.setToolTip(i18n.tr("inst_scan_tt"))
        self._scan_btn.clicked.connect(self._on_scan)
        blo.addWidget(self._scan_btn)
        self._check_btn = _btn(bar, i18n.tr("inst_check"), icon="search")
        self._check_btn.setToolTip(i18n.tr("inst_check_tt"))
        self._check_btn.clicked.connect(self._on_check_updates)
        blo.addWidget(self._check_btn)
        blo.addStretch()
        self._update_all_btn = _btn(bar, i18n.tr("inst_upd_all"), "updateAllBtn", icon="circle-arrow-up")
        self._update_all_btn.setVisible(False)
        self._update_all_btn.clicked.connect(self._on_update_all)
        blo.addWidget(self._update_all_btn)
        root.addWidget(bar)

        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        self._scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._list_container = QWidget()
        self._list_lo = QVBoxLayout(self._list_container)
        self._list_lo.setContentsMargins(24, 16, 24, 16)
        self._list_lo.setSpacing(8)
        self._list_lo.addStretch()
        self._scroll.setWidget(self._list_container)
        root.addWidget(self._scroll)

    def reload(self):
        while self._list_lo.count() > 1:
            item = self._list_lo.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        mods_dir = self._get_dir()
        try:
            mods_dir.mkdir(parents=True, exist_ok=True)
            lf = lockfile_store.load(mods_dir)
        except Exception:
            lf = lockfile_store.Lockfile()

        refs = []
        for mid, ref in lf.mods.items():
            if not ref.is_managed and ref.mod_id == 0:
                ref.mod_id = mid
            refs.append(ref)

        if len(refs) == 1:
            self._count_badge.setText(i18n.tr("inst_count_one"))
        else:
            self._count_badge.setText(i18n.tr("inst_count_many", len(refs)))

        n_updates = sum(1 for r in refs if r.mod_id in self._update_map)
        self._update_all_btn.setVisible(n_updates > 0)
        if n_updates > 0:
            self._update_all_btn.setText(i18n.tr("inst_upd_all_fmt", n_updates))

        if not refs:
            empty = QLabel(i18n.tr("inst_empty"))
            empty.setObjectName("emptyState")
            empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self._list_lo.insertWidget(0, empty)
            return

        app = QApplication.instance()
        main_win = app.activeWindow()
        pal = main_win.get_palette() if hasattr(main_win, "get_palette") else THEMES["Dark"]

        for ref in sorted(refs, key=lambda r: (r.mod_name or r.file_name).lower()):
            row = InstalledModRow(ref, palette=pal, update_file=self._update_map.get(ref.mod_id))
            row.toggle_requested.connect(self._on_toggle)
            row.remove_requested.connect(self._on_remove)
            row.update_requested.connect(self._on_update_one)
            self._list_lo.insertWidget(self._list_lo.count() - 1, row)

    # ── Scan ──────────────────────────────────────────────────────────────────
    def _on_scan(self):
        if self._busy: return
        self._set_panel_busy(True)
        self.status_message.emit(i18n.tr("scan_busy"))
        w = ScanWorker(self._client, self._get_dir())
        w.signals.result.connect(self._on_scan_done)
        w.signals.error.connect(self._on_error)
        w.signals.status.connect(self.status_message.emit)
        self._pool.start(w)

    @pyqtSlot(object)
    def _on_scan_done(self, result: ScanResult):
        self._set_panel_busy(False)
        total = len(result.recognized) + len(result.unrecognized)

        if total == 0:
            self.status_message.emit(i18n.tr("scan_none"))
            QMessageBox.information(self, i18n.tr("scan_done_title"), i18n.tr("scan_none_msg"))
            return

        mods_dir = self._get_dir()
        try:
            mods_dir.mkdir(parents=True, exist_ok=True)
            lf = lockfile_store.load(mods_dir)

            for path, api_file, mod_name in result.recognized:
                actual_name = path.name.removesuffix(lockfile_store.DISABLED_SUFFIX)
                enabled     = not path.name.endswith(lockfile_store.DISABLED_SUFFIX)
                lf.mods[api_file.mod_id] = lockfile_store.InstalledModRef(
                    mod_id=api_file.mod_id, file_id=api_file.id,
                    file_name=actual_name, enabled=enabled,
                    mod_name=mod_name, is_managed=True,
                )

            for path in result.unrecognized:
                actual_name = path.name.removesuffix(lockfile_store.DISABLED_SUFFIX)
                enabled     = not path.name.endswith(lockfile_store.DISABLED_SUFFIX)
                fake_id     = -abs(hash(actual_name)) % 10_000_000
                lf.mods[fake_id] = lockfile_store.InstalledModRef(
                    mod_id=0, file_id=0, file_name=actual_name,
                    enabled=enabled, mod_name=path.stem, is_managed=False,
                )

            lockfile_store.save(mods_dir, lf)
        except Exception as exc:
            QMessageBox.critical(self, i18n.tr("scan_err_imp"), str(exc))
            return

        self.reload()
        self.refresh_needed.emit()
        
        msg = i18n.tr("scan_res_msg", total, len(result.recognized), len(result.unrecognized))
        self.status_message.emit(i18n.tr("scan_res_status", total, len(result.recognized)))
        QMessageBox.information(self, i18n.tr("scan_done_title"), msg)

    # ── Check updates ─────────────────────────────────────────────────────────
    def _on_check_updates(self):
        if self._busy: return
        try:
            lf   = lockfile_store.load(self._get_dir())
            refs = list(lf.mods.values())
        except Exception:
            refs = []
        managed = [r for r in refs if r.mod_id > 0 and r.is_managed]
        if not managed:
            QMessageBox.information(
                self, i18n.tr("chk_no_managed_title"), i18n.tr("chk_no_managed")
            )
            return
        self._set_panel_busy(True)
        self.status_message.emit(i18n.tr("chk_busy", len(managed)))
        w = CheckUpdatesWorker(self._client, managed)
        w.signals.result.connect(self._on_updates_checked)
        w.signals.error.connect(self._on_error)
        w.signals.status.connect(self.status_message.emit)
        self._pool.start(w)

    @pyqtSlot(object)
    def _on_updates_checked(self, result: CheckResult):
        self._set_panel_busy(False)
        self._update_map = result.updates
        self.reload()
        n = len(result.updates)
        if n == 0:
            self.status_message.emit(i18n.tr("chk_ok_status"))
            QMessageBox.information(self, i18n.tr("chk_ok_title"), i18n.tr("chk_ok_msg"))
        else:
            self.status_message.emit(i18n.tr("chk_avail", n))

    # ── Update one / all ──────────────────────────────────────────────────────
    @pyqtSlot(int, object)
    def _on_update_one(self, mod_id: int, new_file: ModFile):
        if self._busy: return
        mods_dir = self._get_dir()
        try:
            ref = lockfile_store.load(mods_dir).mods.get(mod_id)
        except Exception:
            ref = None
        mod_name = (ref.mod_name if ref else None) or f"Mod {mod_id}"
        self._set_panel_busy(True)
        self.status_message.emit(i18n.tr("upd_busy", mod_name))
        w = UpdateOneWorker(self._client, mod_id, mod_name, new_file, mods_dir)
        w.signals.result.connect(self._on_update_one_done)
        w.signals.error.connect(self._on_error)
        w.signals.status.connect(self.status_message.emit)
        self._pool.start(w)

    @pyqtSlot(object)
    def _on_update_one_done(self, mod_id: int):
        self._save_updated_file_id(mod_id)
        self._update_map.pop(mod_id, None)
        self._set_panel_busy(False)
        self.reload()
        self.refresh_needed.emit()
        self.status_message.emit(i18n.tr("upd_done"))

    def _on_update_all(self):
        if self._busy or not self._update_map: return
        self._update_all_queue = list(self._update_map.items())
        self._process_next_update()

    def _process_next_update(self):
        if not self._update_all_queue:
            self._set_panel_busy(False)
            self._update_map.clear()
            self.reload(); self.refresh_needed.emit()
            self.status_message.emit(i18n.tr("upd_all_done"))
            return
        mod_id, new_file = self._update_all_queue.pop(0)
        try:
            ref = lockfile_store.load(self._get_dir()).mods.get(mod_id)
        except Exception:
            ref = None
        mod_name = (ref.mod_name if ref else None) or f"Mod {mod_id}"
        self._set_panel_busy(True)
        self.status_message.emit(i18n.tr("upd_busy", mod_name))
        w = UpdateOneWorker(self._client, mod_id, mod_name, new_file, self._get_dir())
        w.signals.result.connect(lambda mid: (self._save_updated_file_id(mid), self._process_next_update()))
        w.signals.error.connect(self._on_error)
        w.signals.status.connect(self.status_message.emit)
        self._pool.start(w)

    def _save_updated_file_id(self, mod_id: int):
        new_file = self._update_map.get(mod_id)
        if not new_file: return
        try:
            mods_dir = self._get_dir()
            lf  = lockfile_store.load(mods_dir)
            ref = lf.mods.get(mod_id)
            if ref:
                ref.file_id   = new_file.id
                ref.file_name = new_file.file_name
                lockfile_store.save(mods_dir, lf)
        except Exception:
            pass

    # ── Toggle / Remove ───────────────────────────────────────────────────────
    def _on_toggle(self, mod_id: int, enable: bool):
        mods_dir = self._get_dir()
        try:
            mods_dir.mkdir(parents=True, exist_ok=True)
            lf  = lockfile_store.load(mods_dir)
            ref = lf.mods.get(mod_id)
            if ref is None: return
            if enable: ref.enable(mods_dir)
            else:      ref.disable(mods_dir)
            lockfile_store.save(mods_dir, lf)
            self.reload(); self.refresh_needed.emit()
        except Exception as exc:
            QMessageBox.critical(self, i18n.tr("err_title"), str(exc))

    def _on_remove(self, mod_id: int):
        mods_dir = self._get_dir()
        try:
            mods_dir.mkdir(parents=True, exist_ok=True)
            lf  = lockfile_store.load(mods_dir)
            ref = lf.mods.get(mod_id)
            if ref:
                for p in [mods_dir / ref.file_name,
                           mods_dir / (ref.file_name + lockfile_store.DISABLED_SUFFIX)]:
                    if p.exists(): p.unlink()
                lf.mods.pop(mod_id, None)
                lockfile_store.save(mods_dir, lf)
            self._update_map.pop(mod_id, None)
            self.reload(); self.refresh_needed.emit()
        except Exception as exc:
            QMessageBox.critical(self, i18n.tr("err_title"), str(exc))

    def _on_error(self, msg: str):
        self._set_panel_busy(False)
        self.status_message.emit(f"{i18n.tr('err_title')}: {msg}")
        QMessageBox.critical(self, i18n.tr("err_title"), msg)

    def _set_panel_busy(self, busy: bool):
        self._busy = busy
        self._scan_btn.setEnabled(not busy)
        self._check_btn.setEnabled(not busy)
        self._update_all_btn.setEnabled(not busy)


# ── Mod card ──────────────────────────────────────────────────────────────────
class ModCard(QFrame):
    install_requested = pyqtSignal(object)
    remove_requested  = pyqtSignal(object)
    web_requested     = pyqtSignal(object)

    def __init__(self, mod: Mod, installed: bool, palette: Palette, parent: QWidget | None = None):
        super().__init__(parent)
        self.mod = mod
        self.palette = palette
        self.setObjectName("modCard")
        self.setFixedSize(360, 295)
        self.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self._build(installed)

    def _build(self, installed: bool):
        lo = QVBoxLayout(self)
        lo.setContentsMargins(14, 12, 14, 12)
        lo.setSpacing(6)

        hdr = QHBoxLayout()
        name = QLabel(_ellipsize(self.mod.name, 34))
        name.setObjectName("cardName")
        name.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        hdr.addWidget(name)
        if installed:
            badge = QLabel(i18n.tr("card_installed"))
            badge.setStyleSheet(
                f"background:rgba(16,185,129,0.15); color:{self.palette.green};"
                f"font-weight:700; border-radius:6px; padding:2px 8px; font-size:8pt;"
                f"border:1px solid rgba(16,185,129,0.3);"
            )
            hdr.addWidget(badge)
        lo.addLayout(hdr)

        self.img_label = QLabel("…")
        self.img_label.setObjectName("cardImage")
        self.img_label.setFixedSize(110, 110)
        self.img_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        img_row = QHBoxLayout()
        img_row.addStretch()
        img_row.addWidget(self.img_label)
        img_row.addStretch()
        lo.addLayout(img_row)

        summ = QLabel(_ellipsize(self.mod.summary or "", 150))
        summ.setObjectName("cardSummary")
        summ.setWordWrap(True)
        summ.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)
        summ.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        lo.addWidget(summ)

        btns = QHBoxLayout()
        btns.setSpacing(6)
        if installed:
            b1 = _btn(self, i18n.tr("card_reinstall"), icon="refresh-cw")
            b1.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
            b1.clicked.connect(lambda: self.install_requested.emit(self.mod))
            btns.addWidget(b1)
            b2 = _btn(self, i18n.tr("card_remove"), icon="trash-2")
            b2.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
            b2.setStyleSheet(
                f"background-color: {self.palette.red}; color: #FFFFFF;"
                f"border: 1px solid {self.palette.red}; border-radius: 8px;"
                f"padding: 6px 12px; font-weight: 700;"
            )
            b2.clicked.connect(lambda: self.remove_requested.emit(self.mod))
            btns.addWidget(b2)
        else:
            b1 = _btn(self, i18n.tr("card_add"), icon="plus")
            b1.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
            b1.setStyleSheet(
                f"background-color: {self.palette.green}; color: #000000;"
                f"border: 1px solid {self.palette.green}; border-radius: 8px;"
                f"padding: 6px 12px; font-weight: 700;"
            )
            b1.clicked.connect(lambda: self.install_requested.emit(self.mod))
            btns.addWidget(b1)

        bw = _btn(self, i18n.tr("card_web"), icon="external-link")
        bw.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        bw.clicked.connect(lambda: self.web_requested.emit(self.mod))
        btns.addWidget(bw)
        lo.addLayout(btns)

    def set_image(self, px: QPixmap):
        scaled = px.scaled(110, 110, Qt.AspectRatioMode.KeepAspectRatio,
                           Qt.TransformationMode.SmoothTransformation)
        self.img_label.setText("")
        self.img_label.setPixmap(scaled)

    def set_image_error(self): self.img_label.setText(i18n.tr("card_no_img"))


# ── File picker dialog ────────────────────────────────────────────────────────
class FilePickerDialog(QDialog):
    def __init__(self, mod: Mod, files: list[ModFile], parent=None):
        super().__init__(parent)
        self.setWindowTitle(i18n.tr("dlg_ver_title", mod.name))
        self.setMinimumWidth(560)
        self.setModal(True)
        self._files    = files
        self._selected: ModFile | None = None
        lo = QVBoxLayout(self)
        lo.setContentsMargins(20, 20, 20, 20)
        lo.setSpacing(12)
        lo.addWidget(QLabel(i18n.tr("dlg_ver_msg", _ellipsize(mod.name, 60))))
        self._combo = QComboBox()
        for f in files:
            self._combo.addItem(str(f))
        lo.addWidget(self._combo)
        box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        box.accepted.connect(self._accept)
        box.rejected.connect(self.reject)
        lo.addWidget(box)

    def _accept(self):
        idx = self._combo.currentIndex()
        if 0 <= idx < len(self._files):
            self._selected = self._files[idx]
        self.accept()

    def selected_file(self) -> ModFile | None: return self._selected


# ── Explore panel ─────────────────────────────────────────────────────────────
class ExplorePanel(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._build()

    def _build(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        strip = QWidget()
        strip.setObjectName("controlsPanel")
        slo = QVBoxLayout(strip)
        slo.setContentsMargins(20, 12, 20, 12)
        slo.setSpacing(8)

        r1 = QHBoxLayout(); r1.setSpacing(8)
        self.sort_combo = QComboBox(); r1.addWidget(self.sort_combo)
        self.cat_combo  = QComboBox(); r1.addWidget(self.cat_combo)
        self.search_entry = QLineEdit()
        self.search_entry.setPlaceholderText(i18n.tr("search_ph"))
        r1.addWidget(self.search_entry, stretch=1)
        self.search_btn = _btn(strip, i18n.tr("search_btn"), "accentBtn", width=100, icon="search")
        r1.addWidget(self.search_btn)
        slo.addLayout(r1)

        r2 = QHBoxLayout(); r2.setSpacing(8)
        self.prev_btn = _btn(strip, "", width=44, icon="chevron-left")
        r2.addWidget(self.prev_btn)
        self.page_lbl = QLabel(i18n.tr("page_fmt", 1, 1))
        self.page_lbl.setObjectName("pageLabel")
        self.page_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        r2.addWidget(self.page_lbl)
        self.next_btn = _btn(strip, "", width=44, icon="chevron-right")
        r2.addWidget(self.next_btn)
        r2.addStretch()
        slo.addLayout(r2)
        root.addWidget(strip)

        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.cards_container = QWidget()
        self.grid = QGridLayout(self.cards_container)
        self.grid.setContentsMargins(16, 16, 16, 16)
        self.grid.setSpacing(14)
        self.scroll.setWidget(self.cards_container)
        root.addWidget(self.scroll, stretch=1)


# ── Settings panel ────────────────────────────────────────────────────────────
class SettingsPanel(QWidget):
    theme_changed = pyqtSignal(str)
    dir_changed   = pyqtSignal(str)
    lang_changed  = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("settingsPanel")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self._build()

    def _build(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(40, 40, 40, 40)
        root.setSpacing(24)

        title = QLabel(i18n.tr("set_title"))
        title.setStyleSheet("font-size: 20pt; font-weight: bold;")
        root.addWidget(title)

        # Language Section
        l_group = QWidget()
        l_lo = QVBoxLayout(l_group)
        l_lo.setContentsMargins(0, 0, 0, 0)
        l_lo.addWidget(QLabel(i18n.tr("set_lang")))
        self.lang_combo = QComboBox()
        self.lang_combo.setFixedWidth(200)
        self.lang_combo.addItem("English", "en")
        self.lang_combo.addItem("Español", "es")
        
        current_lang = config_store.load_language()
        idx = self.lang_combo.findData(current_lang)
        if idx >= 0:
            self.lang_combo.setCurrentIndex(idx)
            
        self.lang_combo.currentIndexChanged.connect(self._on_lang)
        l_lo.addWidget(self.lang_combo)
        root.addWidget(l_group)

        # Theme Section
        t_group = QWidget()
        t_lo = QVBoxLayout(t_group)
        t_lo.setContentsMargins(0, 0, 0, 0)
        t_lo.addWidget(QLabel(i18n.tr("set_theme")))
        self.theme_combo = QComboBox()
        self.theme_combo.setFixedWidth(200)
        for t in THEMES.keys():
            self.theme_combo.addItem(t)
        self.theme_combo.setCurrentText(config_store.load_theme())
        self.theme_combo.currentTextChanged.connect(self._on_theme)
        t_lo.addWidget(self.theme_combo)
        root.addWidget(t_group)

        # Folder Section
        f_group = QWidget()
        f_lo = QVBoxLayout(f_group)
        f_lo.setContentsMargins(0, 0, 0, 0)
        f_lo.addWidget(QLabel(i18n.tr("set_folder")))
        f_row = QHBoxLayout()
        self.folder_entry = QLineEdit()
        self.folder_entry.setText(config_store.load_mods_dir())
        self.folder_entry.editingFinished.connect(self._on_dir_edit)
        f_row.addWidget(self.folder_entry)
        btn = _btn(f_group, i18n.tr("set_browse"), icon="folder")
        btn.clicked.connect(self._on_browse)
        f_row.addWidget(btn)
        f_lo.addLayout(f_row)
        root.addWidget(f_group)

        root.addStretch()

    def _on_lang(self, idx: int):
        lang = self.lang_combo.itemData(idx)
        if lang:
            config_store.save_language(lang)
            self.lang_changed.emit(lang)

    def _on_theme(self, name: str):
        config_store.save_theme(name)
        self.theme_changed.emit(name)

    def _on_browse(self):
        d = QFileDialog.getExistingDirectory(self, i18n.tr("set_folder_title"), self.folder_entry.text())
        if d:
            self.folder_entry.setText(d)
            self._on_dir_edit()

    def _on_dir_edit(self):
        p = self.folder_entry.text().strip()
        config_store.save_mods_dir(p)
        self.dir_changed.emit(p)


# ── Main window ───────────────────────────────────────────────────────────────
class LauncherWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Hytale Mod Launcher")
        self.setMinimumSize(1240, 760)
        self.resize(1320, 820)
        
        assets_manager.prefetch_icons()

        self._client = CurseForgeClient(CURSEFORGE_API_KEY)
        self._pool   = QThreadPool.globalInstance()
        self._nam    = QNetworkAccessManager(self)
        self._image_cache: dict[str, QPixmap] = {}
        self._pending: dict[QNetworkReply, tuple[str, ModCard]] = {}

        self._mods: list[Mod] = []
        self._installed: dict[int, lockfile_store.InstalledModRef] = {}
        self._cards: list[ModCard] = []
        self._sort_opts = [
            SortOption("sort_pop", 2, "desc"),
            SortOption("sort_upd", 3, "desc"),
            SortOption("sort_dl",  6, "desc"),
            SortOption("sort_name",4, "asc"),
        ]
        self._cat_opts: list[CategoryOption] = [CategoryOption(None, i18n.tr("cat_all"))]
        self._page = 0; self._total = 0; self._page_size = SEARCH_PAGE_SIZE
        self._busy = False; self._cols = 3
        
        self._palette = THEMES.get(config_store.load_theme(), THEMES["Dark"])

        self._build_ui()
        self._apply_theme()
        
        self._resize_timer = QTimer(self)
        self._resize_timer.setSingleShot(True)
        self._resize_timer.timeout.connect(self._apply_resize)

        self._wire()
        self._refresh_installed()
        self._load_categories()
        self._search(reset_page=True)

    def get_palette(self) -> Palette:
        return self._palette

    def _build_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        root = QVBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # Header
        hdr = QWidget(); hdr.setObjectName("headerBar"); hdr.setFixedHeight(72)
        hlo = QHBoxLayout(hdr); hlo.setContentsMargins(24, 0, 24, 0)
        tc = QVBoxLayout(); tc.setSpacing(0)
        tr = QHBoxLayout(); tr.setSpacing(4)
        t = QLabel("Hytale Mod"); t.setObjectName("appTitle")
        a = QLabel(" " + i18n.tr("app_title")); a.setObjectName("accentWord")
        tr.addWidget(t); tr.addWidget(a); tr.addStretch()
        tc.addStretch(); tc.addLayout(tr)
        self._status_lbl = QLabel(i18n.tr("status_ready")); self._status_lbl.setObjectName("statusLabel")
        tc.addWidget(self._status_lbl); tc.addStretch()
        hlo.addLayout(tc, stretch=1)
        badge = QLabel("Powered by CurseForge")
        badge.setStyleSheet("color: #64748B; font-weight: 600; font-size: 9pt;")
        hlo.addWidget(badge, alignment=Qt.AlignmentFlag.AlignVCenter)
        root.addWidget(hdr)

        # Tab bar
        tab_bar = QWidget(); tab_bar.setObjectName("tabBar"); tab_bar.setFixedHeight(46)
        tlo = QHBoxLayout(tab_bar); tlo.setContentsMargins(16, 0, 0, 0); tlo.setSpacing(0)
        self._tab_explore = QPushButton(i18n.tr("tab_explore"))
        self._tab_explore.setIcon(assets_manager.get_icon("search"))
        self._tab_explore.setObjectName("tabBtnActive")
        self._tab_explore.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self._tab_explore.clicked.connect(lambda: self._switch_tab(0))
        
        self._tab_installed = QPushButton(i18n.tr("tab_installed"))
        self._tab_installed.setIcon(assets_manager.get_icon("package"))
        self._tab_installed.setObjectName("tabBtn")
        self._tab_installed.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self._tab_installed.clicked.connect(lambda: self._switch_tab(1))
        
        self._tab_settings = QPushButton(i18n.tr("tab_settings"))
        self._tab_settings.setIcon(assets_manager.get_icon("settings"))
        self._tab_settings.setObjectName("tabBtn")
        self._tab_settings.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self._tab_settings.clicked.connect(lambda: self._switch_tab(2))
        
        tlo.addWidget(self._tab_explore)
        tlo.addWidget(self._tab_installed)
        tlo.addWidget(self._tab_settings)
        tlo.addStretch()
        root.addWidget(tab_bar)

        # Stacked content
        self._stack = QStackedWidget()
        self._explore = ExplorePanel()
        self._stack.addWidget(self._explore)
        self._installed_panel = InstalledPanel(self._mods_dir, self._client, self._pool)
        self._installed_panel.refresh_needed.connect(self._on_installed_changed)
        self._installed_panel.status_message.connect(self._set_status)
        self._stack.addWidget(self._installed_panel)
        self._settings = SettingsPanel()
        self._settings.theme_changed.connect(self._on_theme_changed)
        self._settings.dir_changed.connect(self._on_dir_changed)
        self._settings.lang_changed.connect(self._on_lang_changed)
        self._stack.addWidget(self._settings)
        root.addWidget(self._stack, stretch=1)

        self.statusBar().showMessage(i18n.tr("status_ready"))

    def _apply_theme(self):
        qss = generate_qss(self._palette)
        QApplication.instance().setStyleSheet(qss)
        self._explore.cards_container.setStyleSheet(f"background-color: {self._palette.bg};")
        self._installed_panel._list_container.setStyleSheet(f"background-color: {self._palette.bg};")

    def _on_theme_changed(self, theme_name: str):
        self._palette = THEMES.get(theme_name, THEMES["Dark"])
        self._apply_theme()
        self._render_cards()
        self._installed_panel.reload()

    def _on_dir_changed(self, _):
        self._refresh_installed()
        self._render_cards()
        self._installed_panel.reload()

    def _on_lang_changed(self, lang: str):
        QMessageBox.information(self, i18n.tr("info_title"), i18n.tr("restart_msg"))

    def _switch_tab(self, idx: int):
        self._stack.setCurrentIndex(idx)
        tabs = [self._tab_explore, self._tab_installed, self._tab_settings]
        for i, t in enumerate(tabs):
            t.setObjectName("tabBtnActive" if i == idx else "tabBtn")
            t.style().unpolish(t); t.style().polish(t)
        if idx == 1:
            self._installed_panel.reload()

    def _mods_dir(self) -> Path:
        return Path(config_store.load_mods_dir())

    def _wire(self):
        ex = self._explore
        ex.search_btn.clicked.connect(lambda: self._search(True))
        ex.search_entry.returnPressed.connect(lambda: self._search(True))
        ex.sort_combo.addItems([str(s) for s in self._sort_opts])
        ex.cat_combo.addItems([str(c) for c in self._cat_opts])
        ex.sort_combo.currentIndexChanged.connect(
            lambda _: self._search(True) if not self._busy else None)
        ex.cat_combo.currentIndexChanged.connect(
            lambda _: self._search(True) if not self._busy else None)
        ex.prev_btn.clicked.connect(self._prev_page)
        ex.next_btn.clicked.connect(self._next_page)

    def resizeEvent(self, e: QResizeEvent):
        super().resizeEvent(e); self._resize_timer.start(260)

    def _apply_resize(self):
        w = self._explore.scroll.viewport().width()
        cols = max(1, min(4, w // 395))
        if cols != self._cols:
            self._cols = cols; self._regrid()

    def _regrid(self):
        for i, card in enumerate(self._cards):
            r, c = divmod(i, self._cols)
            self._explore.grid.addWidget(card, r, c)
        for col in range(max(self._cols, 4)):
            self._explore.grid.setColumnStretch(col, 1 if col < self._cols else 0)

    def _prev_page(self):
        if not self._busy and self._page > 0:
            self._page -= 1; self._search(False)

    def _next_page(self):
        if not self._busy and (self._page + 1) * self._page_size < self._total:
            self._page += 1; self._search(False)

    def _load_categories(self):
        w = CategoryWorker(self._client)
        w.signals.result.connect(self._on_cats)
        w.signals.error.connect(lambda e: self._set_status(f"{i18n.tr('err_title')}: {e}"))
        self._pool.start(w)

    @pyqtSlot(object)
    def _on_cats(self, cats: list[Category]):
        cur = self._explore.cat_combo.currentText()
        self._cat_opts = [CategoryOption(None, i18n.tr("cat_all"))]
        self._cat_opts.extend(CategoryOption(c.id, c.name) for c in cats)
        cb = self._explore.cat_combo
        cb.blockSignals(True); cb.clear()
        cb.addItems([str(c) for c in self._cat_opts])
        idx = cb.findText(cur)
        cb.setCurrentIndex(idx if idx >= 0 else 0)
        cb.blockSignals(False)

    def _search(self, reset_page: bool):
        if self._busy: return
        if reset_page: self._page = 0
        self._set_busy(True, i18n.tr("searching"))
        q   = self._explore.search_entry.text().strip()
        ci  = self._explore.cat_combo.currentIndex()
        cat = self._cat_opts[ci] if 0 <= ci < len(self._cat_opts) else self._cat_opts[0]
        si  = self._explore.sort_combo.currentIndex()
        srt = self._sort_opts[si] if 0 <= si < len(self._sort_opts) else self._sort_opts[0]
        w = SearchWorker(self._client, q, cat.id, srt.field, srt.order, self._page)
        w.signals.result.connect(self._on_search_result)
        w.signals.error.connect(self._on_search_error)
        self._pool.start(w)

    @pyqtSlot(object)
    def _on_search_result(self, result):
        self._mods      = [m for m in result.mods if m.name.strip()]
        self._total     = result.pagination.total_count
        self._page_size = result.pagination.page_size or SEARCH_PAGE_SIZE
        self._refresh_installed()
        self._render_cards(); self._update_pager()
        self._set_busy(False, i18n.tr("results_fmt", len(self._mods)))

    @pyqtSlot(str)
    def _on_search_error(self, msg: str):
        self._set_busy(False, i18n.tr("err_search"))
        QMessageBox.critical(self, i18n.tr("err_title"), msg)

    def _render_cards(self):
        vbar = self._explore.scroll.verticalScrollBar()
        old_v = vbar.value()

        for card in self._cards:
            self._explore.grid.removeWidget(card)
            card.hide(); card.deleteLater()
        self._cards = []

        if not self._mods:
            empty = QLabel(i18n.tr("empty_search"))
            empty.setObjectName("emptyState")
            empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self._explore.grid.addWidget(empty, 0, 0, 1, self._cols)
            return

        for col in range(max(self._cols, 4)):
            self._explore.grid.setColumnStretch(col, 1 if col < self._cols else 0)

        for i, mod in enumerate(self._mods):
            card = ModCard(mod, mod.id in self._installed, self._palette)
            card.install_requested.connect(self._on_install_req)
            card.remove_requested.connect(self._on_remove_card)
            card.web_requested.connect(self._on_web)
            r, c = divmod(i, self._cols)
            self._explore.grid.addWidget(card, r, c)
            self._cards.append(card); card.show()
            self._load_image(mod, card)

        # Restore scroll position after rebuilding the grid
        QApplication.instance().processEvents()
        vbar.setValue(old_v)

    def _load_image(self, mod: Mod, card: ModCard):
        url = mod.logo.thumbnail_url if mod.logo else None
        if not url: card.set_image_error(); return
        if url in self._image_cache: card.set_image(self._image_cache[url]); return
        reply = self._nam.get(QNetworkRequest(QUrl(url)))
        self._pending[reply] = (url, card)
        reply.finished.connect(lambda r=reply: self._on_img(r))

    def _on_img(self, reply: QNetworkReply):
        entry = self._pending.pop(reply, None)
        if not entry: reply.deleteLater(); return
        url, card = entry
        if reply.error() != QNetworkReply.NetworkError.NoError:
            card.set_image_error(); reply.deleteLater(); return
        data: QByteArray = reply.readAll(); reply.deleteLater()
        img = QImage()
        if not img.loadFromData(data): card.set_image_error(); return
        px = QPixmap.fromImage(img)
        self._image_cache[url] = px; card.set_image(px)

    @pyqtSlot(object)
    def _on_install_req(self, mod: Mod):
        if self._busy: return
        self._set_busy(True, i18n.tr("loading_files", mod.name))
        w = FetchFilesWorker(self._client, mod)
        w.signals.result.connect(lambda files, m=mod: self._on_files_fetched(m, files))
        w.signals.error.connect(self._on_install_error)
        self._pool.start(w)

    @pyqtSlot(object)
    def _on_files_fetched(self, mod: Mod, files: list[ModFile]):
        if not files:
            self._set_busy(False, i18n.tr("no_files"))
            QMessageBox.warning(self, i18n.tr("warn_title"), i18n.tr("no_files_msg"))
            return
        selected = files[0] if len(files) == 1 else None
        if selected is None:
            dlg = FilePickerDialog(mod, files, self)
            if dlg.exec() != QDialog.DialogCode.Accepted:
                self._set_busy(False, i18n.tr("cancelled")); return
            selected = dlg.selected_file()
        if selected is None:
            self._set_busy(False, i18n.tr("cancelled")); return
        self._set_status(i18n.tr("installing", mod.name))
        w = InstallWorker(self._client, mod, self._mods_dir(), selected)
        w.signals.result.connect(lambda _: self._on_install_done(mod))
        w.signals.error.connect(self._on_install_error)
        w.signals.status.connect(self._set_status)
        self._pool.start(w)

    @pyqtSlot(object)
    def _on_install_done(self, mod: Mod):
        try:
            lf  = lockfile_store.load(self._mods_dir())
            ref = lf.mods.get(mod.id)
            if ref and not ref.mod_name:
                ref.mod_name = mod.name; ref.is_managed = True
                lockfile_store.save(self._mods_dir(), lf)
        except Exception:
            pass
        self._refresh_installed(); self._render_cards()
        self._update_installed_tab_badge()
        self._set_busy(False, i18n.tr("install_done"))

    @pyqtSlot(str)
    def _on_install_error(self, msg: str):
        self._set_busy(False, i18n.tr("err_title"))
        QMessageBox.critical(self, i18n.tr("err_title"), msg)

    @pyqtSlot(object)
    def _on_remove_card(self, mod: Mod):
        try:
            mods_dir = self._mods_dir(); mods_dir.mkdir(parents=True, exist_ok=True)
            lf  = lockfile_store.load(mods_dir)
            ref = lf.mods.get(mod.id)
            if ref:
                for p in [mods_dir / ref.file_name,
                           mods_dir / (ref.file_name + lockfile_store.DISABLED_SUFFIX)]:
                    if p.exists(): p.unlink()
                lf.mods.pop(mod.id, None)
                lockfile_store.save(mods_dir, lf)
            self._refresh_installed(); self._render_cards()
            self._update_installed_tab_badge()
            self._set_status(i18n.tr("mod_removed", mod.name))
        except Exception as exc:
            QMessageBox.critical(self, i18n.tr("err_title"), str(exc))

    @pyqtSlot(object)
    def _on_web(self, mod: Mod):
        url = mod.display_url()
        if url: webbrowser.open(url)
        else: QMessageBox.information(self, i18n.tr("info_title"), i18n.tr("no_url"))

    def _on_installed_changed(self):
        self._refresh_installed(); self._render_cards()
        self._update_installed_tab_badge()

    def _refresh_installed(self):
        self._installed.clear()
        try:
            d = self._mods_dir(); d.mkdir(parents=True, exist_ok=True)
            self._installed.update(lockfile_store.load(d).mods)
        except Exception: pass

    def _update_pager(self):
        total_pages = max(1, math.ceil(self._total / max(self._page_size, 1)))
        self._explore.page_lbl.setText(
            i18n.tr("page_fmt", min(self._page + 1, total_pages), total_pages))

    def _update_installed_tab_badge(self):
        n = len(self._installed)
        txt = f"{i18n.tr('tab_installed')} ({n})" if n else i18n.tr("tab_installed")
        self._tab_installed.setText(txt)

    def _set_busy(self, busy: bool, status: str):
        self._busy = busy
        ex = self._explore
        for w in [ex.search_btn, ex.search_entry, ex.sort_combo, ex.cat_combo]:
            w.setEnabled(not busy)
        ex.prev_btn.setEnabled(not busy and self._page > 0)
        ex.next_btn.setEnabled(not busy and (self._page + 1) * self._page_size < self._total)
        self._set_status(status)

    def _set_status(self, text: str):
        self._status_lbl.setText(text)
        self.statusBar().showMessage(text)


# ── Entry point ───────────────────────────────────────────────────────────────
def main() -> None:
    app = QApplication(sys.argv)
    app.setApplicationName("Hytale Mod Launcher")
    app.setHighDpiScaleFactorRoundingPolicy(
        Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
    )
    window = LauncherWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
