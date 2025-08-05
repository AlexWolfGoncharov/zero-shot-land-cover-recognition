# Quick Start Guide

## Prerequisites

1. **Python 3.8+** installed
2. **Git** for cloning the repository
3. **API Keys** for the VLM services you want to use

## Installation

1. **Clone the repository:**
   ```bash
   git clone <repository-url>
   cd satellite-segmentation-evaluation
   ```

2. **Create virtual environment:**
   ```bash
   python -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   ```

3. **Install dependencies:**
   ```bash
   pip install -r requirements.txt
   ```

## Configuration

### 1. API Keys Setup

Create a `.env` file in the project root:

```bash
cp env.example .env
```

Edit `.env` and add your API keys:

```env
# Required for VLM models
OPENAI_API_KEY=your_openai_api_key_here
ANTHROPIC_API_KEY=your_anthropic_api_key_here
GOOGLE_API_KEY=your_google_api_key_here
GROQ_API_KEY=your_groq_api_key_here
FRIENDLI_API_KEY=your_friendli_api_key_here
QWEN_API_KEY=your_qwen_api_key_here
IBM_API_KEY=your_ibm_api_key_here

# Required for WorldCover data access
TERRASCOPE_USERNAME=your_terrascope_username_here
TERRASCOPE_PASSWORD=your_terrascope_password_here

# Optional settings
DEBUG=false
ENABLE_COST_TRACKING=true
```

### 2. Terrascope Credentials Setup

For WorldCover data access, you need Terrascope credentials:

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

### 3. Verify Setup

Run the setup verification:

```bash
python check_setup.py
```

This will check:
- ✅ Python version
- ✅ Required packages
- ✅ API keys configuration
- ✅ Terrascope credentials
- ✅ Data directories

## Usage

### Basic Test Run

1. **Run a simple test:**
   ```bash
   python tests/test_clustering_final_tiles_v2.py
   ```

2. **Check results:**
   - Results are saved in `tests/final_test/`
   - Each tile has its own directory with masks and metrics

### Advanced Usage

See the main documentation for:
- Custom clustering methods
- Different VLM models
- Batch processing
- Cost tracking

## Troubleshooting

### Common Issues

1. **API Key Errors**: Check that your `.env` file is in the project root and contains valid API keys

2. **Terrascope Authentication Errors**: 
   - Verify your Terrascope credentials in `.env`
   - Make sure you're registered at [terrascope.be](https://terrascope.be)
   - Try interactive authentication if non-interactive fails

3. **Missing Dependencies**: Run `pip install -r requirements.txt`

4. **Memory Issues**: Reduce tile size or use smaller images

### Getting Help

- Check the logs in `tests/final_test/` for detailed error messages
- Review the main documentation for advanced configuration
- Open an issue with error details and system information 