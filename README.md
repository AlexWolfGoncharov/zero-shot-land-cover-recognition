# Satellite Image Segmentation Evaluation Framework

A comprehensive framework for evaluating Vision Language Models (VLMs) on satellite image segmentation tasks using various clustering and segmentation methods.

## Overview

This project evaluates the performance of different VLM models (OpenAI GPT-4, Claude, Gemini, Groq, etc.) on satellite image segmentation tasks. It compares various segmentation methods including K-means clustering, watershed segmentation, SOM (Self-Organizing Maps), and U-Net against ground truth from ESA WorldCover dataset.

## Features

- **Multiple VLM Models**: Support for OpenAI GPT-4, Claude, Gemini, Groq, and other models
- **Various Segmentation Methods**: K-means, watershed, SOM, U-Net
- **Comprehensive Evaluation**: IoU, accuracy, F1-score, precision, recall metrics
- **Cost Tracking**: API cost monitoring and analysis
- **Detailed Reporting**: Automated report generation with visualizations
- **WorldCover Integration**: Ground truth comparison using ESA WorldCover dataset

## Project Structure

```
satellite-segmentation-evaluation/
├── src/
│   ├── vlm_adapters/          # VLM API adapters
│   ├── clustering_methods/     # Segmentation algorithms
│   └── utils/                 # Utility functions
├── tests/                     # Test scripts
├── results/                   # Evaluation results
│   ├── method_1/             # Results from method 1
│   └── method_2/             # Results from method 2
├── cropped_images/            # Satellite image data
├── docs/                      # Documentation
├── requirements.txt           # Python dependencies
├── api_costs.json            # API cost configuration
└── README.md                 # This file
```

## Installation

### Prerequisites

- Python 3.8+
- Git

### Setup

1. **Clone the repository**:
   ```bash
   git clone <repository-url>
   cd satellite-segmentation-evaluation
   ```

2. **Create virtual environment**:
   ```bash
   python -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   ```

3. **Install dependencies**:
   ```bash
   pip install -r requirements.txt
   ```

## Configuration

### API Keys Setup

Create a `.env` file in the project root with your API keys:

```env
# OpenAI
OPENAI_API_KEY=your_openai_api_key_here

# Anthropic (Claude)
ANTHROPIC_API_KEY=your_anthropic_api_key_here

# Google (Gemini)
GOOGLE_API_KEY=your_google_api_key_here

# Groq
GROQ_API_KEY=your_groq_api_key_here

# Friendli
FRIENDLI_API_KEY=your_friendli_api_key_here

# Qwen
QWEN_API_KEY=your_qwen_api_key_here

# IBM
IBM_API_KEY=your_ibm_api_key_here

# Terrascope (WorldCover data access)
TERRASCOPE_USERNAME=your_terrascope_username_here
TERRASCOPE_PASSWORD=your_terrascope_password_here
```

### Required API Keys

| Service | Purpose | Key Name |
|---------|---------|----------|
| OpenAI | GPT-4, GPT-4o models | `OPENAI_API_KEY` |
| Anthropic | Claude models | `ANTHROPIC_API_KEY` |
| Google | Gemini models | `GOOGLE_API_KEY` |
| Groq | Groq models | `GROQ_API_KEY` |
| Friendli | Friendli models | `FRIENDLI_API_KEY` |
| Qwen | Qwen models | `QWEN_API_KEY` |
| IBM | IBM Granite models | `IBM_API_KEY` |

### Terrascope Credentials Setup

For WorldCover data access (required for evaluation), you need Terrascope credentials:

1. **Register at Terrascope:**
   - Go to [https://terrascope.be/en/services](https://terrascope.be/en/services)
   - Create an account
   - Get your username and password

2. **Add credentials to .env:**
   ```env
   TERRASCOPE_USERNAME=your_terrascope_username
   TERRASCOPE_PASSWORD=your_terrascope_password
   ```

3. **Alternative: Set environment variables:**
   ```bash
   export TERRASCOPE_USERNAME=your_username
   export TERRASCOPE_PASSWORD=your_password
   ```

**Note:** WorldCover data is used as ground truth for evaluating segmentation quality. If you don't have Terrascope credentials, the system will use cached WorldCover data if available.

## Usage

### Quick Setup Verification

Before running tests, verify your setup:

```bash
python check_setup.py
```

This script will check:
- ✅ Project structure and files
- ✅ Satellite image data availability
- ✅ API costs configuration
- ✅ Dependencies specification

### Running Tests

1. **Simple functionality test** (recommended for first run):
   ```bash
   python tests/test_simple.py
   ```

2. **Full evaluation with all models** (requires API keys):
   ```bash
   python tests/test_clustering_final_tiles_v2.py
   ```

3. **Test with specific models** (edit the MODELS list in the script):
   ```bash
   # Edit MODELS list in test_clustering_final_tiles_v2.py
   python tests/test_clustering_final_tiles_v2.py
   ```

4. **Analyze results**:
   ```bash
   # For method 1 results
   python tests/analyze_final_test_results_method1.py
   
   # For general results
   python tests/analyze_final_test_results.py
   ```

### Configuration Options

#### Model Selection

Edit the `MODELS` list in `tests/test_clustering_final_tiles_v2.py`:

```python
MODELS = [
    {"name": "gpt-4o-2024-08-06", "api": "openai"},
    {"name": "claude-3-5-haiku-20241022", "api": "claude"},
    {"name": "gemini-2.5-pro-preview-05-06", "api": "gemini"},
    # Add more models as needed
]
```

#### Test Parameters

- `N_TILES`: Number of tiles to process (default: 10)
- `TILE_SIZE`: Size of each tile in pixels (default: 512)
- `BORDER`: Border size for tile overlap (default: 200)

#### Segmentation Methods

Available methods:
- `kmeans`: K-means clustering
- `watershed_kmeans`: Watershed with K-means
- `watershed_ndvi`: Watershed with NDVI
- `som`: Self-Organizing Maps
- `unet`: U-Net segmentation

### Cost Tracking

The framework automatically tracks API costs. View costs:

```bash
python src/vlm_adapters/cost_tracker.py
```

## Results

### Output Structure

Test results are saved in `results/` directory:

```
results/
├── method_1/
│   ├── tile_0/
│   │   ├── kmeans_vlm2wc_gpt-4o.png
│   │   ├── kmeans_mask_gpt-4o_vlm_categories.json
│   │   └── ...
│   ├── final_report.md
│   ├── final_report_en.md
│   └── final_report_en.html
└── method_2/
    └── ...
```

### Report Files

- `final_report_en.md`: English version of the report
- `final_report_en.html`: HTML version with visualizations

### Metrics

The framework calculates:
- **IoU (Intersection over Union)**: Primary segmentation metric
- **Accuracy**: Pixel-level accuracy
- **F1-Score**: Harmonic mean of precision and recall
- **Precision**: True positives / (True positives + False positives)
- **Recall**: True positives / (True positives + False negatives)

## API Cost Management

### Cost Configuration

Edit `api_costs.json` to set cost per 1K tokens:

```json
{
  "openai": {
    "gpt-4o-2024-08-06": {"input": 0.0025, "output": 0.01},
    "gpt-4o-mini-2024-07-18": {"input": 0.00015, "output": 0.0006}
  },
  "anthropic": {
    "claude-3-5-haiku-20241022": {"input": 0.00025, "output": 0.00125}
  }
}
```

### Cost Monitoring

```bash
# View current costs
python src/vlm_adapters/cost_tracker.py

# Generate cost report
python src/analyze_model_costs.py
```

## Troubleshooting

### Common Issues

1. **API Key Errors**:
   - Ensure all required API keys are set in `.env`
   - Check key permissions and quotas

2. **Import Errors**:
   - Ensure virtual environment is activated
   - Install all dependencies: `pip install -r requirements.txt`

3. **Memory Issues**:
   - Reduce `N_TILES` or `TILE_SIZE`
   - Process tiles sequentially

4. **API Rate Limits**:
   - Add delays between requests
   - Use different API keys for parallel processing

### Debug Mode

Enable debug logging:

```python
import logging
logging.basicConfig(level=logging.DEBUG)
```

## Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Add tests if applicable
5. Submit a pull request

## License

[Add your license information here]

## Citation

If you use this framework in your research, please cite:

```bibtex
@software{satellite_segmentation_evaluation,
  title={Satellite Image Segmentation Evaluation Framework},
  author={Your Name},
  year={2024},
  url={https://github.com/yourusername/satellite-segmentation-evaluation}
}
```

## Support

For issues and questions:
- Create an issue on GitHub
- Check the documentation in `docs/`
- Review the example results in `results/` 
