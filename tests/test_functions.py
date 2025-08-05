#!/usr/bin/env python3
"""
Тестовый скрипт для проверки работы основных функций
"""

import os
import sys
import numpy as np
from datetime import datetime

# Добавляем путь к модулю
sys.path.append(os.path.join(os.path.dirname(__file__), '..', 'src'))

def test_imports():
    """Тестируем импорты основных модулей"""
    try:
        from src.utils.tiling import load_channels_from_files, prepare_multichannel_tile
        print("✓ tiling модуль импортирован успешно")
        
        from src.clustering_methods.clustering_methods import cluster_tiles
        print("✓ clustering_methods модуль импортирован успешно")
        
        from src.utils.worldcover import get_worldcover_legend
        print("✓ worldcover модуль импортирован успешно")
        
        from src.vlm_adapters.openai_adapter import openai_vision_categorize
        print("✓ openai_adapter модуль импортирован успешно")
        
        from src.vlm_adapters.claude_adapter import claude_vision_categorize
        print("✓ claude_adapter модуль импортирован успешно")
        
        return True
    except Exception as e:
        print(f"✗ Ошибка импорта: {e}")
        return False

def test_paths():
    """Тестируем создание путей для результатов"""
    try:
        # Тест для method_2
        timestamp = datetime.now().strftime('%Y-%m-%d_%H-%M-%S')
        method_2_path = f"tests/final_test/method_2/{timestamp}"
        os.makedirs(method_2_path, exist_ok=True)
        print(f"✓ Создан путь для method_2: {method_2_path}")
        
        # Тест для method_1
        method_1_path = f"tests/final_test/method_1/{timestamp}"
        os.makedirs(method_1_path, exist_ok=True)
        print(f"✓ Создан путь для method_1: {method_1_path}")
        
        return True
    except Exception as e:
        print(f"✗ Ошибка создания путей: {e}")
        return False

def test_data_loading():
    """Тестируем загрузку данных"""
    try:
        folder = '../cropped_images'  # Исправляем путь
        base_name = 'cropped_T36TWS_20230605T083601'
        channels = ["B02", "B03", "B04"]
        tile_size = 256  # Уменьшенный размер для теста
        x0, y0 = 100, 100
        
        # Проверяем существование файлов
        for channel in channels:
            file_path = os.path.join(folder, f"{base_name}_{channel}_20m.tif")
            if not os.path.exists(file_path):
                print(f"✗ Файл не найден: {file_path}")
                return False
        
        print("✓ Все необходимые файлы найдены")
        
        # Тестируем загрузку каналов
        from src.utils.tiling import load_channels_from_files
        tile_dict = load_channels_from_files(folder, base_name, channels, tile_size=tile_size, x0=x0, y0=y0)
        
        if tile_dict and all(channel in tile_dict for channel in channels):
            print("✓ Загрузка каналов работает")
            return True
        else:
            print("✗ Ошибка загрузки каналов")
            return False
            
    except Exception as e:
        print(f"✗ Ошибка загрузки данных: {e}")
        return False

def test_clustering():
    """Тестируем кластеризацию"""
    try:
        from src.clustering_methods.clustering_methods import cluster_tiles
        
        # Создаем тестовые данные
        test_data = np.random.rand(100, 100, 3)
        
        # Тестируем kmeans
        result = cluster_tiles([test_data], method="kmeans", n_clusters=3)
        
        if result and 'mask' in result:
            print("✓ Кластеризация kmeans работает")
            return True
        else:
            print("✗ Ошибка кластеризации")
            return False
            
    except Exception as e:
        print(f"✗ Ошибка кластеризации: {e}")
        return False

def main():
    """Основная функция тестирования"""
    print("=== Тестирование функций проекта ===\n")
    
    tests = [
        ("Импорты модулей", test_imports),
        ("Создание путей", test_paths),
        ("Загрузка данных", test_data_loading),
        ("Кластеризация", test_clustering),
    ]
    
    passed = 0
    total = len(tests)
    
    for test_name, test_func in tests:
        print(f"\n--- {test_name} ---")
        if test_func():
            passed += 1
            print(f"✓ {test_name} пройден")
        else:
            print(f"✗ {test_name} провален")
    
    print(f"\n=== Результаты тестирования ===")
    print(f"Пройдено: {passed}/{total} тестов")
    
    if passed == total:
        print("🎉 Все тесты пройдены успешно!")
    else:
        print("⚠️  Некоторые тесты провалены")

if __name__ == "__main__":
    main() 