"""
超声 C-scan 缺陷检测插件 v3.0

针对散热器产品的水浸式超声 C-scan 图像，
检测边缘焊接区域的空洞缺陷。

核心判定标准:
1. 横截面打穿检测 — 缺陷是否贯穿焊接带（从内璧到外壁）
2. 最大缺陷宽度 — 单个缺陷在垂直于焊缝方向上的最大跨度
3. 缺陷占比 — 缺陷总面积 / 焊接带总面积
4. 位置归一化 — 消除工件在图像中的位置偏移

模型文件位置:
    models/ultrasonic_defect_model.pkl
    models/ultrasonic_defect_scaler.pkl
    models/ultrasonic_defect_meta.json

训练脚本:
    scripts/train_ultrasonic_detector.py
"""
import os
import sys
import json
from typing import Dict, Any, List, Tuple

import cv2
import numpy as np
import joblib

from plugins.base.defect_base import DetectionAlgorithmBase, DetectionResult


class UltrasonicDefectDetector(DetectionAlgorithmBase):
    """
    超声 C-scan 缺陷检测器（散热器边缘焊接检测）v3.0

    核心判定逻辑:
    - 横截面打穿: 缺陷从内璧贯穿到外壁 → NG
    - 缺陷占比: 缺陷面积 / 焊接带面积 > 阈值 → NG
    - 最大缺陷宽度: 单个缺陷最大径向跨度 > 阈值 → NG
    """

    def __init__(self):
        super().__init__()
        self.name = "Ultrasonic Defect Detector"
        self.version = "3.1.0"
        self.author = "Bearing Defect Detection Team"
        self.description = "散热器超声 C-scan 边缘焊接空洞缺陷检测（含横截面打穿判定）"

        # 模型配置
        self.model = None
        self.scaler = None
        self.feature_names = None
        self.conf_threshold = 0.5  # 模型输出概率阈值
        self.iou_threshold = 0.3   # 缺陷框去重 IoU 阈值

        # 边缘焊接区域配置
        self.edge_width = 20        # 边缘焊接带宽度（像素）

        # 缺陷判定阈值（核心参数）
        self.breach_enabled = False         # 横截面打穿判定（默认关闭：边缘带着色在NG/Ok间无区分度）
        self.hybrid_override = False        # 混合 override（默认关闭：经测试不提升准确率）
        self.hybrid_ratio_threshold = 0.05  # override 触发的缺陷占比阈值
        self.hybrid_breach_threshold = 3    # override 触发的打穿数阈值
        self.hybrid_ml_low = 0.15           # override 生效的 ML 概率下限
        self.defect_ratio_threshold = 0.08  # 缺陷占比阈值 (8%)
        self.max_width_ratio = 0.7          # 最大缺陷宽度 / 焊接带宽度 阈值
        self.min_defect_area = 20           # 最小缺陷面积（像素）
        self.max_defect_area = 5000         # 最大缺陷面积（像素）

        # 位置归一化（仅用于缺陷定位，不影响特征提取）
        self.normalize_position = False     # 是否归一化位置偏移（默认关闭）
        self.norm_margin = 10               # 归一化后的边距

        # 项目根目录（用于定位 models/）
        self.project_root = self._get_project_root()

    def _get_project_root(self) -> str:
        """获取项目根目录，兼容源码和 PyInstaller 打包环境"""
        if getattr(sys, 'frozen', False):
            # PyInstaller onefile: 先查 _MEIPASS（内置数据），再查 exe 同级目录
            meipass = getattr(sys, '_MEIPASS', None)
            if meipass and os.path.exists(os.path.join(meipass, 'models')):
                return meipass
            exe_dir = os.path.dirname(os.path.abspath(sys.executable))
            if os.path.exists(os.path.join(exe_dir, 'models')):
                return exe_dir
            return meipass or exe_dir
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

    # ------------------------------------------------------------------
    # 位置归一化
    # ------------------------------------------------------------------
    @staticmethod
    def _normalize_position(image: np.ndarray, margin: int = 10):
        """
        消除工件在图像中的位置偏移。
        将工件 bounding box 平移到固定位置 (margin, margin)。
        返回: (normalized_image, offset_x, offset_y)
        """
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        _, binary = cv2.threshold(gray, 10, 255, cv2.THRESH_BINARY)
        kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5))
        binary = cv2.morphologyEx(binary, cv2.MORPH_CLOSE, kernel, iterations=2)

        contours, _ = cv2.findContours(binary, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        if not contours:
            return image, 0, 0

        main_contour = sorted(contours, key=cv2.contourArea, reverse=True)[0]
        x, y, w, h = cv2.boundingRect(main_contour)

        # 计算平移量：将 bbox 左上角移到 (margin, margin)
        offset_x = margin - x
        offset_y = margin - y

        # 创建平移后的画布
        new_h = h + margin * 2
        new_w = w + margin * 2
        normalized = np.zeros((new_h, new_w, 3), dtype=np.uint8)

        # 计算源区域（确保不越界）
        src_x1 = max(x, 0)
        src_y1 = max(y, 0)
        src_x2 = min(x + w, image.shape[1])
        src_y2 = min(y + h, image.shape[0])
        dst_x1 = src_x1 + offset_x
        dst_y1 = src_y1 + offset_y

        normalized[dst_y1:dst_y1 + (src_y2 - src_y1),
                   dst_x1:dst_x1 + (src_x2 - src_x1)] = image[src_y1:src_y2, src_x1:src_x2]

        return normalized, offset_x, offset_y

    # ------------------------------------------------------------------
    # ROI / 边缘带提取
    # ------------------------------------------------------------------
    def _extract_roi_and_response(self, image: np.ndarray):
        """
        提取工件 ROI、归一化响应图和边缘焊接区域。
        返回：img_cropped, roi_mask, response_map, roi_bbox, edge_mask, inner_boundary, outer_boundary
        """
        if image is None:
            return None, None, None, None, None, None, None

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

        # 二值化分离工件
        _, binary = cv2.threshold(gray, 10, 255, cv2.THRESH_BINARY)
        kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5))
        binary = cv2.morphologyEx(binary, cv2.MORPH_CLOSE, kernel, iterations=2)
        binary = cv2.morphologyEx(binary, cv2.MORPH_OPEN, kernel, iterations=1)

        contours, _ = cv2.findContours(binary, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        if not contours:
            roi_mask = np.ones_like(gray, dtype=np.uint8) * 255
            roi_bbox = (0, 0, gray.shape[1], gray.shape[0])
            response_map = gray.astype(np.float32) / 255.0
            return img, roi_mask, response_map, roi_bbox, roi_mask.copy(), None, None

        main_contour = sorted(contours, key=cv2.contourArea, reverse=True)[0]
        roi_mask = np.zeros_like(gray, dtype=np.uint8)
        cv2.drawContours(roi_mask, [main_contour], -1, 255, -1)
        roi_mask = cv2.erode(roi_mask, kernel, iterations=2)

        x, y, bw, bh = cv2.boundingRect(main_contour)
        roi_bbox = (x, y, x + bw, y + bh)

        response_map = gray.astype(np.float32) / 255.0

        # 边缘焊接带 = 膨胀 - 腐蚀
        kernel_edge = cv2.getStructuringElement(cv2.MORPH_RECT, (self.edge_width, self.edge_width))
        dilated = cv2.dilate(roi_mask, kernel_edge)
        eroded = cv2.erode(roi_mask, kernel_edge)
        edge_mask = cv2.subtract(dilated, eroded)

        # 内/外边界（用于横截面打穿判定）
        # 内边界 = 腐蚀后 ROI 的边缘（焊接带的内壁）
        inner_eroded = cv2.erode(eroded, np.ones((3, 3), np.uint8))
        inner_boundary = cv2.subtract(eroded, inner_eroded)

        # 外边界 = 膨胀后 ROI 的边缘（焊接带的外壁）
        outer_eroded = cv2.erode(dilated, np.ones((3, 3), np.uint8))
        outer_boundary = cv2.subtract(dilated, outer_eroded)

        return img, roi_mask, response_map, roi_bbox, edge_mask, inner_boundary, outer_boundary

    # ------------------------------------------------------------------
    # 缺陷测量（核心新增）
    # ------------------------------------------------------------------
    def _measure_defects(self, image: np.ndarray, edge_mask: np.ndarray,
                         inner_boundary: np.ndarray, outer_boundary: np.ndarray):
        """
        测量边缘焊接带内的缺陷，返回缺陷列表和聚合指标。

        v3.1 改进:
        - 用颜色规则(红/白/亮黄) + 局部对比度替代纯亮度阈值
        - 打穿检测用距离变换覆盖率(60%阈值) + 边界相交双重确认
        - 径向宽度直接用距离变换值范围

        每个缺陷包含:
        - bbox: 边界框
        - area: 面积
        - radial_width: 径向宽度（距离变换值范围）
        - is_breach: 是否横截面打穿

        聚合指标:
        - max_defect_width: 最大缺陷径向宽度
        - defect_ratio: 缺陷总面积 / 焊接带面积
        - breach_count: 打穿缺陷数量
        - total_defects: 缺陷总数
        """
        hsv = cv2.cvtColor(image, cv2.COLOR_BGR2HSV)
        edge_area = max(np.sum(edge_mask > 0), 1)

        # 边界为空时的空 mask 保护
        if inner_boundary is None:
            inner_boundary = np.zeros_like(edge_mask, dtype=np.uint8)
        if outer_boundary is None:
            outer_boundary = np.zeros_like(edge_mask, dtype=np.uint8)

        # ---- 缺陷检测：颜色规则 + 局部对比度 ----
        h_ch = hsv[:, :, 0]
        s_ch = hsv[:, :, 1]
        v_ch = hsv[:, :, 2]

        # 颜色规则：红/白/亮黄 = 空洞缺陷（与特征提取一致）
        red_mask = (((h_ch < 15) | (h_ch > 165)) & (s_ch > 100) & (v_ch > 150))
        yellow_mask = ((h_ch >= 15) & (h_ch <= 40) & (s_ch > 80) & (v_ch > 180))
        white_mask = ((s_ch < 50) & (v_ch > 200))
        color_defect = (red_mask | yellow_mask | white_mask) & (edge_mask > 0)

        # 局部对比度：V 通道偏离局部中值（过滤均匀背景着色）
        local_bg = cv2.medianBlur(v_ch, 31)
        local_contrast = cv2.absdiff(v_ch, local_bg)
        high_contrast = (local_contrast > 40) & (edge_mask > 0)

        # 缺陷 = 颜色规则 AND 高局部对比度
        defect_mask = (color_defect & high_contrast).astype(np.uint8) * 255
        defect_mask = cv2.morphologyEx(defect_mask, cv2.MORPH_OPEN, np.ones((3, 3), np.uint8), iterations=1)
        defect_mask = cv2.morphologyEx(defect_mask, cv2.MORPH_CLOSE, np.ones((5, 5), np.uint8), iterations=1)

        num, labels, stats, centroids = cv2.connectedComponentsWithStats(defect_mask, connectivity=8)

        # 距离变换（用于径向宽度和打穿判定）
        dist_transform = cv2.distanceTransform(edge_mask, cv2.DIST_L2, 5)
        max_dist = max(dist_transform.max(), 1.0)

        # 膨胀边界用于打穿检测的双重确认
        inner_dilated = cv2.dilate(inner_boundary, np.ones((3, 3), np.uint8), iterations=3)
        outer_dilated = cv2.dilate(outer_boundary, np.ones((3, 3), np.uint8), iterations=3)

        defects = []
        for i in range(1, num):
            area = stats[i, cv2.CC_STAT_AREA]
            if area < self.min_defect_area:
                continue

            x1 = stats[i, cv2.CC_STAT_LEFT]
            y1 = stats[i, cv2.CC_STAT_TOP]
            x2 = x1 + stats[i, cv2.CC_STAT_WIDTH]
            y2 = y1 + stats[i, cv2.CC_STAT_HEIGHT]

            comp_mask = (labels == i).astype(np.uint8) * 255
            ys, xs = np.where(comp_mask > 0)

            if len(ys) == 0:
                continue

            # 径向宽度 = 缺陷覆盖的距离变换值范围
            defect_dists = dist_transform[ys, xs]
            dist_range = float(defect_dists.max() - defect_dists.min())
            radial_width = dist_range

            # 打穿判定:
            # 距离变换覆盖率 >= 50%（缺陷跨越焊接带宽度的一半以上）
            # 或同时接触内边界和外边界（几何确认）
            # 满足任一条件即判为打穿
            dist_coverage = dist_range / max_dist
            touches_inner = np.any(comp_mask[inner_dilated > 0] > 0)
            touches_outer = np.any(comp_mask[outer_dilated > 0] > 0)
            boundary_breach = touches_inner and touches_outer

            is_breach = ((dist_coverage >= 0.5) or boundary_breach) and (area >= 15)

            defects.append({
                'bbox': (x1, y1, x2, y2),
                'area': int(area),
                'radial_width': radial_width,
                'dist_coverage': dist_coverage,
                'is_breach': is_breach,
                'centroid': centroids[i]
            })

        # 聚合指标
        total_defect_area = sum(d['area'] for d in defects)
        max_radial_width = max((d['radial_width'] for d in defects), default=0)
        breach_count = sum(1 for d in defects if d['is_breach'])
        defect_ratio = total_defect_area / edge_area

        metrics = {
            'max_defect_width': max_radial_width,
            'max_defect_width_ratio': max_radial_width / max(self.edge_width, 1),
            'defect_ratio': defect_ratio,
            'breach_count': breach_count,
            'total_defects': len(defects),
            'total_defect_area': total_defect_area,
            'edge_band_area': edge_area,
        }

        return defects, metrics

    # ------------------------------------------------------------------
    # 判定逻辑
    # ------------------------------------------------------------------
    def _classify(self, metrics: Dict[str, float], ml_prob: float) -> Tuple[str, str]:
        """
        综合判定：ML 模型为主，规则指标为辅。

        判定逻辑:
        1. ML 模型判定 NG (ml_prob >= conf_threshold) → NG
        2. 混合 override（可选）: ML 判定 OK 但 defect_ratio 和 breach_count 同时高 → NG
        3. 横截面打穿安全网（可选）: breach_count > 0 → NG
        4. ML 模型判定 OK → OK

        返回: (result_status, reason)
        """
        reasons = []
        ml_status = 'NG' if ml_prob >= self.conf_threshold else 'OK'

        # ML 判定为主
        if ml_status == 'NG':
            reasons.append(f"ML prob={ml_prob:.1%}")
            if metrics['total_defects'] > 0:
                reasons.append(f"缺陷数={metrics['total_defects']}")
            if metrics['breach_count'] > 0:
                reasons.append(f"打穿={metrics['breach_count']}")
            return 'NG', '; '.join(reasons)

        # 混合 override: ML 判 OK 但规则指标强烈指示缺陷
        if self.hybrid_override:
            if (ml_prob >= self.hybrid_ml_low and
                metrics['defect_ratio'] >= self.hybrid_ratio_threshold and
                metrics['breach_count'] >= self.hybrid_breach_threshold):
                reasons.append(f"规则override: ratio={metrics['defect_ratio']:.1%} breach={metrics['breach_count']}")
                return 'NG', '; '.join(reasons)

        # 横截面打穿检测（安全网，默认关闭）
        if self.breach_enabled and metrics['breach_count'] > 0:
            reasons.append(f"横截面打穿 × {metrics['breach_count']}")
            return 'NG', '; '.join(reasons)

        return 'OK', ''

    # ------------------------------------------------------------------
    # 特征提取（用于 ML 模型辅助判断）
    # ------------------------------------------------------------------
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

        # v3.1: 所有统计改为 ROI 内计算，消除位置偏移影响
        roi_mask_bool = roi_mask > 0
        for i, prefix in enumerate(['b', 'g', 'r']):
            ch = image[:, :, i][roi_mask_bool]
            features[f'{prefix}_mean'] = float(ch.mean()) if len(ch) > 0 else 0.0
            features[f'{prefix}_std'] = float(ch.std()) if len(ch) > 0 else 0.0
        for i, prefix in enumerate(['h', 's', 'v']):
            ch = hsv[:, :, i][roi_mask_bool]
            features[f'{prefix}_mean'] = float(ch.mean()) if len(ch) > 0 else 0.0
            features[f'{prefix}_std'] = float(ch.std()) if len(ch) > 0 else 0.0
        for i, prefix in enumerate(['l', 'a', 'b2']):
            ch = lab[:, :, i][roi_mask_bool]
            features[f'{prefix}_mean'] = float(ch.mean()) if len(ch) > 0 else 0.0
            features[f'{prefix}_std'] = float(ch.std()) if len(ch) > 0 else 0.0

        # 梯度/拉普拉斯也限制在 ROI 内
        gx = cv2.Scharr(gray_full, cv2.CV_64F, 1, 0)
        gy = cv2.Scharr(gray_full, cv2.CV_64F, 0, 1)
        grad_mag = np.sqrt(gx ** 2 + gy ** 2)
        grad_roi = grad_mag[roi_mask_bool]
        features['grad_mean'] = float(grad_roi.mean()) if len(grad_roi) > 0 else 0.0
        features['grad_std'] = float(grad_roi.std()) if len(grad_roi) > 0 else 0.0
        lap = cv2.Laplacian(gray_full, cv2.CV_64F)
        lap_roi = lap[roi_mask_bool]
        features['lap_mean'] = float(np.abs(lap_roi).mean()) if len(lap_roi) > 0 else 0.0
        features['lap_std'] = float(lap_roi.std()) if len(lap_roi) > 0 else 0.0

        # 全局亮斑/暗斑
        bright_binary = (response_map > 0.75).astype(np.uint8) * 255
        bright_binary[roi_mask == 0] = 0
        num, _, stats, _ = cv2.connectedComponentsWithStats(bright_binary, connectivity=8)
        areas = stats[1:, cv2.CC_STAT_AREA]
        features['bright_spot_count'] = float(len(areas))
        features['bright_spot_max_area'] = float(areas.max()) if len(areas) > 0 else 0
        features['bright_spot_total_area'] = float(areas.sum()) if len(areas) > 0 else 0
        features['bright_spot_mean_area'] = float(areas.mean()) if len(areas) > 0 else 0
        features['bright_spot_area_std'] = float(areas.std()) if len(areas) > 0 else 0
        features['bright_spot_large_count'] = float(np.sum(areas > 500)) if len(areas) > 0 else 0

        dark_binary = (response_map < 0.15).astype(np.uint8) * 255
        dark_binary[roi_mask == 0] = 0
        num2, _, stats2, _ = cv2.connectedComponentsWithStats(dark_binary, connectivity=8)
        dark_areas = stats2[1:, cv2.CC_STAT_AREA]
        features['dark_spot_count'] = float(len(dark_areas))
        features['dark_spot_max_area'] = float(dark_areas.max()) if len(dark_areas) > 0 else 0
        features['dark_spot_total_area'] = float(dark_areas.sum()) if len(dark_areas) > 0 else 0
        features['dark_spot_large_count'] = float(np.sum(dark_areas > 500)) if len(dark_areas) > 0 else 0

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

            red_mask = ((hsv[:, :, 0] < 15) | (hsv[:, :, 0] > 165)) & (hsv[:, :, 1] > 100) & (hsv[:, :, 2] > 150) & (edge_mask > 0)
            yellow_mask = (hsv[:, :, 0] >= 15) & (hsv[:, :, 0] <= 40) & (hsv[:, :, 1] > 80) & (hsv[:, :, 2] > 180) & (edge_mask > 0)
            white_mask = (hsv[:, :, 1] < 50) & (hsv[:, :, 2] > 200) & (edge_mask > 0)
            defect_color_mask = red_mask | yellow_mask | white_mask

            edge_area = max(np.sum(edge_mask > 0), 1)
            features['edge_defect_color_ratio'] = float(defect_color_mask.sum() / edge_area)
            features['edge_red_ratio'] = float(red_mask.sum() / edge_area)
            features['edge_yellow_ratio'] = float(yellow_mask.sum() / edge_area)
            features['edge_white_ratio'] = float(white_mask.sum() / edge_area)

            bright_edge = ((hsv[:, :, 2] > 180) & (edge_mask > 0)).astype(np.uint8) * 255
            num_e, _, stats_e, _ = cv2.connectedComponentsWithStats(bright_edge, connectivity=8)
            edge_areas = stats_e[1:, cv2.CC_STAT_AREA]
            features['edge_bright_spots'] = float(len(edge_areas))
            features['edge_bright_max_area'] = float(edge_areas.max()) if len(edge_areas) > 0 else 0
            features['edge_bright_total'] = float(edge_areas.sum()) if len(edge_areas) > 0 else 0
            features['edge_bright_large'] = float(np.sum(edge_areas > 50)) if len(edge_areas) > 0 else 0
            features['edge_bright_mean_area'] = float(edge_areas.mean()) if len(edge_areas) > 0 else 0

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

        if self.feature_names:
            try:
                feat_vec = np.array([[features[k] for k in self.feature_names]], dtype=np.float32)
            except KeyError as e:
                raise RuntimeError(f"Missing feature {e}. Please retrain model.")
        else:
            keys = sorted(features.keys())
            feat_vec = np.array([[features[k] for k in keys]], dtype=np.float32)

        return feat_vec

    # ------------------------------------------------------------------
    # NMS
    # ------------------------------------------------------------------
    @staticmethod
    def _iou(box_a, box_b) -> float:
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
        if not detections:
            return detections
        sorted_dets = sorted(detections, key=lambda d: d.confidence, reverse=True)
        keep = []
        while sorted_dets:
            current = sorted_dets.pop(0)
            keep.append(current)
            sorted_dets = [d for d in sorted_dets if self._iou(current.bbox, d.bbox) < threshold]
        return keep

    # ------------------------------------------------------------------
    # 主检测入口
    # ------------------------------------------------------------------
    def detect(self, image_path: str) -> Dict[str, Any]:
        """
        检测超声 C-scan 图像中的缺陷。

        判定流程:
        1. 位置归一化 → 消除位置偏移
        2. 提取边缘焊接带
        3. 测量缺陷（宽度/占比/打穿）
        4. 规则判定 + ML 辅助判定
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
            # 1. 读取原始图片
            image_orig = self._imread_unicode(image_path)
            if image_orig is None:
                raise ValueError(f"Failed to read image: {image_path}")

            # 2. 位置归一化（用于缺陷定位，消除位置偏移影响）
            if self.normalize_position:
                image_norm, offset_x, offset_y = self._normalize_position(image_orig, self.norm_margin)
            else:
                image_norm = image_orig
                offset_x, offset_y = 0, 0

            # 3. 在归一化图像上提取 ROI、响应图和边缘焊接区域
            image_proc, roi_mask, response_map, roi_bbox, edge_mask, inner_boundary, outer_boundary = \
                self._extract_roi_and_response(image_norm)
            if roi_mask is None or response_map is None:
                raise ValueError("Failed to extract ROI")

            # 4. 测量缺陷（核心：宽度/占比/打穿）
            defects, metrics = self._measure_defects(image_proc, edge_mask, inner_boundary, outer_boundary)

            # 5. ML 模型判定（主判定，使用原始图像的特征，不受归一化影响）
            ml_prob = 0.0
            try:
                # 用原始图像提取特征（与训练数据一致）
                img_feat, roi_f, resp_f, _, edge_f, _, _ = self._extract_roi_and_response(image_orig)
                if roi_f is not None:
                    features = self._extract_features(img_feat, roi_f, resp_f, edge_f)
                    features_scaled = self.scaler.transform(features)
                    proba = self.model.predict_proba(features_scaled)[0]
                    ml_prob = float(proba[1])
            except Exception as e:
                print(f"Warning: ML prediction failed: {e}")

            # 6. 综合判定：ML 为主，规则指标为辅
            final_status, final_reason = self._classify(metrics, ml_prob)

            # 8. 构建检测结果
            detections = []
            for d in defects:
                x1, y1, x2, y2 = d['bbox']
                conf = min(0.99, 0.5 + d['area'] / 2000.0 + d['radial_width'] / 100.0)
                # 打穿的缺陷置信度更高
                if d['is_breach']:
                    conf = min(0.99, conf + 0.2)
                detections.append(DetectionResult(
                    class_name='void_breach' if d['is_breach'] else 'void',
                    confidence=conf,
                    bbox=(int(x1), int(y1), int(x2), int(y2))
                ))

            detections = self._nms(detections, self.iou_threshold)

            # 9. 绘制结果图（在归一化图像上绘制，然后映射回原始坐标）
            result_image = image_proc.copy()

            # 绿色半透明高亮边缘焊接带
            edge_overlay = result_image.copy()
            edge_overlay[edge_mask > 0] = edge_overlay[edge_mask > 0] * 0.6 + np.array([0, 255, 0], dtype=np.uint8) * 0.4
            cv2.addWeighted(edge_overlay, 0.3, result_image, 0.7, 0, result_image)

            # 绘制缺陷框
            for det in detections:
                x1, y1, x2, y2 = det.bbox
                if det.class_name == 'void_breach':
                    color = (0, 0, 255)  # 红色 = 打穿缺陷
                    thickness = 3
                else:
                    color = (0, 165, 255)  # 橙色 = 普通缺陷
                    thickness = 2
                cv2.rectangle(result_image, (x1, y1), (x2, y2), color, thickness)
                label = f"{det.class_name} {det.confidence:.0%}"
                cv2.putText(result_image, label, (x1, max(y1 - 5, 15)),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.5, color, 1)

            # 绘制状态信息
            status_text = f"{final_status}"
            if final_reason:
                status_text += f" | {final_reason}"
            color_text = (0, 0, 255) if final_status == 'NG' else (0, 255, 0)
            cv2.putText(result_image, status_text, (10, 30),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.7, color_text, 2)

            # 绘制指标信息
            info_lines = [
                f"defects: {metrics['total_defects']}",
                f"ratio: {metrics['defect_ratio']:.1%}",
                f"max_w: {metrics['max_defect_width']:.0f}px",
                f"breach: {metrics['breach_count']}"
            ]
            for i, line in enumerate(info_lines):
                cv2.putText(result_image, line, (10, 55 + i * 20),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.45, (255, 255, 255), 1)

            return {
                'image_path': image_path,
                'result_status': final_status,
                'result_image': result_image,
                'result_path': None,
                'error_message': '',
                'detections': detections,
                'ng_probability': ml_prob,
                'metrics': metrics,
                'rule_reason': final_reason
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

    # ------------------------------------------------------------------
    # 参数配置
    # ------------------------------------------------------------------
    def set_confidence(self, threshold: float):
        """设置模型输出 NG 概率阈值"""
        self.conf_threshold = max(0.0, min(1.0, threshold))

    def set_iou(self, threshold: float):
        """设置缺陷框 NMS IoU 阈值"""
        self.iou_threshold = max(0.0, min(1.0, threshold))

    def set_edge_width(self, width: int):
        """设置边缘焊接带宽度（像素）"""
        self.edge_width = max(5, min(100, width))

    def set_defect_ratio_threshold(self, ratio: float):
        """设置缺陷占比阈值"""
        self.defect_ratio_threshold = max(0.0, min(1.0, ratio))

    def set_max_width_ratio(self, ratio: float):
        """设置最大缺陷宽度占焊接带宽度比例阈值"""
        self.max_width_ratio = max(0.0, min(1.0, ratio))

    def set_breach_enabled(self, enabled: bool):
        """是否启用横截面打穿判定"""
        self.breach_enabled = enabled

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
            'defect_ratio_threshold': self.defect_ratio_threshold,
            'max_width_ratio': self.max_width_ratio,
            'breach_enabled': self.breach_enabled,
            'normalize_position': self.normalize_position
        }
