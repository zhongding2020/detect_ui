"""
简单模板检测插件

此插件是一个模板，展示了如何创建自定义检测插件
可以基于此模板开发自己的检测算法
"""

import os
from typing import Dict, Any, List
import cv2
from plugins.base.defect_base import DetectionAlgorithmBase, DetectionResult


class TemplateDetector(DetectionAlgorithmBase):
    """
    模板检测器插件
    
    这是一个简单的模板插件，用于演示插件开发流程
    可以替换为实际的检测算法
    """
    
    def __init__(self):
        super().__init__()
        self.name = "Template Detector"
        self.version = "1.0.0"
        self.author = "Developer"
        self.description = "缺陷检测插件模板"
        
        # 在这里添加插件特定的配置参数
        self.detection_threshold = 0.5
        self.max_results = 100
    
    def detect(self, image_path: str) -> Dict[str, Any]:
        """
        检测图片中的缺陷
        
        Args:
            image_path: 待检测图片的路径
            
        Returns:
            Dict: 检测结果字典，包含以下字段:
                - image_path: 原始图片路径
                - result_status: 检测状态 (OK/NG/ERROR)
                - result_image: 检测结果图片数据
                - result_path: 结果保存路径
                - error_message: 错误信息（如有）
                - detections: 检测到的缺陷列表
        """
        # 验证图片
        if not self.validate_image(image_path):
            return {
                'image_path': image_path,
                'result_status': 'ERROR',
                'result_image': None,
                'result_path': None,
                'error_message': 'Invalid image path',
                'detections': []
            }
        
        detections = []
        result_image = None
        
        try:
            # 读取原始图片用于绘制
            result_image = cv2.imread(image_path)
            if result_image is None:
                return {
                    'image_path': image_path,
                    'result_status': 'ERROR',
                    'result_image': None,
                    'result_path': None,
                    'error_message': 'Failed to read image',
                    'detections': []
                }
            
            # ======================================
            # 在这里实现您的检测算法
            # ======================================
            
            # 示例：创建一个假的检测结果（请替换为真实算法）
            # 这是您需要替换的部分
            
            # 示例代码：
            # import cv2
            # image = cv2.imread(image_path)
            # # 进行图像处理和缺陷检测
            # # ...
            
            # 示例检测结果（仅用于演示）
            # 请删除以下几行，使用您的实际检测逻辑
            print(f"Template detector processing: {image_path}")
            print("Please implement your detection algorithm here")
            
            # 示例：添加一个检测结果
            # result = DetectionResult(
            #     class_name="defect_type_1",
            #     confidence=0.95,
            #     bbox=(100, 100, 300, 300)
            # )
            # detections.append(result)
            
            # pass  # 删除此行，当实现真实算法时
            
            # 绘制检测框
            for idx, det in enumerate(detections):
                x1, y1, x2, y2 = det.bbox
                cv2.rectangle(result_image, (x1, y1), (x2, y2), (0, 0, 255), 2)
                label = f"{det.class_name} {det.confidence:.0%}"
                cv2.putText(result_image, label, (x1, y1 - 10),
                           cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 0, 255), 1)
            
            result_status = 'NG' if len(detections) > 0 else 'OK'
            
            return {
                'image_path': image_path,
                'result_status': result_status,
                'result_image': result_image,
                'result_path': None,
                'error_message': '',
                'detections': detections
            }
            
        except Exception as e:
            print(f"Error during detection: {e}")
            import traceback
            traceback.print_exc()
            return {
                'image_path': image_path,
                'result_status': 'ERROR',
                'result_image': None,
                'result_path': None,
                'error_message': str(e),
                'detections': []
            }
    
    def preprocess(self, image_path: str):
        """
        图片预处理
        
        在detect方法之前调用，用于图片预处理
        可选实现
        """
        # 在这里实现图片预处理逻辑
        # 例如：调整大小、归一化、数据增强等
        pass
    
    def postprocess(self, results: List[DetectionResult]) -> List[DetectionResult]:
        """
        结果后处理
        
        在detect方法之后调用，用于结果过滤或增强
        可选实现
        """
        # 在这里实现结果后处理逻辑
        # 例如：NMS、结果过滤等
        
        # 示例：过滤低置信度结果
        filtered_results = [
            r for r in results 
            if r.confidence >= self.detection_threshold
        ]
        
        # 限制最大结果数
        if len(filtered_results) > self.max_results:
            filtered_results = filtered_results[:self.max_results]
        
        return filtered_results
    
    def set_threshold(self, threshold: float):
        """设置检测阈值"""
        self.detection_threshold = max(0.0, min(1.0, threshold))
    
    def get_threshold(self) -> float:
        """获取检测阈值"""
        return self.detection_threshold
