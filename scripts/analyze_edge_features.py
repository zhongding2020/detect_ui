"""
分析边缘焊接区域特征 — 用于改进缺陷检测模型
"""
import cv2
import numpy as np
import os
import glob
import json


def imread_unicode(path):
    data = np.fromfile(path, dtype=np.uint8)
    return cv2.imdecode(data, cv2.IMREAD_UNCHANGED)


def extract_edge_features(image_path):
    """提取边缘焊接区域 + 全局特征"""
    img = imread_unicode(image_path)
    if img is None:
        return None

    h, w = img.shape[:2]
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)

    # 工件轮廓
    _, binary = cv2.threshold(gray, 10, 255, cv2.THRESH_BINARY)
    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5))
    binary = cv2.morphologyEx(binary, cv2.MORPH_CLOSE, kernel, iterations=2)
    contours, _ = cv2.findContours(binary, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    if not contours:
        return None
    main_contour = sorted(contours, key=cv2.contourArea, reverse=True)[0]

    roi_mask = np.zeros_like(gray, dtype=np.uint8)
    cv2.drawContours(roi_mask, [main_contour], -1, 255, -1)

    # 边缘焊接带
    edge_width = 20
    kernel_edge = cv2.getStructuringElement(cv2.MORPH_RECT, (edge_width, edge_width))
    dilated = cv2.dilate(roi_mask, kernel_edge)
    eroded = cv2.erode(roi_mask, kernel_edge)
    edge_mask = cv2.subtract(dilated, eroded)
    inner_mask = cv2.subtract(roi_mask, edge_mask)

    features = {}

    # 全局特征
    roi_pixels = gray[roi_mask > 0].astype(np.float32) / 255.0
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
        features[f'{prefix}_mean'] = float(img[:, :, i].mean())
        features[f'{prefix}_std'] = float(img[:, :, i].std())
    for i, prefix in enumerate(['h', 's', 'v']):
        features[f'{prefix}_mean'] = float(hsv[:, :, i].mean())
        features[f'{prefix}_std'] = float(hsv[:, :, i].std())
    lab = cv2.cvtColor(img, cv2.COLOR_BGR2LAB)
    for i, prefix in enumerate(['l', 'a', 'b2']):
        features[f'{prefix}_mean'] = float(lab[:, :, i].mean())
        features[f'{prefix}_std'] = float(lab[:, :, i].std())

    gx = cv2.Scharr(gray, cv2.CV_64F, 1, 0)
    gy = cv2.Scharr(gray, cv2.CV_64F, 0, 1)
    grad_mag = np.sqrt(gx ** 2 + gy ** 2)
    features['grad_mean'] = float(grad_mag.mean())
    features['grad_std'] = float(grad_mag.std())
    lap = cv2.Laplacian(gray, cv2.CV_64F)
    features['lap_mean'] = float(np.abs(lap).mean())
    features['lap_std'] = float(lap.std())

    bright_binary = (gray > 180).astype(np.uint8) * 255
    bright_binary[roi_mask == 0] = 0
    num, _, stats, _ = cv2.connectedComponentsWithStats(bright_binary, connectivity=8)
    areas = stats[1:, cv2.CC_STAT_AREA]
    features['bright_spot_count'] = float(len(areas))
    features['bright_spot_max_area'] = float(areas.max()) if len(areas) > 0 else 0
    features['bright_spot_total_area'] = float(areas.sum()) if len(areas) > 0 else 0
    features['bright_spot_mean_area'] = float(areas.mean()) if len(areas) > 0 else 0
    features['bright_spot_area_std'] = float(areas.std()) if len(areas) > 0 else 0
    features['bright_spot_large_count'] = float(np.sum(areas > 500)) if len(areas) > 0 else 0

    dark_binary = (gray < 40).astype(np.uint8) * 255
    dark_binary[roi_mask == 0] = 0
    num2, _, stats2, _ = cv2.connectedComponentsWithStats(dark_binary, connectivity=8)
    dark_areas = stats2[1:, cv2.CC_STAT_AREA]
    features['dark_spot_count'] = float(len(dark_areas))
    features['dark_spot_max_area'] = float(dark_areas.max()) if len(dark_areas) > 0 else 0
    features['dark_spot_total_area'] = float(dark_areas.sum()) if len(dark_areas) > 0 else 0
    features['dark_spot_large_count'] = float(np.sum(dark_areas > 500)) if len(dark_areas) > 0 else 0

    features['image_width'] = float(w)
    features['image_height'] = float(h)
    features['roi_area_ratio'] = float(np.sum(roi_mask > 0) / (h * w))

    # 边缘焊接区域特征
    edge_pixels_gray = gray[edge_mask > 0].astype(np.float32)
    edge_pixels_v = hsv[:, :, 2][edge_mask > 0].astype(np.float32)
    edge_pixels_s = hsv[:, :, 1][edge_mask > 0].astype(np.float32)
    inner_pixels_v = hsv[:, :, 2][inner_mask > 0].astype(np.float32)
    inner_pixels_gray = gray[inner_mask > 0].astype(np.float32)

    features['edge_mean_v'] = float(edge_pixels_v.mean())
    features['edge_std_v'] = float(edge_pixels_v.std())
    features['edge_mean_gray'] = float(edge_pixels_gray.mean())
    features['edge_std_gray'] = float(edge_pixels_gray.std())
    features['edge_mean_s'] = float(edge_pixels_s.mean())

    features['edge_inner_v_diff'] = float(edge_pixels_v.mean() - inner_pixels_v.mean())
    features['edge_inner_gray_diff'] = float(edge_pixels_gray.mean() - inner_pixels_gray.mean())
    features['edge_inner_v_ratio'] = float(edge_pixels_v.mean() / max(inner_pixels_v.mean(), 1))

    # 边缘缺陷颜色 (红/白/亮黄)
    red_mask = ((hsv[:, :, 0] < 15) | (hsv[:, :, 0] > 165)) & (hsv[:, :, 1] > 100) & (hsv[:, :, 2] > 150) & (edge_mask > 0)
    yellow_mask = (hsv[:, :, 0] >= 15) & (hsv[:, :, 0] <= 40) & (hsv[:, :, 1] > 80) & (hsv[:, :, 2] > 180) & (edge_mask > 0)
    white_mask = (hsv[:, :, 1] < 50) & (hsv[:, :, 2] > 200) & (edge_mask > 0)

    defect_color_mask = red_mask | yellow_mask | white_mask
    features['edge_defect_color_ratio'] = float(defect_color_mask.sum() / max(edge_mask.sum(), 1))
    features['edge_red_ratio'] = float(red_mask.sum() / max(edge_mask.sum(), 1))
    features['edge_yellow_ratio'] = float(yellow_mask.sum() / max(edge_mask.sum(), 1))
    features['edge_white_ratio'] = float(white_mask.sum() / max(edge_mask.sum(), 1))

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

    return features


def main():
    folders = [
        ('NG', 'sample/原始图片/NG'),
        ('Ok', 'sample/原始图片/Ok'),
        ('NG2', 'sample/2/原始图片/NG'),
        ('Ok2', 'sample/2/原始图片/Ok'),
    ]

    all_results = {}
    for label, folder in folders:
        files = glob.glob(os.path.join(folder, '*.bmp'))[:50]
        results = []
        for f in files:
            s = extract_edge_features(f)
            if s:
                results.append(s)
        all_results[label] = results
        print(f'{folder}: analyzed {len(results)}/{len(files)}')

    print()
    print('=== 边缘特征 NG vs Ok 对比 ===')

    # 找出差异最大的边缘特征
    edge_keys = [k for k in all_results['NG'][0].keys() if k.startswith('edge_')]

    print(f'{"特征":30s} | {"NG Set1":>10s} | {"Ok Set1":>10s} | {"Diff%":>8s} | {"NG Set2":>10s} | {"Ok Set2":>10s} | {"Diff%":>8s}')
    print('-' * 100)

    for k in sorted(edge_keys):
        ng1 = np.mean([r[k] for r in all_results['NG']])
        ok1 = np.mean([r[k] for r in all_results['Ok']])
        ng2 = np.mean([r[k] for r in all_results['NG2']])
        ok2 = np.mean([r[k] for r in all_results['Ok2']])

        diff1 = abs(ng1 - ok1) / max(abs(ng1), abs(ok1), 0.001) * 100
        diff2 = abs(ng2 - ok2) / max(abs(ng2), abs(ok2), 0.001) * 100

        marker = ' ***' if diff1 > 15 or diff2 > 15 else ''
        print(f'{k:30s} | {ng1:10.2f} | {ok1:10.2f} | {diff1:7.1f}% | {ng2:10.2f} | {ok2:10.2f} | {diff2:7.1f}%{marker}')


if __name__ == '__main__':
    main()
