"""
模拟检测插件 - 用于测试界面显示效果

此插件生成模拟的检测数据，用于测试界面功能
"""

import os
import random
from typing import List
from plugins.base.defect_base import DetectionAlgorithmBase, DetectionResult


class MockDetector(DetectionAlgorithmBase):
    """模拟缺陷检测器"""
    
    def __init__(self):
        super().__init__()
        self.name = "Mock Detector"
        self.version = "1.0.0"
        self.author = "Test Team"
        self.description = "模拟检测器 - 用于测试界面显示"
        
        # 缺陷类别
        self.defect_classes = ['crack', 'scratch', 'pitting', 'dent', 'wear']
        
        # 检测模式
        self.detection_mode = 'random'  # 'random', 'always_ok', 'always_ng'
    
    def detect(self, image_path: str) -> List[DetectionResult]:
        """
        生成模拟检测结果
        
        Args:
            image_path: 图片路径
            
        Returns:
            List[DetectionResult]: 模拟的检测结果
        """
        results = []
        
        # 验证图片
        if not self.validate_image(image_path):
            return results
        
        try:
            # 根据检测模式生成结果
            if self.detection_mode == 'always_ok':
                # 总是返回OK（无缺陷）
                pass
                
            elif self.detection_mode == 'always_ng':
                # 总是返回NG（有缺陷）
                num_defects = random.randint(1, 3)
                for i in range(num_defects):
                    result = self._generate_random_defect(image_path)
                    results.append(result)
                    
            else:  # 'random'
                # 随机决定是否有缺陷（70%概率有缺陷）
                if random.random() < 0.7:
                    num_defects = random.randint(1, 4)
                    for i in range(num_defects):
                        result = self._generate_random_defect(image_path)
                        results.append(result)
            
        except Exception as e:
            print(f"Error in mock detection: {e}")
        
        return results
    
    def _generate_random_defect(self, image_path: str) -> DetectionResult:
        """生成随机缺陷"""
        # 随机选择缺陷类别
        class_name = random.choice(self.defect_classes)
        
        # 随机生成置信度（0.6 - 0.99）
        confidence = random.uniform(0.6, 0.99)
        
        # 随机生成边界框坐标
        # 基于常见的图片尺寸，生成合理的坐标
        x1 = random.randint(50, 300)
        y1 = random.randint(50, 300)
        x2 = x1 + random.randint(50, 200)
        y2 = y1 + random.randint(50, 200)
        
        # 确保坐标在合理范围内（不超过图片尺寸 640x480）
        x2 = min(x2, 630)
        y2 = min(y2, 470)
        
        result = DetectionResult(
            class_name=class_name,
            confidence=confidence,
            bbox=(x1, y1, x2, y2)
        )
        
        return result
    
    def set_mode(self, mode: str):
        """设置检测模式"""
        if mode in ['random', 'always_ok', 'always_ng']:
            self.detection_mode = mode
            print(f"Mock detector mode set to: {mode}")
        else:
            print(f"Invalid mode: {mode}. Use 'random', 'always_ok', or 'always_ng'")
    
    def get_info(self) -> dict:
        """获取插件信息"""
        return {
            'name': self.name,
            'version': self.version,
            'author': self.author,
            'description': self.description,
            'mode': self.detection_mode,
            'defect_classes': ', '.join(self.defect_classes)
        }
