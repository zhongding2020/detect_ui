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
    """
    超声 C-scan 缺陷检测器（散热器边缘焊接检测）

    针对散热器产品的水浸式超声 C-scan 图像，
    检测边缘焊接区域的空洞缺陷（红色/白色/亮黄高亮区域）。
    """

    def __init__(self):
        super().__init__()
        self.name = "Ultrasonic Defect Detector"
        self.version = "2.0.0"
        self.author = "Bearing Defect Detection Team"
        self.description = "散热器超声 C-scan 边缘焊接空洞缺陷检测"

        # 模型配置
        self.model = None
        self.scaler = None
        self.feature_names = None
        self.conf_threshold = 0.5  # 模型输出概率阈值
        self.iou_threshold = 0.3   # 缺陷框去重 IoU 阈值

        # 边缘焊接区域配置
        self.edge_width = 20        # 边缘焊接带宽度（像素）

        # 缺陷框检测配置
        self.min_defect_area = 20   # 最小缺陷面积（像素）
        self.max_defect_area = 5000 # 最大缺陷面积（像素）

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
        提取工件 ROI、归一化响应图和边缘焊接区域。
        返回：img_cropped, roi_mask, response_map, roi_bbox, edge_mask
        """
        if image is None:
            return None, None, None, None, None

        h, w = image.shape[:2]
        img = image.copy()

        # 仅对带色标的 TIFF 裁剪右侧色标条
        if w > h * 2.5 and w > 1100:
            right_strip = img[:, int(w * 0.95):, :]
            strip_mean = right_strip.mean()
            body_mean = img[:, :int(w * 0.95), :].mean()
            if abs(strip_mean - body_mean) > 30:
                crop_width = int(w * 0.92)
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
            return img, roi_mask, response_map, roi_bbox, roi_mask.copy()

        main_contour = sorted(contours, key=cv2.contourArea, reverse=True)[0]
        roi_mask = np.zeros_like(gray, dtype=np.uint8)
        cv2.drawContours(roi_mask, [main_contour], -1, 255, -1)
        roi_mask = cv2.erode(roi_mask, kernel, iterations=2)

        x, y, bw, bh = cv2.boundingRect(main_contour)
        roi_bbox = (x, y, x + bw, y + bh)

        response_map = gray.astype(np.float32) / 255.0

        # 边缘焊接区域 = 膨胀 - 腐蚀
        edge_width = 20
        kernel_edge = cv2.getStructuringElement(cv2.MORPH_RECT, (edge_width, edge_width))
        dilated = cv2.dilate(roi_mask, kernel_edge)
        eroded = cv2.erode(roi_mask, kernel_edge)
        edge_mask = cv2.subtract(dilated, eroded)

        return img, roi_mask, response_map, roi_bbox, edge_mask

    def _extract_features(self, image: np.ndarray, roi_mask: np.ndarray,
                          response_map: np.ndarray, edge_mask: np.ndarray) -> np.ndarray:
        """提取模型所需特征向量（全局 + 边缘焊接区域）"""
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
        bright_binary = (response_map > 0.75).astype(np.uint8) * 255
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
            for k in ['bright_spot_count', 'bright_spot_max_area', 'bright_spot_total_area',
                       'bright_spot_mean_area', 'bright_spot_area_std', 'bright_spot_large_count']:
                features[k] = 0.0

        # 低响应连通域
        dark_binary = (response_map < 0.15).astype(np.uint8) * 255
        dark_binary[roi_mask == 0] = 0
        num_labels2, labels2, stats2, _ = cv2.connectedComponentsWithStats(dark_binary, connectivity=8)
        dark_areas = stats2[1:, cv2.CC_STAT_AREA]
        if len(dark_areas) > 0:
            features['dark_spot_count'] = float(len(dark_areas))
            features['dark_spot_max_area'] = float(np.max(dark_areas))
            features['dark_spot_total_area'] = float(np.sum(dark_areas))
            features['dark_spot_large_count'] = float(np.sum(dark_areas > 500))
        else:
            for k in ['dark_spot_count', 'dark_spot_max_area', 'dark_spot_total_area',
                       'dark_spot_large_count']:
                features[k] = 0.0

        features['image_width'] = float(image.shape[1])
        features['image_height'] = float(image.shape[0])
        features['roi_area_ratio'] = float(np.sum(roi_mask > 0) / (image.shape[0] * image.shape[1]))

        # 边缘焊接区域特征
        if edge_mask is not None and np.sum(edge_mask > 0) > 0:
            edge_pixels_gray = gray_full[edge_mask > 0].astype(np.float32)
            edge_pixels_v = hsv[:, :, 2][edge_mask > 0].astype(np.float32)
            edge_pixels_s = hsv[:, :, 1][edge_mask > 0].astype(np.float32)
            inner_mask = cv2.subtract(roi_mask, edge_mask)
            inner_pixels_v = hsv[:, :, 2][inner_mask > 0].astype(np.float32) if np.sum(inner_mask > 0) > 0 else np.array([128.0])
            inner_pixels_gray = gray_full[inner_mask > 0].astype(np.float32) if np.sum(inner_mask > 0) > 0 else np.array([128.0])

            features['edge_mean_v'] = float(edge_pixels_v.mean())
            features['edge_std_v'] = float(edge_pixels_v.std())
            features['edge_mean_gray'] = float(edge_pixels_gray.mean())
            features['edge_std_gray'] = float(edge_pixels_gray.std())
            features['edge_mean_s'] = float(edge_pixels_s.mean())

            features['edge_inner_v_diff'] = float(edge_pixels_v.mean() - inner_pixels_v.mean())
            features['edge_inner_gray_diff'] = float(edge_pixels_gray.mean() - inner_pixels_gray.mean())
            features['edge_inner_v_ratio'] = float(edge_pixels_v.mean() / max(inner_pixels_v.mean(), 1))

            # 边缘缺陷颜色 (红/白/亮黄 = 空洞)
            red_mask = ((hsv[:, :, 0] < 15) | (hsv[:, :, 0] > 165)) & (hsv[:, :, 1] > 100) & (hsv[:, :, 2] > 150) & (edge_mask > 0)
            yellow_mask = (hsv[:, :, 0] >= 15) & (hsv[:, :, 0] <= 40) & (hsv[:, :, 1] > 80) & (hsv[:, :, 2] > 180) & (edge_mask > 0)
            white_mask = (hsv[:, :, 1] < 50) & (hsv[:, :, 2] > 200) & (edge_mask > 0)
            defect_color_mask = red_mask | yellow_mask | white_mask

            edge_area = max(np.sum(edge_mask > 0), 1)
            features['edge_defect_color_ratio'] = float(defect_color_mask.sum() / edge_area)
            features['edge_red_ratio'] = float(red_mask.sum() / edge_area)
            features['edge_yellow_ratio'] = float(yellow_mask.sum() / edge_area)
            features['edge_white_ratio'] = float(white_mask.sum() / edge_area)

            # 边缘区域高亮连通域
            bright_edge = ((hsv[:, :, 2] > 180) & (edge_mask > 0)).astype(np.uint8) * 255
            num_e, _, stats_e, _ = cv2.connectedComponentsWithStats(bright_edge, connectivity=8)
            edge_areas = stats_e[1:, cv2.CC_STAT_AREA]
            features['edge_bright_spots'] = float(len(edge_areas))
            features['edge_bright_max_area'] = float(edge_areas.max()) if len(edge_areas) > 0 else 0
            features['edge_bright_total'] = float(edge_areas.sum()) if len(edge_areas) > 0 else 0
            features['edge_bright_large'] = float(np.sum(edge_areas > 50)) if len(edge_areas) > 0 else 0
            features['edge_bright_mean_area'] = float(edge_areas.mean()) if len(edge_areas) > 0 else 0

            # 边缘局部对比度
            v_f = hsv[:, :, 2].astype(np.float32)
            local_bg = cv2.medianBlur(v_f.astype(np.uint8), 31).astype(np.float32)
            local_contrast = v_f - local_bg
            edge_contrast = local_contrast[edge_mask > 0]
            features['edge_contrast_mean'] = float(edge_contrast.mean())
            features['edge_contrast_std'] = float(edge_contrast.std())
            features['edge_contrast_max'] = float(edge_contrast.max())
            features['edge_contrast_p95'] = float(np.percentile(edge_contrast, 95))
            features['edge_contrast_high_ratio'] = float(np.mean(edge_contrast > 50))
        else:
            for k in ['edge_mean_v', 'edge_std_v', 'edge_mean_gray', 'edge_std_gray', 'edge_mean_s',
                       'edge_inner_v_diff', 'edge_inner_gray_diff', 'edge_inner_v_ratio',
                       'edge_defect_color_ratio', 'edge_red_ratio', 'edge_yellow_ratio', 'edge_white_ratio',
                       'edge_bright_spots', 'edge_bright_max_area', 'edge_bright_total',
                       'edge_bright_large', 'edge_bright_mean_area',
                       'edge_contrast_mean', 'edge_contrast_std', 'edge_contrast_max',
                       'edge_contrast_p95', 'edge_contrast_high_ratio']:
                features[k] = 0.0

        # 按模型训练时的顺序排列
        if self.feature_names:
            try:
                feat_vec = np.array([[features[k] for k in self.feature_names]], dtype=np.float32)
            except KeyError as e:
                raise RuntimeError(f"Missing feature {e}. Please retrain model with current plugin version.")
        else:
            keys = sorted(features.keys())
            feat_vec = np.array([[features[k] for k in keys]], dtype=np.float32)

        return feat_vec

    def _find_defect_regions(self, image: np.ndarray, roi_mask: np.ndarray,
                             edge_mask: np.ndarray, response_map: np.ndarray) -> List[DetectionResult]:
        """
        在边缘焊接区域内定位空洞缺陷（高亮异常区域）。
        """
        detections = []
        hsv = cv2.cvtColor(image, cv2.COLOR_BGR2HSV)

        if edge_mask is None or np.sum(edge_mask > 0) == 0:
            return detections

        # 方法1: 边缘区域高亮连通域
        # 边缘正常焊接应偏蓝（低V），空洞表现为高亮（高V）
        bright_in_edge = ((hsv[:, :, 2] > 180) & (edge_mask > 0)).astype(np.uint8) * 255
        bright_in_edge = cv2.morphologyEx(bright_in_edge, cv2.MORPH_OPEN,
                                           np.ones((3, 3), np.uint8), iterations=1)
        bright_in_edge = cv2.morphologyEx(bright_in_edge, cv2.MORPH_CLOSE,
                                           np.ones((7, 7), np.uint8), iterations=1)

        num, labels, stats, centroids = cv2.connectedComponentsWithStats(bright_in_edge, connectivity=8)
        for i in range(1, num):
            area = stats[i, cv2.CC_STAT_AREA]
            if self.min_defect_area <= area <= self.max_defect_area:
                x1 = stats[i, cv2.CC_STAT_LEFT]
                y1 = stats[i, cv2.CC_STAT_TOP]
                x2 = x1 + stats[i, cv2.CC_STAT_WIDTH]
                y2 = y1 + stats[i, cv2.CC_STAT_HEIGHT]

                # 置信度基于面积和最大亮度
                region_v = hsv[:, :, 2][labels == i]
                max_v = region_v.max()
                conf = min(0.99, 0.5 + area / 2000.0 + max_v / 500.0)

                detections.append(DetectionResult(
                    class_name='void',
                    confidence=conf,
                    bbox=(int(x1), int(y1), int(x2), int(y2))
                ))

        # 方法2: 边缘区域局部对比度异常
        v_f = hsv[:, :, 2].astype(np.float32)
        local_bg = cv2.medianBlur(v_f.astype(np.uint8), 31).astype(np.float32)
        local_contrast = v_f - local_bg

        contrast_mask = ((local_contrast > 50) & (edge_mask > 0)).astype(np.uint8) * 255
        contrast_mask = cv2.morphologyEx(contrast_mask, cv2.MORPH_OPEN,
                                          np.ones((3, 3), np.uint8), iterations=1)

        num2, labels2, stats2, _ = cv2.connectedComponentsWithStats(contrast_mask, connectivity=8)
        for i in range(1, num2):
            area = stats2[i, cv2.CC_STAT_AREA]
            if self.min_defect_area <= area <= self.max_defect_area:
                x1 = stats2[i, cv2.CC_STAT_LEFT]
                y1 = stats2[i, cv2.CC_STAT_TOP]
                x2 = x1 + stats2[i, cv2.CC_STAT_WIDTH]
                y2 = y1 + stats2[i, cv2.CC_STAT_HEIGHT]

                max_contrast = local_contrast[labels2 == i].max()
                conf = min(0.99, 0.5 + max_contrast / 200.0)

                detections.append(DetectionResult(
                    class_name='void',
                    confidence=conf,
                    bbox=(int(x1), int(y1), int(x2), int(y2))
                ))

        # 按面积排序并限制数量
        detections.sort(key=lambda d: (d.bbox[2] - d.bbox[0]) * (d.bbox[3] - d.bbox[1]), reverse=True)
        detections = detections[:15]

        # NMS 去重
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

            # 提取 ROI、响应图和边缘焊接区域
            image, roi_mask, response_map, roi_bbox, edge_mask = self._extract_roi_and_response(image)
            if roi_mask is None or response_map is None:
                raise ValueError("Failed to extract ROI")

            # 提取特征并预测
            features = self._extract_features(image, roi_mask, response_map, edge_mask)
            features_scaled = self.scaler.transform(features)

            proba = self.model.predict_proba(features_scaled)[0]
            ng_prob = float(proba[1])
            predicted_class = 1 if ng_prob >= self.conf_threshold else 0

            # 在边缘焊接区域定位缺陷
            detections = []
            result_status = 'OK'
            if predicted_class == 1:
                detections = self._find_defect_regions(image, roi_mask, edge_mask, response_map)
                if detections:
                    result_status = 'NG'
                else:
                    # 模型判断为 NG 但未定位到框，给出整张 ROI 作为缺陷区域
                    x1, y1, x2, y2 = roi_bbox
                    detections.append(DetectionResult(
                        class_name='void',
                        confidence=ng_prob,
                        bbox=(x1, y1, x2, y2)
                    ))
                    result_status = 'NG'

            # 绘制结果图
            result_image = image.copy()
            # 绘制边缘焊接区域轮廓（绿色半透明）
            edge_overlay = result_image.copy()
            edge_overlay[edge_mask > 0] = edge_overlay[edge_mask > 0] * 0.6 + np.array([0, 255, 0], dtype=np.uint8) * 0.4
            cv2.addWeighted(edge_overlay, 0.3, result_image, 0.7, 0, result_image)

            # 绘制缺陷框
            colors = {
                'void': (0, 0, 255),       # 红色 = 空洞缺陷
                'high_response': (0, 0, 255),
                'low_response': (255, 0, 0),
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

    def set_edge_width(self, width: int):
        """设置边缘焊接带宽度（像素）"""
        self.edge_width = max(5, min(100, width))

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
            'edge_width': self.edge_width,
            'min_defect_area': self.min_defect_area,
            'max_defect_area': self.max_defect_area
        }
