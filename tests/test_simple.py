#!/usr/bin/env python3
"""
Simple test to verify basic functionality without WorldCover
"""

import numpy as np
import os
import sys
import json
import random
from datetime import datetime
import logging

# Add src to path
sys.path.append(os.path.join(os.path.dirname(__file__), '..', 'src'))

from src.utils.tiling import load_channels_from_files, prepare_multichannel_tile
from src.clustering_methods.clustering_methods import cluster_tiles
from PIL import Image

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

def test_basic_clustering():
    """Test basic clustering functionality"""
    logger.info("Testing basic clustering functionality...")
    
    # Parameters
    tile_size = 256  # Smaller for faster testing
    border = 100
    folder = 'cropped_images'
    base_name = 'cropped_T36TWS_20230605T083601'
    channels = ["B02", "B03", "B04"]  # Only RGB channels for simplicity
    
    # Generate a single tile
    x0 = 1000
    y0 = 1000
    
    try:
        # Load channels
        logger.info("Loading satellite channels...")
        tile_dict = load_channels_from_files(folder, base_name, channels, tile_size=tile_size, x0=x0, y0=y0)
        tile_data = prepare_multichannel_tile(tile_dict)
        
        logger.info(f"Tile shape: {tile_data.shape}")
        
        # Test different clustering methods
        methods = ["kmeans", "som"]
        
        for method in methods:
            logger.info(f"Testing {method} clustering...")
            
            # Perform clustering
            result = cluster_tiles([tile_data], method=method, n_clusters=5)
            
            if isinstance(result, dict) and 'mask' in result:
                mask = result['mask']
            else:
                mask = result
                
            logger.info(f"{method} clustering completed. Mask shape: {mask.shape}")
            logger.info(f"Unique clusters: {np.unique(mask)}")
            
            # Save visualization
            output_dir = f"test_results_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
            os.makedirs(output_dir, exist_ok=True)
            
            # Create colored mask
            unique_clusters = np.unique(mask)
            colored_mask = np.zeros((mask.shape[0], mask.shape[1], 3), dtype=np.uint8)
            
            for i, cluster in enumerate(unique_clusters):
                color = np.random.randint(0, 255, 3)
                colored_mask[mask == cluster] = color
            
            # Save results
            mask_path = os.path.join(output_dir, f"{method}_mask.png")
            Image.fromarray(colored_mask).save(mask_path)
            
            # Save metadata
            metadata = {
                "method": method,
                "n_clusters": len(unique_clusters),
                "tile_coords": {"x0": x0, "y0": y0},
                "tile_size": tile_size,
                "channels": channels
            }
            
            metadata_path = os.path.join(output_dir, f"{method}_metadata.json")
            with open(metadata_path, 'w') as f:
                json.dump(metadata, f, indent=2)
            
            logger.info(f"Results saved to {output_dir}")
        
        logger.info("✅ All basic clustering tests passed!")
        return True
        
    except Exception as e:
        logger.error(f"❌ Test failed: {e}")
        return False

def test_vlm_imports():
    """Test VLM adapter imports"""
    logger.info("Testing VLM adapter imports...")
    
    try:
        # Test imports
        from src.vlm_adapters.openai_adapter import openai_vision_categorize
        from src.vlm_adapters.claude_adapter import claude_vision_categorize
        from src.vlm_adapters.groq_adapter import groq_vision_categorize
        
        logger.info("✅ VLM adapter imports successful!")
        return True
        
    except Exception as e:
        logger.error(f"❌ VLM import test failed: {e}")
        return False

def main():
    """Main test function"""
    logger.info("🚀 Starting simple functionality tests...")
    
    tests = [
        test_basic_clustering,
        test_vlm_imports
    ]
    
    passed = 0
    total = len(tests)
    
    for test in tests:
        if test():
            passed += 1
    
    logger.info(f"\n📊 Test Results: {passed}/{total} tests passed")
    
    if passed == total:
        logger.info("🎉 All tests passed! Project is working correctly.")
    else:
        logger.error("❌ Some tests failed. Check the logs above.")
    
    return passed == total

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1) 