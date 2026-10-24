# Paczka aplikacji okienkowej (PyInstaller, folder z programem):
#   npm --prefix frontend run build
#   uv run pyinstaller packaging/faktury-ksef.spec --noconfirm
# Instalator Windows powstaje z tego folderu przez packaging/installer.iss.

import sys
from pathlib import Path

from PyInstaller.utils.hooks import collect_data_files, copy_metadata

ROOT = Path(SPECPATH).parent
NAME = "Faktury KSeF"

if not (ROOT / "frontend" / "dist" / "index.html").is_file():
    raise SystemExit("Najpierw zbuduj interfejs: npm --prefix frontend run build")

# Okno korzysta z modułu platformy importowanego dopiero przy starcie.
WINDOW = (
    ["webview.platforms.winforms", "webview.platforms.edgechromium"]
    if sys.platform == "win32"
    else ["webview.platforms.cocoa"]
)

a = Analysis(
    [str(ROOT / "packaging" / "launcher.py")],
    pathex=[str(ROOT / "src")],
    datas=[
        (str(ROOT / "frontend" / "dist"), "frontend"),
        *copy_metadata("accounting-agent"),
        *collect_data_files("signxml"),
        *collect_data_files("fpdf"),
    ],
    hiddenimports=WINDOW,
    excludes=["tkinter"],
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name=NAME,
    console=False,
    icon=str(ROOT / "packaging" / "icon.ico"),
    upx=False,
)
coll = COLLECT(exe, a.binaries, a.datas, name=NAME, upx=False)
