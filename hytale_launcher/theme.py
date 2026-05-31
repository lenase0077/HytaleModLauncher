"""Theme manager for HytaleModLauncher.

Provides a Palette dataclass and a QSS generator to allow hot-swapping
between different color themes (Dark, Dracula, Ocean, Light).
"""

from __future__ import annotations

from dataclasses import dataclass

@dataclass(frozen=True)
class Palette:
    name: str
    bg: str
    surface: str
    surface2: str
    card: str
    border: str
    border_lit: str
    accent: str
    green: str
    red: str
    amber: str
    purple: str
    text: str
    text2: str
    text3: str
    btn: str
    btn_h: str

THEMES = {
    "Dark": Palette(
        name="Dark",
        bg="#080B12", surface="#0E1420", surface2="#131926",
        card="#111827", border="#1E293B", border_lit="#334155",
        accent="#06B6D4", green="#10B981", red="#F43F5E",
        amber="#F59E0B", purple="#818CF8",
        text="#F1F5F9", text2="#94A3B8", text3="#475569",
        btn="#1E293B", btn_h="#273447"
    ),
    "Dracula": Palette(
        name="Dracula",
        bg="#282A36", surface="#44475A", surface2="#44475A",
        card="#282A36", border="#6272A4", border_lit="#8BE9FD",
        accent="#FF79C6", green="#50FA7B", red="#FF5555",
        amber="#F1FA8C", purple="#BD93F9",
        text="#F8F8F2", text2="#F8F8F2", text3="#6272A4",
        btn="#44475A", btn_h="#6272A4"
    ),
    "Ocean": Palette(
        name="Ocean",
        bg="#0F172A", surface="#1E293B", surface2="#0F172A",
        card="#0F172A", border="#334155", border_lit="#475569",
        accent="#38BDF8", green="#34D399", red="#FB7185",
        amber="#FBBF24", purple="#A78BFA",
        text="#F8FAFC", text2="#CBD5E1", text3="#64748B",
        btn="#1E293B", btn_h="#334155"
    ),
    "Light": Palette(
        name="Light",
        bg="#F8FAFC", surface="#F1F5F9", surface2="#E2E8F0",
        card="#FFFFFF", border="#CBD5E1", border_lit="#94A3B8",
        accent="#0284C7", green="#059669", red="#E11D48",
        amber="#D97706", purple="#4F46E5",
        text="#0F172A", text2="#334155", text3="#64748B",
        btn="#FFFFFF", btn_h="#F1F5F9"
    ),
}

def generate_qss(palette: Palette) -> str:
    P = palette
    return f"""
* {{ box-sizing: border-box; }}
QMainWindow, QDialog {{ background-color: {P.bg}; }}
QWidget {{
    font-family: 'Segoe UI', 'Inter', 'Arial', sans-serif;
    font-size: 10pt;
    color: {P.text};
    background-color: transparent;
}}
/* Scrollbars */
QScrollArea {{ background-color: {P.bg}; border: none; }}
QScrollBar:vertical {{ background:{P.surface}; width:6px; border-radius:3px; }}
QScrollBar::handle:vertical {{ background:{P.border_lit}; border-radius:3px; min-height:32px; }}
QScrollBar::handle:vertical:hover {{ background:{P.accent}; }}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height:0; }}
QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{ background:none; }}

/* Header */
#headerBar {{
    background-color: {P.bg};
    border-bottom: 1px solid {P.border};
}}
#appTitle {{ font-size:20pt; font-weight:700; color:{P.text}; }}
#accentWord {{ font-size:20pt; font-weight:900; color:{P.accent}; }}
#statusLabel {{ font-size:9pt; color:{P.text2}; }}
#badgeLabel {{
    background-color: transparent; color:{P.amber};
    font-weight:700; border-radius:8px; padding:4px 12px; font-size:9pt;
    border:1px solid {P.amber};
}}

/* Tab bar */
#tabBar {{ background-color:{P.surface}; border-bottom:1px solid {P.border}; }}
#tabBtn {{
    background:transparent; border:none;
    border-bottom:3px solid transparent; border-radius:0;
    color:{P.text2}; font-size:10pt; font-weight:600;
    padding:10px 24px; min-width:140px;
}}
#tabBtn:hover {{ color:{P.text}; background-color:{P.surface2}; }}
#tabBtnActive {{
    background:transparent; border:none;
    border-bottom:3px solid {P.accent}; border-radius:0;
    color:{P.accent}; font-size:10pt; font-weight:700;
    padding:10px 24px; min-width:140px;
}}

/* Controls */
#controlsPanel {{ background-color:{P.surface}; border-bottom:1px solid {P.border}; }}

/* Inputs */
QLineEdit {{
    background-color:{P.surface2}; border:1px solid {P.border};
    border-radius:8px; color:{P.text}; padding:6px 12px;
}}
QLineEdit:focus {{ border-color:{P.accent}; }}
QLineEdit:disabled {{ color:{P.text3}; }}
QComboBox {{
    background-color:{P.surface2}; border:1px solid {P.border};
    border-radius:8px; color:{P.text}; padding:6px 12px; min-width:130px;
}}
QComboBox:focus {{ border-color:{P.accent}; }}
QComboBox:disabled {{ color:{P.text3}; }}
QComboBox::drop-down {{ border:none; width:20px; }}
QComboBox::down-arrow {{
    width:0; height:0;
    border-left:4px solid transparent; border-right:4px solid transparent;
    border-top:5px solid {P.text2};
}}
QComboBox QAbstractItemView {{
    background-color:{P.surface2}; border:1px solid {P.border_lit};
    border-radius:8px; color:{P.text};
    selection-background-color:{P.btn_h}; outline:none; padding:4px;
}}

/* Buttons — base */
QPushButton {{
    background-color:{P.btn}; color:{P.text};
    border:1px solid {P.border_lit}; border-radius:8px;
    padding:6px 16px; font-weight:600;
}}
QPushButton:hover {{ background-color:{P.btn_h}; border-color:{P.accent}; }}
QPushButton:pressed {{ background-color:{P.surface}; }}
QPushButton:disabled {{ background-color:{P.surface}; color:{P.text3}; border-color:{P.border}; }}

/* Accent (search) */
QPushButton#accentBtn {{
    background-color:{P.accent}; color:#000; border:1px solid {P.accent}; font-weight:700;
}}
QPushButton#accentBtn:hover {{ opacity:0.9; border-color:{P.text}; color:#000; }}
QPushButton#accentBtn:pressed {{ opacity:0.8; color:#000; }}
QPushButton#accentBtn:disabled {{ background-color:{P.surface}; color:{P.text3}; border-color:{P.border}; }}

/* Colored buttons are now styled inline via Python to avoid layout bugs inside QFrames. */

/* Cards */
QFrame#modCard {{
    background-color:{P.card}; border:1px solid {P.border}; border-radius:14px;
}}
QFrame#modCard:hover {{ border-color:{P.border_lit}; }}
#cardName {{ font-size:10pt; font-weight:700; color:{P.text}; }}
#cardSummary {{ font-size:9pt; color:{P.text2}; }}
QLabel#cardImage {{
    background-color:{P.surface2}; border-radius:10px;
    color:{P.text3}; font-size:9pt;
}}

/* Installed panel */
#installedPanel, #settingsPanel {{ background-color:{P.bg}; }}
#installedHeader {{
    background-color: {P.bg};
    border-bottom:1px solid {P.border};
}}
#installedTitle {{ font-size:15pt; font-weight:700; color:{P.text}; }}
#installedSubtitle {{ font-size:9pt; color:{P.text2}; }}
#actionBar {{ background-color:{P.surface}; border-bottom:1px solid {P.border}; }}

/* Mod rows */
QFrame#modRow {{
    background-color:{P.card}; border:1px solid {P.border}; border-radius:12px;
}}
QFrame#modRow:hover {{ border-color:{P.border_lit}; }}
#rowName {{ font-size:10pt; font-weight:700; color:{P.text}; }}
#rowFile {{ font-size:8pt; color:{P.text3}; font-family:'Consolas','Courier New',monospace; }}
#enabledDot {{ font-size:16pt; color:{P.green}; }}
#disabledDot {{ font-size:16pt; color:{P.text3}; }}

/* Update all */
QPushButton#updateAllBtn {{
    background-color:{P.purple}; color:#fff; border:1px solid {P.purple}; font-weight:700; font-size:9pt;
}}
QPushButton#updateAllBtn:hover {{ opacity: 0.8; border-color:{P.text}; color:#fff; }}

#emptyState {{ color:{P.text2}; font-size:12pt; padding:60px; }}
#pageLabel {{
    background-color:{P.surface2}; color:{P.text}; font-weight:700;
    border-radius:8px; padding:5px 16px; border:1px solid {P.border};
}}
#folderLabel {{ font-weight:600; color:{P.text2}; font-size:9pt; }}

QStatusBar {{
    background-color:{P.surface}; color:{P.text2};
    font-size:9pt; border-top:1px solid {P.border};
}}
QDialog {{ background-color:{P.surface}; }}
"""
