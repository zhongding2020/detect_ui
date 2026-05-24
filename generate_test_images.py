#!/usr/bin/env python3
"""
生成测试用超声图片

用于测试缺陷检测系统的界面显示效果
"""

import os
import cv2
import numpy as np


def create_test_image(output_path, image_type='normal'):
    """
    创建测试图片
    
    Args:
        output_path: 输出路径
        image_type: 图片类型 ('normal', 'with_defects', 'complex')
    """
    # 创建基础图片（灰度超声图像）
    width, height = 640, 480
    
    if image_type == 'normal':
        # 正常的超声图像
        img = np.random.randint(50, 100, (height, width), dtype=np.uint8)
        # 添加一些纹理
        for _ in range(100):
            x, y = np.random.randint(0, width, 2)
            r = np.random.randint(5, 20)
            cv2.circle(img, (x, y), r, 100, -1)
        
    elif image_type == 'with_defects':
        # 带缺陷的图像
        img = np.random.randint(50, 100, (height, width), dtype=np.uint8)
        # 添加一些纹理
        for _ in range(100):
            x, y = np.random.randint(0, width, 2)
            r = np.random.randint(5, 20)
            cv2.circle(img, (x, y), r, 100, -1)
        
        # 添加模拟缺陷
        # 裂纹 - 细长的线条
        pts = np.array([[200, 100], [250, 150], [300, 130], [350, 180]], np.int32)
        cv2.polylines(img, [pts], False, 150, 2)
        
        # 划痕 - 直线
        cv2.line(img, (100, 300), (400, 320), 160, 3)
        
        # 点蚀 - 小圆点
        for _ in range(10):
            x, y = np.random.randint(50, 400, 2)
            r = np.random.randint(3, 8)
            cv2.circle(img, (x, y), r, 140, -1)
        
        # 凹坑 - 较大圆形
        for _ in range(5):
            x, y = np.random.randint(100, 500, 2)
            r = np.random.randint(10, 20)
            cv2.circle(img, (x, y), r, 130, -1)
    
    elif image_type == 'complex':
        # 复杂缺陷图像
        img = np.random.randint(40, 90, (height, width), dtype=np.uint8)
        
        # 添加复杂的纹理
        for i in range(0, width, 20):
            cv2.line(img, (i, 0), (i, height), 70, 1)
        for i in range(0, height, 20):
            cv2.line(img, (0, i), (width, i), 70, 1)
        
        # 添加多种缺陷
        # 裂纹（多条）
        for _ in range(3):
            x1 = np.random.randint(50, 300)
            y1 = np.random.randint(50, 400)
            x2 = x1 + np.random.randint(50, 200)
            y2 = y1 + np.random.randint(-100, 100)
            cv2.line(img, (x1, y1), (x2, y2), 170, 2)
        
        # 划痕
        cv2.line(img, (50, 200), (500, 220), 175, 4)
        cv2.line(img, (80, 350), (600, 320), 165, 3)
        
        # 点蚀群
        for i in range(20):
            x = 100 + i * 25
            y = 150 + (i % 5) * 15
            cv2.circle(img, (x, y), 5, 145, -1)
        
        # 凹坑
        for _ in range(8):
            x, y = np.random.randint(100, 550, 2)
            r = np.random.randint(15, 30)
            cv2.circle(img, (x, y), r, 135, -1)
            cv2.circle(img, (x, y), r - 5, 125, 2)
    
    # 应用高斯模糊使其更真实
    img = cv2.GaussianBlur(img, (5, 5), 0)
    
    # 转换为BGR格式
    img_color = cv2.cvtColor(img, cv2.COLOR_GRAY2BGR)
    
    # 添加伪彩色效果（可选）
    # img_color = cv2.applyColorMap(img, cv2.COLORMAP_JET)
    
    # 保存图片
    cv2.imwrite(output_path, img_color)
    print(f"✓ Created: {output_path}")


def create_dataset(output_dir, num_images=10):
    """
    创建测试数据集
    
    Args:
        output_dir: 输出目录
        num_images: 生成图片数量
    """
    # 创建输出目录
    os.makedirs(output_dir, exist_ok=True)
    
    print("=" * 60)
    print("生成测试超声图像数据集")
    print("=" * 60)
    print()
    
    # 生成不同类型的图片
    types = ['normal', 'with_defects', 'complex']
    
    for i in range(num_images):
        # 随机选择类型
        image_type = types[i % len(types)]
        
        # 生成文件名
        filename = f"test_image_{i+1:03d}_{image_type}.jpg"
        output_path = os.path.join(output_dir, filename)
        
        # 创建图片
        create_test_image(output_path, image_type)
    
    print()
    print("=" * 60)
    print(f"✓ 数据集生成完成！")
    print(f"  路径: {output_dir}")
    print(f"  数量: {num_images} 张图片")
    print("=" * 60)
    print()
    print("使用方法：")
    print(f"  1. 打开软件")
    print(f"  2. 选择图片或文件夹: {output_dir}")
    print(f"  3. 选择插件: 'Mock Detector'")
    print(f"  4. 点击'立即开始'测试")
    print()


if __name__ == "__main__":
    # 生成测试数据
    dataset_dir = "test_images"
    create_dataset(dataset_dir, num_images=15)
