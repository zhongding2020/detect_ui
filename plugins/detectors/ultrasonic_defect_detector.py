"""
超声 C-scan 缺陷检测插件

基于从 sample/ 目录下标注数据训练的机器学习模型（Random Forest），
对超声 C-scan 图像进行缺陷检测。支持 BMP、TIFF 格式，兼容中文路径。

模型文件位置:
    models/ultrasonic_defect_model.pkl
    models/ultrasonic_defect_scaler.pkl
    models/ultrasonic_defect_meta.json

训练脚本:
    scripts/train_ultrasonic_detector.py
"""
import os
import json
from typing import Dict, Any, List

import cv2
import numpy as np
import joblib

from plugins.base.defect_base import DetectionAlgorithmBase, DetectionResult


class UltrasonicDefectDetector(DetectionAlgorithmBase):
    """超声 C-scan 缺陷检测器"""

    def __init__(self):
        super().__init__()
        self.name = "Ultrasonic Defect Detector"
        self.version = "1.0.0"
        self.author = "Bearing Defect Detection Team"
        self.description = "基于机器学习的超声 C-scan 缺陷检测插件"

        # 模型配置
        self.model = None
        self.scaler = None
        self.feature_names = None
        self.conf_threshold = 0.5  # 模型输出概率阈值
        self.iou_threshold = 0.3   # 缺陷框去重 IoU 阈值

        # 缺陷框检测配置
        self.response_high = 0.75   # 高响应异常阈值（超声回波过强）
        self.response_low = 0.15    # 低响应异常阈值（脱层/气孔等）
        self.min_defect_area = 80   # 最小缺陷面积（像素）
        self.max_defect_area = 8000 # 最大缺陷面积（像素），过滤超大噪声

        # 项目根目录（用于定位 models/）
        self.project_root = self._get_project_root()

    def _get_project_root(self) -> str:
        """获取项目根目录，兼容源码和 PyInstaller 打包环境"""
        if getattr(sys := __import__('sys'), 'frozen', False):
            return os.path.dirname(os.path.abspath(sys.executable))
        # plugins/detectors/<this_file>.py -> 向上三级到项目根目录
        return os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

    def _load_model(self) -> bool:
        """加载预训练模型与标准化器"""
        model_path = os.path.join(self.project_root, 'models', 'ultrasonic_defect_model.pkl')
        scaler_path = os.path.join(self.project_root, 'models', 'ultrasonic_defect_scaler.pkl')
        meta_path = os.path.join(self.project_root, 'models', 'ultrasonic_defect_meta.json')

        if not os.path.exists(model_path) or not os.path.exists(scaler_path):
            print(f"Warning: Model not found at {model_path}. Please run scripts/train_ultrasonic_detector.py first.")
            return False

        try:
            self.model = joblib.load(model_path)
            self.scaler = joblib.load(scaler_path)
            if os.path.exists(meta_path):
                with open(meta_path, 'r', encoding='utf-8') as f:
                    meta = json.load(f)
                    self.feature_names = meta.get('feature_names')
            print(f"Loaded ultrasonic defect model: {model_path}")
            return True
        except Exception as e:
            print(f"Error loading model: {e}")
            self.model = None
            self.scaler = None
            return False

    @staticmethod
    def _imread_unicode(path: str):
        """Unicode 安全的图片读取"""
        data = np.fromfile(path, dtype=np.uint8)
        return cv2.imdecode(data, cv2.IMREAD_UNCHANGED)

    @staticmethod
    def _extract_roi_and_response(image: np.ndarray):
        """
        提取工件 ROI 与归一化响应图。
        输入：BGR 超声 C-scan 图
        返回：roi_mask (uint8), response_map (float32 [0,1]), roi_bbox
        """
        if image is None:
            return None, None, None

        h, w = image.shape[:2]
        img = image.copy()

        # TIFF 图像右侧常带色标，按长宽比进行裁剪
        if w > h * 2.5 and w > 1100:
            crop_width = max(w - 120, int(w * 0.92))
            img = img[:, :crop_width]

        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)

        # 二值化分离工件（背景接近黑色）
        _, binary = cv2.threshold(gray, 10, 255, cv2.THRESH_BINARY)

        # 形态学清理
        kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5))
        binary = cv2.morphologyEx(binary, cv2.MORPH_CLOSE, kernel, iterations=2)
        binary = cv2.morphologyEx(binary, cv2.MORPH_OPEN, kernel, iterations=1)

        contours, _ = cv2.findContours(binary, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        if not contours:
            roi_mask = np.ones_like(gray, dtype=np.uint8) * 255
            roi_bbox = (0, 0, gray.shape[1], gray.shape[0])
            response_map = gray.astype(np.float32) / 255.0
            return roi_mask, response_map, roi_bbox

        main_contour = sorted(contours, key=cv2.contourArea, reverse=True)[0]
        roi_mask = np.zeros_like(gray, dtype=np.uint8)
        cv2.drawContours(roi_mask, [main_contour], -1, 255, -1)
        roi_mask = cv2.erode(roi_mask, kernel, iterations=2)

        x, y, bw, bh = cv2.boundingRect(main_contour)
        roi_bbox = (x, y, x + bw, y + bh)

        response_map = gray.astype(np.float32) / 255.0
        return roi_mask, response_map, roi_bbox

    def _extract_features(self, image: np.ndarray, roi_mask: np.ndarray,
                          response_map: np.ndarray) -> np.ndarray:
        """提取模型所需特征向量"""
        roi_pixels = response_map[roi_mask > 0]
        if len(roi_pixels) == 0:
            roi_pixels = response_map.flatten()

        gray_full = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        hsv = cv2.cvtColor(image, cv2.COLOR_BGR2HSV)
        lab = cv2.cvtColor(image, cv2.COLOR_BGR2LAB)

        features = {}
        features['mean'] = float(np.mean(roi_pixels))
        features['std'] = float(np.std(roi_pixels))
        features['median'] = float(np.median(roi_pixels))
        features['p5'] = float(np.percentile(roi_pixels, 5))
        features['p95'] = float(np.percentile(roi_pixels, 95))
        features['p99'] = float(np.percentile(roi_pixels, 99))

        features['high_ratio'] = float(np.mean(roi_pixels > 0.7))
        features['low_ratio'] = float(np.mean(roi_pixels < 0.2))
        features['mid_ratio'] = float(np.mean((roi_pixels >= 0.2) & (roi_pixels <= 0.7)))
        features['very_high_ratio'] = float(np.mean(roi_pixels > 0.9))
        features['very_low_ratio'] = float(np.mean(roi_pixels < 0.05))

        for i, prefix in enumerate(['b', 'g', 'r']):
            features[f'{prefix}_mean'] = float(image[:, :, i].mean())
            features[f'{prefix}_std'] = float(image[:, :, i].std())
        for i, prefix in enumerate(['h', 's', 'v']):
            features[f'{prefix}_mean'] = float(hsv[:, :, i].mean())
            features[f'{prefix}_std'] = float(hsv[:, :, i].std())
        for i, prefix in enumerate(['l', 'a', 'b2']):
            features[f'{prefix}_mean'] = float(lab[:, :, i].mean())
            features[f'{prefix}_std'] = float(lab[:, :, i].std())

        gx = cv2.Scharr(gray_full, cv2.CV_64F, 1, 0)
        gy = cv2.Scharr(gray_full, cv2.CV_64F, 0, 1)
        grad_mag = np.sqrt(gx ** 2 + gy ** 2)
        features['grad_mean'] = float(grad_mag.mean())
        features['grad_std'] = float(grad_mag.std())

        lap = cv2.Laplacian(gray_full, cv2.CV_64F)
        features['lap_mean'] = float(np.abs(lap).mean())
        features['lap_std'] = float(lap.std())

        # 高响应连通域
        bright_binary = (response_map > self.response_high).astype(np.uint8) * 255
        bright_binary[roi_mask == 0] = 0
        num_labels, labels, stats, centroids = cv2.connectedComponentsWithStats(bright_binary, connectivity=8)
        areas = stats[1:, cv2.CC_STAT_AREA]
        if len(areas) > 0:
            features['bright_spot_count'] = float(len(areas))
            features['bright_spot_max_area'] = float(np.max(areas))
            features['bright_spot_total_area'] = float(np.sum(areas))
            features['bright_spot_mean_area'] = float(np.mean(areas))
            features['bright_spot_area_std'] = float(np.std(areas))
            features['bright_spot_large_count'] = float(np.sum(areas > 500))
        else:
            features['bright_spot_count'] = 0.0
            features['bright_spot_max_area'] = 0.0
            features['bright_spot_total_area'] = 0.0
            features['bright_spot_mean_area'] = 0.0
            features['bright_spot_area_std'] = 0.0
            features['bright_spot_large_count'] = 0.0

        # 低响应连通域
        dark_binary = (response_map < self.response_low).astype(np.uint8) * 255
        dark_binary[roi_mask == 0] = 0
        num_labels2, labels2, stats2, _ = cv2.connectedComponentsWithStats(dark_binary, connectivity=8)
        dark_areas = stats2[1:, cv2.CC_STAT_AREA]
        if len(dark_areas) > 0:
            features['dark_spot_count'] = float(len(dark_areas))
            features['dark_spot_max_area'] = float(np.max(dark_areas))
            features['dark_spot_total_area'] = float(np.sum(dark_areas))
            features['dark_spot_large_count'] = float(np.sum(dark_areas > 500))
        else:
            features['dark_spot_count'] = 0.0
            features['dark_spot_max_area'] = 0.0
            features['dark_spot_total_area'] = 0.0
            features['dark_spot_large_count'] = 0.0

        features['image_width'] = float(image.shape[1])
        features['image_height'] = float(image.shape[0])
        features['roi_area_ratio'] = float(np.sum(roi_mask > 0) / (image.shape[0] * image.shape[1]))

        # 按模型训练时的顺序排列
        if self.feature_names:
            try:
                feat_vec = np.array([[features[k] for k in self.feature_names]], dtype=np.float32)
            except KeyError as e:
                raise RuntimeError(f"Missing feature {e}. Please retrain model with current plugin version.")
        else:
            # 兜底：按字母序（与训练脚本默认排序一致）
            keys = sorted(features.keys())
            feat_vec = np.array([[features[k] for k in keys]], dtype=np.float32)

        return feat_vec

    def _find_defect_regions(self, image: np.ndarray, roi_mask: np.ndarray,
                             response_map: np.ndarray) -> List[DetectionResult]:
        """
        在 ROI 内定位高/低响应异常区域，返回候选缺陷框。
        """
        detections = []
        h, w = response_map.shape

        # 高响应异常：可能是夹杂、裂纹等
        bright_binary = (response_map > self.response_high).astype(np.uint8) * 255
        bright_binary[roi_mask == 0] = 0
        bright_binary = cv2.morphologyEx(bright_binary, cv2.MORPH_OPEN,
                                           np.ones((3, 3), np.uint8), iterations=1)

        num_labels, labels, stats, centroids = cv2.connectedComponentsWithStats(bright_binary, connectivity=8)
        for i in range(1, num_labels):
            area = stats[i, cv2.CC_STAT_AREA]
            if self.min_defect_area <= area <= self.max_defect_area:
                x1 = stats[i, cv2.CC_STAT_LEFT]
                y1 = stats[i, cv2.CC_STAT_TOP]
                x2 = x1 + stats[i, cv2.CC_STAT_WIDTH]
                y2 = y1 + stats[i, cv2.CC_STAT_HEIGHT]
                conf = min(0.99, 0.6 + area / 2000.0)
                detections.append(DetectionResult(
                    class_name='high_response',
                    confidence=conf,
                    bbox=(int(x1), int(y1), int(x2), int(y2))
                ))

        # 低响应异常：可能是脱层、气孔等
        dark_binary = (response_map < self.response_low).astype(np.uint8) * 255
        dark_binary[roi_mask == 0] = 0
        dark_binary = cv2.morphologyEx(dark_binary, cv2.MORPH_OPEN,
                                       np.ones((3, 3), np.uint8), iterations=1)

        num_labels2, labels2, stats2, centroids2 = cv2.connectedComponentsWithStats(dark_binary, connectivity=8)
        for i in range(1, num_labels2):
            area = stats2[i, cv2.CC_STAT_AREA]
            if self.min_defect_area <= area <= self.max_defect_area:
                x1 = stats2[i, cv2.CC_STAT_LEFT]
                y1 = stats2[i, cv2.CC_STAT_TOP]
                x2 = x1 + stats2[i, cv2.CC_STAT_WIDTH]
                y2 = y1 + stats2[i, cv2.CC_STAT_HEIGHT]
                conf = min(0.99, 0.6 + area / 2000.0)
                detections.append(DetectionResult(
                    class_name='low_response',
                    confidence=conf,
                    bbox=(int(x1), int(y1), int(x2), int(y2))
                ))

        # 按面积排序并限制数量
        detections.sort(key=lambda d: (d.bbox[2] - d.bbox[0]) * (d.bbox[3] - d.bbox[1]), reverse=True)
        detections = detections[:20]

        # 简单 NMS
        detections = self._nms(detections, self.iou_threshold)
        return detections

    @staticmethod
    def _iou(box_a, box_b) -> float:
        """计算两个框的 IoU"""
        x1 = max(box_a[0], box_b[0])
        y1 = max(box_a[1], box_b[1])
        x2 = min(box_a[2], box_b[2])
        y2 = min(box_a[3], box_b[3])
        inter = max(0, x2 - x1) * max(0, y2 - y1)
        area_a = (box_a[2] - box_a[0]) * (box_a[3] - box_a[1])
        area_b = (box_b[2] - box_b[0]) * (box_b[3] - box_b[1])
        if area_a + area_b - inter == 0:
            return 0.0
        return inter / (area_a + area_b - inter)

    def _nms(self, detections: List[DetectionResult], threshold: float) -> List[DetectionResult]:
        """非极大值抑制"""
        if not detections:
            return detections

        sorted_dets = sorted(detections, key=lambda d: d.confidence, reverse=True)
        keep = []
        while sorted_dets:
            current = sorted_dets.pop(0)
            keep.append(current)
            sorted_dets = [
                d for d in sorted_dets
                if self._iou(current.bbox, d.bbox) < threshold
            ]
        return keep

    def detect(self, image_path: str) -> Dict[str, Any]:
        """
        检测超声 C-scan 图像中的缺陷。

        Args:
            image_path: 待检测图片路径

        Returns:
            Dict: 符合项目规范的检测结果字典
        """
        if not self.validate_image(image_path):
            return {
                'image_path': image_path,
                'result_status': 'ERROR',
                'result_image': None,
                'result_path': None,
                'error_message': 'Invalid image path or format',
                'detections': []
            }

        # 延迟加载模型
        if self.model is None or self.scaler is None:
            if not self._load_model():
                return {
                    'image_path': image_path,
                    'result_status': 'ERROR',
                    'result_image': None,
                    'result_path': None,
                    'error_message': 'Model not loaded. Run scripts/train_ultrasonic_detector.py first.',
                    'detections': []
                }

        try:
            # 读取图片
            image = self._imread_unicode(image_path)
            if image is None:
                raise ValueError(f"Failed to read image: {image_path}")

            # 提取 ROI 与响应图
            roi_mask, response_map, roi_bbox = self._extract_roi_and_response(image)
            if roi_mask is None or response_map is None:
                raise ValueError("Failed to extract ROI")

            # 提取特征并预测
            features = self._extract_features(image, roi_mask, response_map)
            features_scaled = self.scaler.transform(features)

            proba = self.model.predict_proba(features_scaled)[0]
            ng_prob = float(proba[1])
            predicted_class = 1 if ng_prob >= self.conf_threshold else 0

            # 定位缺陷区域
            detections = []
            result_status = 'OK'
            if predicted_class == 1:
                detections = self._find_defect_regions(image, roi_mask, response_map)
                if detections:
                    result_status = 'NG'
                else:
                    # 模型判断为 NG 但未定位到框，给出整张 ROI 作为缺陷区域
                    x1, y1, x2, y2 = roi_bbox
                    detections.append(DetectionResult(
                        class_name='defect',
                        confidence=ng_prob,
                        bbox=(x1, y1, x2, y2)
                    ))
                    result_status = 'NG'

            # 绘制结果图
            result_image = image.copy()
            colors = {
                'high_response': (0, 0, 255),   # 红
                'low_response': (255, 0, 0),    # 蓝
                'defect': (0, 255, 255)         # 黄
            }
            for idx, det in enumerate(detections):
                x1, y1, x2, y2 = det.bbox
                color = colors.get(det.class_name, (0, 0, 255))
                cv2.rectangle(result_image, (x1, y1), (x2, y2), color, 2)
                label = f"{det.class_name} {det.confidence:.0%}"
                cv2.putText(result_image, label, (x1, max(y1 - 5, 15)),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.5, color, 1)

            # 在左上角绘制整体状态
            status_text = f"{result_status} (NG prob: {ng_prob:.1%})"
            color_text = (0, 0, 255) if result_status == 'NG' else (0, 255, 0)
            cv2.putText(result_image, status_text, (10, 30),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.8, color_text, 2)

            return {
                'image_path': image_path,
                'result_status': result_status,
                'result_image': result_image,
                'result_path': None,
                'error_message': '',
                'detections': detections,
                'ng_probability': ng_prob
            }

        except Exception as e:
            print(f"Error during ultrasonic detection: {e}")
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

    def set_confidence(self, threshold: float):
        """设置模型输出 NG 概率阈值"""
        self.conf_threshold = max(0.0, min(1.0, threshold))

    def set_iou(self, threshold: float):
        """设置缺陷框 NMS IoU 阈值"""
        self.iou_threshold = max(0.0, min(1.0, threshold))

    def set_response_thresholds(self, high: float = None, low: float = None):
        """
        设置高/低响应缺陷检测阈值（高级配置）

        Args:
            high: 高响应阈值 (0-1)
            low: 低响应阈值 (0-1)
        """
        if high is not None:
            self.response_high = max(0.0, min(1.0, high))
        if low is not None:
            self.response_low = max(0.0, min(1.0, low))

    def get_info(self) -> dict:
        """获取插件信息"""
        return {
            'name': self.name,
            'version': self.version,
            'author': self.author,
            'description': self.description,
            'model_loaded': self.model is not None,
            'conf_threshold': self.conf_threshold,
            'iou_threshold': self.iou_threshold,
            'response_high': self.response_high,
            'response_low': self.response_low
        }
