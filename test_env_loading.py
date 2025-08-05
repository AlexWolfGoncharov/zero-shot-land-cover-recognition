#!/usr/bin/env python3
"""
Тест загрузки переменных окружения из .env файла
"""

import os
import sys
from pathlib import Path

def test_env_loading():
    """Тестирует загрузку переменных окружения из .env файла"""
    
    # Добавляем путь к проекту
    project_root = Path(__file__).parent
    sys.path.insert(0, str(project_root))
    
    # Пытаемся загрузить .env файл
    env_file = project_root / ".env"
    print(f"Проверяем файл .env: {env_file}")
    print(f"Файл существует: {env_file.exists()}")
    
    if env_file.exists():
        print("Содержимое .env файла:")
        with open(env_file, 'r') as f:
            for line in f:
                if line.strip() and not line.startswith('#'):
                    key = line.split('=')[0]
                    print(f"  {key}")
    
    # Проверяем переменные окружения
    print("\nПроверяем переменные окружения:")
    env_vars = [
        "OPENAI_API_KEY",
        "CLAUDE_API_KEY", 
        "GOOGLE_API_KEY",
        "GROQ_API_KEY",
        "FRIENDLI_TOKEN",
        "HF_API_KEY",
        "IBM_API_KEY",
        "TERRASCOPE_USERNAME",
        "TERRASCOPE_PASSWORD"
    ]
    
    for var in env_vars:
        value = os.environ.get(var)
        if value:
            print(f"  {var}: {'*' * min(len(value), 10)}...")
        else:
            print(f"  {var}: НЕ НАЙДЕН")
    
    # Тестируем загрузку через python-dotenv
    try:
        from dotenv import load_dotenv
        print("\nПытаемся загрузить .env через python-dotenv...")
        load_dotenv(env_file)
        
        print("После загрузки .env:")
        for var in env_vars:
            value = os.environ.get(var)
            if value:
                print(f"  {var}: {'*' * min(len(value), 10)}...")
            else:
                print(f"  {var}: НЕ НАЙДЕН")
                
    except ImportError:
        print("python-dotenv не установлен")
    except Exception as e:
        print(f"Ошибка при загрузке .env: {e}")

if __name__ == "__main__":
    test_env_loading() 