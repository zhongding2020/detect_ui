# 插件开发指南

## 目录结构

```
项目根目录/
├── bearing_defect_detection.py    # 主程序
├── plugins/                        # 插件目录
│   ├── __init__.py
│   ├── plugin_manager.py          # 插件管理器
│   ├── base/
│   │   ├── __init__.py
│   │   └── defect_base.py         # 基类定义
│   └── detectors/
│       ├── __init__.py
│       ├── yolov8_detector.py     # YOLOv8示例插件
│       └── template_detector.py    # 模板插件
└── models/                         # 模型目录
    └── yolov8_bearing.pt          # 训练好的模型文件
```

---

## 创建新插件

### 1. 基本结构

创建一个新的Python文件，继承 `defectBase` 类：

```python
from plugins.base.defect_base import defectBase, DetectionResult
from typing import List


class MyDetector(defectBase):
    """自定义检测器"""
    
    def __init__(self):
        super().__init__()
        self.name = "My Detector"
        self.version = "1.0.0"
        self.author = "Your Name"
        self.description = "自定义缺陷检测插件"
    
    def detect(self, image_path: str) -> List[DetectionResult]:
        """
        实现检测逻辑
        
        Args:
            image_path: 待检测图片的路径
            
        Returns:
            List[DetectionResult]: 检测结果列表
        """
        results = []
        
        # 验证图片
        if not self.validate_image(image_path):
            return results
        
        # 在这里实现您的检测算法
        # ...
        
        # 添加检测结果
        result = DetectionResult(
            class_name="defect_type",
            confidence=0.95,
            bbox=(x1, y1, x2, y2)
        )
        results.append(result)
        
        return results
```

### 2. 放置插件文件

将插件文件放在 `plugins/detectors/` 目录下：

```
plugins/detectors/my_detector.py
```

### 3. 自动编译

程序启动时会自动：
1. 扫描 `plugins/` 目录下的所有 `.py` 文件
2. 将它们编译为 `.pyc` 字节码文件
3. 加载并注册所有继承 `defectBase` 的类

---

## DetectionResult 类

### 构造函数

```python
DetectionResult(class_name, confidence, bbox)
```

### 参数说明

- **class_name** (str): 检测到的缺陷类别名称
- **confidence** (float): 置信度，范围 0-1
- **bbox** (tuple): 边界框坐标 `(x1, y1, x2, y2)`
  - x1, y1: 左上角坐标
  - x2, y2: 右下角坐标

### 方法

```python
result.to_dict()  # 转换为字典格式
```

---

## defectBase 基类方法

### 必需实现

```python
def detect(self, image_path: str) -> List[DetectionResult]
```

### 可选覆盖

```python
def preprocess(self, image_path: str)
    # 图片预处理

def postprocess(self, results: List[DetectionResult]) -> List[DetectionResult]
    # 结果后处理
```

### 可用工具方法

```python
def validate_image(self, image_path: str) -> bool
    # 验证图片是否有效

def get_info(self) -> Dict[str, str]
    # 获取插件信息
```

---

## 示例：使用OpenCV的简单插件

```python
from plugins.base.defect_base import defectBase, DetectionResult
from typing import List
import cv2
import numpy as np


class OpenCVEdgeDetector(defectBase):
    """基于OpenCV边缘检测的简单缺陷检测"""
    
    def __init__(self):
        super().__init__()
        self.name = "Edge Detector"
        self.version = "1.0.0"
        self.author = "Developer"
        self.description = "使用Canny边缘检测识别缺陷"
        self.threshold1 = 100
        self.threshold2 = 200
    
    def detect(self, image_path: str) -> List[DetectionResult]:
        results = []
        
        if not self.validate_image(image_path):
            return results
        
        # 读取图片
        image = cv2.imread(image_path)
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        
        # 边缘检测
        edges = cv2.Canny(gray, self.threshold1, self.threshold2)
        
        # 查找轮廓
        contours, _ = cv2.findContours(
            edges, 
            cv2.RETR_EXTERNAL, 
            cv2.CHAIN_APPROX_SIMPLE
        )
        
        # 转换为检测结果
        height, width = image.shape[:2]
        
        for contour in contours:
            if cv2.contourArea(contour) > 500:  # 过滤小轮廓
                x, y, w, h = cv2.boundingRect(contour)
                
                result = DetectionResult(
                    class_name="edge_defect",
                    confidence=0.8,
                    bbox=(x, y, x + w, y + h)
                )
                results.append(result)
        
        return results
```

---

## 示例：使用YOLOv8的插件

```python
from plugins.base.defect_base import defectBase, DetectionResult
from typing import List
import os


class YOLOv8Detector(defectBase):
    """YOLOv8检测器"""
    
    def __init__(self):
        super().__init__()
        self.name = "YOLOv8 Detector"
        self.version = "1.0.0"
        self.author = "Team"
        self.description = "基于YOLOv8的检测器"
        self.model = None
    
    def detect(self, image_path: str) -> List[DetectionResult]:
        results = []
        
        if not self.validate_image(image_path):
            return results
        
        # 加载模型（延迟加载）
        if self.model is None:
            from ultralytics import YOLO
            self.model = YOLO('yolov8n.pt')
        
        # 执行检测
        predictions = self.model.predict(image_path, verbose=False)
        
        # 解析结果
        for pred in predictions:
            boxes = pred.boxes
            
            for box in boxes:
                x1, y1, x2, y2 = box.xyxy[0].tolist()
                class_id = int(box.cls[0])
                confidence = float(box.conf[0])
                class_name = pred.names[class_id]
                
                result = DetectionResult(
                    class_name=class_name,
                    confidence=confidence,
                    bbox=(int(x1), int(y1), int(x2), int(y2))
                )
                results.append(result)
        
        return results
```

---

## 编译和加载

### 自动编译

程序启动时会自动编译 `.py` 文件为 `.pyc`：

```
plugins/detectors/my_detector.py      →  plugins/detectors/my_detector.pyc
```

### 手动编译

如果需要手动编译：

```bash
python -m py_compile plugins/detectors/my_detector.py
```

### 查看已加载的插件

在程序运行时，可以在终端看到加载信息：

```
Loading plugins...
Loaded plugin: YOLOv8 Detector v1.0.0
Loaded plugin: Template Detector v1.0.0
Loaded 2 plugins
```

---

## 注意事项

1. **类名唯一性**：每个插件的 `name` 属性应该唯一
2. **线程安全**：如果插件需要处理耗时操作，考虑使用多线程
3. **错误处理**：始终进行适当的错误处理和日志记录
4. **模型路径**：使用相对路径时，相对于项目根目录
5. **内存管理**：大型模型使用后应该及时释放

---

## 测试插件

创建测试脚本 `test_plugin.py`：

```python
from plugins.plugin_manager import PluginManager

# 创建插件管理器
manager = PluginManager()

# 加载所有插件
plugins = manager.load_all_plugins()

# 获取插件
plugin = manager.get_plugin("My Detector")

# 测试检测
if plugin:
    results = plugin.detect("test_image.jpg")
    
    print(f"Found {len(results)} defects:")
    for result in results:
        print(f"  - {result.class_name}: {result.confidence:.2%}")
```

运行测试：

```bash
python test_plugin.py
```
