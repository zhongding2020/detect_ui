"""
训练超声缺陷检测模型

根据 sample/ 目录下的标注数据训练一个基于机器学习的缺陷检测器，
并导出模型供 plugins/detectors/ultrasonic_defect_detector.py 使用。

用法:
    python scripts/train_ultrasonic_detector.py
"""
import os
import sys
import glob
import json
import pickle
import argparse
from datetime import datetime

import cv2
import numpy as np
from sklearn.ensemble import RandomForestClassifier, GradientBoostingClassifier
from sklearn.model_selection import train_test_split, cross_val_score, StratifiedKFold
from sklearn.metrics import classification_report, confusion_matrix, accuracy_score
from sklearn.preprocessing import StandardScaler
import joblib


# ---------------------------------------------------------------------------
# 图像加载（支持中文路径）
# ---------------------------------------------------------------------------
def imread_unicode(path):
    """Unicode 安全的 cv2.imread"""
    data = np.fromfile(path, dtype=np.uint8)
    img = cv2.imdecode(data, cv2.IMREAD_UNCHANGED)
    return img


# ---------------------------------------------------------------------------
# ROI 与响应图提取
# ---------------------------------------------------------------------------
def extract_roi_and_response(image):
    """
    提取工件 ROI 和归一化响应图。
    输入：BGR 超声 C-scan 图（可能带右侧色标）
    输出：roi_mask, response_map, roi_bbox
    """
    if image is None:
        return None, None, None

    # 去色标：TIFF 右侧有色标条，宽度约占 5-10%，根据长宽比判断
    h, w = image.shape[:2]
    img = image.copy()
    if w > h * 2.5 and w > 1100:
        # 右侧 100px 可能是色标，先裁剪看看
        crop_width = max(w - 120, int(w * 0.92))
        img = img[:, :crop_width]

    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)

    # 二值化分离工件区域（背景偏黑）
    _, binary = cv2.threshold(gray, 10, 255, cv2.THRESH_BINARY)

    # 形态学清理
    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5))
    binary = cv2.morphologyEx(binary, cv2.MORPH_CLOSE, kernel, iterations=2)
    binary = cv2.morphologyEx(binary, cv2.MORPH_OPEN, kernel, iterations=1)

    # 找最大轮廓（工件主体）
    contours, _ = cv2.findContours(binary, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    if not contours:
        # 全图作为 ROI
        roi_mask = np.ones_like(gray, dtype=np.uint8) * 255
        roi_bbox = (0, 0, gray.shape[1], gray.shape[0])
        response_map = gray.astype(np.float32) / 255.0
        return roi_mask, response_map, roi_bbox

    # 选面积最大的轮廓
    contours = sorted(contours, key=cv2.contourArea, reverse=True)
    main_contour = contours[0]

    # 生成 ROI mask
    roi_mask = np.zeros_like(gray, dtype=np.uint8)
    cv2.drawContours(roi_mask, [main_contour], -1, 255, -1)

    # 轻微腐蚀去掉边缘伪影
    roi_mask = cv2.erode(roi_mask, kernel, iterations=2)

    x, y, bw, bh = cv2.boundingRect(main_contour)
    roi_bbox = (x, y, x + bw, y + bh)

    # 响应图：归一化到 [0, 1]，超声回波振幅越高越亮
    response_map = gray.astype(np.float32) / 255.0

    return roi_mask, response_map, roi_bbox


# ---------------------------------------------------------------------------
# 特征工程
# ---------------------------------------------------------------------------
def extract_features(image_path):
    """
    从单张超声 C-scan 图中提取用于缺陷检测的特征向量。
    返回 dict，若失败返回 None。
    """
    img = imread_unicode(image_path)
    if img is None:
        return None

    roi_mask, response_map, roi_bbox = extract_roi_and_response(img)
    if roi_mask is None or response_map is None:
        return None

    # 仅 ROI 内的像素
    roi_pixels = response_map[roi_mask > 0]
    if len(roi_pixels) == 0:
        return None

    gray_full = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
    lab = cv2.cvtColor(img, cv2.COLOR_BGR2LAB)

    features = {}

    # 1. 全局统计
    features['mean'] = float(np.mean(roi_pixels))
    features['std'] = float(np.std(roi_pixels))
    features['median'] = float(np.median(roi_pixels))
    features['p5'] = float(np.percentile(roi_pixels, 5))
    features['p95'] = float(np.percentile(roi_pixels, 95))
    features['p99'] = float(np.percentile(roi_pixels, 99))

    # 2. 高/低响应区域比例
    features['high_ratio'] = float(np.mean(roi_pixels > 0.7))
    features['low_ratio'] = float(np.mean(roi_pixels < 0.2))
    features['mid_ratio'] = float(np.mean((roi_pixels >= 0.2) & (roi_pixels <= 0.7)))

    # 3. 极值区域比例
    features['very_high_ratio'] = float(np.mean(roi_pixels > 0.9))
    features['very_low_ratio'] = float(np.mean(roi_pixels < 0.05))

    # 4. BGR/HSV/Lab 全局均值与标准差
    for i, prefix in enumerate(['b', 'g', 'r']):
        features[f'{prefix}_mean'] = float(img[:, :, i].mean())
        features[f'{prefix}_std'] = float(img[:, :, i].std())
    for i, prefix in enumerate(['h', 's', 'v']):
        features[f'{prefix}_mean'] = float(hsv[:, :, i].mean())
        features[f'{prefix}_std'] = float(hsv[:, :, i].std())
    for i, prefix in enumerate(['l', 'a', 'b2']):
        features[f'{prefix}_mean'] = float(lab[:, :, i].mean())
        features[f'{prefix}_std'] = float(lab[:, :, i].std())

    # 5. 纹理/梯度
    gx = cv2.Scharr(gray_full, cv2.CV_64F, 1, 0)
    gy = cv2.Scharr(gray_full, cv2.CV_64F, 0, 1)
    grad_mag = np.sqrt(gx ** 2 + gy ** 2)
    features['grad_mean'] = float(grad_mag.mean())
    features['grad_std'] = float(grad_mag.std())

    lap = cv2.Laplacian(gray_full, cv2.CV_64F)
    features['lap_mean'] = float(np.abs(lap).mean())
    features['lap_std'] = float(lap.std())

    # 6. 连通域分析（高响应斑点）
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
        features['bright_spot_count'] = 0.0
        features['bright_spot_max_area'] = 0.0
        features['bright_spot_total_area'] = 0.0
        features['bright_spot_mean_area'] = 0.0
        features['bright_spot_area_std'] = 0.0
        features['bright_spot_large_count'] = 0.0

    # 7. 低响应异常（脱层/气孔可能表现为低响应暗区）
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
        features['dark_spot_count'] = 0.0
        features['dark_spot_max_area'] = 0.0
        features['dark_spot_total_area'] = 0.0
        features['dark_spot_large_count'] = 0.0

    # 8. 形状/尺寸
    features['image_width'] = float(img.shape[1])
    features['image_height'] = float(img.shape[0])
    features['roi_area_ratio'] = float(np.sum(roi_mask > 0) / (img.shape[0] * img.shape[1]))

    return features


def build_dataset(sample_root):
    """
    从 sample/ 目录构建训练数据集。
    期望结构：
        sample/原始图片/NG/*.bmp
        sample/原始图片/Ok/*.bmp
        sample/2/原始图片/NG/*.bmp
        sample/2/原始图片/Ok/*.bmp
    返回值：X (np.ndarray), y (np.ndarray), feature_names, file_paths
    """
    X_list = []
    y_list = []
    paths = []

    candidates = [
        (os.path.join(sample_root, '原始图片/NG'), 1),
        (os.path.join(sample_root, '原始图片/Ok'), 0),
        (os.path.join(sample_root, '2/原始图片/NG'), 1),
        (os.path.join(sample_root, '2/原始图片/Ok'), 0),
    ]

    for folder, label in candidates:
        if not os.path.exists(folder):
            print(f'Warning: folder not found {folder}')
            continue
        files = glob.glob(os.path.join(folder, '*.bmp'))
        print(f'Loading {len(files)} images from {folder} -> label={label}')
        for f in files:
            feats = extract_features(f)
            if feats is not None:
                X_list.append(feats)
                y_list.append(label)
                paths.append(f)

    if not X_list:
        raise RuntimeError('No valid samples found')

    # 统一特征顺序
    feature_names = sorted(X_list[0].keys())
    X = np.array([[feat[k] for k in feature_names] for feat in X_list], dtype=np.float32)
    y = np.array(y_list, dtype=np.int32)

    print(f'\nTotal samples: {len(y)}, NG={sum(y)}, Ok={len(y)-sum(y)}')
    return X, y, feature_names, paths


def main():
    parser = argparse.ArgumentParser(description='Train ultrasonic defect detection model')
    parser.add_argument('--sample-root', default='sample', help='sample directory root')
    parser.add_argument('--output-dir', default='models', help='directory to save model')
    parser.add_argument('--model-type', default='rf', choices=['rf', 'gbdt'], help='model type')
    parser.add_argument('--test-size', type=float, default=0.2, help='test set ratio')
    args = parser.parse_args()

    # 构建数据集
    X, y, feature_names, paths = build_dataset(args.sample_root)

    # 数据集划分（按标签分层）
    X_train, X_test, y_train, y_test, paths_train, paths_test = train_test_split(
        X, y, paths, test_size=args.test_size, random_state=42, stratify=y
    )

    # 特征缩放
    scaler = StandardScaler()
    X_train_s = scaler.fit_transform(X_train)
    X_test_s = scaler.transform(X_test)

    # 训练模型
    if args.model_type == 'rf':
        model = RandomForestClassifier(
            n_estimators=200,
            max_depth=12,
            min_samples_split=5,
            min_samples_leaf=2,
            class_weight='balanced',
            random_state=42,
            n_jobs=-1
        )
    else:
        model = GradientBoostingClassifier(
            n_estimators=200,
            max_depth=5,
            learning_rate=0.1,
            random_state=42
        )

    print('\nTraining model...')
    model.fit(X_train_s, y_train)

    # 评估
    y_pred = model.predict(X_test_s)
    acc = accuracy_score(y_test, y_pred)
    print(f'\nTest Accuracy: {acc:.4f}')
    print('\nClassification Report:')
    print(classification_report(y_test, y_pred, target_names=['Ok', 'NG']))
    print('Confusion Matrix:')
    print(confusion_matrix(y_test, y_pred))

    # 交叉验证
    print('\n5-fold Cross Validation:')
    cv_scores = cross_val_score(model, X_train_s, y_train, cv=StratifiedKFold(5, shuffle=True, random_state=42))
    print(f'CV Accuracy: {cv_scores.mean():.4f} ± {cv_scores.std():.4f}')

    # 特征重要性
    if hasattr(model, 'feature_importances_'):
        print('\nTop 15 Feature Importances:')
        importances = model.feature_importances_
        idx = np.argsort(importances)[::-1]
        for i in range(min(15, len(feature_names))):
            print(f'  {feature_names[idx[i]]}: {importances[idx[i]]:.4f}')

    # 保存模型
    os.makedirs(args.output_dir, exist_ok=True)
    model_path = os.path.join(args.output_dir, 'ultrasonic_defect_model.pkl')
    scaler_path = os.path.join(args.output_dir, 'ultrasonic_defect_scaler.pkl')
    meta_path = os.path.join(args.output_dir, 'ultrasonic_defect_meta.json')

    joblib.dump(model, model_path)
    joblib.dump(scaler, scaler_path)

    meta = {
        'created_at': datetime.now().isoformat(),
        'feature_names': feature_names,
        'model_type': args.model_type,
        'test_accuracy': float(acc),
        'cv_accuracy_mean': float(cv_scores.mean()),
        'cv_accuracy_std': float(cv_scores.std()),
        'num_samples': len(y),
        'num_ng': int(sum(y)),
        'num_ok': int(len(y) - sum(y)),
        'top_features': [
            {'name': feature_names[idx[i]], 'importance': float(importances[idx[i]])}
            for i in range(min(15, len(feature_names)))
        ]
    }
    with open(meta_path, 'w', encoding='utf-8') as f:
        json.dump(meta, f, indent=2, ensure_ascii=False)

    print(f'\nModel saved: {model_path}')
    print(f'Scaler saved: {scaler_path}')
    print(f'Meta saved:   {meta_path}')


if __name__ == '__main__':
    main()
