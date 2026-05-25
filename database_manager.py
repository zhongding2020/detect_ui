"""
数据库管理模块
用于管理检测记录的持久化存储
"""

import sqlite3
import os
from datetime import datetime
from typing import List, Dict, Any, Optional
import sys

# 导入 DetectionResult 类（从插件基类导入
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from plugins.base.defect_base import DetectionResult


def get_app_data_directory() -> str:
    """
    获取应用数据目录
    
    在打包成 exe 后，需要确保数据存储在持久化的位置，而不是临时目录。
    返回的目录优先级：
    1. 打包后：可执行文件所在目录的 data 文件夹
    2. 开发模式：脚本所在目录的 data 文件夹
    """
    # 判断是否是打包后的环境
    if getattr(sys, 'frozen', False):
        # 打包后的情况：使用可执行文件所在目录
        app_dir = os.path.dirname(sys.executable)
    else:
        # 开发模式：使用脚本所在目录
        app_dir = os.path.dirname(os.path.abspath(__file__))
    
    # 创建并返回 data 目录
    data_dir = os.path.join(app_dir, 'data')
    os.makedirs(data_dir, exist_ok=True)
    return data_dir


class DatabaseManager:
    """
    数据库管理器
    """
    
    def __init__(self, db_path: str = None):
        """
        初始化数据库管理器
        
        Args:
            db_path: 数据库文件路径，默认为项目目录下的 data/detection_records.db
        """
        if db_path is None:
            # 默认数据库路径在应用数据目录的 data 文件夹
            data_dir = get_app_data_directory()
            db_path = os.path.join(data_dir, 'detection_records.db')
        
        self.db_path = db_path
        # 确保数据库目录存在
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
        self._create_tables()
    
    def _get_connection(self):
        """获取数据库连接"""
        return sqlite3.connect(self.db_path)
    
    def _create_tables(self):
        """创建数据库表结构"""
        conn = self._get_connection()
        cursor = conn.cursor()
        
        # 创建检测记录表
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS detection_records (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL,
                image_path TEXT NOT NULL,
                filename TEXT NOT NULL,
                defect_count INTEGER DEFAULT 0,
                status TEXT NOT NULL,
                elapsed_time REAL DEFAULT 0.0,
                result_image_path TEXT,
                error_message TEXT,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        # 创建检测结果表
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS detection_results (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                record_id INTEGER NOT NULL,
                class_name TEXT NOT NULL,
                confidence REAL NOT NULL,
                x1 INTEGER NOT NULL,
                y1 INTEGER NOT NULL,
                x2 INTEGER NOT NULL,
                y2 INTEGER NOT NULL,
                FOREIGN KEY (record_id) REFERENCES detection_records(id)
            )
        ''')
        
        conn.commit()
        conn.close()
    
    def save_record(self, timestamp: str, image_path: str, filename: str, 
                  defect_count: int, status: str, elapsed_time: float,
                  result_image_path: str, results: List[DetectionResult],
                  error_message: str = None) -> int:
        """
        保存检测记录到数据库
        
        Args:
            timestamp: 检测时间
            image_path: 原始图片路径
            filename: 文件名
            defect_count: 缺陷数量
            status: 状态 OK/NG/ERROR
            elapsed_time: 检测耗时
            result_image_path: 标注图片路径
            results: 检测结果列表
            error_message: 错误信息（可选）
            
        Returns:
            int: 插入的记录 ID
        """
        conn = self._get_connection()
        cursor = conn.cursor()
        
        # 插入主记录
        cursor.execute('''
            INSERT INTO detection_records 
            (timestamp, image_path, filename, defect_count, status, elapsed_time, result_image_path, error_message)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ''', (timestamp, image_path, filename, defect_count, status, elapsed_time, result_image_path, error_message))
        
        record_id = cursor.lastrowid
        
        # 插入检测结果
        for result in results:
            cursor.execute('''
                INSERT INTO detection_results 
                (record_id, class_name, confidence, x1, y1, x2, y2)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            ''', (record_id, result.class_name, result.confidence,
                  result.bbox[0], result.bbox[1], result.bbox[2], result.bbox[3]))
        
        conn.commit()
        conn.close()
        
        print(f"[Database] Saved record ID: {record_id}")
        return record_id
    
    def load_records(self) -> List[Dict[str, Any]]:
        """
        加载所有历史检测记录
        
        Returns:
            List[Dict]: 记录列表
        """
        conn = self._get_connection()
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        # 获取所有记录
        cursor.execute('SELECT * FROM detection_records ORDER BY id DESC')
        rows = cursor.fetchall()
        
        records = []
        for row in rows:
            record_id = row['id']
            
            # 获取该记录的检测结果
            cursor.execute('SELECT * FROM detection_results WHERE record_id = ?', (record_id,))
            result_rows = cursor.fetchall()
            
            results = []
            for result_row in result_rows:
                results.append(DetectionResult(
                    class_name=result_row['class_name'],
                    confidence=result_row['confidence'],
                    bbox=(result_row['x1'], result_row['y1'], result_row['x2'], result_row['y2'])
                ))
            
            # 构建记录字典
            record = {
                'id': record_id,
                'timestamp': row['timestamp'],
                'image_path': row['image_path'],
                'filename': row['filename'],
                'results': results,
                'defect_count': row['defect_count'],
                'status': row['status'],
                'elapsed_time': row['elapsed_time'],
                'result_image_path': row['result_image_path']
            }
            records.append(record)
        
        conn.close()
        
        print(f"[Database] Loaded {len(records)} records from database")
        return records
    
    def clear_all_records(self):
        """清空所有记录"""
        conn = self._get_connection()
        cursor = conn.cursor()
        
        cursor.execute('DELETE FROM detection_results')
        cursor.execute('DELETE FROM detection_records')
        cursor.execute('DELETE FROM sqlite_sequence WHERE name="detection_records"')
        
        conn.commit()
        conn.close()
        
        print(f"[Database] All records cleared")
    
    def delete_record(self, record_id: int):
        """删除指定记录"""
        conn = self._get_connection()
        cursor = conn.cursor()
        
        cursor.execute('DELETE FROM detection_results WHERE record_id = ?', (record_id,))
        cursor.execute('DELETE FROM detection_records WHERE id = ?', (record_id,))
        
        conn.commit()
        conn.close()
        
        print(f"[Database] Deleted record ID: {record_id}")
    
    @staticmethod
    def save_result_image(image_path: str, annotated_image) -> Optional[str]:
        """
        保存标注后的图片
        
        Args:
            image_path: 原始图片路径
            annotated_image: 带标注的图片对象（OpenCV格式）
            
        Returns:
            str: 保存的图片路径，失败返回None
        """
        try:
            import cv2
            import uuid
            
            # 创建保存目录（使用持久化的数据目录）
            data_dir = get_app_data_directory()
            results_dir = os.path.join(data_dir, 'results_images')
            os.makedirs(results_dir, exist_ok=True)
            
            # 生成文件名（使用UUID避免文件名+时间戳）
            filename = os.path.basename(image_path)
            name, ext = os.path.splitext(filename)
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            new_filename = f"{name}_{timestamp}_{uuid.uuid4().hex[:8]}{ext}"
            save_path = os.path.join(results_dir, new_filename)
            
            # 保存图片
            cv2.imwrite(save_path, annotated_image)
            print(f"[Database] Saved result image to: {save_path}")
            return save_path
            
        except Exception as e:
            print(f"[Database] Error saving result image: {e}")
            return None
