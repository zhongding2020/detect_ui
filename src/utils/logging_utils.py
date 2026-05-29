import sys
import os
import logging
from logging.handlers import RotatingFileHandler

def get_app_data_directory() -> str:
    """获取应用数据目录"""
    if getattr(sys, 'frozen', False):
        app_dir = os.path.dirname(sys.executable)
    else:
        app_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    
    return app_dir

def setup_logging():
    """初始化日志系统"""
    app_dir = get_app_data_directory()
    log_dir = os.path.join(app_dir, 'logs')
    os.makedirs(log_dir, exist_ok=True)
    
    log_file = os.path.join(log_dir, 'app.log')
    
    # 创建根日志记录器
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.DEBUG)
    
    # 避免重复添加处理器
    if root_logger.handlers:
        return
    
    # 文件处理器
    file_handler = RotatingFileHandler(
        log_file,
        maxBytes=10 * 1024 * 1024,
        backupCount=5,
        encoding='utf-8'
    )
    file_handler.setLevel(logging.DEBUG)
    
    # 控制台处理器
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.INFO)
    
    # 格式化器
    formatter = logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    
    file_handler.setFormatter(formatter)
    console_handler.setFormatter(formatter)
    
    root_logger.addHandler(file_handler)
    root_logger.addHandler(console_handler)


def get_logger(name: str) -> logging.Logger:
    """获取日志记录器（不添加处理器，继承根日志记录器的配置）"""
    logger = logging.getLogger(name)
    
    # 确保 setup_logging 已调用
    root_logger = logging.getLogger()
    if not root_logger.handlers:
        setup_logging()
    
    return logger
