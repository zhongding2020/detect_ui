# 超声缺陷检测系统 - 打包指南

本文档介绍如何将软件打包为独立的可执行文件，不包含源代码。

---

## 📋 前置要求

### 1. 安装 Python
确保已安装 Python 3.8 或更高版本。

### 2. 安装依赖
```bash
pip install -r requirements.txt
```

### 3. 安装 PyInstaller
```bash
pip install pyinstaller
```

---

## 🚀 快速开始

### 方式1：使用一键打包脚本（推荐）

```bash
python package.py
```

这个脚本会：
1. ✅ 清理旧的构建文件
2. ✅ 编译所有插件为 .pyc
3. ✅ 使用 PyInstaller 打包
4. ✅ 复制插件到输出目录
5. ✅ 显示打包信息

### 方式2：使用完整打包脚本

```bash
python build.py
```

### 方式3：直接使用 PyInstaller

```bash
# 先编译插件
python -c "import py_compile, os; list(map(lambda f: py_compile.compile(f), [os.path.join(r,f) for r,_,fs in os.walk('plugins') for f in fs if f.endswith('.py')]))"

# 然后使用 spec 文件打包
pyinstaller --clean --noconfirm ultrasound_defect_detection.spec

# 最后复制 plugins 到 dist 目录
# (Windows: xcopy plugins dist\plugins /E /I /Y)
# (Linux/Mac: cp -r plugins dist/)
```

---

## 📁 输出目录结构

打包完成后，输出目录结构如下：

```
dist/
├── ultrasound_defect_detection.exe  (Windows)
└── plugins/
    ├── __init__.pyc
    ├── plugin_manager.pyc
    ├── base/
    │   ├── __init__.pyc
    │   └── defect_base.pyc
    └── detectors/
        ├── __init__.pyc
        ├── mock_detector.pyc
        ├── yolov8_detector.pyc
        └── template_detector.pyc
```

**重要**：`plugins` 目录必须与可执行文件放在一起！

---

## 🛠️ 详细打包步骤

### 步骤1：准备工作

确保项目目录结构正确：
```
trae_projects/
├── bearing_defect_detection.py
├── package.py
├── ultrasound_defect_detection.spec
├── requirements.txt
└── plugins/
    ├── __init__.py
    ├── plugin_manager.py
    ├── base/
    └── detectors/
```

### 步骤2：运行打包脚本

```bash
python package.py
```

### 步骤3：检查输出

打包成功后，检查 `dist/` 目录：
- 可执行文件存在
- plugins 目录已复制

### 步骤4：测试

在分发前，测试打包后的程序：
1. 进入 `dist/` 目录
2. 运行可执行文件
3. 验证插件加载正常
4. 测试所有功能

---

## 📤 分发说明

### Windows

创建一个 ZIP 压缩包：

```bash
cd dist/
# 打包为 ultrasound_defect_detection_v1.0.zip
# 包含可执行文件和 plugins 文件夹
```

### Linux

创建 tar.gz 或 AppImage：

```bash
cd dist/
tar -czf ultrasound_defect_detection_v1.0.tar.gz ultrasound_defect_detection plugins/
```

### macOS

创建 .app 包或 DMG：
```bash
# 需要额外的配置
```

---

## 📦 requirements.txt 更新

如果使用新的依赖，更新 requirements.txt：

```
PyQt5>=5.15.0
opencv-python>=4.5.0
# 添加新的依赖
```

然后重新打包。

---

## 🔧 常见问题

### 问题1：找不到 PyInstaller

**错误**：`No module named 'PyInstaller'`

**解决**：
```bash
pip install pyinstaller
```

### 问题2：打包后找不到插件

**原因**：plugins 目录位置错误

**解决**：
- 确保 `plugins/` 与可执行文件在同一目录
- 检查插件路径配置

### 问题3：OpenCV 相关错误

**解决**：
```bash
# 确保 opencv-python 已安装
pip install opencv-python

# 更新 spec 文件中的 hiddenimports
hiddenimports=['cv2', 'numpy'],
```

### 问题4：文件太大

**解决**：
- 使用 UPX 压缩
- 排除不必要的模块
- 检查 spec 文件配置

---

## 🎯 高级选项

### 修改窗口图标

编辑 `ultrasound_defect_detection.spec`：
```python
exe = EXE(
    ...
    icon='icon.ico',  # 添加这行
    ...
)
```

### 启用控制台（调试用）

在 spec 文件中设置：
```python
console=True,  # 显示控制台窗口
```

### 添加启动画面

参考 PyInstaller 文档添加 splash screen。

### 创建安装程序

使用 NSIS（Windows）或其他安装包制作工具：

```ini
# nsis 脚本示例
!define APP_NAME "超声缺陷检测系统"
!define APP_VERSION "1.0.0"
```

---

## 📊 打包检查清单

- [ ] 安装所有依赖（PyInstaller, PyQt5, OpenCV）
- [ ] 运行 package.py 无错误
- [ ] 检查 dist/ 目录结构正确
- [ ] 可执行文件可以正常启动
- [ ] 插件可以正常加载
- [ ] 图片选择功能正常
- [ ] 检测功能正常
- [ ] 结果显示正常
- [ ] 创建分发包（ZIP/EXE/DMG）

---

## 📝 版本控制

打包时，建议更新版本号：

1. 在代码中更新版本号
2. 更新 spec 文件中的名称
3. 打包后测试
4. 分发包命名包含版本号

```
ultrasound_defect_detection_v1.0.0.zip
ultrasound_defect_detection_v1.0.1.zip
...
```

---

## 📞 故障排除

如遇到问题，查看：
1. 终端错误信息
2. build/warn-ultrasound_defect_detection.txt（警告信息）
3. build/error-ultrasound_defect_detection.txt（错误信息）

---

**打包顺利！** 🎉
