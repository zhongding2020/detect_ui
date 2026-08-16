"""
评估当前检测器的各项指标在 NG/Ok 样本上的区分度。

重点关注:
1. defect_ratio (缺陷占比) 是否有区分度
2. breach_count (打穿数量) 是否有区分度
3. max_defect_width (最大缺陷宽度) 是否有区分度
4. ML 概率是否有区分度
5. 各指标的 ROC AUC
"""
import os
import sys
import glob
import json

import cv2
import numpy as np

# 添加项目根目录到 path
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, project_root)

from plugins.detectors.ultrasonic_defect_detector import UltrasonicDefectDetector


def evaluate():
    detector = UltrasonicDefectDetector()
    detector.breach_enabled = False  # ML 为唯一判定
    detector.normalize_position = False

    sample_root = os.path.join(project_root, 'sample')

    candidates = [
        (os.path.join(sample_root, '原始图片/NG'), 1),
        (os.path.join(sample_root, '原始图片/Ok'), 0),
        (os.path.join(sample_root, '2/原始图片/NG'), 1),
        (os.path.join(sample_root, '2/原始图片/Ok'), 0),
    ]

    results = []
    for folder, label in candidates:
        if not os.path.exists(folder):
            continue
        files = glob.glob(os.path.join(folder, '*.bmp'))
        for f in files:
            result = detector.detect(f)
            if result['result_status'] == 'ERROR':
                print(f"ERROR: {f}: {result.get('error_message', '')}")
                continue
            metrics = result.get('metrics', {})
            results.append({
                'path': os.path.basename(f),
                'label': label,
                'pred': 1 if result['result_status'] == 'NG' else 0,
                'ml_prob': result.get('ng_probability', 0),
                'defect_ratio': metrics.get('defect_ratio', 0),
                'breach_count': metrics.get('breach_count', 0),
                'max_width': metrics.get('max_defect_width', 0),
                'max_width_ratio': metrics.get('max_defect_width_ratio', 0),
                'total_defects': metrics.get('total_defects', 0),
                'total_defect_area': metrics.get('total_defect_area', 0),
            })

    if not results:
        print("No results!")
        return

    # 分析
    labels = np.array([r['label'] for r in results])
    preds = np.array([r['pred'] for r in results])

    ng_results = [r for r in results if r['label'] == 1]
    ok_results = [r for r in results if r['label'] == 0]

    print(f"\n{'='*70}")
    print(f"总样本数: {len(results)}, NG={len(ng_results)}, Ok={len(ok_results)}")
    print(f"当前准确率: {np.mean(preds == labels):.4f}")
    print(f"  NG 召回率: {np.sum((preds==1)&(labels==1))}/{len(ng_results)} = {np.sum((preds==1)&(labels==1))/len(ng_results):.1%}")
    print(f"  Ok 召回率: {np.sum((preds==0)&(labels==0))}/{len(ok_results)} = {np.sum((preds==0)&(labels==0))/len(ok_results):.1%}")

    # 各指标区分度分析
    metrics_to_check = ['ml_prob', 'defect_ratio', 'breach_count', 'max_width',
                         'max_width_ratio', 'total_defects', 'total_defect_area']

    print(f"\n{'='*70}")
    print(f"{'指标':<25} {'NG 均值':>12} {'Ok 均值':>12} {'NG 中位':>12} {'Ok 中位':>12} {'AUC':>8}")
    print('-' * 70)

    for metric_name in metrics_to_check:
        ng_vals = np.array([r[metric_name] for r in ng_results])
        ok_vals = np.array([r[metric_name] for r in ok_results])

        # 计算 AUC (简化版)
        all_vals = np.concatenate([ng_vals, ok_vals])
        all_labels = np.concatenate([np.ones(len(ng_vals)), np.zeros(len(ok_vals))])
        sorted_idx = np.argsort(-all_vals)  # 降序
        sorted_labels = all_labels[sorted_idx]
        tp = np.cumsum(sorted_labels)
        fp = np.cumsum(1 - sorted_labels)
        tpr = tp / max(len(ng_vals), 1)
        fpr = fp / max(len(ok_vals), 1)
        auc_fn = getattr(np, 'trapezoid', getattr(np, 'trapz', None))
        auc = auc_fn(tpr, fpr)

        print(f"{metric_name:<25} {ng_vals.mean():>12.4f} {ok_vals.mean():>12.4f} "
              f"{np.median(ng_vals):>12.4f} {np.median(ok_vals):>12.4f} {auc:>8.4f}")

    # 打印 NG 样本中被判 Ok 的
    print(f"\n{'='*70}")
    print("NG 样本中被判 OK 的 (漏检):")
    for r in ng_results:
        if r['pred'] == 0:
            print(f"  {r['path']}: ml={r['ml_prob']:.3f} ratio={r['defect_ratio']:.4f} "
                  f"breach={r['breach_count']} width={r['max_width']:.0f} defects={r['total_defects']}")

    # 打印 Ok 样本中被判 NG 的
    print(f"\n{'='*70}")
    print("Ok 样本中被判 NG 的 (误报):")
    for r in ok_results:
        if r['pred'] == 1:
            print(f"  {r['path']}: ml={r['ml_prob']:.3f} ratio={r['defect_ratio']:.4f} "
                  f"breach={r['breach_count']} width={r['max_width']:.0f} defects={r['total_defects']}")

    # breach_count 分布
    print(f"\n{'='*70}")
    print("breach_count 分布:")
    for bc in range(5):
        ng_count = sum(1 for r in ng_results if r['breach_count'] == bc)
        ok_count = sum(1 for r in ok_results if r['breach_count'] == bc)
        print(f"  breach={bc}: NG={ng_count}, Ok={ok_count}")
    ng_high = sum(1 for r in ng_results if r['breach_count'] >= 1)
    ok_high = sum(1 for r in ok_results if r['breach_count'] >= 1)
    print(f"  breach>=1: NG={ng_high}/{len(ng_results)}, Ok={ok_high}/{len(ok_results)}")

    # defect_ratio 分布
    print(f"\n{'='*70}")
    print("defect_ratio 分布 (按区间):")
    for lo, hi in [(0, 0.01), (0.01, 0.02), (0.02, 0.05), (0.05, 0.08), (0.08, 0.15), (0.15, 0.30), (0.30, 1.0)]:
        ng_count = sum(1 for r in ng_results if lo <= r['defect_ratio'] < hi)
        ok_count = sum(1 for r in ok_results if lo <= r['defect_ratio'] < hi)
        print(f"  [{lo:.2f}, {hi:.2f}): NG={ng_count}, Ok={ok_count}")


if __name__ == '__main__':
    evaluate()
