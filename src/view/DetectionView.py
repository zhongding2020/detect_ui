"""检测界面视图"""
import os
import sys
from PyQt5.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, 
                             QHBoxLayout, QPushButton, QLabel, QSlider, 
                             QTableWidget, QTableWidgetItem, QSplitter, 
                             QGroupBox, QFrame, QGridLayout, QScrollArea,
                             QFileDialog, QMessageBox, QComboBox, QDialog)
from PyQt5.QtCore import Qt, QTimer, pyqtSignal
from PyQt5.QtGui import QFont, QColor, QImage, QPixmap

from src.utils.logging_utils import get_logger

logger = get_logger('view.detection')


class DraggableScrollArea(QScrollArea):
    """可拖拽的滚动区域"""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.setWidgetResizable(False)
        self.setFrameStyle(QFrame.NoFrame)
        self.dragging = False
        self.last_pos = None
    
    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.dragging = True
            self.last_pos = event.globalPos()
            self.setCursor(Qt.ClosedHandCursor)
        super().mousePressEvent(event)
    
    def mouseMoveEvent(self, event):
        if self.dragging and self.last_pos:
            delta = event.globalPos() - self.last_pos
            self.horizontalScrollBar().setValue(
                self.horizontalScrollBar().value() - delta.x()
            )
            self.verticalScrollBar().setValue(
                self.verticalScrollBar().value() - delta.y()
            )
            self.last_pos = event.globalPos()
        super().mouseMoveEvent(event)
    
    def mouseReleaseEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.dragging = False
            self.last_pos = None
            self.unsetCursor()
        super().mouseReleaseEvent(event)


class HistoryDialog(QDialog):
    """历史记录对话框"""
    
    def __init__(self, history_data, parent=None):
        super().__init__(parent)
        self.history_data = history_data
        self.selected_record = None
        self.init_ui()
    
    def init_ui(self):
        self.setWindowTitle("检测历史记录")
        self.setGeometry(200, 200, 900, 600)
        
        layout = QVBoxLayout()
        
        # 表格
        self.table = QTableWidget()
        self.table.setColumnCount(5)
        self.table.setHorizontalHeaderLabels(["序号", "文件名", "检测时间", "状态", "缺陷数量"])
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.setStyleSheet("""
            QTableWidget {
                background-color: #ffffff;
                border: 1px solid #ddd;
                color: #333;
            }
            QHeaderView::section {
                background-color: #e8e8e8;
                color: #333;
                padding: 8px;
                font-weight: bold;
            }
            QTableWidget::item {
                border: 1px solid #eee;
                padding: 8px;
            }
        """)
        layout.addWidget(self.table)
        
        # 按钮
        btn_layout = QHBoxLayout()
        self.view_btn = QPushButton("查看详情")
        self.view_btn.clicked.connect(self.view_record)
        self.close_btn = QPushButton("关闭")
        self.close_btn.clicked.connect(self.close)
        
        btn_layout.addStretch()
        btn_layout.addWidget(self.view_btn)
        btn_layout.addWidget(self.close_btn)
        layout.addLayout(btn_layout)
        
        self.setLayout(layout)
        self.populate_table()
    
    def populate_table(self):
        """填充表格数据"""
        self.table.setRowCount(len(self.history_data))
        
        for row, record in enumerate(self.history_data):
            # 序号
            self.table.setItem(row, 0, QTableWidgetItem(str(row + 1)))
            
            # 文件名
            filename = os.path.basename(record.get('image_path', ''))
            self.table.setItem(row, 1, QTableWidgetItem(filename))
            
            # 检测时间
            detect_time = record.get('detect_time', '')
            self.table.setItem(row, 2, QTableWidgetItem(detect_time))
            
            # 状态
            status = record.get('status', 'UNKNOWN')
            status_item = QTableWidgetItem(status)
            if status == 'NG':
                status_item.setBackground(QColor(255, 0, 0))
                status_item.setForeground(QColor(255, 255, 255))
            elif status == 'OK':
                status_item.setBackground(QColor(0, 200, 0))
                status_item.setForeground(QColor(0, 0, 0))
            else:
                status_item.setBackground(QColor(255, 165, 0))
                status_item.setForeground(QColor(0, 0, 0))
            self.table.setItem(row, 3, status_item)
            
            # 缺陷数量
            defect_count = record.get('defect_count', 0)
            self.table.setItem(row, 4, QTableWidgetItem(str(defect_count)))
    
    def view_record(self):
        """查看选中记录的详情"""
        selected_items = self.table.selectedItems()
        if not selected_items:
            QMessageBox.warning(self, "提示", "请先选择一条记录！")
            return
        
        row = selected_items[0].row()
        if row < len(self.history_data):
            self.selected_record = self.history_data[row]
            self.accept()


class DetectionView(QMainWindow):
    """检测主界面视图"""
    
    # 信号定义
    signal_start_detection = pyqtSignal()
    signal_stop_detection = pyqtSignal()
    signal_select_plugin = pyqtSignal(str)
    signal_select_image = pyqtSignal()
    signal_select_directory = pyqtSignal()
    signal_start_monitoring = pyqtSignal()
    signal_stop_monitoring = pyqtSignal()
    signal_view_history = pyqtSignal()
    
    def __init__(self):
        super().__init__()
        self.current_zoom = 1.0
        self._current_pixmap = None
        self.init_ui()
    
    def init_ui(self):
        self.setWindowTitle("超声缺陷检测系统")
        self.setGeometry(100, 100, 1400, 900)
        
        # 设置窗口图标
        self.set_window_icon()
        
        # 设置窗口可以最大化
        self.setWindowFlags(self.windowFlags() | Qt.WindowMaximizeButtonHint | Qt.WindowMinimizeButtonHint)
        
        # 设置最小尺寸，确保窗口不会太小
        self.setMinimumSize(1200, 700)
        
        # 设置全局样式
        self.setStyleSheet("""
            QMainWindow {
                background-color: #2b2b2b;
            }
            QPushButton {
                background-color: #4a4a4a;
                color: #ffffff;
                border: none;
                padding: 12px 20px;
                border-radius: 5px;
                font-size: 16px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #5a5a5a;
            }
            QGroupBox {
                color: #ffffff;
                font-weight: bold;
                border: 1px solid #555;
                border-radius: 5px;
                margin-top: 10px;
                padding-top: 10px;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 10px;
                padding: 0 5px;
            }
            QTableWidget {
                background-color: #3a3a3a;
                color: #ffffff;
                gridline-color: #555;
                border: none;
            }
            QTableWidget::item {
                padding: 5px;
            }
            QHeaderView::section {
                background-color: #4a4a4a;
                color: #ffffff;
                padding: 5px;
                border: 1px solid #555;
            }
            QComboBox {
                background-color: #4a4a4a;
                color: #ffffff;
                border: 1px solid #555;
                padding: 5px;
                border-radius: 3px;
            }
            QComboBox::drop-down {
                background-color: #4a4a4a;
                border: none;
            }
            QComboBox QAbstractItemView {
                background-color: #3a3a3a;
                color: #ffffff;
                border: 1px solid #555;
            }
            QSlider::groove:horizontal {
                height: 8px;
                background-color: #4a4a4a;
                border-radius: 4px;
            }
            QSlider::handle:horizontal {
                background-color: #6a8a6a;
                width: 16px;
                margin: -4px 0;
                border-radius: 8px;
            }
            QLabel {
                color: #ffffff;
            }
            QTextEdit {
                background-color: #3a3a3a;
                color: #ffffff;
                border: 1px solid #555;
                border-radius: 3px;
            }
        """)
        
        # 主布局
        main_widget = QWidget()
        self.setCentralWidget(main_widget)
        
        main_layout = QHBoxLayout(main_widget)
        main_layout.setContentsMargins(5, 5, 5, 5)
        main_layout.setSpacing(5)
        
        # 水平布局
        splitter = QSplitter(Qt.Horizontal)
        
        left_panel = self.create_left_panel()
        center_panel = self.create_center_panel()
        
        splitter.addWidget(left_panel)
        splitter.addWidget(center_panel)
        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 5)
        
        main_layout.addWidget(splitter)
    
    def set_window_icon(self):
        """设置窗口图标"""
        icon_path = os.path.join(os.path.dirname(__file__), '..', '..', 'icon.ico')
        if os.path.exists(icon_path):
            self.setWindowIcon(QIcon(icon_path))
        else:
            # 创建默认图标
            from PyQt5.QtGui import QIcon, QPainter
            pixmap = QPixmap(64, 64)
            pixmap.fill(QColor(74, 106, 74))
            painter = QPainter(pixmap)
            painter.setPen(QColor(255, 255, 255))
            painter.drawLine(32, 10, 32, 54)
            painter.drawLine(10, 32, 54, 32)
            painter.drawEllipse(28, 28, 8, 8)
            painter.end()
            self.setWindowIcon(QIcon(pixmap))
    
    def create_left_panel(self):
        """创建左侧控制面板"""
        panel = QGroupBox()
        layout = QVBoxLayout(panel)
        
        # 标题
        title_label = QLabel("超声缺陷检测系统")
        title_label.setStyleSheet("color: #ffffff; font-size: 18px; font-weight: bold; padding: 10px 0;")
        layout.addWidget(title_label)
        
        # 插件选择
        plugin_label = QLabel("选择检测插件:")
        plugin_label.setStyleSheet("color: #aaaaaa; font-size: 12px; padding: 5px 0;")
        layout.addWidget(plugin_label)
        
        self.plugin_combo = QComboBox()
        self.plugin_combo.setMinimumHeight(35)
        self.plugin_combo.addItem("未选择插件")
        self.plugin_combo.currentTextChanged.connect(self.signal_select_plugin.emit)
        layout.addWidget(self.plugin_combo)
        
        # 分隔线
        separator_plugin = QLabel("━━━━━━━━━━━━━━")
        separator_plugin.setStyleSheet("color: #666666; padding: 5px 0;")
        layout.addWidget(separator_plugin)
        
        # 图片选择按钮
        self.image_btn = QPushButton("📷 图片选择")
        self.image_btn.clicked.connect(self.signal_select_image.emit)
        layout.addWidget(self.image_btn)
        
        # 文件夹选择按钮
        self.folder_btn = QPushButton("📁 文件夹选择")
        self.folder_btn.clicked.connect(self.signal_select_directory.emit)
        layout.addWidget(self.folder_btn)
        
        # 检测按钮区域
        detect_btn_layout = QHBoxLayout()
        
        # 立即检测按钮
        self.start_btn = QPushButton("⚡ 立即检测")
        self.start_btn.setStyleSheet("background-color: #4a6a4a; font-weight: bold;")
        self.start_btn.clicked.connect(self.signal_start_detection.emit)
        detect_btn_layout.addWidget(self.start_btn)
        
        # 停止检测按钮
        self.stop_btn = QPushButton("⏹️ 停止检测")
        self.stop_btn.setStyleSheet("background-color: #6a4a4a; font-weight: bold;")
        self.stop_btn.clicked.connect(self.signal_stop_detection.emit)
        self.stop_btn.setEnabled(False)
        detect_btn_layout.addWidget(self.stop_btn)
        
        layout.addLayout(detect_btn_layout)
        
        # 文件夹监听区域
        monitor_separator = QLabel("━━━━━━━━━━━━━━")
        monitor_separator.setStyleSheet("color: #666666; padding: 5px 0;")
        layout.addWidget(monitor_separator)
        
        # 监听状态标签
        self.monitor_status_label = QLabel("监听: 未启动")
        self.monitor_status_label.setStyleSheet("color: #aaaaaa; font-size: 12px; padding: 5px;")
        self.monitor_status_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(self.monitor_status_label)
        
        # 启动监听按钮
        self.start_monitor_btn = QPushButton("▶️ 启动监听")
        self.start_monitor_btn.clicked.connect(self.signal_start_monitoring.emit)
        self.start_monitor_btn.setEnabled(False)
        self.start_monitor_btn.setStyleSheet("background-color: #4a6a4a;")
        layout.addWidget(self.start_monitor_btn)
        
        # 停止监听按钮
        self.stop_monitor_btn = QPushButton("⏹️ 停止监听")
        self.stop_monitor_btn.clicked.connect(self.signal_stop_monitoring.emit)
        self.stop_monitor_btn.setEnabled(False)
        self.stop_monitor_btn.setStyleSheet("background-color: #6a4a4a;")
        layout.addWidget(self.stop_monitor_btn)
        
        # 分隔线
        separator = QLabel("━━━━━━━━━━━━━━")
        separator.setStyleSheet("color: #666666; padding: 5px 0;")
        layout.addWidget(separator)
        
        # 查看历史按钮
        self.view_history_btn = QPushButton("📋 查看历史")
        self.view_history_btn.setStyleSheet("background-color: #4a4a6a; font-weight: bold;")
        self.view_history_btn.clicked.connect(self.signal_view_history.emit)
        layout.addWidget(self.view_history_btn)
        
        layout.addStretch()
        
        return panel
    
    def create_center_panel(self):
        """创建中央显示面板"""
        panel = QWidget()
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(0, 0, 0, 0)
        
        top_bar = self.create_top_bar()
        layout.addWidget(top_bar)
        
        display_area = self.create_display_area()
        layout.addWidget(display_area, stretch=1)
        
        return panel
    
    def create_top_bar(self):
        """创建顶部工具栏"""
        bar = QGroupBox()
        bar.setStyleSheet("background-color: #3a3a3a;")
        layout = QVBoxLayout(bar)
        
        slider_layout = QHBoxLayout()
        
        # 置信度设置
        conf_layout = QHBoxLayout()
        self.conf_label = QLabel("置信度 (Conf): 0.5")
        self.conf_label.setStyleSheet("color: #ffffff;")
        self.conf_slider = QSlider(Qt.Horizontal)
        self.conf_slider.setRange(0, 100)
        self.conf_slider.setValue(50)
        self.conf_slider.valueChanged.connect(self.on_conf_changed)
        conf_layout.addWidget(self.conf_label)
        conf_layout.addWidget(self.conf_slider)
        
        # IoU设置
        iou_layout = QHBoxLayout()
        self.iou_label = QLabel("交并比 (IoU): 0.5")
        self.iou_label.setStyleSheet("color: #ffffff;")
        self.iou_slider = QSlider(Qt.Horizontal)
        self.iou_slider.setRange(0, 100)
        self.iou_slider.setValue(50)
        self.iou_slider.valueChanged.connect(self.on_iou_changed)
        iou_layout.addWidget(self.iou_label)
        iou_layout.addWidget(self.iou_slider)
        
        slider_layout.addLayout(conf_layout)
        slider_layout.addLayout(iou_layout)
        
        status_layout = QHBoxLayout()
        
        self.time_label = QLabel("⏱️ 检测耗时: 0.00s")
        self.time_label.setStyleSheet("color: #ffffff; background-color: #2a4a6a; padding: 5px 10px; border-radius: 3px;")
        
        self.target_label = QLabel("🎯 检测目标: 0个")
        self.target_label.setStyleSheet("color: #ffffff; background-color: #6a2a2a; padding: 5px 10px; border-radius: 3px;")
        
        status_layout.addWidget(self.time_label)
        status_layout.addStretch()
        status_layout.addWidget(self.target_label)
        
        layout.addLayout(slider_layout)
        layout.addLayout(status_layout)
        
        return bar
    
    def on_conf_changed(self, value):
        """置信度滑块变化"""
        self.conf_label.setText(f"置信度 (Conf): {value / 100:.2f}")
    
    def on_iou_changed(self, value):
        """IoU滑块变化"""
        self.iou_label.setText(f"交并比 (IoU): {value / 100:.2f}")
    
    def create_display_area(self):
        """创建图片显示区域"""
        area = QFrame()
        area.setStyleSheet("background-color: #1a1a2e; border: 2px solid #444; border-radius: 5px;")
        layout = QVBoxLayout(area)
        
        # 顶部状态栏
        status_bar = QHBoxLayout()
        
        # OK/NG 状态标签 - 醒目显示
        self.status_label = QLabel("待检测")
        self.status_label.setAlignment(Qt.AlignCenter)
        self.status_label.setFont(QFont("Arial", 32, QFont.Bold))
        self.status_label.setStyleSheet("""
            QLabel {
                color: #888888;
                background-color: #2a2a2a;
                border: 3px solid #555555;
                border-radius: 10px;
                padding: 15px 40px;
                min-width: 120px;
            }
        """)
        
        # 缺陷数量标签
        self.defect_count_label = QLabel("缺陷数量: 0")
        self.defect_count_label.setAlignment(Qt.AlignCenter)
        self.defect_count_label.setFont(QFont("Arial", 16, QFont.Bold))
        self.defect_count_label.setStyleSheet("color: #ffffff; padding: 5px;")
        
        # 图片文件名标签
        self.filename_label = QLabel("未选择图片")
        self.filename_label.setAlignment(Qt.AlignCenter)
        self.filename_label.setFont(QFont("Arial", 12))
        self.filename_label.setStyleSheet("color: #aaaaaa; padding: 5px;")
        
        status_bar.addWidget(self.status_label)
        status_bar.addWidget(self.defect_count_label)
        status_bar.addStretch()
        status_bar.addWidget(self.filename_label)
        
        layout.addLayout(status_bar)
        
        # 图片显示区域 - 使用可拖拽的滚动区域
        self.scroll_area = DraggableScrollArea()
        self.scroll_area.setWidgetResizable(False)
        self.scroll_area.setStyleSheet("""
            QScrollArea {
                background-color: #0a0a15;
                border: 2px solid #333;
                border-radius: 5px;
            }
        """)
        
        self.image_label = QLabel()
        self.image_label.setAlignment(Qt.AlignCenter)
        self.image_label.setMinimumSize(640, 480)
        self.image_label.setFixedSize(640, 480)
        self.image_label.setStyleSheet("""
            QLabel {
                background-color: #0a0a15;
                color: #666666;
            }
        """)
        self.image_label.setText("请选择图片并开始检测\n结果将显示在这里")
        self.image_label.setScaledContents(False)
        
        self.scroll_area.setWidget(self.image_label)
        
        # 放大控制按钮
        zoom_layout = QHBoxLayout()
        self.zoom_in_btn = QPushButton("🔍 放大")
        self.zoom_in_btn.setStyleSheet("background-color: #4a4a6a; font-weight: bold;")
        self.zoom_in_btn.clicked.connect(self.zoom_in)
        zoom_layout.addWidget(self.zoom_in_btn)
        
        self.zoom_out_btn = QPushButton("🔍 缩小")
        self.zoom_out_btn.setStyleSheet("background-color: #4a4a6a; font-weight: bold;")
        self.zoom_out_btn.clicked.connect(self.zoom_out)
        zoom_layout.addWidget(self.zoom_out_btn)
        
        self.reset_zoom_btn = QPushButton("🔍 重置")
        self.reset_zoom_btn.setStyleSheet("background-color: #4a4a6a; font-weight: bold;")
        self.reset_zoom_btn.clicked.connect(self.reset_zoom)
        zoom_layout.addWidget(self.reset_zoom_btn)
        
        zoom_layout.addStretch()
        
        # 缩放比例显示
        self.zoom_label = QLabel("缩放: 100%")
        self.zoom_label.setStyleSheet("color: #ffffff;")
        zoom_layout.addWidget(self.zoom_label)
        
        layout.addWidget(self.scroll_area, stretch=1)
        layout.addLayout(zoom_layout)
        
        # 缩放相关变量
        self.current_zoom = 1.0
        self.min_zoom = 0.1
        self.max_zoom = 4.0
        self.zoom_step = 0.1
        
        return area
    
    def show_initial_image(self):
        """显示初始提示图片"""
        pixmap = QPixmap(800, 600)
        pixmap.fill(QColor(26, 26, 46))  # 与背景色一致
        
        from PyQt5.QtGui import QPainter
        painter = QPainter(pixmap)
        painter.setPen(QColor(100, 100, 100))
        painter.setFont(QFont("Arial", 14))
        painter.drawText(pixmap.rect(), Qt.AlignCenter, "请选择图片或启动监听")
        painter.end()
        
        self._current_pixmap = pixmap
        self.image_label.setPixmap(pixmap)
        self.image_label.setFixedSize(800, 600)
    
    # 缩放方法
    def zoom_in(self):
        """放大图片"""
        if self.current_zoom < self.max_zoom:
            self.current_zoom += self.zoom_step
            self.update_zoom_display()
    
    def zoom_out(self):
        """缩小图片"""
        if self.current_zoom > self.min_zoom:
            self.current_zoom -= self.zoom_step
            self.update_zoom_display()
    
    def reset_zoom(self):
        """重置缩放比例"""
        self.current_zoom = 1.0
        self.update_zoom_display()
    
    def update_zoom_display(self):
        """更新缩放显示"""
        zoom_percent = int(self.current_zoom * 100)
        self.zoom_label.setText(f"缩放: {zoom_percent}%")
        
        # 更新图片显示
        if hasattr(self, '_current_pixmap') and self._current_pixmap is not None:
            # 将浮点数转换为整数
            new_width = int(self._current_pixmap.width() * self.current_zoom)
            new_height = int(self._current_pixmap.height() * self.current_zoom)
            
            scaled_pixmap = self._current_pixmap.scaled(
                new_width,
                new_height,
                Qt.KeepAspectRatio,
                Qt.SmoothTransformation
            )
            
            # 更新图片标签大小以支持拖拽滚动
            self.image_label.setFixedSize(new_width, new_height)
            self.image_label.setPixmap(scaled_pixmap)
    
    def display_image(self, image_array):
        """显示图片"""
        import cv2
        
        # 转换颜色空间
        img_rgb = cv2.cvtColor(image_array, cv2.COLOR_BGR2RGB)
        
        # 创建 QImage
        h, w, ch = img_rgb.shape
        bytes_per_line = ch * w
        q_image = QImage(img_rgb.data, w, h, bytes_per_line, QImage.Format_RGB888)
        
        # 设置 pixmap
        self._current_pixmap = QPixmap.fromImage(q_image)
        self.current_zoom = 1.0
        self.update_zoom_display()
    
    def display_text(self, text):
        """显示文本信息"""
        self.image_label.setText(text)
        self.image_label.setStyleSheet("color: #FF8800; font-size: 14px; background-color: #1a1a1a;")
    
    def update_log(self, text):
        """更新日志显示"""
        # 在原文件中日志显示在状态栏，这里简化处理
        print(f"[LOG] {text}")
    
    def update_status(self, status, stats=None):
        """更新状态显示"""
        # 原文件中的状态显示在状态栏，这里简化处理
        logger.info(f"Status: {status}")
    
    def update_plugin_list(self, plugins):
        """更新插件列表"""
        self.plugin_combo.clear()
        self.plugin_combo.addItems(plugins)
    
    def update_directory(self, directory):
        """更新目录显示"""
        if directory:
            self.monitor_status_label.setText(f"监听: {os.path.basename(directory)}")
        else:
            self.monitor_status_label.setText("监听: 未启动")
    
    def update_result(self, result):
        """更新检测结果显示"""
        if result:
            status = result.get('result_status', 'UNKNOWN')
            detections = result.get('detections', [])
            defect_count = len(detections)
            
            # 更新状态标签
            self.status_label.setText(status)
            
            # 根据状态设置颜色
            if status == 'OK':
                self.status_label.setStyleSheet("""
                    QLabel {
                        color: #00ff00;
                        background-color: #1a3a1a;
                        border: 3px solid #00aa00;
                        border-radius: 10px;
                        padding: 15px 40px;
                        min-width: 120px;
                    }
                """)
            elif status == 'NG':
                self.status_label.setStyleSheet("""
                    QLabel {
                        color: #ff0000;
                        background-color: #3a1a1a;
                        border: 3px solid #aa0000;
                        border-radius: 10px;
                        padding: 15px 40px;
                        min-width: 120px;
                    }
                """)
            elif status == 'ERROR':
                self.status_label.setStyleSheet("""
                    QLabel {
                        color: #ff8800;
                        background-color: #3a2a1a;
                        border: 3px solid #aa6600;
                        border-radius: 10px;
                        padding: 15px 40px;
                        min-width: 120px;
                    }
                """)
            else:
                self.status_label.setStyleSheet("""
                    QLabel {
                        color: #888888;
                        background-color: #2a2a2a;
                        border: 3px solid #555555;
                        border-radius: 10px;
                        padding: 15px 40px;
                        min-width: 120px;
                    }
                """)
            
            # 更新缺陷数量
            self.defect_count_label.setText(f"缺陷数量: {defect_count}")
            
            # 更新检测目标数量
            self.target_label.setText(f"🎯 检测目标: {defect_count}个")
            
            logger.info(f"检测结果: {status}, 缺陷数量: {defect_count}")
        else:
            logger.info("检测失败")
    
    def show_message(self, title, message, type='info'):
        """显示消息对话框"""
        if type == 'error':
            QMessageBox.critical(self, title, message)
        elif type == 'warning':
            QMessageBox.warning(self, title, message)
        else:
            QMessageBox.information(self, title, message)
    
    def show_history_dialog(self, history_data):
        """显示历史记录对话框"""
        dialog = HistoryDialog(history_data, self)
        if dialog.exec_() == QDialog.Accepted and dialog.selected_record:
            return dialog.selected_record
        return None
    
    def get_directory(self):
        """选择目录对话框"""
        directory = QFileDialog.getExistingDirectory(self, "选择监控目录")
        return directory
    
    def get_image_file(self):
        """选择图片文件对话框（支持多选）"""
        files, _ = QFileDialog.getOpenFileNames(
            self, "选择图片文件", "", "图片文件 (*.jpg *.jpeg *.png *.bmp *.tiff *.webp);;所有文件 (*.*)"
        )
        return files
    
    def set_detecting_state(self, detecting):
        """设置检测状态（启用/禁用按钮）"""
        self.start_btn.setEnabled(not detecting)
        self.stop_btn.setEnabled(detecting)
    
    def set_monitoring_state(self, monitoring):
        """设置监听状态"""
        self.start_monitor_btn.setEnabled(not monitoring)
        self.stop_monitor_btn.setEnabled(monitoring)
        if monitoring:
            self.monitor_status_label.setStyleSheet("color: #4CAF50; font-size: 12px; padding: 5px;")
        else:
            self.monitor_status_label.setStyleSheet("color: #aaaaaa; font-size: 12px; padding: 5px;")
