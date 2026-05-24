"""
YOLOv8超声缺陷检测插件示例

此插件使用YOLOv8模型进行超声缺陷检测
使用方法：
1. 确保已安装 ultralytics 包：pip install ultralytics
2. 将训练好的yolov8模型文件(.pt)放在models目录下
3. 在plugins目录下创建__init__.py文件（如果不存在）
"""

import os
from typing import List
from plugins.base.defect_base import DetectionAlgorithmBase, DetectionResult


class YOLOv8Detector(DetectionAlgorithmBase):
    """YOLOv8缺陷检测器"""
    
    def __init__(self):
        super().__init__()
        self.name = "YOLOv8 Detector"
        self.version = "1.0.0"
        self.author = "Bearing Defect Detection Team"
        self.description = "基于YOLOv8的超声缺陷检测插件"
        
        # 模型配置
        self.model_path = "models/yolov8_bearing.pt"
        self.conf_threshold = 0.5
        self.iou_threshold = 0.5
        self.model = None
    
    def _load_model(self):
        """加载YOLOv8模型"""
        try:
            from ultralytics import YOLO
            
            # 检查模型文件是否存在
            project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
            full_model_path = os.path.join(project_root, self.model_path)
            
            if not os.path.exists(full_model_path):
                print(f"Warning: Model file not found at {full_model_path}")
                print("Using default YOLOv8n model for testing")
                self.model = YOLO('yolov8n.pt')
            else:
                self.model = YOLO(full_model_path)
                
        except ImportError:
            print("Error: ultralytics package not installed")
            print("Please install with: pip install ultralytics")
            self.model = None
    
    def detect(self, image_path: str) -> List[DetectionResult]:
        """
        使用YOLOv8检测图片中的缺陷
        
        Args:
            image_path: 待检测图片的路径
            
        Returns:
            List[DetectionResult]: 检测结果列表
        """
        results = []
        
        # 验证图片
        if not self.validate_image(image_path):
            return results
        
        # 延迟加载模型
        if self.model is None:
            self._load_model()
        
        if self.model is None:
            print("Error: Model not loaded")
            return results
        
        try:
            # 执行检测
            detections = self.model.predict(
                source=image_path,
                conf=self.conf_threshold,
                iou=self.iou_threshold,
                verbose=False
            )
            
            # 解析检测结果
            for detection in detections:
                boxes = detection.boxes
                
                for box in boxes:
                    # 获取边界框坐标
                    x1, y1, x2, y2 = box.xyxy[0].tolist()
                    bbox = (int(x1), int(y1), int(x2), int(y2))
                    
                    # 获取类别名称
                    class_id = int(box.cls[0])
                    class_name = detection.names[class_id]
                    
                    # 获取置信度
                    confidence = float(box.conf[0])
                    
                    # 创建检测结果
                    result = DetectionResult(class_name, confidence, bbox)
                    results.append(result)
            
        except Exception as e:
            print(f"Error during detection: {e}")
            import traceback
            traceback.print_exc()
        
        return results
    
    def set_confidence(self, threshold: float):
        """设置置信度阈值"""
        self.conf_threshold = max(0.0, min(1.0, threshold))
    
    def set_iou(self, threshold: float):
        """设置IoU阈值"""
        self.iou_threshold = max(0.0, min(1.0, threshold))
    
    def get_model_info(self) -> dict:
        """获取模型信息"""
        if self.model is None:
            self._load_model()
        
        return {
            'model_path': self.model_path,
            'confidence': self.conf_threshold,
            'iou': self.iou_threshold,
            'loaded': self.model is not None
        }
