# -*- mode: python ; coding: utf-8 -*-
from PyInstaller.utils.hooks import collect_submodules
from PyInstaller.utils.hooks import collect_all

datas = [('C:\\Users\\Head Huncho Guam\\AppData\\Local\\Programs\\Python\\Python314\\Lib\\tkinter', 'tkinter'), ('C:\\Users\\Head Huncho Guam\\AppData\\Local\\Programs\\Python\\Python314\\tcl\\tcl8.6', '_tcl_data'), ('C:\\Users\\Head Huncho Guam\\AppData\\Local\\Programs\\Python\\Python314\\tcl\\tk8.6', '_tk_data')]
datas += [('assets\\app_icon.ico', 'assets'), ('assets\\app_icon.png', 'assets')]
datas += [('client_secrets.json', '.')]
binaries = [('C:\\Users\\Head Huncho Guam\\AppData\\Local\\Programs\\Python\\Python314\\DLLs\\tcl86t.dll', '.'), ('C:\\Users\\Head Huncho Guam\\AppData\\Local\\Programs\\Python\\Python314\\DLLs\\tk86t.dll', '.'), ('C:\\Users\\Head Huncho Guam\\AppData\\Local\\Programs\\Python\\Python314\\DLLs\\_tkinter.pyd', '.')]
hiddenimports = ['tkinter', '_tkinter']
hiddenimports += collect_submodules('tkinter')
tmp_ret = collect_all('tkinterdnd2')
datas += tmp_ret[0]; binaries += tmp_ret[1]; hiddenimports += tmp_ret[2]
tmp_ret = collect_all('PIL')
datas += tmp_ret[0]; binaries += tmp_ret[1]; hiddenimports += tmp_ret[2]


a = Analysis(
    ['music_organizer.py'],
    pathex=[],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=['pyinstaller_tk_runtime_hook.py'],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='Music Distribution Organizer',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon='assets\\app_icon.ico',
)
