# Deployment Guide for GitHub

This guide will help you deploy the Satellite Image Segmentation Evaluation Framework to GitHub.

## Pre-Deployment Checklist

### 1. Review and Update Files

Before pushing to GitHub, make sure to:

- [ ] Update `setup.py` with your actual information
- [ ] Update `README.md` with your repository URL
- [ ] Review `.gitignore` to ensure sensitive files are excluded
- [ ] Check that all API keys are properly configured in `env.example`

### 2. Update Configuration Files

#### setup.py
Update the following fields:
```python
author="Your Name",
author_email="your.email@example.com",
url="https://github.com/yourusername/satellite-segmentation-evaluation",
```

#### README.md
Replace `<repository-url>` with your actual repository URL:
```bash
git clone https://github.com/yourusername/satellite-segmentation-evaluation.git
```

### 3. Test the Setup

Before pushing to GitHub, test that everything works:

```bash
# Test imports
python -c "from src.vlm_adapters import openai_adapter; print('Import successful')"

# Test analysis scripts
python tests/analyze_final_test_results_method1.py --help
```

## GitHub Deployment Steps

### 1. Initialize Git Repository

```bash
# Initialize git repository
git init

# Add all files
git add .

# Make initial commit
git commit -m "Initial commit: Satellite Image Segmentation Evaluation Framework"

# Add remote repository
git remote add origin https://github.com/yourusername/satellite-segmentation-evaluation.git

# Push to GitHub
git push -u origin main
```

### 2. Set Up GitHub Repository

1. **Create Repository**: Go to GitHub and create a new repository
2. **Set Description**: Add a clear description of the project
3. **Add Topics**: Add relevant topics like `satellite-imagery`, `segmentation`, `vlm`, `evaluation`
4. **Set License**: Choose an appropriate license (MIT, Apache, etc.)

### 3. Configure GitHub Pages (Optional)

If you want to host the documentation:

1. Go to repository Settings > Pages
2. Select source: "Deploy from a branch"
3. Select branch: "main"
4. Select folder: "/docs"
5. Save

### 4. Set Up GitHub Actions (Optional)

Create `.github/workflows/ci.yml` for continuous integration:

```yaml
name: CI

on:
  push:
    branches: [ main ]
  pull_request:
    branches: [ main ]

jobs:
  test:
    runs-on: ubuntu-latest
    strategy:
      matrix:
        python-version: [3.8, 3.9, 3.10, 3.11]

    steps:
    - uses: actions/checkout@v2
    
    - name: Set up Python ${{ matrix.python-version }}
      uses: actions/setup-python@v2
      with:
        python-version: ${{ matrix.python-version }}
    
    - name: Install dependencies
      run: |
        python -m pip install --upgrade pip
        pip install -r requirements.txt
    
    - name: Run tests
      run: |
        python -c "import src; print('Import test passed')"
```

## Post-Deployment Tasks

### 1. Update Documentation

- [ ] Update README.md with actual repository URL
- [ ] Add badges for build status, code coverage, etc.
- [ ] Update installation instructions if needed

### 2. Create Release

1. Go to GitHub repository > Releases
2. Click "Create a new release"
3. Tag version: `v1.0.0`
4. Title: `Initial Release`
5. Description: Add release notes
6. Publish release

### 3. Set Up Issue Templates

Create `.github/ISSUE_TEMPLATE/bug_report.md`:

```markdown
---
name: Bug report
about: Create a report to help us improve
title: ''
labels: bug
assignees: ''

---

**Describe the bug**
A clear and concise description of what the bug is.

**To Reproduce**
Steps to reproduce the behavior:
1. Run command '...'
2. See error

**Expected behavior**
A clear and concise description of what you expected to happen.

**Environment:**
 - OS: [e.g. Ubuntu 20.04]
 - Python version: [e.g. 3.9]
 - Package version: [e.g. 1.0.0]

**Additional context**
Add any other context about the problem here.
```

### 4. Set Up Pull Request Template

Create `.github/pull_request_template.md`:

```markdown
## Description
Brief description of changes

## Type of change
- [ ] Bug fix
- [ ] New feature
- [ ] Documentation update
- [ ] Other

## Testing
- [ ] Tested locally
- [ ] Added unit tests
- [ ] Updated documentation

## Checklist
- [ ] Code follows style guidelines
- [ ] Self-review completed
- [ ] Documentation updated
```

## Security Considerations

### 1. API Keys

- [ ] Never commit `.env` files
- [ ] Use GitHub Secrets for CI/CD
- [ ] Rotate API keys regularly
- [ ] Use environment-specific keys

### 2. Large Files

- [ ] Use Git LFS for large files if needed
- [ ] Consider excluding large result files
- [ ] Document data requirements

### 3. Dependencies

- [ ] Pin dependency versions
- [ ] Regularly update dependencies
- [ ] Monitor for security vulnerabilities

## Maintenance

### Regular Tasks

1. **Update Dependencies**: Monthly dependency updates
2. **Security Audits**: Regular security scans
3. **Documentation**: Keep documentation up to date
4. **Issues**: Respond to issues and pull requests

### Monitoring

- [ ] Set up repository insights
- [ ] Monitor API usage and costs
- [ ] Track performance metrics
- [ ] Monitor community engagement

## Troubleshooting

### Common Issues

1. **Import Errors**: Check Python path and virtual environment
2. **API Key Issues**: Verify environment variables
3. **Large File Issues**: Check `.gitignore` and Git LFS
4. **CI/CD Failures**: Check GitHub Actions logs

### Getting Help

- Create detailed issue reports
- Provide minimal reproduction examples
- Include environment information
- Check existing issues first

## Next Steps

After successful deployment:

1. **Share**: Share the repository with your community
2. **Document**: Add more detailed documentation
3. **Contribute**: Encourage contributions from others
4. **Maintain**: Regular maintenance and updates
5. **Scale**: Consider additional features and improvements 