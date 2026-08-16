# 超声缺陷检测系统 - 代码架构分析报告

## 一、项目概述

这是一个基于 **PyQt5 + YOLO** 的超声缺陷检测可视化系统，支持实时缺陷检测、可视化标注、历史记录持久化和文件夹监听自动检测。

- **技术栈**: Python 3.8+, PyQt5, OpenCV, SQLite, YOLOv8 (ultralytics)
- **架构模式**: MVP (Model-View-Presenter) + 插件系统
- **打包方式**: PyInstaller (支持 .pyc 插件热加载)

---

## 二、项目结构

```
detect_ui/
├── main.py                          # MVP 架构入口 (推荐)
├── bearing_defect_detection.py      # 单体架构入口 (1754行, 遗留代码)
├── src/
│   ├── model/
│   │   └── DetectionModel.py        # 业务逻辑: 检测/保存/历史/图像处理
│   ├── view/
│   │   └── DetectionView.py         # PyQt5 界面: 信号定义 + UI 组件
│   ├── presenter/
│   │   └── DetectionPresenter.py    # 控制器: 信号路由 + 线程管理
│   └── utils/
│       ├── database_manager.py      # SQLite 持久化 + 图片保存
│       └── logging_utils.py         # 日志轮转 + 控制台输出
├── plugins/
│   ├── base/
│   │   └── defect_base.py           # ABC 基类 + DetectionResult 数据类
│   ├── detectors/
│   │   ├── mock_detector.py         # 模拟检测器 (测试用)
│   │   ├── template_detector.py     # 模板检测器 (开发骨架)
│   │   └── yolov8_detector.py       # YOLOv8 深度学习检测器
│   └── plugin_manager.py            # 插件管理器: 扫描/编译/加载/卸载
├── build.py                         # PyInstaller 打包脚本
├── ultrasound_defect_detection.spec # PyInstaller 配置
├── generate_test_images.py          # 测试图片生成
├── install_deps.py                  # 依赖安装脚本
├── requirements.txt                 # Python 依赖
└── docs/                            # 文档 (6个 .md 文件)
```

---

## 三、架构分层

### 3.1 MVP 分层 (main.py 路径)

```
main.py
  └── QApplication
       ├── DetectionModel     (业务逻辑 + 数据访问)
       ├── DetectionView      (PyQt5 界面 + 信号定义)
       └── DetectionPresenter (控制器, 连接 Model 和 View)
```

**信号流向**:
1. 用户在 View 上操作 → View 发出 `pyqtSignal`
2. Presenter 接收信号 → 调用 Model 方法
3. Model 执行检测/保存 → 返回结果
4. Presenter 调用 View 方法更新界面

**View 定义的信号** (8个):
- `signal_start_detection` / `signal_stop_detection`
- `signal_select_plugin(str)` / `signal_select_image` / `signal_select_directory`
- `signal_start_monitoring` / `signal_stop_monitoring`
- `signal_view_history`

**Presenter 额外信号**:
- `signal_detection_error(str, str)` — 跨线程错误传递

### 3.2 插件系统

```
PluginManager
  ├── scan_plugins()     → 遍历 plugins/detectors/ 目录
  ├── compile_plugin()   → py_compile 编译 .py → .pyc
  ├── load_plugin()      → importlib 动态导入, 实例化插件类
  └── load_all_plugins() → 批量加载所有插件
```

**插件基类** `DetectionAlgorithmBase(ABC)`:
- 抽象方法: `detect(image_path) → Dict` (必须实现)
- 可选方法: `preprocess()`, `postprocess()`, `validate_image()`, `get_info()`
- 返回格式: `{'result_status': 'OK/NG/ERROR', 'result_image': ndarray, 'detections': [DetectionResult], ...}`

**DetectionResult 数据类**:
- `class_name: str` — 缺陷类别
- `confidence: float` — 置信度 (0-1)
- `bbox: tuple` — 边界框 (x1, y1, x2, y2)

### 3.3 数据持久化

**DatabaseManager** 管理 SQLite 数据库:
- `detection_records` 表: 检测记录 (时间/路径/状态/缺陷数/耗时/标注图路径/错误信息)
- `detection_results` 表: 单个缺陷详情 (类别/置信度/坐标), 外键关联 record_id
- 标注图片保存到 `data/results_images/` 目录

**日志系统**:
- `RotatingFileHandler`: 10MB 轮转, 保留 5 个备份
- 输出到 `logs/app.log` + 控制台

---

## 四、检测数据流

```
用户点击「立即检测」
  → View.emit(signal_start_detection)
    → Presenter.start_detection()
      → threading.Thread(_run_detection)     [子线程]
        → 遍历 selected_images
          → Model.detect(image_path)
            → current_plugin.detect(image_path)
              → 返回 result dict
          → Model.save_result(image_path, result)
            → DatabaseManager.save_record()
              → SQLite INSERT + 图片保存
          → View.display_image(result_image)  [跨线程!]
          → View.update_result(result)        [跨线程!]
```

---

## 五、发现的关键问题

### 严重问题 (P0 - 需立即修复)

#### 1. 双入口代码重复
- `main.py` (MVP 架构, 77行) 和 `bearing_defect_detection.py` (单体架构, 1754行) 功能完全重复
- README 指向 `bearing_defect_detection.py` 作为主入口, 但 `.spec` 打包配置指向 `main.py`
- 两套代码各自维护, 修复只在一边生效, 容易出现不一致
- **建议**: 删除 `bearing_defect_detection.py`, 统一使用 `main.py` MVP 架构, 更新 README

#### 2. 线程安全缺陷 (MVP Presenter)
- `DetectionPresenter._run_detection()` 在子线程中运行
- 但直接调用 `self.view.update_log()`, `self.view.display_image()`, `self.view.update_result()` 等 UI 方法
- Qt 禁止从非主线程操作 UI 组件, 可能导致崩溃或不可预知行为
- 旧版 `bearing_defect_detection.py` 使用 `Worker` 类 + `pyqtSignal` 正确处理了此问题
- **建议**: Presenter 中增加 `pyqtSignal` 用于跨线程通信, 或使用 `QMetaObject.invokeMethod`

#### 3. MockDetector 硬编码异常
- 文件: `plugins/detectors/mock_detector.py` 第 104 行
- `raise ValueError("Mock detector error")` 位于 `return` 语句之前
- 导致该插件永远抛出异常, 返回 ERROR 状态, 无法正常模拟检测
- **建议**: 删除第 104 行的 `raise ValueError`

#### 4. save_result_image 参数错位
- `DatabaseManager.save_result_image` 签名: `(image_path: str, annotated_image)` — 第一个参数是路径字符串
- `DetectionModel.save_result` 调用: `self.db_manager.save_result_image(result['result_image'], os.path.basename(image_path))` — 第一个参数传了图片数组
- 参数类型和顺序不匹配
- **建议**: 修正调用参数顺序, 或将方法签名改为 `(annotated_image, filename)` 更符合实际用法

### 中等问题 (P1 - 建议改进)

#### 5. requirements.txt 缺失/错误依赖
- `ultralytics` (YOLOv8 依赖) 未列出, YOLOv8Detector 会因 ImportError 静默失败
- `pandas>=3.0.3` — pandas 目前最新版本是 2.x, 3.0.3 不存在, pip install 会报错
- **建议**: 添加 `ultralytics>=8.0.0`, 修正 pandas 版本为 `>=2.0.0`

#### 6. MVP 版本丢失 watchdog 支持
- 旧版 `bearing_defect_detection.py` 支持 `watchdog` 实时文件监听 + polling 降级
- 新版 `DetectionPresenter` 仅使用 `time.sleep(1)` 轮询, 未利用 `watchdog`
- `requirements.txt` 列出了 `watchdog>=3.0.0` 但 MVP 代码未使用
- **建议**: 将 watchdog 监听逻辑迁移到 Presenter

#### 7. src/ 缺少 `__init__.py`
- `src/`, `src/model/`, `src/view/`, `src/presenter/`, `src/utils/` 均缺少 `__init__.py`
- 虽然 Python 3 支持命名空间包, 但可能导致打包和导入问题
- **建议**: 添加 `__init__.py` 文件

#### 8. get_app_data_directory() 实现不一致
- `database_manager.py` 版本: 返回 `os.path.join(app_dir, 'data')`
- `logging_utils.py` 版本: 返回 `app_dir` (不含 'data' 子目录)
- 两个函数同名但行为不同, 容易混淆
- **建议**: 统一到一个公共工具模块

#### 9. 置信度/IoU 滑块未连接到插件
- View 中有置信度和 IoU 滑块 (`conf_slider`, `iou_slider`)
- 但 Presenter 未读取滑块值传递给插件
- YOLOv8Detector 有 `set_confidence()` 和 `set_iou()` 方法但从未被调用
- **建议**: 在 Presenter 中读取滑块值并传递给当前插件

---

## 六、架构评价

### 优点
1. **MVP 分层清晰**: Model/View/Presenter 职责分明, 比旧版单体架构大幅改善
2. **插件系统设计良好**: ABC 基类 + 动态加载, 支持热插拔, 扩展性强
3. **数据持久化完善**: SQLite 双表设计, 支持历史记录恢复
4. **打包支持完善**: build.py + .spec + .pyc 编译, 支持插件以字节码分发
5. **日志系统规范**: 轮转日志 + 模块化 logger, 便于调试

### 不足
1. **新旧代码并存**: 迁移未完成, 旧代码仍在, 造成混乱
2. **线程安全未完善**: MVP 版本的 Presenter 缺少跨线程信号机制
3. **依赖管理不严谨**: requirements.txt 有错误, 部分依赖缺失
4. **配置未贯通**: UI 控件 (滑块) 与插件参数未连接

---

## 七、改进建议优先级

| 优先级 | 问题 | 工作量 |
|--------|------|--------|
| P0 | 删除旧版 bearing_defect_detection.py, 统一入口 | 小 |
| P0 | 修复 MockDetector raise ValueError | 极小 |
| P0 | 修复 save_result_image 参数错位 | 极小 |
| P0 | Presenter 增加跨线程 pyqtSignal | 中 |
| P1 | 修正 requirements.txt | 极小 |
| P1 | 迁移 watchdog 监听到 Presenter | 中 |
| P1 | 添加 src/ 下 __init__.py | 极小 |
| P1 | 统一 get_app_data_directory() | 小 |
| P1 | 连接置信度/IoU 滑块到插件 | 小 |
