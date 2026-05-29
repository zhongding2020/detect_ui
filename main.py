#!/usr/bin/env python3
"""超声缺陷检测系统 - 主入口"""

import sys
import os

# 设置 Qt 环境变量（修复 Linux 平台插件问题）
if sys.platform.startswith('linux'):
    try:
        import PyQt5
        pyqt5_path = os.path.dirname(PyQt5.__file__)
        qt_plugins_path = os.path.join(pyqt5_path, 'Qt5', 'plugins')
        if os.path.exists(qt_plugins_path):
            os.environ['QT_PLUGIN_PATH'] = qt_plugins_path
    except:
        pass
    os.environ['QT_QPA_PLATFORM'] = 'xcb'

# 添加项目路径
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from src.utils.logging_utils import get_logger, setup_logging

# 初始化日志
setup_logging()
logger = get_logger('main')


def main():
    """主函数"""
    logger.info("========== 启动超声缺陷检测系统 ==========")
    
    try:
        logger.info("1. 导入 PyQt5 模块")
        from PyQt5.QtWidgets import QApplication
        logger.info("2. 导入 MVP 模块")
        from src.view.DetectionView import DetectionView
        from src.model.DetectionModel import DetectionModel
        from src.presenter.DetectionPresenter import DetectionPresenter
        
        logger.info("3. 创建 QApplication")
        app = QApplication(sys.argv)
        logger.info(f"   - QApplication 创建成功: {app}")
        
        logger.info("4. 创建 DetectionModel")
        model = DetectionModel()
        logger.info(f"   - DetectionModel 创建成功: {model}")
        
        logger.info("5. 创建 DetectionView")
        view = DetectionView()
        logger.info(f"   - DetectionView 创建成功: {view}")
        
        logger.info("6. 创建 DetectionPresenter")
        presenter = DetectionPresenter(view, model)
        logger.info(f"   - DetectionPresenter 创建成功: {presenter}")
        
        logger.info("7. 加载历史记录")
        presenter.load_history_on_startup()
        logger.info("   - 历史记录加载完成")
        
        logger.info("8. 显示窗口")
        view.show()
        logger.info("   - 窗口显示成功")
        
        logger.info("系统启动成功，进入事件循环")
        
        # 运行应用
        sys.exit(app.exec_())
        
    except Exception as e:
        logger.error(f"系统启动失败: {str(e)}", exc_info=True)
        print(f"Error: {str(e)}")
        raise


if __name__ == '__main__':
    main()
