"""检测业务逻辑控制层"""
import os
import time
import threading

from PyQt5.QtCore import QObject, pyqtSignal

from src.utils.logging_utils import get_logger
from src.model.DetectionModel import DetectionModel
from src.view.DetectionView import DetectionView

logger = get_logger('presenter.detection')


class DetectionPresenter(QObject):
    """检测业务控制器"""
    
    signal_detection_error = pyqtSignal(str, str)  # image_path, error_message
    
    def __init__(self, view: DetectionView, model: DetectionModel):
        super().__init__()
        self.view = view
        self.model = model
        
        # 检测状态
        self.is_detecting = False
        self.is_monitoring = False
        self.detect_stop_event = threading.Event()
        self.monitor_directory = None
        self.selected_images = []
        
        # 统计信息
        self.stats = {'total': 0, 'ng': 0, 'ok': 0}
        
        # 连接信号
        self._connect_signals()
        
        # 初始化
        self._init_plugins()
    
    def _connect_signals(self):
        """连接信号与槽"""
        self.view.signal_start_detection.connect(self.start_detection)
        self.view.signal_stop_detection.connect(self.stop_detection)
        self.view.signal_select_plugin.connect(self.select_plugin)
        self.view.signal_select_image.connect(self.select_image)
        self.view.signal_select_directory.connect(self.select_directory)
        self.view.signal_start_monitoring.connect(self.start_monitoring)
        self.view.signal_stop_monitoring.connect(self.stop_monitoring)
        self.view.signal_view_history.connect(self.view_history)
        
        self.signal_detection_error.connect(self._handle_detection_error)
    
    def _init_plugins(self):
        """初始化插件"""
        plugins = self.model.load_plugins()
        self.view.update_plugin_list(list(plugins.keys()))
        
        # 默认选择第一个插件
        if plugins:
            first_plugin = list(plugins.keys())[0]
            self.model.select_plugin(first_plugin)
    
    def select_plugin(self, plugin_name):
        """选择检测插件"""
        if self.model.select_plugin(plugin_name):
            logger.info(f"Selected plugin: {plugin_name}")
            self.view.update_log(f"✓ 已选择检测算法: {plugin_name}")
        else:
            logger.error(f"Plugin not found: {plugin_name}")
    
    def select_image(self):
        """选择图片进行检测（支持多选）"""
        image_files = self.view.get_image_file()
        if image_files:
            # 更新选中的图片列表
            self.selected_images = image_files
            logger.info(f"Selected {len(image_files)} images")
            
            # 显示第一张图片的文件名
            if image_files:
                self.view.filename_label.setText(os.path.basename(image_files[0]))
            
            # 如果只有一张图片，立即处理
            if len(image_files) == 1:
                self._process_image(image_files[0])
            # 如果有多张图片，等待用户点击开始检测按钮
            else:
                self.view.update_log(f"📷 已选择 {len(image_files)} 张图片")
    
    def select_directory(self):
        """选择监控目录"""
        directory = self.view.get_directory()
        if directory:
            self.monitor_directory = directory
            
            # 自动扫描文件夹中的图片
            image_extensions = {'.jpg', '.jpeg', '.png', '.bmp', '.tiff', '.webp'}
            images = []
            
            for root, _, files in os.walk(directory):
                for file in files:
                    if os.path.splitext(file.lower())[1] in image_extensions:
                        images.append(os.path.join(root, file))
            
            if images:
                self.selected_images = images
                logger.info(f"Found {len(images)} images in folder")
                self.view.update_log(f"📁 监控目录: {directory} (发现 {len(images)} 张图片)")
            else:
                # 即使没找到图片，也允许监听
                self.selected_images = []
                self.view.show_message("提示", "在所选文件夹中未找到任何支持的图片文件\n\n但仍可以启动监听，检测新增文件", 'info')
                self.view.update_log(f"📁 监控目录: {directory} (未发现图片)")
            
            self.view.update_directory(directory)
            self.view.start_monitor_btn.setEnabled(True)
            logger.info(f"Selected monitor directory: {directory}")
    
    def start_detection(self):
        """开始检测"""
        if self.is_detecting:
            return
        
        # 检查是否有选择的图片
        if not self.selected_images and not self.monitor_directory:
            self.view.show_message("错误", "请先选择要检测的图片或监控目录！", 'error')
            return
        
        # 检查是否选择了插件
        if not self.model.current_plugin:
            self.view.show_message("错误", "请先选择一个检测插件！", 'error')
            return
        
        # 更新状态
        self.is_detecting = True
        self.detect_stop_event.clear()
        self.view.set_detecting_state(True)
        
        # 启动检测线程
        detect_thread = threading.Thread(target=self._run_detection, daemon=True)
        detect_thread.start()

    def stop_detection(self):
        """停止检测"""
        self.detect_stop_event.set()
        self.is_detecting = False
        self.view.set_detecting_state(False)
        logger.info("Detection stopped")

    def _run_detection(self):
        """检测线程主循环"""
        logger.info("Starting detection...")
        
        try:
            # 确定要检测的图片列表
            if self.selected_images:
                # 使用已选择的图片
                image_files = self.selected_images
            elif self.monitor_directory:
                # 从监控目录获取图片
                image_extensions = ('.jpg', '.jpeg', '.png', '.bmp', '.tiff', '.webp')
                image_files = []
                
                for filename in os.listdir(self.monitor_directory):
                    if filename.lower().endswith(image_extensions):
                        image_files.append(os.path.join(self.monitor_directory, filename))
                
                # 按修改时间排序
                image_files.sort(key=lambda x: os.path.getmtime(x), reverse=True)
            else:
                logger.error("No images selected and no monitor directory set")
                return
            
            # 处理每个文件
            for idx, image_path in enumerate(image_files, 1):
                # 检查是否需要停止
                if self.detect_stop_event.is_set():
                    logger.info("Detection stopped by user")
                    break
                
                # 更新进度
                self.view.update_log(f"🔍 [{idx}/{len(image_files)}] 检测中: {os.path.basename(image_path)}")
                
                # 执行检测
                self._process_image(image_path)
                
                # 短暂等待
                time.sleep(0.1)
            
        except Exception as e:
            logger.error(f"Detection loop error: {str(e)}")
            self.signal_detection_error.emit("", str(e))
        
        finally:
            # 更新状态
            self.is_detecting = False
            self.view.set_detecting_state(False)
    
    def start_monitoring(self):
        """开始监听目录"""
        if not self.monitor_directory:
            self.view.show_message("错误", "请先选择监控目录！", 'error')
            return
        
        self.is_monitoring = True
        self.view.set_monitoring_state(True)
        logger.info(f"Started monitoring directory: {self.monitor_directory}")
        
        # 启动监听线程
        monitor_thread = threading.Thread(target=self._monitor_directory, daemon=True)
        monitor_thread.start()
    
    def stop_monitoring(self):
        """停止监听目录"""
        self.is_monitoring = False
        self.view.set_monitoring_state(False)
        logger.info("Monitoring stopped")
    
    def _monitor_directory(self):
        """目录监听线程"""
        last_files = set()
        logger.info(f"Started monitoring directory: {self.monitor_directory}")
        
        while self.is_monitoring:
            try:
                # 获取当前目录中的图片文件（与选择文件夹时保持一致）
                image_extensions = ('.jpg', '.jpeg', '.png', '.bmp', '.tiff', '.webp')
                current_files = set()
                
                for filename in os.listdir(self.monitor_directory):
                    if filename.lower().endswith(image_extensions):
                        current_files.add(os.path.join(self.monitor_directory, filename))
                
                # 找出新增的文件
                new_files = current_files - last_files
                
                if new_files:
                    logger.info(f"Detected {len(new_files)} new file(s): {[os.path.basename(f) for f in new_files]}")
                    
                    for new_file in new_files:
                        # 等待文件写入完成
                        time.sleep(0.5)
                        logger.info(f"Processing new file: {new_file}")
                        self._process_image(new_file)
                
                last_files = current_files
                
                # 等待一段时间后再次检查
                time.sleep(1)
            
            except Exception as e:
                logger.error(f"Monitor error: {str(e)}")
                time.sleep(1)
    
    def _process_image(self, image_path):
        """处理单张图片"""
        logger.info(f"Processing image: {image_path}")
        self.view.update_log(f"🔍 检测中: {os.path.basename(image_path)}")
        
        try:
            # 执行检测
            result = self.model.detect(image_path)
            
            if result is None:
                # 检测失败，发送错误信号
                error_msg = "检测插件返回空结果"
                logger.error(f"Detection returned None for: {image_path}")
                self.signal_detection_error.emit(image_path, error_msg)
                return
            
            # 处理检测结果
            status = result.get('result_status', 'UNKNOWN')
            logger.info(f"Detection result status: {status}")
            
            if status == 'ERROR':
                # 错误状态，发送错误信号
                error_msg = result.get('error_message', '检测错误')
                logger.error(f"Detection error for {image_path}: {error_msg}")
                self.signal_detection_error.emit(image_path, error_msg)
                return
            
            # 更新统计
            self.stats['total'] += 1
            if status == 'NG':
                self.stats['ng'] += 1
            elif status == 'OK':
                self.stats['ok'] += 1
            
            # 保存结果到数据库
            logger.info(f"Saving result to database for: {image_path}")
            record_id = self.model.save_result(image_path, result)
            if record_id:
                logger.info(f"Successfully saved record with ID: {record_id}")
            else:
                logger.error(f"Failed to save record for: {image_path}")
            
            # 更新界面
            self.view.update_result(result)
            
            # 显示图片
            if 'result_image' in result and result['result_image'] is not None:
                self.view.display_image(result['result_image'])
            else:
                # 读取原图并绘制检测框
                image = self.model.read_image(image_path)
                if image is not None:
                    detections = result.get('detections', [])
                    image_with_boxes = self.model.draw_detections(image, detections)
                    self.view.display_image(image_with_boxes)
            
            self.view.update_log(f"✓ 检测完成: {status}")
            logger.info(f"Detection completed: {status}")
            
        except Exception as e:
            logger.error(f"Process image error: {str(e)}")
            self.signal_detection_error.emit(image_path, str(e))
    
    def _handle_detection_error(self, image_path, error_message):
        """处理检测错误（在主线程中调用）"""
        logger.error(f"Detection error: {error_message}")
        
        # 更新统计
        self.stats['total'] += 1
        
        # 更新状态
        self.view.update_log(f"❌ 检测错误: {error_message}")
        
        # 保存错误记录
        result = {
            'result_status': 'ERROR',
            'detections': [],
            'error_message': error_message
        }
        self.model.save_result(image_path, result)
        
        # 显示原图并叠加错误信息
        image = self.model.read_image(image_path)
        if image is not None:
            image_with_error = self.model.draw_error_overlay(image, error_message)
            self.view.display_image(image_with_error)
    
    def view_history(self):
        """查看历史记录"""
        history = self.model.load_history()
        if not history:
            self.view.show_message("提示", "暂无检测记录", 'info')
            return
        
        record = self.view.show_history_dialog(history)
        if record:
            # 显示选中记录的图片
            image_path = record.get('result_image_path', record.get('image_path'))
            if image_path and os.path.exists(image_path):
                image = self.model.read_image(image_path)
                if image is not None:
                    self.view.display_image(image)
                
                # 更新结果显示
                result = {
                    'result_status': record.get('status', 'UNKNOWN'),
                    'detections': [],
                    'error_message': record.get('error_message', '')
                }
                self.view.update_result(result)
    
    def load_history_on_startup(self):
        """启动时加载历史记录"""
        history = self.model.load_history()
        logger.info(f"Loaded {len(history)} history records")
