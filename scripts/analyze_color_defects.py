"""
分析颜色规则缺陷检测的区分度（200 样本快速测试）
"""
import cv2
import numpy as np
import glob
import os


def imread_unicode(path):
    data = np.fromfile(path, dtype=np.uint8)
    return cv2.imdecode(data, cv2.IMREAD_UNCHANGED)


def get_edge_and_boundaries(img):
    h, w = img.shape[:2]
    if w > h * 2.5 and w > 1100:
        right_strip = img[:, int(w * 0.95):, :]
        strip_mean = right_strip.mean()
        body_mean = img[:, :int(w * 0.95), :].mean()
        if abs(strip_mean - body_mean) > 30:
            img = img[:, :int(w * 0.92)]
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    _, binary = cv2.threshold(gray, 10, 255, cv2.THRESH_BINARY)
    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5))
    binary = cv2.morphologyEx(binary, cv2.MORPH_CLOSE, kernel, iterations=2)
    binary = cv2.morphologyEx(binary, cv2.MORPH_OPEN, kernel, iterations=1)
    contours, _ = cv2.findContours(binary, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    if not contours:
        return None, None, None, None
    main_contour = sorted(contours, key=cv2.contourArea, reverse=True)[0]
    roi_mask = np.zeros_like(gray, dtype=np.uint8)
    cv2.drawContours(roi_mask, [main_contour], -1, 255, -1)
    roi_mask = cv2.erode(roi_mask, kernel, iterations=2)
    edge_width = 20
    kernel_edge = cv2.getStructuringElement(cv2.MORPH_RECT, (edge_width, edge_width))
    dilated = cv2.dilate(roi_mask, kernel_edge)
    eroded = cv2.erode(roi_mask, kernel_edge)
    edge_mask = cv2.subtract(dilated, eroded)
    inner_eroded = cv2.erode(eroded, np.ones((3, 3), np.uint8))
    inner_boundary = cv2.subtract(eroded, inner_eroded)
    outer_eroded = cv2.erode(dilated, np.ones((3, 3), np.uint8))
    outer_boundary = cv2.subtract(dilated, outer_eroded)
    return img, edge_mask, inner_boundary, outer_boundary


def detect_defects_color(img, edge_mask, inner_boundary, outer_boundary):
    hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
    # 颜色规则：红/白/亮黄 = 缺陷
    red_mask = (((hsv[:, :, 0] < 15) | (hsv[:, :, 0] > 165)) & (hsv[:, :, 1] > 100) & (hsv[:, :, 2] > 150) & (edge_mask > 0))
    yellow_mask = ((hsv[:, :, 0] >= 15) & (hsv[:, :, 0] <= 40) & (hsv[:, :, 1] > 80) & (hsv[:, :, 2] > 180) & (edge_mask > 0))
    white_mask = ((hsv[:, :, 1] < 50) & (hsv[:, :, 2] > 200) & (edge_mask > 0))
    defect_mask = (red_mask | yellow_mask | white_mask).astype(np.uint8) * 255
    defect_mask = cv2.morphologyEx(defect_mask, cv2.MORPH_OPEN, np.ones((3, 3), np.uint8), iterations=1)
    defect_mask = cv2.morphologyEx(defect_mask, cv2.MORPH_CLOSE, np.ones((5, 5), np.uint8), iterations=1)

    inner_dilated = cv2.dilate(inner_boundary, np.ones((5, 5), np.uint8), iterations=2)
    outer_dilated = cv2.dilate(outer_boundary, np.ones((5, 5), np.uint8), iterations=2)

    num, labels, stats, centroids = cv2.connectedComponentsWithStats(defect_mask, connectivity=8)
    edge_area = max(np.sum(edge_mask > 0), 1)

    total_defect_area = 0
    breach_count = 0
    max_radial = 0
    num_defects = 0

    dist_transform = cv2.distanceTransform(edge_mask, cv2.DIST_L2, 5)

    for i in range(1, num):
        area = stats[i, cv2.CC_STAT_AREA]
        if area < 10:
            continue
        defect_mask_i = (labels == i).astype(np.uint8) * 255
        touches_inner = np.any(defect_mask_i[inner_dilated > 0] > 0)
        touches_outer = np.any(defect_mask_i[outer_dilated > 0] > 0)
        is_breach = touches_inner and touches_outer and area >= 30

        ys, xs = np.where(defect_mask_i > 0)
        if len(ys) > 0:
            dists = dist_transform[ys, xs]
            radial = float(dists.max() - dists.min())
        else:
            radial = 0

        if is_breach:
            breach_count += 1
        max_radial = max(max_radial, radial)
        total_defect_area += area
        num_defects += 1

    return {
        'defect_ratio': total_defect_area / edge_area,
        'breach_count': breach_count,
        'max_radial': max_radial,
        'num_defects': num_defects,
        'total_area': total_defect_area,
    }


def main():
    ng_files = sorted(glob.glob('sample/原始图片/NG/*.bmp'))[:50] + sorted(glob.glob('sample/2/原始图片/NG/*.bmp'))[:50]
    ok_files = sorted(glob.glob('sample/原始图片/Ok/*.bmp'))[:50] + sorted(glob.glob('sample/2/原始图片/Ok/*.bmp'))[:50]

    ng_metrics = []
    ok_metrics = []

    for f in ng_files:
        img = imread_unicode(f)
        if img is None:
            continue
        img, edge, inner, outer = get_edge_and_boundaries(img)
        if edge is None:
            continue
        m = detect_defects_color(img, edge, inner, outer)
        ng_metrics.append(m)

    for f in ok_files:
        img = imread_unicode(f)
        if img is None:
            continue
        img, edge, inner, outer = get_edge_and_boundaries(img)
        if edge is None:
            continue
        m = detect_defects_color(img, edge, inner, outer)
        ok_metrics.append(m)

    print('=== 颜色规则缺陷检测 (100 NG vs 100 Ok) ===')
    header = f"{'metric':<20} {'NG mean':>12} {'Ok mean':>12} {'NG median':>12} {'Ok median':>12}"
    print(header)
    print('-' * 70)
    for key in ['defect_ratio', 'breach_count', 'max_radial', 'num_defects', 'total_area']:
        ng_vals = np.array([m[key] for m in ng_metrics])
        ok_vals = np.array([m[key] for m in ok_metrics])
        print(f'{key:<20} {ng_vals.mean():>12.4f} {ok_vals.mean():>12.4f} {np.median(ng_vals):>12.4f} {np.median(ok_vals):>12.4f}')

    print()
    print('breach_count distribution:')
    for bc in range(6):
        ng_c = sum(1 for m in ng_metrics if m['breach_count'] == bc)
        ok_c = sum(1 for m in ok_metrics if m['breach_count'] == bc)
        print(f'  breach={bc}: NG={ng_c}, Ok={ok_c}')
    ng_breach = sum(1 for m in ng_metrics if m['breach_count'] >= 1)
    ok_breach = sum(1 for m in ok_metrics if m['breach_count'] >= 1)
    print(f'  breach>=1: NG={ng_breach}/100, Ok={ok_breach}/100')

    print()
    print('defect_ratio distribution:')
    for lo, hi in [(0, 0.02), (0.02, 0.05), (0.05, 0.08), (0.08, 0.12), (0.12, 0.20), (0.20, 1.0)]:
        ng_c = sum(1 for m in ng_metrics if lo <= m['defect_ratio'] < hi)
        ok_c = sum(1 for m in ok_metrics if lo <= m['defect_ratio'] < hi)
        print(f'  [{lo:.2f}, {hi:.2f}): NG={ng_c}, Ok={ok_c}')

    # 计算 AUC
    print()
    print('AUC (simplified):')
    for key in ['defect_ratio', 'breach_count', 'max_radial', 'num_defects', 'total_area']:
        ng_vals = np.array([m[key] for m in ng_metrics])
        ok_vals = np.array([m[key] for m in ok_metrics])
        all_vals = np.concatenate([ng_vals, ok_vals])
        all_labels = np.concatenate([np.ones(len(ng_vals)), np.zeros(len(ok_vals))])
        sorted_idx = np.argsort(-all_vals)
        sorted_labels = all_labels[sorted_idx]
        tp = np.cumsum(sorted_labels)
        fp = np.cumsum(1 - sorted_labels)
        tpr = tp / max(len(ng_vals), 1)
        fpr = fp / max(len(ok_vals), 1)
        auc_fn = getattr(np, 'trapezoid', getattr(np, 'trapz', None))
        auc = auc_fn(tpr, fpr)
        print(f'  {key}: AUC={auc:.4f}')


if __name__ == '__main__':
    main()
