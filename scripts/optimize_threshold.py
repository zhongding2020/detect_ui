"""阈值优化分析：寻找最佳 ML 阈值和混合策略"""
import sys, os, glob, numpy as np
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

def collect_predictions():
    """收集所有样本的 ML 预测和规则指标"""
    from plugins.detectors.ultrasonic_defect_detector import UltrasonicDefectDetector
    
    detector = UltrasonicDefectDetector()
    detector.breach_enabled = False
    detector.normalize_position = False
    
    sample_root = 'sample'
    folders = [
        (os.path.join(sample_root, '原始图片', 'NG'), 1),
        (os.path.join(sample_root, '原始图片', 'Ok'), 0),
        (os.path.join(sample_root, '2', '原始图片', 'NG'), 1),
        (os.path.join(sample_root, '2', '原始图片', 'Ok'), 0),
    ]
    
    results = []
    for folder, label in folders:
        if not os.path.exists(folder):
            continue
        for f in sorted(glob.glob(os.path.join(folder, '*.bmp'))):
            try:
                result = detector.detect(f)
                ml_prob = result.get('ng_probability', 0.0)
                metrics = result.get('metrics', {})
                results.append({
                    'file': os.path.basename(f),
                    'label': label,
                    'ml_prob': ml_prob,
                    'defect_ratio': metrics.get('defect_ratio', 0),
                    'breach_count': metrics.get('breach_count', 0),
                    'max_width': metrics.get('max_defect_width', 0),
                    'total_defects': metrics.get('total_defects', 0),
                })
            except Exception as e:
                print(f"Error: {f}: {e}")
    return results


def evaluate_threshold(results, threshold):
    """评估给定阈值下的准确率"""
    tp = fp = tn = fn = 0
    for r in results:
        pred = 1 if r['ml_prob'] >= threshold else 0
        if pred == 1 and r['label'] == 1: tp += 1
        elif pred == 1 and r['label'] == 0: fp += 1
        elif pred == 0 and r['label'] == 0: tn += 1
        else: fn += 1
    acc = (tp + tn) / max(len(results), 1)
    ng_recall = tp / max(tp + fn, 1)
    ok_recall = tn / max(tn + fp, 1)
    precision = tp / max(tp + fp, 1)
    f1 = 2 * precision * ng_recall / max(precision + ng_recall, 1e-6)
    return acc, ng_recall, ok_recall, precision, f1, tp, fp, tn, fn


def evaluate_hybrid(results, ml_threshold, ratio_threshold, breach_threshold, ml_low, ml_high):
    """
    混合策略:
    - ml_prob >= ml_threshold → NG
    - ml_prob < ml_threshold 但 ratio >= ratio_threshold AND breach >= breach_threshold 
      AND ml_prob >= ml_low → NG (规则 override)
    - ml_prob in [ml_high, ml_threshold) AND ratio == 0 AND breach == 0 → OK (反 override)
    - else → OK
    """
    tp = fp = tn = fn = 0
    for r in results:
        ml = r['ml_prob']
        ratio = r['defect_ratio']
        breach = r['breach_count']
        
        if ml >= ml_threshold:
            pred = 1
        elif ml >= ml_low and ratio >= ratio_threshold and breach >= breach_threshold:
            pred = 1  # 规则 override
        elif ml >= ml_high and ratio == 0 and breach == 0:
            pred = 0  # 反 override
        else:
            pred = 0
        
        if pred == 1 and r['label'] == 1: tp += 1
        elif pred == 1 and r['label'] == 0: fp += 1
        elif pred == 0 and r['label'] == 0: tn += 1
        else: fn += 1
    
    acc = (tp + tn) / max(len(results), 1)
    ng_recall = tp / max(tp + fn, 1)
    ok_recall = tn / max(tn + fp, 1)
    precision = tp / max(tp + fp, 1)
    f1 = 2 * precision * ng_recall / max(precision + ng_recall, 1e-6)
    return acc, ng_recall, ok_recall, precision, f1, tp, fp, tn, fn


if __name__ == '__main__':
    print("收集预测结果...")
    results = collect_predictions()
    ng_count = sum(1 for r in results if r['label'] == 1)
    ok_count = sum(1 for r in results if r['label'] == 0)
    print(f"总样本: {len(results)}, NG={ng_count}, Ok={ok_count}")
    print()
    
    # 1. 阈值扫描
    print("=" * 80)
    print("1. ML 阈值扫描")
    print("=" * 80)
    print(f"{'阈值':>8} {'准确率':>8} {'NG召回':>8} {'Ok召回':>8} {'精确率':>8} {'F1':>8} {'FP':>5} {'FN':>5}")
    print("-" * 70)
    best_acc = 0
    best_thresh = 0.5
    for t in np.arange(0.30, 0.65, 0.05):
        acc, nr, okr, prec, f1, tp, fp, tn, fn = evaluate_threshold(results, t)
        print(f"{t:>8.2f} {acc:>8.4f} {nr:>8.4f} {okr:>8.4f} {prec:>8.4f} {f1:>8.4f} {fp:>5} {fn:>5}")
        if acc > best_acc:
            best_acc = acc
            best_thresh = t
    
    print(f"\n最佳阈值: {best_thresh:.2f}, 准确率: {best_acc:.4f}")
    
    # 2. 混合策略搜索
    print()
    print("=" * 80)
    print("2. 混合策略搜索（ML + 规则 override）")
    print("=" * 80)
    print(f"{'ML阈值':>7} {'ratio':>7} {'breach':>7} {'ml_low':>7} {'准确率':>8} {'NG召回':>8} {'Ok召回':>8} {'F1':>8} {'FP':>5} {'FN':>5}")
    print("-" * 85)
    
    best_hybrid = (0, None)
    for ml_thresh in [0.45, 0.50, 0.55]:
        for ratio_t in [0.02, 0.03, 0.04, 0.05]:
            for breach_t in [1, 2, 3]:
                for ml_low in [0.15, 0.20, 0.25, 0.30]:
                    acc, nr, okr, prec, f1, tp, fp, tn, fn = evaluate_hybrid(
                        results, ml_thresh, ratio_t, breach_t, ml_low, 0.0)
                    if acc > best_hybrid[0]:
                        best_hybrid = (acc, (ml_thresh, ratio_t, breach_t, ml_low))
                        print(f"{ml_thresh:>7.2f} {ratio_t:>7.2f} {breach_t:>7d} {ml_low:>7.2f} {acc:>8.4f} {nr:>8.4f} {okr:>8.4f} {f1:>8.4f} {fp:>5} {fn:>5}")
    
    print(f"\n最佳混合策略: {best_hybrid[1]}, 准确率: {best_hybrid[0]:.4f}")
    
    # 3. 详细分析最佳混合策略
    if best_hybrid[1]:
        ml_t, r_t, b_t, ml_low = best_hybrid[1]
        acc, nr, okr, prec, f1, tp, fp, tn, fn = evaluate_hybrid(
            results, ml_t, r_t, b_t, ml_low, 0.0)
        print(f"\n最佳混合策略详情:")
        print(f"  ML阈值={ml_t}, ratio>={r_t}, breach>={b_t}, ml_low={ml_low}")
        print(f"  准确率={acc:.4f}, NG召回={nr:.4f}, Ok召回={okr:.4f}, F1={f1:.4f}")
        print(f"  TP={tp}, FP={fp}, TN={tn}, FN={fn}")
        
        # 显示被 override 的样本
        print(f"\n  被 override 为 NG 的样本 (原 ML < {ml_t}):")
        for r in results:
            ml = r['ml_prob']
            if ml < ml_t and ml >= ml_low and r['defect_ratio'] >= r_t and r['breach_count'] >= b_t:
                status = "✓ NG" if r['label'] == 1 else "✗ Ok (误报)"
                print(f"    {r['file']}: ml={ml:.3f} ratio={r['defect_ratio']:.4f} breach={r['breach_count']} → {status}")
