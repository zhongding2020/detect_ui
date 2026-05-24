# 超声缺陷检测系统

基于 PyQt5 和 YOLO 算法的超声缺陷检测可视化系统。

## 🎯 功能特性

### 核心功能
- **实时缺陷检测**：支持多种检测算法插件，实时检测图片中的缺陷
- **可视化标注**：检测结果以彩色框标注显示在图片上
- **状态判断**：自动判断检测结果为 OK（合格）或 NG（不合格）
- **历史记录**：支持查看历史检测记录，可恢复查看历史检测结果
- **记录持久化**：检测记录自动保存到 SQLite 数据库，重启软件后数据不丢失

### 插件系统
- **插件化架构**：支持动态加载检测算法插件
- **Mock 检测器**：内置模拟检测器，用于界面测试
- **模板检测器**：模板匹配检测算法示例
- **YOLOv8 检测器**：基于 YOLOv8 的深度学习检测算法

### 文件处理
- **单文件检测**：支持选择单个图片文件进行检测
- **文件夹监听**：支持监听文件夹，自动检测新增图片
- **多格式支持**：支持 JPG、PNG 等常见图片格式

## 📁 项目结构

```
welding_ui/
├── bearing_defect_detection.py    # 主程序入口
├── database_manager.py            # 数据库管理模块
├── requirements.txt               # 依赖列表
├── data/                          # 数据目录
│   ├── detection_records.db       # SQLite 数据库文件
│   └── results_images/            # 标注图片保存目录
├── plugins/                       # 插件目录
│   ├── base/                      # 插件基类
│   │   └── defect_base.py         # DetectionAlgorithmBase 基类
│   ├── detectors/                 # 检测器插件
│   │   ├── mock_detector.py       # 模拟检测器
│   │   ├── template_detector.py   # 模板检测器
│   │   └── yolov8_detector.py     # YOLOv8 检测器
│   └── plugin_manager.py          # 插件管理器
└── docs/                          # 文档目录
    ├── PLUGIN_DEVELOPMENT_GUIDE.md    # 插件开发指南
    ├── FOLDER_MONITOR_GUIDE.md        # 文件夹监听指南
    └── TEST_GUIDE.md                  # 测试指南
```

## 🛠️ 安装步骤

### 环境要求
- Python 3.8+
- Ubuntu 20.04+ (推荐)

### 安装依赖

```bash
# 克隆项目
git clone <repository-url>
cd welding_ui

# 创建虚拟环境
python -m venv .venv

# 激活虚拟环境
source .venv/bin/activate

# 安装依赖
pip install -r requirements.txt
```

### 安装 Qt 平台插件（Linux）

```bash
# Ubuntu/Debian
sudo apt-get install libxcb-xinerama0 libxcb-cursor0

# 设置环境变量（可选）
export QT_QPA_PLATFORM=xcb
```

## 🚀 运行程序

```bash
# 激活虚拟环境
source .venv/bin/activate

# 运行主程序
python bearing_defect_detection.py
```

## 📖 使用说明

### 检测流程

1. **选择检测插件**：从左侧侧边栏选择检测算法插件
2. **选择图片**：点击「📷 图片选择」选择待检测图片
   - 或点击「📁 文件夹选择」监听整个文件夹
3. **开始检测**：点击「⚡ 立即检测」开始检测
4. **查看结果**：检测结果会显示在主界面，包含：
   - 带标注的检测图片
   - 缺陷数量统计
   - OK/NG 状态标签

### 历史记录

1. **查看历史**：点击「📋 查看历史」打开历史记录对话框
2. **选择记录**：在历史记录中选择一条记录
3. **查看详情**：点击「👁️ 查看详情」在主界面显示该记录的检测结果

### 文件夹监听

1. **选择文件夹**：点击「📁 文件夹选择」选择监听目录
2. **启动监听**：点击「▶️ 启动监听」开始监听
3. **自动检测**：当有新图片添加到文件夹时，会自动进行检测

## 🔧 插件开发

参考 [PLUGIN_DEVELOPMENT_GUIDE.md](file:///home/ding/下载/welding_ui/PLUGIN_DEVELOPMENT_GUIDE.md) 了解如何开发自定义检测插件。

### 插件基类

所有检测插件必须继承 `DetectionAlgorithmBase` 类并实现 `detect` 方法：

```python
from plugins.base.defect_base import DetectionAlgorithmBase, DetectionResult

class MyDetector(DetectionAlgorithmBase):
    def detect(self, image_path: str) -> List[DetectionResult]:
        # 实现检测逻辑
        pass
```

## 📊 数据库结构

### detection_records 表

| 字段 | 类型 | 说明 |
|------|------|------|
| id | INTEGER | 主键，自增 |
| timestamp | TEXT | 检测时间 |
| image_path | TEXT | 原始图片路径 |
| filename | TEXT | 文件名 |
| defect_count | INTEGER | 缺陷数量 |
| status | TEXT | 状态（OK/NG） |
| elapsed_time | REAL | 检测耗时 |
| result_image_path | TEXT | 标注图片路径 |

### detection_results 表

| 字段 | 类型 | 说明 |
|------|------|------|
| id | INTEGER | 主键，自增 |
| record_id | INTEGER | 关联记录ID |
| class_name | TEXT | 缺陷类别 |
| confidence | REAL | 置信度 |
| x1, y1, x2, y2 | INTEGER | 检测框坐标 |

## 📝 配置说明

### 环境变量

- `QT_QPA_PLATFORM`：Qt 平台插件设置（Linux 上建议设置为 `xcb`）

### 插件目录

插件默认加载自 `plugins/detectors/` 目录，可在 `plugin_manager.py` 中修改配置。

## 🤝 贡献指南

欢迎提交 Issue 和 Pull Request！

### 开发规范

1. 代码遵循 PEP 8 规范
2. 使用类型注解
3. 添加必要的文档字符串
4. 保持代码简洁清晰

## 📄 许可证

MIT License


---

**版本**: 1.0.0  
**最后更新**: 2026年5月
