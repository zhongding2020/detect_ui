# -*- coding: utf-8 -*-
"""离屏冒烟测试：历史记录右侧面板 + 双击打开详情"""
import os
import sys

os.environ['QT_QPA_PLATFORM'] = 'offscreen'
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from PyQt5.QtWidgets import QApplication
from src.model.DetectionModel import DetectionModel
from src.view.DetectionView import DetectionView
from src.presenter.DetectionPresenter import DetectionPresenter

app = QApplication(sys.argv)

view = DetectionView()
model = DetectionModel()
presenter = DetectionPresenter(view, model)
view.show()  # 模拟真实启动（offscreen）

# 1. 初始状态：面板隐藏
assert not view.is_history_panel_visible(), "面板初始应隐藏"
print("1. 初始面板隐藏 OK")

# 2. view_history：右侧显示面板
presenter.view_history()
assert view.is_history_panel_visible(), "点击后面板应显示"
rows = view.history_panel.table.rowCount()
print(f"2. 查看历史 -> 右侧面板显示, {rows} 条记录 OK")
assert rows > 0, "应有历史记录"

# 3. 表格内容检查（时间列不应为空 — 修复了 timestamp 字段 bug）
time_item = view.history_panel.table.item(0, 2)
assert time_item is not None and time_item.text(), "时间列不应为空"
print(f"3. 时间列修复 OK: '{time_item.text()}'")

# 4. 再次点击 -> 隐藏（toggle）
presenter.view_history()
assert not view.is_history_panel_visible(), "再次点击应隐藏"
presenter.view_history()
assert view.is_history_panel_visible(), "第三次点击应再显示"
print("4. 显示/隐藏切换 OK")

# 5. 双击打开详情
record = model.load_history()[0]
presenter.open_history_record(record)
status_text = view.status_label.text()
defects_text = view.defect_count_label.text()
fname = view.filename_label.text()
print(f"5. 双击打开详情 OK: 状态={status_text}, {defects_text}, 文件={fname}")
assert status_text == record.get('status'), "状态应回填"

# 6. 面板双击信号路径
got = []
view.signal_open_history_record.connect(lambda r: got.append(r))
view.history_panel._on_cell_double_clicked(0, 0)
assert len(got) == 1 and got[0].get('id') is not None, "双击信号应携带记录"
print(f"6. 双击信号路径 OK (record id={got[0]['id']})")

# 7. 缺陷明细回填
record_with = [r for r in model.load_history() if r.get('results')]
if record_with:
    n = len(record_with[0]['results'])
    presenter.open_history_record(record_with[0])
    assert view.defect_count_label.text().endswith(str(n)), "缺陷数量应等于明细数"
    print(f"7. 缺陷明细回填 OK ({n} 个检测框)")
else:
    print("7. (无带明细的历史记录, 跳过)")

print("\n=== 全部测试通过 ===")
