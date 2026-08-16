# -*- mode: python ; coding: utf-8 -*-

import os
import sys

# 确定项目根目录
PROJECT_ROOT = os.path.abspath('.')

a = Analysis(
    ['main.py'],
    pathex=[PROJECT_ROOT],
    binaries=[],
    datas=[
        ('plugins', 'plugins'),
        ('models', 'models'),
    ],
    hiddenimports=[
        # PyQt5
        'PyQt5', 'PyQt5.QtCore', 'PyQt5.QtGui', 'PyQt5.QtWidgets',
        'PyQt5.QtWidgets.QApplication',
        # OpenCV
        'cv2',
        # ML
        'sklearn', 'sklearn.ensemble', 'sklearn.preprocessing',
        'sklearn.tree', 'sklearn.utils',
        'joblib',
        # Image
        'PIL', 'PIL.Image', 'PIL.ImageDraw', 'PIL.ImageOps',
        # Data
        'pandas', 'numpy',
        # Watchdog
        'watchdog', 'watchdog.observers', 'watchdog.events',
        # Project modules
        'src', 'src.utils', 'src.utils.logging_utils',
        'src.utils.database_manager',
        'src.model', 'src.model.DetectionModel',
        'src.view', 'src.view.DetectionView',
        'src.presenter', 'src.presenter.DetectionPresenter',
        'plugins', 'plugins.base', 'plugins.base.defect_base',
        'plugins.plugin_manager',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=['ultralytics', 'torch', 'torchvision', 'matplotlib', 'tkinter'],
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
    name='ultrasound_defect_detection',
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
    icon=None,
)
