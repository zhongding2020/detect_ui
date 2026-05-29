"""
插件加载管理器
负责扫描、加载和管理检测插件
"""

import os
import sys
import importlib
import py_compile
from pathlib import Path
from typing import List, Dict, Optional

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from plugins.base.defect_base import DetectionAlgorithmBase, DetectionResult
from src.utils.logging_utils import get_logger

logger = get_logger('plugin')


class PluginManager:
    """插件管理器类"""

    def __init__(self, plugin_dir: str = "plugins"):
        """
        初始化插件管理器

        Args:
            plugin_dir: 插件目录路径（相对于项目根目录）
        """
        self.plugin_dir = plugin_dir
        self.plugins: Dict[str, DetectionAlgorithmBase] = {}
        self.plugin_info: Dict[str, Dict] = {}
        self.loaded_plugins = []

    def get_plugin_directory(self) -> str:
        """获取插件目录的绝对路径"""
        # 检查是否是打包后的环境（PyInstaller）
        if getattr(sys, 'frozen', False) and hasattr(sys, '_MEIPASS'):
            # 打包后的环境：先尝试从可执行文件所在目录加载插件
            exe_dir = os.path.dirname(os.path.abspath(sys.executable))
            plugin_path = os.path.join(exe_dir, self.plugin_dir)
            if os.path.exists(plugin_path):
                return plugin_path

            # 否则从 _MEIPASS（临时解压目录）加载
            plugin_path = os.path.join(sys._MEIPASS, self.plugin_dir)
            if os.path.exists(plugin_path):
                return plugin_path

        # 开发环境
        try:
            # 先尝试从 __file__ 获取路径（源代码环境）
            # __file__ = d:\dev\detect_ui-main\plugins\plugin_manager.py
            # parent.parent = 项目根目录
            project_root = Path(__file__).parent.parent.absolute()
            plugin_path = project_root / self.plugin_dir
            if os.path.exists(plugin_path):
                return str(plugin_path)
        except:
            pass

        # 最后尝试从当前工作目录查找
        plugin_path = os.path.join(os.getcwd(), self.plugin_dir)
        return plugin_path

    def scan_plugins(self) -> List[str]:
        """
        扫描插件目录，查找所有插件文件

        Returns:
            List[str]: 插件文件路径列表
        """
        plugin_files = []
        plugin_path = self.get_plugin_directory()

        if not os.path.exists(plugin_path):
            logger.warning(f"Plugin directory not found: {plugin_path}")
            return plugin_files

        # 遍历插件目录
        for root, dirs, files in os.walk(plugin_path):
            # 过滤掉 __pycache__ 目录
            dirs[:] = [d for d in dirs if d != '__pycache__']

            for file in files:
                # 只查找 detectors/ 目录下的文件，避免加载基类和管理器
                if 'detectors' in root:
                    # 查找.py和.pyc文件，但排除__init__.py
                    if file.endswith('.pyc') or (file.endswith('.py') and not file.startswith('__')):
                        file_path = os.path.join(root, file)
                        plugin_files.append(file_path)

        return plugin_files

    def compile_plugin(self, plugin_path: str) -> bool:
        """
        将Python插件文件编译为.pyc字节码文件

        Args:
            plugin_path: 插件Python文件路径

        Returns:
            bool: 编译是否成功
        """
        try:
            py_compile.compile(plugin_path, doraise=True)
            return True
        except py_compile.PyCompileError as e:
            logger.error(f"Error compiling plugin {plugin_path}: {e}")
            return False

    def load_plugin(self, plugin_path: str) -> Optional[DetectionAlgorithmBase]:
        """
        加载单个插件

        Args:
            plugin_path: 插件文件路径

        Returns:
            Optional[DetectionAlgorithmBase]: 加载的插件实例，失败返回None
        """
        try:
            # 获取插件目录和文件名
            plugin_dir = self.get_plugin_directory()
            rel_path = os.path.relpath(plugin_path, plugin_dir)

            # 正确处理文件扩展名
            base_name = os.path.splitext(rel_path)[0]
            if base_name.endswith('.py'):
                base_name = base_name[:-3]
            module_name = base_name.replace('/', '.').replace('\\', '.')

            # 动态导入模块
            if module_name not in sys.modules:
                spec = importlib.util.spec_from_file_location(module_name, plugin_path)
                if spec and spec.loader:
                    module = importlib.util.module_from_spec(spec)
                    sys.modules[module_name] = module
                    spec.loader.exec_module(module)

            # 查找继承DetectionAlgorithmBase的类
            module = sys.modules[module_name]
            for attr_name in dir(module):
                attr = getattr(module, attr_name)
                if (isinstance(attr, type) and
                    issubclass(attr, DetectionAlgorithmBase) and
                    attr is not DetectionAlgorithmBase):

                    # 实例化插件
                    plugin_instance = attr()
                    plugin_name = plugin_instance.name

                    self.plugins[plugin_name] = plugin_instance
                    self.plugin_info[plugin_name] = plugin_instance.get_info()
                    self.loaded_plugins.append(plugin_name)

                    logger.info(f"Loaded plugin: {plugin_name} v{plugin_instance.version}")
                    return plugin_instance

            return None

        except Exception as e:
            logger.error(f"Error loading plugin {plugin_path}: {e}")
            import traceback
            traceback.print_exc()
            return None

    def load_all_plugins(self) -> Dict[str, DetectionAlgorithmBase]:
        """
        加载所有插件

        Returns:
            Dict[str, DetectionAlgorithmBase]: 已加载的插件字典
        """
        self.plugins.clear()
        self.plugin_info.clear()
        self.loaded_plugins.clear()

        plugin_files = self.scan_plugins()

        for plugin_path in plugin_files:
            # 如果是.py文件，先编译为.pyc
            if plugin_path.endswith('.py'):
                self.compile_plugin(plugin_path)
                # 加载.pyc文件
                pyc_path = plugin_path + 'c'
                if os.path.exists(pyc_path):
                    self.load_plugin(pyc_path)
                else:
                    self.load_plugin(plugin_path)
            else:
                self.load_plugin(plugin_path)

        return self.plugins

    def get_plugin(self, name: str) -> Optional[DetectionAlgorithmBase]:
        """
        获取指定名称的插件

        Args:
            name: 插件名称

        Returns:
            Optional[DetectionAlgorithmBase]: 插件实例
        """
        return self.plugins.get(name)

    def get_all_plugins(self) -> Dict[str, DetectionAlgorithmBase]:
        """
        获取所有已加载的插件

        Returns:
            Dict[str, DetectionAlgorithmBase]: 插件字典
        """
        return self.plugins

    def get_plugin_info(self, name: str) -> Optional[Dict]:
        """
        获取插件信息

        Args:
            name: 插件名称

        Returns:
            Optional[Dict]: 插件信息字典
        """
        return self.plugin_info.get(name)

    def get_all_plugin_info(self) -> Dict[str, Dict]:
        """
        获取所有插件信息

        Returns:
            Dict[str, Dict]: 所有插件信息
        """
        return self.plugin_info

    def reload_plugin(self, name: str) -> Optional[DetectionAlgorithmBase]:
        """
        重新加载指定插件

        Args:
            name: 插件名称

        Returns:
            Optional[DetectionAlgorithmBase]: 重新加载的插件实例
        """
        # 从已加载的插件中移除
        if name in self.plugins:
            del self.plugins[name]
        if name in self.plugin_info:
            del self.plugin_info[name]
        if name in self.loaded_plugins:
            self.loaded_plugins.remove(name)

        # 重新扫描和加载
        self.load_all_plugins()

        return self.plugins.get(name)

    def unload_plugin(self, name: str) -> bool:
        """
        卸载指定插件

        Args:
            name: 插件名称

        Returns:
            bool: 是否卸载成功
        """
        if name in self.plugins:
            del self.plugins[name]
        if name in self.plugin_info:
            del self.plugin_info[name]
        if name in self.loaded_plugins:
            self.loaded_plugins.remove(name)
        return True

    def list_plugins(self) -> List[str]:
        """
        列出所有已加载的插件名称

        Returns:
            List[str]: 插件名称列表
        """
        return self.loaded_plugins

    def get_plugin_count(self) -> int:
        """
        获取已加载插件数量

        Returns:
            int: 插件数量
        """
        return len(self.plugins)
