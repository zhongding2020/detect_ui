#!/usr/bin/env python3
"""
安装打包所需的依赖
"""

import sys
import subprocess

print("=" * 70)
print("安装打包依赖...")
print("=" * 70)
print()

# 安装 requirements.txt 中的所有依赖
try:
    print("正在安装依赖...")
    subprocess.check_call([
        sys.executable, '-m', 'pip', 'install',
        '-r', 'requirements.txt'
    ])
    print()
    print("✓ 依赖安装成功!")
except Exception as e:
    print(f"✗ 安装失败: {e}")
    sys.exit(1)

print()
print("现在可以运行打包脚本了:")
print("  python package.py")
print()
