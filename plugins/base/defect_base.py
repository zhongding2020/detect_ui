"""
缺陷检测插件基类
所有检测插件必须继承此基类
"""

from abc import ABC, abstractmethod
from typing import List, Dict, Any
import os


class DetectionResult:
    """检测结果数据类"""
    def __init__(self, class_name: str, confidence: float, bbox: tuple):
        """
        初始化检测结果
        
        Args:
            class_name: 检测类别名称
            confidence: 置信度 (0-1)
            bbox: 边界框坐标 (x1, y1, x2, y2)
        """
        self.class_name = class_name
        self.confidence = confidence
        self.bbox = bbox  # (x1, y1, x2, y2)
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典格式"""
        return {
            'class_name': self.class_name,
            'confidence': self.confidence,
            'bbox': self.bbox
        }
    
    def __repr__(self):
        return f"DetectionResult(class={self.class_name}, conf={self.confidence:.2f}, bbox={self.bbox})"


class DetectionAlgorithmBase(ABC):
    """
    缺陷检测插件基类
    
    所有检测插件必须继承此类并实现 detect 方法
    """
    
    def __init__(self):
        """初始化插件"""
        self.name = "BaseDetector"
        self.version = "1.0.0"
        self.author = "Unknown"
        self.description = "Base defect detector"
    
    @abstractmethod
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
        """
        pass
    
    def get_info(self) -> Dict[str, str]:
        """
        获取插件信息
        
        Returns:
            Dict: 包含插件名称、版本、作者、描述等信息的字典
        """
        return {
            'name': self.name,
            'version': self.version,
            'author': self.author,
            'description': self.description
        }
    
    def validate_image(self, image_path: str) -> bool:
        """
        验证图片路径是否有效
        
        Args:
            image_path: 图片路径
            
        Returns:
            bool: 图片是否有效
        """
        if not os.path.exists(image_path):
            print(f"Error: Image file not found: {image_path}")
            return False
        
        valid_extensions = {'.jpg', '.jpeg', '.png', '.bmp', '.tiff', '.webp'}
        ext = os.path.splitext(image_path)[1].lower()
        
        if ext not in valid_extensions:
            print(f"Error: Unsupported image format: {ext}")
            return False
        
        return True
    
    def preprocess(self, image_path: str) -> Any:
        """
        图片预处理（可选实现）
        
        Args:
            image_path: 图片路径
            
        Returns:
            预处理后的图片数据
        """
        return None
    
    def postprocess(self, results: List[DetectionResult]) -> List[DetectionResult]:
        """
        结果后处理（可选实现）
        
        Args:
            results: 原始检测结果
            
        Returns:
            处理后的检测结果
        """
        return results
