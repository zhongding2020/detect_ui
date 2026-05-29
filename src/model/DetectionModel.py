"""检测业务逻辑模型"""
import os
import cv2
import numpy as np
import datetime

from src.utils.logging_utils import get_logger
from plugins.plugin_manager import PluginManager
from src.utils.database_manager import DatabaseManager, DetectionResult

logger = get_logger('model.detection')


class DetectionModel:
    """检测业务模型"""
    
    def __init__(self):
        self.plugin_manager = PluginManager()
        self.db_manager = DatabaseManager()
        self.current_plugin = None
        self.detection_history = []
        
    def load_plugins(self):
        """加载所有插件"""
        self.plugin_manager.load_all_plugins()
        logger.info(f"Loaded {len(self.plugin_manager.plugins)} plugins")
        return self.plugin_manager.plugins
    
    def select_plugin(self, plugin_name):
        """选择检测插件"""
        if plugin_name in self.plugin_manager.plugins:
            self.current_plugin = self.plugin_manager.plugins[plugin_name]
            logger.info(f"Selected plugin: {plugin_name}")
            return True
        return False
    
    def get_available_plugins(self):
        """获取可用插件列表"""
        return list(self.plugin_manager.plugins.keys())
    
    def detect(self, image_path):
        """执行检测"""
        if not self.current_plugin:
            logger.error("No plugin selected")
            return None
        
        try:
            result = self.current_plugin.detect(image_path)
            return result
        except Exception as e:
            logger.error(f"Detection error: {str(e)}")
            return None
    
    def save_result(self, image_path, result):
        """保存检测结果到数据库"""
        if result is None:
            return None
        
        try:
            # 获取当前时间戳
            timestamp = datetime.datetime.now().isoformat()
            
            # 保存结果图片
            result_image_path = None
            if 'result_image' in result and result['result_image'] is not None:
                result_image_path = self.db_manager.save_result_image(
                    result['result_image'], 
                    os.path.basename(image_path)
                )
            
            # 获取检测结果信息
            status = result.get('result_status', 'UNKNOWN')
            detections = result.get('detections', [])
            defect_count = len(detections)
            error_message = result.get('error_message', '')
            
            # 将检测结果转换为 DetectionResult 对象列表
            results_list = []
            for det in detections:
                if isinstance(det, dict):
                    result_obj = DetectionResult(
                        class_name=det.get('class_name', 'unknown'),
                        confidence=det.get('confidence', 0.0),
                        bbox=det.get('bbox', [0, 0, 0, 0])
                    )
                    results_list.append(result_obj)
            
            # 保存记录（与原文件调用方式一致）
            record_id = self.db_manager.save_record(
                timestamp=timestamp,
                image_path=image_path,
                filename=os.path.basename(image_path),
                defect_count=defect_count,
                status=status,
                elapsed_time=0,
                result_image_path=result_image_path,
                results=results_list,
                error_message=error_message
            )
            
            # 更新历史记录
            self.detection_history.append({
                'id': record_id,
                'image_path': image_path,
                'status': status,
                'defect_count': defect_count,
                'result_image_path': result_image_path,
                'error_message': error_message
            })
            
            logger.info(f"Saved detection result: {image_path} (ID: {record_id})")
            return record_id
        except Exception as e:
            logger.error(f"Save result error: {str(e)}")
            return None
    
    def load_history(self):
        """加载历史记录"""
        try:
            self.detection_history = self.db_manager.load_records()
            logger.info(f"Loaded {len(self.detection_history)} history records")
            return self.detection_history
        except Exception as e:
            logger.error(f"Load history error: {str(e)}")
            return []
    
    def delete_history(self, record_id):
        """删除历史记录"""
        try:
            self.db_manager.delete_record(record_id)
            self.detection_history = [h for h in self.detection_history if h['id'] != record_id]
            logger.info(f"Deleted history record: {record_id}")
            return True
        except Exception as e:
            logger.error(f"Delete history error: {str(e)}")
            return False
    
    @staticmethod
    def read_image(image_path):
        """读取图片（支持中文路径）"""
        try:
            img_array = np.fromfile(image_path, dtype=np.uint8)
            img = cv2.imdecode(img_array, cv2.IMREAD_COLOR)
            return img
        except Exception as e:
            logger.error(f"Read image error: {str(e)}")
            return None
    
    @staticmethod
    def draw_detections(image, detections):
        """在图片上绘制检测框"""
        if image is None or not detections:
            return image
        
        img = image.copy()
        colors = {
            'crack': (0, 0, 255),
            'void': (0, 255, 0),
            'porosity': (255, 0, 0),
            'inclusion': (255, 255, 0),
            'other': (255, 0, 255)
        }
        
        for idx, result in enumerate(detections):
            x1, y1, x2, y2 = result.bbox
            class_name = result.class_name if hasattr(result, 'class_name') else 'defect'
            color = colors.get(class_name, (0, 0, 255))
            
            # 绘制矩形框
            cv2.rectangle(img, (x1, y1), (x2, y2), color, 2)
            
            # 绘制标签
            label = f"{class_name} {result.confidence:.0%}" if hasattr(result, 'confidence') else class_name
            cv2.putText(img, label, (x1, y1 - 5), 
                        cv2.FONT_HERSHEY_SIMPLEX, 0.5, color, 2)
            
            # 绘制序号
            cv2.circle(img, (x1, y1), 10, color, -1)
            cv2.putText(img, str(idx + 1), (x1 - 5, y1 + 5),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.4, (255, 255, 255), 1)
        
        return img
    
    @staticmethod
    def draw_error_overlay(image, error_message):
        """在图片上绘制错误信息"""
        if image is None or not error_message:
            return image
        
        img = image.copy()
        font = cv2.FONT_HERSHEY_SIMPLEX
        text_lines = error_message.split('\n')
        
        # 计算文本大小
        max_width = 0
        for line in text_lines:
            (text_w, text_h), _ = cv2.getTextSize(line, font, 0.7, 2)
            max_width = max(max_width, text_w)
        
        # 绘制背景矩形
        padding = 10
        box_height = len(text_lines) * 30 + padding * 2
        box_width = max_width + padding * 2
        
        # 半透明背景
        overlay = img.copy()
        cv2.rectangle(overlay, (0, 0), (box_width, box_height), (40, 40, 20), -1)
        cv2.addWeighted(overlay, 0.7, img, 0.3, 0, img)
        
        # 绘制边框
        cv2.rectangle(img, (0, 0), (box_width, box_height), (255, 136, 0), 2)
        
        # 绘制文本
        y_offset = padding + 25
        for line in text_lines:
            cv2.putText(img, line, (padding, y_offset), font, 0.7, (255, 136, 0), 2)
            y_offset += 30
        
        return img
