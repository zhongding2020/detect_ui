# -*- mode: python ; coding: utf-8 -*-
"""
超声缺陷检测系统 - PyInstaller 打包配置
"""

import os
import sys
from pathlib import Path

block_cipher = None

# 收集数据文件
datas = []

# 添加插件目录
plugins_dir = 'plugins'
if os.path.exists(plugins_dir):
    datas.append((plugins_dir, 'plugins'))

a = Analysis(
    ['bearing_defect_detection.py'],
    pathex=[],
    binaries=[],
    datas=datas,
    hiddenimports=[
        'PyQt5',
        'PyQt5.QtCore',
        'PyQt5.QtGui',
        'PyQt5.QtWidgets',
        'cv2',
        'numpy',
        'watchdog',
        'watchdog.observers',
        'watchdog.events',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name='ultrasound_defect_detection',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,  # 设置为 False 隐藏控制台窗口
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=None,  # Windows: 添加图标路径 'icon.ico'
)
