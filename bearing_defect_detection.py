import sys
import os

# 设置 Qt 环境变量（修复 Linux 平台插件问题）
if sys.platform.startswith('linux'):
    # 查找 PyQt5 安装路径
    try:
        import PyQt5
        pyqt5_path = os.path.dirname(PyQt5.__file__)
        qt_plugins_path = os.path.join(pyqt5_path, 'Qt5', 'plugins')
        if os.path.exists(qt_plugins_path):
            os.environ['QT_PLUGIN_PATH'] = qt_plugins_path
    except:
        pass
    # 优先使用 xcb 平台（兼容 Wayland）
    os.environ['QT_QPA_PLATFORM'] = 'xcb'

import time
import threading
from PyQt5.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, 
                             QHBoxLayout, QPushButton, QLabel, QSlider, 
                             QTableWidget, QTableWidgetItem, QSplitter, 
                             QGroupBox, QFrame, QGridLayout, QScrollArea,
                             QFileDialog, QMessageBox, QComboBox, QDialog)
from PyQt5.QtCore import Qt, QTimer, QObject, pyqtSignal
from PyQt5.QtGui import QFont

# 导入插件系统
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from plugins.plugin_manager import PluginManager
from database_manager import DatabaseManager

# 尝试导入watchdog，如果没有则降级使用定期扫描
try:
    from watchdog.observers import Observer
    from watchdog.events import FileSystemEventHandler, FileCreatedEvent, FileModifiedEvent
    HAS_WATCHDOG = True

    class NewFileHandler(FileSystemEventHandler):
        """文件系统事件处理器 - 监听新文件创建"""
        
        def __init__(self, callback, supported_extensions):
            super().__init__()
            self.callback = callback
            self.supported_extensions = supported_extensions
            self.processing_files = set()  # 避免重复处理同一文件
        
        def on_created(self, event):
            """文件创建事件"""
            if event.is_directory:
                return
            self._process_event(event)
        
        def on_modified(self, event):
            """文件修改事件 - 有时创建文件会触发modified"""
            if event.is_directory:
                return
            self._process_event(event)
        
        def _process_event(self, event):
            """处理文件事件"""
            filepath = event.src_path
            ext = os.path.splitext(filepath.lower())[1]
            
            if ext in self.supported_extensions:
                # 避免重复处理
                if filepath in self.processing_files:
                    return
                
                self.processing_files.add(filepath)
                
                # 短暂延迟确保文件写入完成
                def delayed_process():
                    time.sleep(0.3)
                    if filepath not in self.processing_files:
                        return
                    self.callback(filepath)
                    # 保持在processing中，避免立即再次触发，会在主程序的processed_files中管理
                
                threading.Thread(target=delayed_process, daemon=True).start()

except ImportError:
    HAS_WATCHDOG = False
    NewFileHandler = None


class DraggableScrollArea(QScrollArea):
    """支持鼠标拖拽滚动的滚动区域"""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMouseTracking(True)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self._dragging = False
        self._last_pos = None
        self._cursor_changed = False
    
    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self._dragging = True
            self._last_pos = event.pos()
            self.setCursor(Qt.ClosedHandCursor)
            self._cursor_changed = True
        super().mousePressEvent(event)
    
    def mouseMoveEvent(self, event):
        if self._dragging and self._last_pos:
            delta = event.pos() - self._last_pos
            self._last_pos = event.pos()
            
            # 移动滚动条
            h_bar = self.horizontalScrollBar()
            v_bar = self.verticalScrollBar()
            h_bar.setValue(h_bar.value() - delta.x())
            v_bar.setValue(v_bar.value() - delta.y())
        super().mouseMoveEvent(event)
    
    def mouseReleaseEvent(self, event):
        if event.button() == Qt.LeftButton:
            self._dragging = False
            self._last_pos = None
            self.setCursor(Qt.ArrowCursor)
            self._cursor_changed = False
        super().mouseReleaseEvent(event)
    
    def leaveEvent(self, event):
        if self._cursor_changed:
            self.setCursor(Qt.ArrowCursor)
            self._cursor_changed = False
        super().leaveEvent(event)


class Worker(QObject):
    """信号处理类，用于在主线程执行UI操作"""
    file_detected = pyqtSignal(str)
    
    def __init__(self):
        super().__init__()


class HistoryDialog(QDialog):
    """历史检测记录对话框"""
    
    def __init__(self, history_data, parent=None):
        super().__init__(parent)
        self.history_data = history_data
        self.selected_record = None
        self.init_ui()
    
    def init_ui(self):
        self.setWindowTitle("📋 历史检测记录")
        self.setMinimumSize(900, 600)
        self.resize(1000, 700)
        
        # 设置样式
        self.setStyleSheet("""
            QDialog {
                background-color: #f5f5f5;
            }
            QTableWidget {
                background-color: #ffffff;
                gridline-color: #ddd;
                border: 1px solid #ccc;
                border-radius: 5px;
            }
            QTableWidget::item {
                padding: 8px;
                border-bottom: 1px solid #eee;
                color: #333;
            }
            QHeaderView::section {
                background-color: #e8e8e8;
                color: #333;
                padding: 10px;
                border: 1px solid #ddd;
                font-weight: bold;
            }
            QPushButton {
                background-color: #4a8c4a;
                color: #ffffff;
                border: none;
                padding: 10px 20px;
                border-radius: 5px;
                font-size: 14px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #5a7a5a;
            }
            QPushButton#closeBtn {
                background-color: #6a4a4a;
            }
            QPushButton#closeBtn:hover {
                background-color: #7a5a5a;
            }
            QLabel {
                color: #ffffff;
                font-size: 14px;
            }
        """)
        
        # 主布局
        layout = QVBoxLayout(self)
        
        # 标题
        title_label = QLabel(f"📋 历史检测记录 (共 {len(self.history_data)} 条)")
        title_label.setStyleSheet("font-size: 18px; font-weight: bold; padding: 10px 0;")
        layout.addWidget(title_label)
        
        # 创建表格
        self.table = QTableWidget()
        self.table.setColumnCount(5)
        self.table.setHorizontalHeaderLabels([
            "序号", "检测时间", "图片文件", "缺陷数量", "状态"
        ])
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        self.table.setSelectionMode(QTableWidget.SingleSelection)
        self.table.verticalHeader().setDefaultSectionSize(45)
        self.table.horizontalHeader().setStretchLastSection(True)
        
        # 填充数据
        self.populate_table()
        
        layout.addWidget(self.table)
        
        # 按钮区域
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()
        
        view_btn = QPushButton("👁️ 查看详情")
        view_btn.clicked.connect(self.view_record)
        btn_layout.addWidget(view_btn)
        
        close_btn = QPushButton("✕ 关闭")
        close_btn.setObjectName("closeBtn")
        close_btn.clicked.connect(self.accept)
        btn_layout.addWidget(close_btn)
        
        layout.addLayout(btn_layout)
    
    def populate_table(self):
        """填充表格数据"""
        self.table.setRowCount(len(self.history_data))
        
        for row, record in enumerate(self.history_data):
            # 序号
            self.table.setItem(row, 0, QTableWidgetItem(str(record['id'])))
            
            # 检测时间
            self.table.setItem(row, 1, QTableWidgetItem(record['timestamp']))
            
            # 图片文件
            self.table.setItem(row, 2, QTableWidgetItem(record['filename']))
            
            # 缺陷数量
            defect_item = QTableWidgetItem(f"{record['defect_count']}个")
            defect_item.setTextAlignment(Qt.AlignCenter)
            self.table.setItem(row, 3, defect_item)
            
            # 状态
            status_item = QTableWidgetItem(record['status'])
            status_item.setTextAlignment(Qt.AlignCenter)
            
            if record['status'] == 'NG':
                status_item.setBackground(Qt.red)
                status_item.setForeground(Qt.white)
            elif record['status'] == 'OK':
                status_item.setBackground(Qt.green)
                status_item.setForeground(Qt.black)
            else:
                status_item.setBackground(Qt.orange)
                status_item.setForeground(Qt.black)
                
            self.table.setItem(row, 4, status_item)
    
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


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("超声缺陷检测系统")
        self.setGeometry(100, 100, 1400, 900)
        
        # 设置窗口图标
        self.set_window_icon()
        
        # 设置窗口可以最大化
        self.setWindowFlags(self.windowFlags() | Qt.WindowMaximizeButtonHint | Qt.WindowMinimizeButtonHint)
        
        # 设置最小尺寸，确保窗口不会太小
        self.setMinimumSize(1200, 700)
        
        # 初始化插件管理器
        self.plugin_manager = PluginManager()
        self.current_plugin = None
        self.selected_images = []
        
        # 历史检测记录
        self.detection_history = []  # 存储每次检测的完整信息
        
        # 初始化数据库管理器
        try:
            self.db_manager = DatabaseManager()
            # 从数据库加载历史记录
            self.detection_history = self.db_manager.load_records()
        except Exception as e:
            print(f"[Database] Error initializing database: {e}")
            self.db_manager = None
        
        # 文件夹监听相关
        self.monitored_folder = None
        self.is_monitoring = False
        self.monitor_thread = None
        self.monitor_stop_event = threading.Event()
        self.processed_files = set()
        # watchdog相关
        self.file_observer = None
        self.file_event_handler = None
        
        # 检测控制相关
        self.is_detecting = False
        self.detect_stop_event = threading.Event()
        
        # 信号处理
        self.worker = Worker()
        self.worker.file_detected.connect(self._process_new_file)
        
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
                border: none;
            }
            QComboBox QAbstractItemView {
                background-color: #3a3a3a;
                color: #ffffff;
                selection-background-color: #5a5a5a;
            }
        """)
        
        self.init_ui()
        self.load_plugins()
    
    def load_plugins(self):
        """加载所有检测插件"""
        try:
            print("Loading plugins...")
            self.plugin_manager.load_all_plugins()
            plugin_count = self.plugin_manager.get_plugin_count()
            print(f"Loaded {plugin_count} plugins")
            
            # 更新插件选择下拉框
            if hasattr(self, 'plugin_combo'):
                self.plugin_combo.clear()
                for plugin_name in self.plugin_manager.list_plugins():
                    self.plugin_combo.addItem(plugin_name)
                
                if plugin_count > 0:
                    self.plugin_combo.setCurrentIndex(0)
                    self.current_plugin = self.plugin_manager.get_plugin(self.plugin_combo.currentText())
                    
        except Exception as e:
            print(f"Error loading plugins: {e}")
            import traceback
            traceback.print_exc()
    
    def init_ui(self):
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
    
    def create_left_panel(self):
        panel = QGroupBox()
        layout = QVBoxLayout(panel)
        
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
        self.plugin_combo.currentIndexChanged.connect(self.on_plugin_changed)
        layout.addWidget(self.plugin_combo)
        
        # 分隔线
        separator_plugin = QLabel("━━━━━━━━━━━━━━")
        separator_plugin.setStyleSheet("color: #666666; padding: 5px 0;")
        layout.addWidget(separator_plugin)
        
        # 图片选择按钮
        self.image_btn = QPushButton("📷 图片选择")
        self.image_btn.clicked.connect(self.select_images)
        layout.addWidget(self.image_btn)
        
        # 文件夹选择按钮
        self.folder_btn = QPushButton("📁 文件夹选择")
        self.folder_btn.clicked.connect(self.select_folder)
        layout.addWidget(self.folder_btn)
        
        # 检测按钮区域
        detect_btn_layout = QHBoxLayout()
        
        # 立即检测按钮
        self.start_btn = QPushButton("⚡ 立即检测")
        self.start_btn.setStyleSheet("background-color: #4a6a4a; font-weight: bold;")
        self.start_btn.clicked.connect(self.start_detection)
        detect_btn_layout.addWidget(self.start_btn)
        
        # 停止检测按钮
        self.stop_btn = QPushButton("⏹️ 停止检测")
        self.stop_btn.setStyleSheet("background-color: #6a4a4a; font-weight: bold;")
        self.stop_btn.clicked.connect(self.stop_detection)
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
        self.start_monitor_btn.clicked.connect(self.start_monitoring)
        self.start_monitor_btn.setEnabled(False)
        self.start_monitor_btn.setStyleSheet("background-color: #4a6a4a;")
        layout.addWidget(self.start_monitor_btn)
        
        # 停止监听按钮
        self.stop_monitor_btn = QPushButton("⏹️ 停止监听")
        self.stop_monitor_btn.clicked.connect(self.stop_monitoring)
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
        self.view_history_btn.clicked.connect(self.show_history_dialog)
        layout.addWidget(self.view_history_btn)
        
        layout.addStretch()
        
        return panel
    
    def create_center_panel(self):
        panel = QWidget()
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(0, 0, 0, 0)
        
        top_bar = self.create_top_bar()
        layout.addWidget(top_bar)
        
        display_area = self.create_display_area()
        layout.addWidget(display_area, stretch=1)
        
        return panel
    
    def create_top_bar(self):
        bar = QGroupBox()
        bar.setStyleSheet("background-color: #3a3a3a;")
        layout = QVBoxLayout(bar)
        
        slider_layout = QHBoxLayout()
        
        conf_layout = QHBoxLayout()
        conf_label = QLabel("置信度 (Conf): 0.5")
        conf_label.setStyleSheet("color: #ffffff;")
        self.conf_slider = QSlider(Qt.Horizontal)
        self.conf_slider.setRange(0, 100)
        self.conf_slider.setValue(50)
        conf_layout.addWidget(conf_label)
        conf_layout.addWidget(self.conf_slider)
        
        iou_layout = QHBoxLayout()
        iou_label = QLabel("交并比 (IoU): 0.5")
        iou_label.setStyleSheet("color: #ffffff;")
        self.iou_slider = QSlider(Qt.Horizontal)
        self.iou_slider.setRange(0, 100)
        self.iou_slider.setValue(50)
        iou_layout.addWidget(iou_label)
        iou_layout.addWidget(self.iou_slider)
        
        slider_layout.addLayout(conf_layout, stretch=1)
        slider_layout.addLayout(iou_layout, stretch=1)
        
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
    
    def create_display_area(self):
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
        
        layout.addLayout(status_bar)
        layout.addWidget(self.scroll_area, stretch=1)
        layout.addLayout(zoom_layout)
        
        # 缩放相关变量
        self.current_zoom = 1.0
        self.min_zoom = 0.1
        self.max_zoom = 4.0
        self.zoom_step = 0.1
        
        return area
    
    def select_images(self):
        """选择图片文件"""
        files, _ = QFileDialog.getOpenFileNames(
            self,
            "选择图片文件",
            "",
            "图片文件 (*.jpg *.jpeg *.png *.bmp *.tiff *.webp);;所有文件 (*.*)"
        )
        
        if files:
            self.selected_images = files
            print(f"Selected {len(files)} images")
            for file in files:
                print(f"  - {file}")
            return files
        else:
            print("No images selected")
            return []
    
    def select_folder(self):
        """选择文件夹"""
        folder = QFileDialog.getExistingDirectory(
            self,
            "选择文件夹",
            "",
            QFileDialog.ShowDirsOnly | QFileDialog.DontResolveSymlinks
        )
        
        if folder:
            self.selected_folder = folder
            self.monitored_folder = folder
            print(f"Selected folder: {folder}")
            
            # 自动扫描文件夹中的图片
            image_extensions = {'.jpg', '.jpeg', '.png', '.bmp', '.tiff', '.webp'}
            images = []
            
            for root, _, files in os.walk(folder):
                for file in files:
                    if os.path.splitext(file.lower())[1] in image_extensions:
                        images.append(os.path.join(root, file))
            
            if images:
                self.selected_images = images
                # 初始化已处理文件集合
                self.processed_files = set(images)
                print(f"Found {len(images)} images in folder")
            else:
                # 即使没找到图片，也允许监听
                self.selected_images = []
                self.processed_files = set()
                QMessageBox.warning(
                    self, 
                    "未找到图片", 
                    "在所选文件夹中未找到任何支持的图片文件\n\n但仍可以启动监听，检测新增文件"
                )
            
            # 启用监听按钮
            self.start_monitor_btn.setEnabled(True)
            self.update_monitor_status(f"文件夹已选择: {os.path.basename(folder)}")
            
            return folder
        else:
            print("No folder selected")
            return None
    
    def select_model(self):
        """选择模型文件"""
        file, _ = QFileDialog.getOpenFileName(
            self,
            "选择模型文件",
            "",
            "模型文件 (*.pt *.onnx *.pth);;所有文件 (*.*)"
        )
        
        if file:
            self.selected_model = file
            print(f"Selected model: {file}")
            return file
        else:
            print("No model selected")
            return None
    
    def save_results(self):
        """保存检测结果"""
        if not self.selected_images:
            print("❌ 错误：未选择图片")
            return
        
        folder = QFileDialog.getExistingDirectory(
            self,
            "选择保存位置",
            "",
            QFileDialog.ShowDirsOnly | QFileDialog.DontResolveSymlinks
        )
        
        if folder:
            self.save_folder = folder
            print(f"Results will be saved to: {folder}")
        else:
            print("No save location selected")
    
    def start_detection(self):
        """开始检测"""
        # 检查是否有图片
        if not self.selected_images:
            QMessageBox.warning(self, "警告", "请先选择要检测的图片！")
            print("❌ 错误：未选择图片")
            return
        
        # 检查是否选择了插件
        if not self.current_plugin:
            QMessageBox.warning(self, "警告", "请先选择一个检测插件！")
            print("❌ 错误：未选择检测插件")
            return
        
        # 设置检测状态
        self.is_detecting = True
        self.detect_stop_event.clear()
        
        # 更新按钮状态
        self.start_btn.setEnabled(False)
        self.start_btn.setText("⏳ 检测中...")
        self.stop_btn.setEnabled(True)
        
        # 在独立线程中执行检测
        detect_thread = threading.Thread(target=self._run_detection, daemon=True)
        detect_thread.start()
    
    def _run_detection(self):
        """执行检测的实际逻辑（在独立线程中运行）"""
        import time
        import os
        
        print("\n" + "=" * 70)
        print("🚀 超声缺陷检测系统 - 开始检测")
        print("=" * 70)
        
        # 打印插件信息
        plugin_info = self.current_plugin.get_info()
        print(f"\n📋 插件信息:")
        print(f"   插件名称: {plugin_info['name']}")
        print(f"   插件版本: {plugin_info['version']}")
        print(f"   插件作者: {plugin_info['author']}")
        print(f"   插件描述: {plugin_info['description']}")
        
        # 打印图片信息
        print(f"\n📷 待检测图片信息:")
        print(f"   图片总数: {len(self.selected_images)} 张")
        for i, img_path in enumerate(self.selected_images, 1):
            if os.path.exists(img_path):
                file_size = os.path.getsize(img_path) / 1024  # KB
                print(f"   [{i}] {img_path} ({file_size:.2f} KB)")
            else:
                print(f"   [{i}] {img_path} (⚠️ 文件不存在)")
        
        # 重置界面状态
        self.status_label.setText("检测中")
        self.status_label.setStyleSheet("""
            QLabel {
                color: #FFA500;
                background-color: #2a2a2a;
                border: 3px solid #FFA500;
                border-radius: 10px;
                padding: 15px 40px;
                min-width: 120px;
            }
        """)
        self.defect_count_label.setText("缺陷数量: 0")
        
        # 开始计时
        start_time = time.time()
        
        # 用于统计
        total_detections = 0
        row_index = 0
        
        try:
            # 遍历所有图片进行检测
            print(f"\n🔄 开始检测...")
            print("-" * 70)
            
            for idx, image_path in enumerate(self.selected_images, 1):
                # 检查是否需要停止
                if self.detect_stop_event.is_set():
                    print(f"\n⏹️ 检测已停止")
                    break
                
                print(f"\n📸 [{idx}/{len(self.selected_images)}] 处理图片: {image_path}")
                
                # 更新文件名标签
                filename = os.path.basename(image_path)
                self.filename_label.setText(filename)
                
                # 检查文件是否存在
                if not os.path.exists(image_path):
                    print(f"   ❌ 文件不存在，跳过")
                    continue
                
                # 调用插件的检测方法
                print(f"   🔧 调用插件 {self.current_plugin.name} 的 detect() 方法...")
                try:
                    detect_result = self.current_plugin.detect(image_path)
                    results = detect_result.get('detections', [])
                    result_status = detect_result.get('result_status', 'OK')
                    result_image = detect_result.get('result_image', None)
                    error_message = detect_result.get('error_message', '')
                    print(f"   ✅ 插件调用成功，返回 {len(results)} 个检测结果，状态: {result_status}")
                except Exception as e:
                    error_msg = f"插件调用失败: {str(e)}"
                    print(f"   ❌ {error_msg}")
                    import traceback
                    traceback.print_exc()
                    
                    # 弹出错误对话框
                    QMessageBox.critical(self, "检测错误", f"检测过程中发生错误：\n\n{error_msg}\n\n请检查插件配置或尝试其他检测算法。")
                    
                    # 将错误记录添加到历史
                    self.add_to_history(image_path, [], 0, None, status='ERROR', error_message=error_msg)
                    
                    continue
                
                # 显示图片（带标注）并保存
                result_image_path = self.display_image_with_results(image_path, results, result_image, save_result=True)
                
                # 将结果显示到表格
                if results:
                    print(f"   📊 检测到 {len(results)} 个缺陷...")
                    for result_idx, result in enumerate(results):
                        # 坐标位置
                        x1, y1, x2, y2 = result.bbox
                        coord_text = f"({x1}, {y1}, {x2}, {y2})"
                        print(f"      [{result_idx+1}] 类别: {result.class_name}, "
                              f"置信度: {result.confidence:.2%}, "
                              f"坐标: {coord_text}")
                    
                    print(f"   ✅ 检测完成")
                elif error_message:
                    print(f"   ❌ 检测错误: {error_message}")
                else:
                    print(f"   ℹ️ 未检测到缺陷")
                
                # 添加到历史记录（这里我们用单张图片的时间，后续优化）
                single_image_time = 0  # 暂时设为0
                self.add_to_history(image_path, results, single_image_time, result_image_path)
                
                total_detections += len(results)
                
                # 更新界面状态
                self.defect_count_label.setText(f"缺陷数量: {total_detections}")
                
                # 根据当前图片的检测结果更新OK/NG状态
                if result_status == 'NG':
                    self.status_label.setText("NG")
                    self.status_label.setStyleSheet("""
                        QLabel {
                            color: #FF4444;
                            background-color: #2a1a1a;
                            border: 3px solid #FF4444;
                            border-radius: 10px;
                            padding: 15px 40px;
                            min-width: 120px;
                        }
                    """)
                elif result_status == 'ERROR':
                    self.status_label.setText("ERROR")
                    self.status_label.setStyleSheet("""
                        QLabel {
                            color: #FF8800;
                            background-color: #2a2a1a;
                            border: 3px solid #FF8800;
                            border-radius: 10px;
                            padding: 15px 40px;
                            min-width: 120px;
                        }
                    """)
                else:
                    self.status_label.setText("OK")
                    self.status_label.setStyleSheet("""
                        QLabel {
                            color: #00FF00;
                            background-color: #1a2a1a;
                            border: 3px solid #00FF00;
                            border-radius: 10px;
                            padding: 15px 40px;
                            min-width: 120px;
                        }
                    """)
                
                # 处理事件，保持界面响应
                QApplication.processEvents()
                
                print(f"   📈 当前进度: {idx}/{len(self.selected_images)} 张图片, "
                      f"累计缺陷: {total_detections} 个")
            
            print("\n" + "-" * 70)
            
            # 结束计时
            end_time = time.time()
            elapsed_time = end_time - start_time
            
            # 更新界面显示
            print(f"\n📤 更新界面显示...")
            self.update_detection_results(total_detections, elapsed_time)
            print(f"   ✅ 检测耗时已更新: {elapsed_time:.2f}s")
            print(f"   ✅ 检测目标数已更新: {total_detections}个")
            
            print(f"\n" + "=" * 70)
            print(f"✅ 检测完成！")
            print(f"=" * 70)
            print(f"   📊 检测统计:")
            print(f"      • 处理图片数: {len(self.selected_images)}")
            print(f"      • 检测到缺陷: {total_detections} 个")
            print(f"      • 总耗时: {elapsed_time:.2f} 秒")
            print(f"      • 平均每张: {elapsed_time/len(self.selected_images):.2f} 秒")
            print(f"=" * 70 + "\n")
            
        except Exception as e:
            print(f"\n❌ 检测过程中出现严重错误: {str(e)}")
            import traceback
            traceback.print_exc()
            QMessageBox.critical(self, "错误", f"检测过程中出现错误：\n{str(e)}")
        
        finally:
            # 重置检测状态
            self.is_detecting = False
            self.detect_stop_event.clear()
            
            # 重新启用按钮
            self.start_btn.setEnabled(True)
            self.start_btn.setText("⚡ 立即检测")
            self.stop_btn.setEnabled(False)
            print(f"🔄 界面已恢复就绪状态")
    
    def stop_detection(self):
        """停止正在进行的检测"""
        if self.is_detecting:
            print("\n⏹️ 正在停止检测...")
            self.detect_stop_event.set()
            self.status_label.setText("停止中")
            self.status_label.setStyleSheet("""
                QLabel {
                    color: #FF8800;
                    background-color: #2a2a1a;
                    border: 3px solid #FF8800;
                    border-radius: 10px;
                    padding: 15px 40px;
                    min-width: 120px;
                }
            """)
        else:
            print("⚠️ 没有正在进行的检测")
    
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
    
    def display_image_with_results(self, image_path, results, result_image=None, save_result=True):
        """在界面上显示带标注的图片
        
        Args:
            image_path: 原始图片路径
            results: 检测结果列表
            result_image: 插件返回的已标注图片（可选）
            save_result: 是否保存标注后的图片
            
        Returns:
            str: 保存的图片路径，未保存时返回None
        """
        result_image_path = None
        try:
            import cv2
            from PyQt5.QtGui import QImage, QPixmap
            from PyQt5.QtCore import Qt
            
            # 使用插件返回的图片，如果没有则自己读取并绘制
            if result_image is not None:
                img = result_image.copy()
            else:
                # 读取图片
                img = cv2.imread(image_path)
                if img is None:
                    print(f"   ⚠️ 无法读取图片: {image_path}")
                    return None
                
                # 绘制检测框
                for idx, result in enumerate(results):
                    x1, y1, x2, y2 = result.bbox
                    
                    # 根据类别设置颜色
                    colors = {
                        'crack': (0, 0, 255),      # 红色
                        'scratch': (0, 255, 255),   # 黄色
                        'pitting': (255, 0, 0),     # 蓝色
                        'default': (0, 255, 0)       # 绿色
                    }
                    color = colors.get(result.class_name.lower(), colors['default'])
                    
                    # 绘制矩形框
                    cv2.rectangle(img, (x1, y1), (x2, y2), color, 2)
                    
                    # 绘制标签背景
                    label = f"{result.class_name} {result.confidence:.0%}"
                    label_size, _ = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.5, 1)
                    cv2.rectangle(img, (x1, y1 - label_size[1] - 10), 
                                (x1 + label_size[0], y1), color, -1)
                    
                    # 绘制标签文字
                    cv2.putText(img, label, (x1, y1 - 5),
                               cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1)
                    
                    # 绘制序号
                    cv2.circle(img, (x1, y1), 10, color, -1)
                    cv2.putText(img, str(idx + 1), (x1 - 5, y1 + 5),
                               cv2.FONT_HERSHEY_SIMPLEX, 0.4, (255, 255, 255), 1)
            
            # 保存标注图片（如果需要）
            if save_result and hasattr(self, 'db_manager'):
                try:
                    result_image_path = self.db_manager.save_result_image(image_path, img.copy())
                except Exception as e:
                    print(f"   ⚠️ 保存标注图片失败: {str(e)}")
            
            # 调整图片大小以适应显示区域
            max_width = 800
            max_height = 600
            height, width = img.shape[:2]
            
            if width > max_width or height > max_height:
                scale = min(max_width / width, max_height / height)
                img = cv2.resize(img, None, fx=scale, fy=scale)
            
            # 转换颜色空间 BGR -> RGB
            img_rgb = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
            
            # 转换为QImage
            height, width, _ = img_rgb.shape
            bytes_per_line = 3 * width
            q_image = QImage(img_rgb.data, width, height, bytes_per_line, QImage.Format_RGB888)
            
            # 创建原始 pixmap 并保存
            self._current_pixmap = QPixmap.fromImage(q_image)
            self._original_width = width
            self._original_height = height
            
            # 应用当前缩放比例（转换为整数）
            scaled_pixmap = self._current_pixmap.scaled(
                int(width * self.current_zoom),
                int(height * self.current_zoom),
                Qt.KeepAspectRatio,
                Qt.SmoothTransformation
            )
            
            # 设置图片标签大小为缩放后的大小，以支持拖拽滚动
            self.image_label.setFixedSize(
                int(width * self.current_zoom),
                int(height * self.current_zoom)
            )
            
            # 设置图片
            self.image_label.setPixmap(scaled_pixmap)
            self.image_label.setAlignment(Qt.AlignCenter)
            
            # 更新缩放显示
            self.update_zoom_display()
            
        except ImportError:
            print(f"   ⚠️ OpenCV未安装，无法显示标注图片")
            # 如果没有OpenCV，只显示文件名
            filename = os.path.basename(image_path)
            self.image_label.setText(f"处理中: {filename}\n(安装了OpenCV后可以显示标注)")
        except Exception as e:
            print(f"   ⚠️ 显示图片时出错: {str(e)}")
        
        return result_image_path
    
    def update_detection_results(self, total_detections, elapsed_time):
        """更新检测结果到界面"""
        # 更新检测耗时标签
        self.time_label.setText(f"⏱️ 检测耗时: {elapsed_time:.2f}s")
        
        # 更新检测目标标签
        self.target_label.setText(f"🎯 检测目标: {total_detections}个")
    
    def set_window_icon(self):
        """设置窗口图标"""
        try:
            from PyQt5.QtGui import QIcon
            import sys
            
            # 图标文件路径（支持开发模式和打包模式）
            if getattr(sys, 'frozen', False):
                # 打包后的情况：可执行文件所在目录
                app_dir = os.path.dirname(sys.executable)
            else:
                # 开发模式：脚本所在目录
                app_dir = os.path.dirname(os.path.abspath(__file__))
            
            icon_path = os.path.join(app_dir, 'icon.ico')
            
            if os.path.exists(icon_path):
                self.setWindowIcon(QIcon(icon_path))
            else:
                # 创建一个简单的默认图标
                self.create_default_icon()
                
        except Exception as e:
            print(f"[Icon] Error setting window icon: {e}")
    
    def create_default_icon(self):
        """创建一个简单的默认图标"""
        try:
            from PyQt5.QtGui import QIcon, QPixmap, QPainter, QColor
            from PyQt5.QtCore import Qt
            
            # 创建一个 64x64 的图标
            pixmap = QPixmap(64, 64)
            pixmap.fill(QColor(74, 106, 74))  # 绿色背景
            
            # 创建画家
            painter = QPainter(pixmap)
            painter.setPen(QColor(255, 255, 255))
            painter.setBrush(QColor(255, 255, 255))
            
            # 绘制一个简单的检测图标（十字瞄准器样式）
            # 绘制十字线
            painter.drawLine(32, 10, 32, 54)
            painter.drawLine(10, 32, 54, 32)
            
            # 绘制中心圆点
            painter.drawEllipse(28, 28, 8, 8)
            
            # 绘制四个角
            painter.drawLine(16, 16, 24, 24)
            painter.drawLine(40, 16, 48, 24)
            painter.drawLine(16, 48, 24, 40)
            painter.drawLine(48, 48, 40, 40)
            
            painter.end()
            
            self.setWindowIcon(QIcon(pixmap))
            
        except Exception as e:
            print(f"[Icon] Error creating default icon: {e}")
    
    def on_plugin_changed(self, index):
        """插件选择改变时的回调"""
        plugin_name = self.plugin_combo.itemText(index)
        if plugin_name and plugin_name != "未选择插件":
            self.current_plugin = self.plugin_manager.get_plugin(plugin_name)
            if self.current_plugin:
                print(f"Selected plugin: {plugin_name}")
        else:
            self.current_plugin = None
    
    def update_monitor_status(self, status_text, is_active=False):
        """更新监听状态显示"""
        self.monitor_status_label.setText(status_text)
        if is_active:
            self.monitor_status_label.setStyleSheet("color: #00ff00; font-size: 12px; padding: 5px; font-weight: bold;")
        else:
            self.monitor_status_label.setStyleSheet("color: #aaaaaa; font-size: 12px; padding: 5px;")
    
    def start_monitoring(self):
        """启动文件夹监听"""
        if not self.monitored_folder:
            QMessageBox.warning(self, "警告", "请先选择要监听的文件夹")
            return
        
        if not self.current_plugin:
            QMessageBox.warning(self, "警告", "请先选择检测插件")
            return
        
        self.is_monitoring = True
        self.monitor_stop_event.clear()
        
        # 更新UI
        self.start_monitor_btn.setEnabled(False)
        self.stop_monitor_btn.setEnabled(True)
        
        # 显示使用的监听模式
        if HAS_WATCHDOG:
            self.update_monitor_status(f"实时监听中: {os.path.basename(self.monitored_folder)}", is_active=True)
        else:
            self.update_monitor_status(f"扫描监听中: {os.path.basename(self.monitored_folder)}", is_active=True)
        
        # 根据是否有watchdog选择监听方式
        if HAS_WATCHDOG:
            self._start_watchdog_monitoring()
        else:
            self._start_polling_monitoring()
        
        print(f"Started monitoring folder: {self.monitored_folder} (mode: {'watchdog' if HAS_WATCHDOG else 'polling'})")
    
    def _start_watchdog_monitoring(self):
        """使用watchdog进行实时监听"""
        image_extensions = {'.jpg', '.jpeg', '.png', '.bmp', '.tiff', '.webp'}
        
        # 创建事件处理器
        self.file_event_handler = NewFileHandler(
            callback=self._on_new_file_detected,
            supported_extensions=image_extensions
        )
        
        # 创建并启动observer
        self.file_observer = Observer()
        self.file_observer.schedule(self.file_event_handler, self.monitored_folder, recursive=True)
        self.file_observer.start()
        
        print("[Watchdog] File system observer started")
    
    def _start_polling_monitoring(self):
        """使用定期扫描作为降级方案"""
        self.monitor_thread = threading.Thread(target=self._monitor_folder_thread, daemon=True)
        self.monitor_thread.start()
        
        print("[Polling] Polling monitor started")
    
    def _on_new_file_detected(self, filepath):
        """当检测到新文件时的回调"""
        # 检查是否已处理过
        if filepath in self.processed_files:
            print(f"[Watchdog] File already processed, skipping: {filepath}")
            return
        
        print(f"[Watchdog] New file detected: {filepath}")
        
        # 添加到已处理
        self.processed_files.add(filepath)
        
        # 清除processor中的记录（允许下次修改时处理）
        if self.file_event_handler and filepath in self.file_event_handler.processing_files:
            self.file_event_handler.processing_files.remove(filepath)
        
        # 在主线程中处理 - 不使用lambda避免闭包问题
        print(f"[Watchdog] Scheduling processing for: {filepath}")
        self._schedule_process_new_file(filepath)
    
    def _schedule_process_new_file(self, filepath):
        """安排在主线程处理文件（使用信号确保安全）"""
        print(f"[Schedule] Emitting signal for: {filepath}")
        self.worker.file_detected.emit(filepath)
    
    def stop_monitoring(self):
        """停止文件夹监听"""
        if not self.is_monitoring:
            return
        
        self.is_monitoring = False
        self.monitor_stop_event.set()
        
        # 停止watchdog observer
        if HAS_WATCHDOG and self.file_observer:
            self.file_observer.stop()
            self.file_observer.join(timeout=1.0)
            self.file_observer = None
            self.file_event_handler = None
        
        # 停止polling线程
        if self.monitor_thread and self.monitor_thread.is_alive():
            self.monitor_thread.join(timeout=2.0)
        
        # 更新UI
        self.start_monitor_btn.setEnabled(True)
        self.stop_monitor_btn.setEnabled(False)
        self.update_monitor_status(f"监听已停止: {os.path.basename(self.monitored_folder)}")
        
        print(f"Stopped monitoring folder: {self.monitored_folder}")
    
    def _monitor_folder_thread(self):
        """文件夹监听线程"""
        image_extensions = {'.jpg', '.jpeg', '.png', '.bmp', '.tiff', '.webp'}
        scan_interval = 2.0  # 每2秒扫描一次
        
        while not self.monitor_stop_event.is_set():
            try:
                new_files = []
                
                # 扫描文件夹，查找新文件
                for root, _, files in os.walk(self.monitored_folder):
                    for file in files:
                        file_path = os.path.join(root, file)
                        ext = os.path.splitext(file.lower())[1]
                        
                        if ext in image_extensions and file_path not in self.processed_files:
                            # 等待文件写入完成
                            time.sleep(0.5)
                            new_files.append(file_path)
                
                # 处理新文件
                for file_path in new_files:
                    if self.monitor_stop_event.is_set():
                        break
                    
                    print(f"[Monitor] New file detected: {file_path}")
                    
                    # 添加到已处理集合
                    self.processed_files.add(file_path)
                    
                    # 在主线程中处理检测 - 不使用lambda
                    print(f"[Monitor] Scheduling processing for: {file_path}")
                    self._schedule_process_new_file(file_path)
                
                # 等待下次扫描
                self.monitor_stop_event.wait(scan_interval)
                
            except Exception as e:
                print(f"[Monitor] Error in monitoring thread: {e}")
                time.sleep(scan_interval)
    
    def _process_new_file(self, image_path):
        """处理新检测到的文件（在主线程中调用）"""
        try:
            print(f"[Process] Entering _process_new_file for: {image_path}")
            
            if not self.current_plugin:
                print(f"[Process] ERROR: No plugin selected!")
                return
            
            print(f"[Process] Using plugin: {self.current_plugin}")
            print(f"[Process] Processing new file: {image_path}")
            
            # 显示文件名
            filename = os.path.basename(image_path)
            self.filename_label.setText(f"新文件: {filename}")
            
            # 调用插件检测
            try:
                detect_result = self.current_plugin.detect(image_path)
                results = detect_result.get('detections', [])
                result_status = detect_result.get('result_status', 'OK')
                result_image = detect_result.get('result_image', None)
                print(f"[Process] Detected {len(results)} defects in {filename}, status: {result_status}")
            except Exception as e:
                error_msg = f"插件调用失败: {str(e)}"
                print(f"[Process] ❌ {error_msg}")
                import traceback
                traceback.print_exc()
                
                # 弹出错误对话框
                QMessageBox.critical(self, "检测错误", f"检测过程中发生错误：\n\n{error_msg}\n\n请检查插件配置或尝试其他检测算法。")
                
                # 将错误记录添加到历史
                self.add_to_history(image_path, [], 0, None, status='ERROR', error_message=error_msg)
                
                # 更新状态为错误
                self.status_label.setText("ERROR")
                self.status_label.setStyleSheet("""
                    QLabel {
                        color: #FF8800;
                        background-color: #2a2a1a;
                        border: 3px solid #FF8800;
                        border-radius: 10px;
                        padding: 15px 40px;
                        min-width: 120px;
                    }
                """)
                
                print(f"[Process] Finished processing {filename}")
                return
            
            # 显示图片和结果
            result_image_path = self.display_image_with_results(image_path, results, result_image, save_result=True)
            
            # 添加到历史记录
            self.add_to_history(image_path, results, 0, result_image_path)
            
            # 更新状态
            if result_status == 'NG':
                self.status_label.setText("NG")
                self.status_label.setStyleSheet("""
                    QLabel {
                        color: #FF4444;
                        background-color: #2a1a1a;
                        border: 3px solid #FF4444;
                        border-radius: 10px;
                        padding: 15px 40px;
                        min-width: 120px;
                    }
                """)
                defect_count = int(self.defect_count_label.text().split(":")[-1].strip()) + len(results)
                self.defect_count_label.setText(f"缺陷数量: {defect_count}")
            elif result_status == 'ERROR':
                self.status_label.setText("ERROR")
                self.status_label.setStyleSheet("""
                    QLabel {
                        color: #FF8800;
                        background-color: #2a2a1a;
                        border: 3px solid #FF8800;
                        border-radius: 10px;
                        padding: 15px 40px;
                        min-width: 120px;
                    }
                """)
            else:
                self.status_label.setText("OK")
                self.status_label.setStyleSheet("""
                    QLabel {
                        color: #00FF00;
                        background-color: #1a2a1a;
                        border: 3px solid #00FF00;
                        border-radius: 10px;
                        padding: 15px 40px;
                        min-width: 120px;
                    }
                """)
            
            print(f"[Process] Finished processing {filename}")
            
        except Exception as e:
            print(f"[Process] Error in _process_new_file: {e}")
            import traceback
            traceback.print_exc()
    
    def add_to_history(self, image_path, results, elapsed_time, result_image_path=None, status=None, error_message=None):
        """
        添加检测记录到历史
        
        Args:
            image_path: 图片路径
            results: 检测结果列表
            elapsed_time: 检测耗时
            result_image_path: 标注图片路径
            status: 状态（可选，自动推断时为 None）
            error_message: 错误信息（可选）
        """
        from datetime import datetime
        
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        # 确定状态
        if status is not None:
            record_status = status
        else:
            record_status = 'NG' if len(results) > 0 else 'OK'
        
        # 创建历史记录
        history_record = {
            'id': len(self.detection_history) + 1,
            'timestamp': timestamp,
            'image_path': image_path,
            'filename': os.path.basename(image_path),
            'results': results,
            'defect_count': len(results),
            'status': record_status,
            'elapsed_time': elapsed_time,
            'result_image_path': result_image_path,
            'error_message': error_message if error_message else ''
        }
        
        # 添加到历史列表
        self.detection_history.append(history_record)
        
        # 保存到数据库（如果有数据库管理器）
        if hasattr(self, 'db_manager'):
            try:
                record_id = self.db_manager.save_record(
                    timestamp=timestamp,
                    image_path=image_path,
                    filename=os.path.basename(image_path),
                    defect_count=len(results),
                    status=record_status,
                    elapsed_time=elapsed_time,
                    result_image_path=result_image_path,
                    results=results,
                    error_message=error_message
                )
                # 更新历史记录的 ID 为数据库分配的 ID
                history_record['id'] = record_id
            except Exception as e:
                print(f"[Database] Error saving record: {e}")
        
        print(f"[History] Added detection record: {history_record['filename']} - {history_record['status']}")
    
    def clear_history(self):
        """清空历史记录"""
        if not self.detection_history:
            print("[History] No history to clear")
            return
            
        self.detection_history.clear()
        # 清空数据库记录
        if hasattr(self, 'db_manager') and self.db_manager:
            try:
                self.db_manager.clear_all_records()
            except Exception as e:
                print(f"[Database] Error clearing records: {e}")
        print("[History] History cleared")
    
    def show_history_dialog(self):
        """显示历史记录对话框"""
        if not self.detection_history:
            print("[History] No history records")
            return
        
        # 创建并显示对话框
        dialog = HistoryDialog(self.detection_history, self)
        if dialog.exec_() == QDialog.Accepted:
            # 如果用户选择了记录并点击查看详情
            if dialog.selected_record:
                record = dialog.selected_record
                print(f"[History] 从对话框加载记录: {record['filename']}")
                
                # 显示图片和结果
                self.display_image_with_results(record['image_path'], record['results'])
                
                # 更新文件名标签
                self.filename_label.setText(f"[历史] {record['filename']}")
                
                # 更新状态标签
                if record['status'] == 'NG':
                    self.status_label.setText("NG")
                    self.status_label.setStyleSheet("""
                        QLabel {
                            color: #FF4444;
                            background-color: #2a1a1a;
                            border: 3px solid #FF4444;
                            border-radius: 10px;
                            padding: 15px 40px;
                            min-width: 120px;
                        }
                    """)
                    self.defect_count_label.setText(f"缺陷数量: {record['defect_count']}")
                else:
                    self.status_label.setText("OK")
                    self.status_label.setStyleSheet("""
                        QLabel {
                            color: #00FF00;
                            background-color: #1a2a1a;
                            border: 3px solid #00FF00;
                            border-radius: 10px;
                            padding: 15px 40px;
                            min-width: 120px;
                        }
                    """)
                    self.defect_count_label.setText("缺陷数量: 0")
                
                # 更新检测耗时
                self.time_label.setText(f"⏱️ 检测耗时: {record['elapsed_time']:.2f}s")
                self.target_label.setText(f"🎯 检测目标: {record['defect_count']}个")
    
    def closeEvent(self, event):
        """窗口关闭时停止监听"""
        self.stop_monitoring()
        event.accept()


def main():
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
