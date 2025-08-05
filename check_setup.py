#!/usr/bin/env python3
"""
Script to verify the correct setup of the satellite-segmentation-evaluation project
"""

import os
import sys
import json
from pathlib import Path

# Load .env file if it exists
def load_env_file():
    """Load environment variables from .env file"""
    # Try to load from current directory
    env_file = Path(".env")
    if not env_file.exists():
        # Try to load from parent directory (project root)
        env_file = Path("../.env")
    
    if env_file.exists():
        try:
            from dotenv import load_dotenv
            load_dotenv(env_file)
            print(f"✅ Loaded environment variables from {env_file}")
        except ImportError:
            # Manual loading as fallback
            with open(env_file, "r") as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith("#"):
                        if "=" in line:
                            key, value = line.split("=", 1)
                            os.environ[key] = value
            print(f"✅ Manually loaded environment variables from {env_file}")
    else:
        print("⚠️  No .env file found")

# Load environment variables at startup
load_env_file()

def check_project_structure():
    """Checks if the project has the correct structure"""
    print("📁 Checking project structure...")
    
    required_dirs = [
        'src',
        'src/clustering_methods',
        'src/utils',
        'src/vlm_adapters',
        'tests',
        'results',
        'cropped_images',
        'docs'
    ]
    
    missing_dirs = []
    for dir_name in required_dirs:
        if not os.path.exists(dir_name):
            missing_dirs.append(dir_name)
        else:
            print(f"✅ {dir_name}/")
    
    if missing_dirs:
        print(f"❌ Missing directories: {missing_dirs}")
        return False
    
    return True

def check_cropped_images():
    """Checks if cropped images are available"""
    print("\n🖼️  Checking cropped images...")
    
    cropped_images_dir = 'cropped_images'
    if not os.path.exists(cropped_images_dir):
        print("❌ cropped_images directory not found")
        return False
    
    # Check for main channels
    expected_channels = ['B02', 'B03', 'B04', 'B05', 'B06', 'B07', 'B8A', 'B11', 'B12']
    base_name = 'cropped_T36TWS_20230605T083601'
    
    missing_channels = []
    for channel in expected_channels:
        file_path = os.path.join(cropped_images_dir, f"{base_name}_{channel}_20m.tif")
        if not os.path.exists(file_path):
            missing_channels.append(channel)
        else:
            file_size = os.path.getsize(file_path) / (1024 * 1024)  # MB
            print(f"✅ {channel}: {file_size:.1f} MB")
    
    if missing_channels:
        print(f"❌ Missing channels: {missing_channels}")
        return False
    
    return True

def check_terrascope_credentials():
    """Checks Terrascope credentials configuration"""
    print("\n🌍 Checking Terrascope credentials...")
    
    username = os.environ.get("TERRASCOPE_USERNAME")
    password = os.environ.get("TERRASCOPE_PASSWORD")
    
    if not username:
        print("❌ TERRASCOPE_USERNAME not set in environment variables")
        print("   Add to .env file: TERRASCOPE_USERNAME=your_username")
        return False
    
    if not password:
        print("❌ TERRASCOPE_PASSWORD not set in environment variables")
        print("   Add to .env file: TERRASCOPE_PASSWORD=your_password")
        return False
    
    print("✅ Terrascope credentials found in environment variables")
    print(f"   Username: {username[:3]}***{username[-3:] if len(username) > 6 else '***'}")
    print(f"   Password: {'*' * len(password)}")
    
    return True

def check_api_costs():
    """Checks API costs configuration"""
    print("\n💰 Checking API costs configuration...")
    
    if not os.path.exists('api_costs.json'):
        print("❌ File api_costs.json not found")
        return False
    
    try:
        with open('api_costs.json', 'r', encoding='utf-8') as f:
            costs = json.load(f)
        
        if not isinstance(costs, dict):
            print("❌ api_costs.json should contain a dictionary")
            return False
        
        print(f"✅ api_costs.json loaded successfully ({len(costs)} entries)")
        return True
        
    except Exception as e:
        print(f"❌ Error loading api_costs.json: {e}")
        return False

def check_requirements():
    """Checks requirements.txt file"""
    print("\n📦 Checking requirements.txt...")
    
    if not os.path.exists('requirements.txt'):
        print("❌ File requirements.txt not found")
        return False
    
    try:
        with open('requirements.txt', 'r', encoding='utf-8') as f:
            requirements = f.read().strip()
        
        if not requirements:
            print("❌ requirements.txt is empty")
            return False
        
        lines = requirements.split('\n')
        print(f"✅ requirements.txt contains {len(lines)} dependencies")
        return True
        
    except Exception as e:
        print(f"❌ Error reading requirements.txt: {e}")
        return False

def main():
    """Main verification function"""
    print("🚀 Verifying satellite-segmentation-evaluation project setup\n")
    
    checks = [
        check_project_structure,
        check_cropped_images,
        check_terrascope_credentials,
        check_api_costs,
        check_requirements
    ]
    
    all_passed = True
    for check in checks:
        if not check():
            all_passed = False
    
    print("\n" + "="*50)
    if all_passed:
        print("🎉 All checks passed! Project is ready for use.")
        print("\nNext steps:")
        print("1. Create virtual environment: python -m venv venv")
        print("2. Activate it: source venv/bin/activate (Linux/Mac) or venv\\Scripts\\activate (Windows)")
        print("3. Install dependencies: pip install -r requirements.txt")
        print("4. Configure API keys in .env file")
        print("5. Configure Terrascope credentials in .env file")
        print("6. Run tests: python tests/test_clustering_final_tiles_v2.py")
    else:
        print("❌ Some checks failed. Fix the errors and run the verification again.")
    
    return all_passed

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1) 