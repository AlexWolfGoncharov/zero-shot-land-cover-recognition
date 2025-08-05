# Project Structure

This document provides a detailed overview of the project structure and the purpose of each component.

## Directory Structure

```
satellite-segmentation-evaluation/
├── src/                          # Source code
│   ├── vlm_adapters/            # VLM API adapters
│   │   ├── __init__.py
│   │   ├── openai_adapter.py    # OpenAI GPT-4 adapter
│   │   ├── claude_adapter.py    # Anthropic Claude adapter
│   │   ├── gemini_adapter.py    # Google Gemini adapter
│   │   ├── groq_adapter.py      # Groq adapter
│   │   ├── friendli_adapter.py  # Friendli adapter
│   │   ├── qwen_adapter.py      # Qwen adapter
│   │   ├── ibm_granite_adapter.py # IBM Granite adapter
│   │   ├── cost_tracker.py      # API cost tracking
│   │   └── response_parser.py   # Response parsing utilities
│   ├── clustering_methods/       # Segmentation algorithms
│   │   ├── __init__.py
│   │   └── clustering_methods.py # K-means, watershed, SOM, U-Net
│   └── utils/                   # Utility functions
│       ├── __init__.py
│       ├── tiling.py           # Image tiling utilities
│       └── worldcover.py       # WorldCover dataset utilities
├── tests/                       # Test scripts
│   ├── test_clustering_final_tiles_v2.py    # Main test script
│   ├── analyze_final_test_results.py         # Analysis for method 2
│   └── analyze_final_test_results_method1.py # Analysis for method 1
├── results/                     # Evaluation results
│   ├── method_1/               # Results from method 1
│   │   ├── tile_0/             # Results for tile 0
│   │   ├── tile_1/             # Results for tile 1
│   │   ├── ...
│   │   ├── final_report.md     # Russian report
│   │   ├── final_report_en.md  # English report
│   │   └── final_report_en.html # HTML report with visualizations
│   └── method_2/               # Results from method 2
│       ├── tile_0/             # Results for tile 0
│       ├── tile_1/             # Results for tile 1
│       ├── ...
│       ├── final_report.md     # Russian report
│       ├── final_report_en.md  # English report
│       └── final_report_en.html # HTML report with visualizations
├── docs/                        # Documentation
│   ├── QUICK_START.md          # Quick start guide
│   └── PROJECT_STRUCTURE.md    # This file
├── requirements.txt             # Python dependencies
├── api_costs.json              # API cost configuration
├── setup.py                    # Package setup
├── .gitignore                  # Git ignore rules
├── env.example                 # Environment variables template
└── README.md                   # Main documentation
```

## Component Details

### Source Code (`src/`)

#### VLM Adapters (`src/vlm_adapters/`)

Contains adapters for different Vision Language Model APIs:

- **`openai_adapter.py`**: Handles OpenAI GPT-4, GPT-4o models
- **`claude_adapter.py`**: Handles Anthropic Claude models
- **`gemini_adapter.py`**: Handles Google Gemini models
- **`groq_adapter.py`**: Handles Groq models
- **`friendli_adapter.py`**: Handles Friendli models
- **`qwen_adapter.py`**: Handles Qwen models
- **`ibm_granite_adapter.py`**: Handles IBM Granite models
- **`cost_tracker.py`**: Tracks API usage costs
- **`response_parser.py`**: Parses VLM responses

#### Clustering Methods (`src/clustering_methods/`)

Contains segmentation algorithms:

- **`clustering_methods.py`**: Implements K-means, watershed, SOM, and U-Net segmentation

#### Utils (`src/utils/`)

Utility functions:

- **`tiling.py`**: Handles image tiling and multichannel processing
- **`worldcover.py`**: Manages ESA WorldCover dataset integration

### Tests (`tests/`)

Test scripts for running evaluations:

- **`test_clustering_final_tiles_v2.py`**: Main test script that runs VLM evaluations
- **`analyze_final_test_results.py`**: Analyzes results from method 2
- **`analyze_final_test_results_method1.py`**: Analyzes results from method 1

### Results (`results/`)

Contains evaluation results organized by method:

#### Method 1 (`results/method_1/`)

Results from the first evaluation method:
- Individual tile results in `tile_0/`, `tile_1/`, etc.
- Generated reports in various formats

#### Method 2 (`results/method_2/`)

Results from the second evaluation method:
- Individual tile results in `tile_0/`, `tile_1/`, etc.
- Generated reports in various formats

### Documentation (`docs/`)

- **`QUICK_START.md`**: Quick start guide for new users
- **`PROJECT_STRUCTURE.md`**: This file

### Configuration Files

- **`requirements.txt`**: Python package dependencies
- **`api_costs.json`**: API cost configuration for different models
- **`setup.py`**: Package installation configuration
- **`.gitignore`**: Git ignore rules
- **`env.example`**: Template for environment variables

## File Naming Conventions

### Test Results

Results are organized by tile and method:

```
tile_{tile_number}/
├── {method}_vlm2wc_{model}.png          # VLM vs WorldCover comparison
├── {method}_mask_{model}_vlm_categories.json # VLM categorization results
├── {method}_vlm_vs_worldcover_metrics.json  # Evaluation metrics
└── {method}_legend_{model}.png          # Legend for visualization
```

### Report Files

- `final_report.md`: Russian version
- `final_report_en.md`: English version
- `final_report_en.html`: HTML version with visualizations

## Data Flow

1. **Input**: Satellite images are tiled into smaller chunks
2. **Segmentation**: Various methods (K-means, watershed, etc.) segment the tiles
3. **VLM Processing**: VLM models categorize the segmented regions
4. **Comparison**: VLM results are compared against WorldCover ground truth
5. **Metrics**: IoU, accuracy, F1-score, etc. are calculated
6. **Analysis**: Results are analyzed and visualized
7. **Reporting**: Comprehensive reports are generated

## Key Functions

### Main Test Script

- `main()`: Orchestrates the entire evaluation process
- `process_method_model_for_tile()`: Processes a single tile with a method-model combination
- `generate_non_overlapping_tiles()`: Generates test tiles from satellite data

### Analysis Scripts

- `collect_metrics()`: Collects metrics from result files
- `generate_full_report()`: Generates comprehensive reports
- `plot_metrics()`: Creates visualizations
- `check_completeness()`: Verifies all combinations were tested

## Configuration

### Environment Variables

Required API keys (see `env.example`):
- `OPENAI_API_KEY`: For OpenAI models
- `ANTHROPIC_API_KEY`: For Claude models
- `GOOGLE_API_KEY`: For Gemini models
- `GROQ_API_KEY`: For Groq models
- `FRIENDLI_API_KEY`: For Friendli models
- `QWEN_API_KEY`: For Qwen models
- `IBM_API_KEY`: For IBM Granite models

### Test Parameters

In `test_clustering_final_tiles_v2.py`:
- `N_TILES`: Number of tiles to process
- `TILE_SIZE`: Size of each tile in pixels
- `BORDER`: Border size for tile overlap
- `MODELS`: List of models to test

## Extending the Framework

### Adding New VLM Models

1. Create a new adapter in `src/vlm_adapters/`
2. Implement the required functions
3. Add the model to the `MODELS` list in the test script

### Adding New Segmentation Methods

1. Implement the method in `src/clustering_methods/clustering_methods.py`
2. Add the method to the processing pipeline
3. Update the analysis scripts if needed

### Adding New Metrics

1. Implement the metric calculation
2. Update the analysis scripts to include the new metric
3. Add visualizations if needed 