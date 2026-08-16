# 超声缺陷检测插件实现方案

## 1. 样本数据分析

### 1.1 目录结构

```
sample/
├── 原始图片/
│   ├── NG/          # 207 张缺陷样本 (BMP)
│   └── Ok/          # 535 张正常样本 (BMP)
├── 2/原始图片/
│   ├── NG/          # 253 张缺陷样本 (BMP)
│   └── Ok/          # 765 张正常样本 (BMP)
└── 需单独判定的图片20260408/
    ├── *.bmp        # 207 张 BMP
    └── *_闸门A.tiff # 67 张 TIFF (Gate A 闸门)
```

- **总样本数**: 2034 张
- **BMP**: 1967 张
- **TIFF**: 67 张
- **有标签样本**: 1760 张（NG: 460, Ok: 1300）

### 1.2 图像特征

| 属性 | 数值 |
|------|------|
| 格式 | BMP / TIFF |
| 通道 | BGR 3 通道 |
| 位深 | uint8 |
| 主要尺寸 | 1300×339、1100×339、1196×291 |
| 色彩 | 伪彩色超声 C-scan（蓝→绿→黄→红 表示回波振幅） |

图像为超声 C-scan 扫描图，颜色代表超声回波振幅：
- **红色/黄色**: 高振幅区（强反射）
- **绿色/青色**: 中振幅区
- **蓝色/黑色**: 低振幅区（弱反射 / 背景）

### 1.3 NG vs Ok 差异

全局统计（亮度、标准差）差异较小，说明缺陷是**局部异常**而非整体亮度变化：

- **Set 1 样本 (`原始图片/`)**：缺陷主要表现为高响应斑块的面积异常增大
- **Set 2 样本 (`2/原始图片/`)**：缺陷与正常样本在均值、标准差、梯度、亮斑数量上差异显著
- **TIFF 闸门图**：部分带右侧色标，需预处理裁剪

最重要的区分特征：
1. `lap_mean` / `lap_std` — 图像局部二阶纹理
2. `bright_spot_count` / `bright_spot_max_area` — 高响应异常区域
3. `v_mean` / `v_std` — HSV 亮度通道统计
4. `very_high_ratio` / `very_low_ratio` — 极端响应像素比例

## 2. 实现方案

### 2.1 技术路线

采用 **"传统 CV 预处理 + 机器学习分类 + 连通域定位"** 的混合方案：

```
输入图像
  │
  ▼
Unicode 安全读取 (np.fromfile + cv2.imdecode)
  │
  ▼
ROI 提取 ──► 二值化 + 形态学 + 最大轮廓
  │
  ▼
响应图归一化 ──► gray / 255
  │
  ├──────────────┐
  ▼              ▼
特征提取      缺陷定位
  │              │
  ▼              ▼
Random Forest  高/低响应连通域
分类 (NG/Ok)   + NMS
  │              │
  └──────┬───────┘
         ▼
    输出: result_status + detections + result_image
```

### 2.2 插件文件

| 文件 | 职责 |
|------|------|
| `plugins/detectors/ultrasonic_defect_detector.py` | 缺陷检测插件，符合 `DetectionAlgorithmBase` 接口 |
| `scripts/train_ultrasonic_detector.py` | 训练脚本，从 sample 目录生成模型 |
| `models/ultrasonic_defect_model.pkl` | 训练好的 Random Forest 模型 |
| `models/ultrasonic_defect_scaler.pkl` | 特征标准化器 |
| `models/ultrasonic_defect_meta.json` | 模型元数据（特征顺序、准确率等） |

### 2.3 接口规范

继承 `DetectionAlgorithmBase`，实现：

- `detect(image_path: str) -> Dict[str, Any]`
  - `result_status`: `OK` / `NG` / `ERROR`
  - `result_image`: 绘制检测框后的 BGR 图像
  - `detections`: `List[DetectionResult]`
  - `error_message`: 错误信息
- `set_confidence(threshold: float)` — 调整 NG 概率阈值
- `set_iou(threshold: float)` — 调整缺陷框 NMS 阈值
- `get_info()` — 返回插件信息

### 2.4 特征工程

提取 46 维特征：

| 类别 | 特征数量 | 说明 |
|------|---------|------|
| 全局统计 | 9 | mean/std/median/p5/p95/p99 |
| 响应分布 | 5 | 高/中/低/极高/极低响应比例 |
| 颜色空间 | 18 | BGR/HSV/Lab 均值与标准差 |
| 纹理/梯度 | 4 | Scharr 梯度、Laplacian |
| 亮斑连通域 | 6 | 高响应区域数量、面积统计 |
| 暗斑连通域 | 4 | 低响应区域数量、面积统计 |
| 几何 | 3 | 图像尺寸、ROI 面积比例 |

### 2.5 缺陷定位

模型判断为 NG 后，对响应图执行：

1. **高响应异常**: `response_map > 0.75`
2. **低响应异常**: `response_map < 0.15`
3. 在 ROI mask 内做连通域分析
4. 过滤面积过小 / 过大区域
5. 按置信度排序后做 NMS
6. 返回 `DetectionResult` 列表（class_name 为 `high_response` / `low_response`）

## 3. 训练结果

使用 `RandomForestClassifier(n_estimators=200, max_depth=12)`：

| 指标 | 数值 |
|------|------|
| 测试集准确率 | **79.26%** |
| 5 折交叉验证 | 76.90% ± 1.44% |
| 全量数据插件评估 | **94.83%** |

按文件夹评估插件表现：

| 文件夹 | 准确率 |
|--------|--------|
| `原始图片/NG` | 90.34% (187/207) |
| `原始图片/Ok` | 93.27% (499/535) |
| `2/原始图片/NG` | 93.28% (236/253) |
| `2/原始图片/Ok` | 97.65% (747/765) |

> 注：94.83% 是在训练数据上的评估结果（模型见过这些数据），实际泛化能力应以训练脚本输出的 **79.26%** 为准。

## 4. 使用方式

### 4.1 训练模型

```bash
python scripts/train_ultrasonic_detector.py
```

可选参数：
```bash
python scripts/train_ultrasonic_detector.py --model-type gbdt --test-size 0.2
```

### 4.2 运行检测

启动主程序后，在下拉框中选择 **"Ultrasonic Defect Detector"** 即可：

```bash
python main.py
```

### 4.3 调整参数

插件暴露以下可调参数：

```python
det.set_confidence(0.5)          # NG 概率阈值
det.set_iou(0.3)                 # 缺陷框 NMS IoU
det.set_response_thresholds(
    high=0.75,                   # 高响应缺陷阈值
    low=0.15                     # 低响应缺陷阈值
)
```

## 5. 后续优化建议

### 5.1 数据层面

1. **增加标注框**：当前只有图片级 OK/NG 标签。若对缺陷区域画 bounding box，可训练 YOLO / Faster R-CNN 做精确定位。
2. **清洗 sample 目录**：`原始图片/` 和 `2/原始图片/` 似为不同产品型号，建议按型号分模型训练。
3. **单独判定文件夹**：`需单独判定的图片20260408/` 无标签，建议人工标注后纳入训练或验证。
4. **剔除色标/子图**：`_闸门A.tiff` 右侧色标已处理；`_1.bmp`、`_2.bmp` 子图建议按同一工件合并或单独处理。

### 5.2 算法层面

1. **按产品型号分模型**：Set 1 与 Set 2 缺陷模式不同，分别训练模型可提升准确率。
2. **引入深度学习**：
   - 分类：ResNet / EfficientNet 做 OK/NG 二分类
   - 检测：YOLOv8 需要 bbox 标注
   - 异常检测：Autoencoder / One-class SVM 仅用 Ok 样本训练
3. **颜色-振幅校准**：从 TIFF 色标提取真实百分比映射，替代简单的 gray/255。
4. **时序/多闸门融合**：若实际产线有多个超声闸门（A/B/C），可融合多通道信息。

### 5.3 工程层面

1. 增加模型版本管理（训练时间、数据集版本、准确率记录）。
2. 增加 `confidence` 阈值实时滑块联动。
3. 检测结果保存到数据库时，记录 `ng_probability` 便于后续追溯。

## 6. 文件清单

- 新增：`plugins/detectors/ultrasonic_defect_detector.py`
- 新增：`scripts/train_ultrasonic_detector.py`
- 新增：`models/ultrasonic_defect_model.pkl`
- 新增：`models/ultrasonic_defect_scaler.pkl`
- 新增：`models/ultrasonic_defect_meta.json`
- 修改：`requirements.txt`（添加 `joblib`）
- 新增：`docs/ULTRASONIC_DETECTOR_DESIGN.md`

## 7. 依赖

```
opencv-python>=4.5.0
numpy>=1.24.0
scikit-learn>=1.3.0
joblib>=1.3.0
```
