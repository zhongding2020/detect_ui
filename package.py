#!/usr/bin/env python3
"""
简单版打包脚本 - 一键打包
"""

import os
import sys
import subprocess
import shutil
import py_compile


def check_dependencies():
    """检查依赖是否安装"""
    print("=" * 70)
    print("检查依赖...")
    print("=" * 70)
    
    dependencies = [
        ('PyInstaller', 'pyinstaller>=5.10.0'),
        ('PyQt5', 'pyqt5>=5.15.0'),
        ('cv2', 'opencv-python>=4.5.0'),
        ('watchdog', 'watchdog>=3.0.0'),
        ('sklearn', 'scikit-learn>=1.3.0'),
        ('pandas', 'pandas>=3.0.3'),
        ('PIL', 'Pillow>=10.0.0'),
    ]
    
    all_installed = True
    
    for import_name, package_name in dependencies:
        try:
            __import__(import_name)
            print(f"✓ {package_name.split('>=')[0]}: 已安装")
        except ImportError:
            print(f"✗ {package_name.split('>=')[0]}: 未安装")
            print(f"  正在安装...")
            try:
                subprocess.check_call([sys.executable, '-m', 'pip', 'install', package_name])
                print(f"  ✓ {package_name.split('>=')[0]} 安装成功")
            except Exception as e:
                print(f"  ✗ 安装失败，请手动运行: pip install {package_name}")
                print(f"    错误: {e}")
                all_installed = False
    
    print()
    return all_installed


def compile_all_plugins():
    """编译所有插件"""
    print("=" * 70)
    print("编译所有插件为 .pyc...")
    print("=" * 70)
    
    count = 0
    plugins_dir = 'plugins'
    if not os.path.exists(plugins_dir):
        print("  警告: plugins目录不存在")
        return
    
    for root, dirs, files in os.walk(plugins_dir):
        for file in files:
            if file.endswith('.py') and not file.startswith('__'):
                py_file = os.path.join(root, file)
                pyc_file = py_file + 'c'
                
                try:
                    py_compile.compile(py_file, pyc_file, doraise=True)
                    print(f"  ✓ {file}")
                    count += 1
                except Exception as e:
                    print(f"  ✗ {file}: {e}")
    
    print(f"  编译完成: {count} 个插件")
    print()


def clean_before_build():
    """清理旧的构建文件"""
    print("=" * 70)
    print("清理旧文件...")
    print("=" * 70)
    
    dirs_to_remove = ['build', 'dist']
    for dir_name in dirs_to_remove:
        if os.path.exists(dir_name):
            shutil.rmtree(dir_name)
            print(f"  ✓ 删除 {dir_name}")
    
    print()


def copy_plugins_to_dist():
    """复制编译好的插件到 dist 目录"""
    print("=" * 70)
    print("准备插件...")
    print("=" * 70)
    
    dist_dir = 'dist'
    if not os.path.exists(dist_dir):
        os.makedirs(dist_dir)
    
    plugins_source = 'plugins'
    plugins_dest = os.path.join(dist_dir, 'plugins')
    
    if os.path.exists(plugins_dest):
        shutil.rmtree(plugins_dest)
    
    # 创建目录结构
    def ignore_non_pyc_and_init(dir_name, files):
        return [
            f for f in files 
            if (f.endswith('.py') and f != '__init__.py') or 
               f.endswith('.pyc') or
               f == '__pycache__'
        ]
    
    # 先复制目录结构和 __init__.py
    shutil.copytree(plugins_source, plugins_dest, ignore=lambda d, f: [
        item for item in f
        if item.endswith('.py') and item != '__init__.py'
    ])
    
    # 然后复制 pyc 文件
    for root, dirs, files in os.walk(plugins_source):
        for file in files:
            if file.endswith('.pyc'):
                src = os.path.join(root, file)
                rel = os.path.relpath(root, plugins_source)
                dest_dir = os.path.join(plugins_dest, rel)
                dest = os.path.join(dest_dir, file)
                
                if os.path.exists(dest_dir):
                    shutil.copy2(src, dest)
                    print(f"  ✓ 复制 {file}")
    
    print("  插件准备完成")
    print()


def run_pyinstaller_simple():
    """运行 PyInstaller 使用 spec 文件"""
    print("=" * 70)
    print("开始 PyInstaller 打包...")
    print("=" * 70)
    
    # 使用 python -m PyInstaller 调用，更可靠
    cmd = [
        sys.executable, '-m', 'PyInstaller',
        '--clean',
        '--noconfirm',
        'ultrasound_defect_detection.spec'
    ]
    
    try:
        result = subprocess.run(cmd, check=True)
        print("  ✓ 打包完成")
        return True
    except Exception as e:
        print(f"  ✗ 打包失败: {e}")
        print(f"\n  请尝试手动安装: pip install pyinstaller")
        return False
    finally:
        print()


def show_finish_info():
    """显示完成信息"""
    print("=" * 70)
    print("打包完成!")
    print("=" * 70)
    print()
    
    if os.path.exists('dist'):
        exe_file = 'ultrasound_defect_detection.exe' if sys.platform == 'win32' else 'ultrasound_defect_detection'
        exe_path = os.path.join('dist', exe_file)
        
        if os.path.exists(exe_path):
            size = os.path.getsize(exe_path) / (1024 * 1024)
            print(f"✓ 可执行文件:")
            print(f"  {os.path.abspath(exe_path)}")
            print(f"  大小: {size:.1f} MB")
            
            print()
            print("使用方法:")
            print("  1. 确保 'plugins' 文件夹与可执行文件在同一目录")
            print("  2. 双击运行或在命令行执行")
            print("  3. 选择图片或文件夹进行检测")
            print()
            print("目录结构:")
            print(f"  {exe_file}")
            print(f"  plugins/")
            print(f"    base/")
            print(f"    detectors/")
            print()


def main():
    print()
    print("╔" + "═" * 68 + "╗")
    print("║" + " " * 10 + "超声缺陷检测系统 - 打包工具" + " " * 33 + "║")
    print("╚" + "═" * 68 + "╝")
    print()
    
    # 检查依赖
    if not check_dependencies():
        print("\n依赖检查失败，请先安装依赖!")
        return
    
    # 检查是否在项目根目录
    if not os.path.exists('bearing_defect_detection.py'):
        print("错误: 请在项目根目录运行此脚本")
        print(f"当前目录: {os.getcwd()}")
        sys.exit(1)
    
    # 清理
    clean_before_build()
    
    # 编译插件
    compile_all_plugins()
    
    # 打包
    if not run_pyinstaller_simple():
        print("\n打包失败!")
        sys.exit(1)
    
    # 复制插件
    copy_plugins_to_dist()
    
    # 完成信息
    show_finish_info()


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\n用户中断")
        sys.exit(1)
    except Exception as e:
        print(f"\n\n错误: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
