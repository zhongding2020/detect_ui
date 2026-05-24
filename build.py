#!/usr/bin/env python3
"""
超声缺陷检测系统 - 打包脚本

使用 PyInstaller 将软件打包为可执行文件
"""

import os
import sys
import shutil
from pathlib import Path


def check_dependencies():
    """检查依赖是否安装"""
    print("=" * 70)
    print("检查依赖...")
    print("=" * 70)
    
    try:
        import PyInstaller
        print("✓ PyInstaller: 已安装")
    except ImportError:
        print("✗ PyInstaller: 未安装")
        print("  请运行: pip install pyinstaller")
        return False
    
    try:
        import PyQt5
        print("✓ PyQt5: 已安装")
    except ImportError:
        print("✗ PyQt5: 未安装")
        print("  请运行: pip install pyqt5")
        return False
    
    print()
    return True


def clean_build_dirs():
    """清理构建目录"""
    print("=" * 70)
    print("清理构建目录...")
    print("=" * 70)
    
    dirs_to_clean = ['build', 'dist']
    for dir_name in dirs_to_clean:
        if os.path.exists(dir_name):
            print(f"  删除目录: {dir_name}")
            shutil.rmtree(dir_name)
    
    spec_files = ['ultrasound_defect_detection.spec', 'detector.spec']
    for spec_file in spec_files:
        if os.path.exists(spec_file):
            print(f"  删除文件: {spec_file}")
            os.remove(spec_file)
    
    print("✓ 清理完成")
    print()


def compile_plugins():
    """编译插件为 pyc 文件"""
    print("=" * 70)
    print("编译插件...")
    print("=" * 70)
    
    import py_compile
    
    plugins_dir = 'plugins'
    if not os.path.exists(plugins_dir):
        print(f"  警告: {plugins_dir} 目录不存在")
        return
    
    # 编译所有插件
    compiled_count = 0
    for root, dirs, files in os.walk(plugins_dir):
        # 跳过 __pycache__
        if '__pycache__' in root:
            continue
        
        for file in files:
            if file.endswith('.py') and not file.startswith('__'):
                py_file = os.path.join(root, file)
                pyc_file = py_file + 'c'
                
                print(f"  编译: {py_file}")
                
                try:
                    py_compile.compile(py_file, pyc_file, doraise=True)
                    compiled_count += 1
                except Exception as e:
                    print(f"    警告: 编译失败 - {e}")
    
    print(f"✓ 编译完成，共编译 {compiled_count} 个插件")
    print()


def create_output_dirs():
    """创建输出目录结构"""
    print("=" * 70)
    print("创建输出目录结构...")
    print("=" * 70)
    
    # 创建临时目录用于复制插件
    temp_dir = 'temp_build'
    if os.path.exists(temp_dir):
        shutil.rmtree(temp_dir)
    os.makedirs(temp_dir)
    
    # 复制插件（只复制 pyc 和 __init__.py）
    plugins_temp = os.path.join(temp_dir, 'plugins')
    os.makedirs(plugins_temp)
    
    plugins_source = 'plugins'
    if os.path.exists(plugins_source):
        for root, dirs, files in os.walk(plugins_source):
            # 创建相应的目录
            relative_path = os.path.relpath(root, plugins_source)
            target_dir = os.path.join(plugins_temp, relative_path)
            
            if not os.path.exists(target_dir):
                os.makedirs(target_dir)
            
            # 复制文件
            for file in files:
                # 只复制 __init__.py 和 .pyc 文件
                if file == '__init__.py' or file.endswith('.pyc'):
                    src_file = os.path.join(root, file)
                    dst_file = os.path.join(target_dir, file)
                    
                    # 不复制 __pycache__ 目录中的文件
                    if '__pycache__' in src_file:
                        continue
                    
                    shutil.copy2(src_file, dst_file)
                    print(f"  复制: {src_file} -> {dst_file}")
    
    print("✓ 目录结构创建完成")
    print()
    
    return temp_dir


def run_pyinstaller():
    """运行 PyInstaller"""
    print("=" * 70)
    print("开始打包...")
    print("=" * 70)
    
    # 使用 python -m PyInstaller 调用，更可靠
    command = [
        sys.executable, '-m', 'PyInstaller',
        '--onefile',
        '--windowed',
        '--name=ultrasound_defect_detection',
        '--add-data=plugins;plugins' if sys.platform == 'win32' else '--add-data=plugins:plugins',
        '--hidden-import=PyQt5',
        '--hidden-import=PyQt5.QtCore',
        '--hidden-import=PyQt5.QtGui',
        '--hidden-import=PyQt5.QtWidgets',
        '--hidden-import=cv2',
        'bearing_defect_detection.py'
    ]
    
    # 对于 Windows 平台，添加图标
    if sys.platform == 'win32':
        command.append('--icon=icon.ico')
    
    print(f"  命令: {' '.join(command)}")
    print()
    
    try:
        import subprocess
        result = subprocess.run(
            command,
            check=True,
            capture_output=True,
            text=True
        )
        print(result.stdout)
        if result.stderr:
            print(result.stderr)
        print("✓ PyInstaller 打包完成")
    except subprocess.CalledProcessError as e:
        print("✗ 打包失败!")
        print(f"  返回码: {e.returncode}")
        print(f"  输出: {e.output}")
        if e.stderr:
            print(f"  错误: {e.stderr}")
        print(f"\n  请确保已安装: pip install pyinstaller")
        return False
    except Exception as e:
        print(f"✗ 打包错误: {e}")
        import traceback
        traceback.print_exc()
        print(f"\n  请确保已安装: pip install pyinstaller")
        return False
    
    print()
    return True


def copy_plugins_to_dist():
    """复制编译好的插件到 dist 目录"""
    print("=" * 70)
    print("复制插件到输出目录...")
    print("=" * 70)
    
    dist_dir = 'dist'
    if not os.path.exists(dist_dir):
        print(f"  错误: {dist_dir} 目录不存在")
        return False
    
    # 复制 plugins 目录
    source_plugins = 'plugins'
    dest_plugins = os.path.join(dist_dir, 'plugins')
    
    if os.path.exists(source_plugins):
        if os.path.exists(dest_plugins):
            shutil.rmtree(dest_plugins)
        
        # 使用忽略模式，只复制 pyc 和 __init__.py
        def ignore_py_files(dir_name, files):
            return [f for f in files if f.endswith('.py') and f != '__init__.py']
        
        shutil.copytree(source_plugins, dest_plugins, ignore=ignore_py_files)
        
        # 复制 pyc 文件
        for root, dirs, files in os.walk(source_plugins):
            for file in files:
                if file.endswith('.pyc'):
                    src = os.path.join(root, file)
                    relative_root = os.path.relpath(root, source_plugins)
                    dest_dir = os.path.join(dest_plugins, relative_root)
                    dest = os.path.join(dest_dir, file)
                    
                    if os.path.exists(dest_dir):
                        shutil.copy2(src, dest)
                        print(f"  复制: {file}")
        
        print("✓ 插件复制完成")
    else:
        print(f"  警告: {source_plugins} 目录不存在")
    
    print()
    return True


def cleanup_temp():
    """清理临时文件"""
    print("=" * 70)
    print("清理临时文件...")
    print("=" * 70)
    
    if os.path.exists('temp_build'):
        shutil.rmtree('temp_build')
    
    if os.path.exists('ultrasound_defect_detection.spec'):
        os.remove('ultrasound_defect_detection.spec')
    
    print("✓ 清理完成")
    print()


def show_summary():
    """显示打包总结"""
    print("=" * 70)
    print("打包完成!")
    print("=" * 70)
    
    dist_dir = 'dist'
    if os.path.exists(dist_dir):
        exe_name = 'ultrasound_defect_detection.exe' if sys.platform == 'win32' else 'ultrasound_defect_detection'
        exe_path = os.path.join(dist_dir, exe_name)
        
        if os.path.exists(exe_path):
            print(f"\n✓ 可执行文件位置:")
            print(f"  {os.path.abspath(exe_path)}")
            
            # 显示大小
            size_mb = os.path.getsize(exe_path) / (1024 * 1024)
            print(f"\n✓ 文件大小: {size_mb:.1f} MB")
            
            print(f"\n✓ 使用方法:")
            print(f"  1. 确保 'plugins' 目录与可执行文件在同一位置")
            print(f"  2. 运行可执行文件")
            print(f"  3. 选择图片或文件夹进行检测")
    
    print("\n" + "=" * 70)


def main():
    """主函数"""
    print("\n" + "=" * 70)
    print("超声缺陷检测系统 - 打包工具")
    print("=" * 70 + "\n")
    
    # 检查依赖
    if not check_dependencies():
        print("\n请先安装依赖后重试!")
        return
    
    # 清理旧目录
    clean_build_dirs()
    
    # 编译插件
    compile_plugins()
    
    # 运行 PyInstaller
    if not run_pyinstaller():
        print("\n打包失败!")
        return
    
    # 复制插件到输出目录
    copy_plugins_to_dist()
    
    # 清理临时文件
    cleanup_temp()
    
    # 显示总结
    show_summary()


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
