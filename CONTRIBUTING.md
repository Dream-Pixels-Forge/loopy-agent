# 🤝 Contributing to loopy-agent

Thank you for your interest in contributing to loopy-agent! This document provides guidelines and information for contributors.

---

## 📋 Table of Contents

- [Code of Conduct](#code-of-conduct)
- [Getting Started](#getting-started)
- [Development Setup](#development-setup)
- [Making Changes](#making-changes)
- [Testing](#testing)
- [Pull Request Process](#pull-request-process)
- [Style Guidelines](#style-guidelines)
- [Adding Features](#adding-features)
- [Bug Reports](#bug-reports)

---

## 📜 Code of Conduct

Please read and follow our [Code of Conduct](CODE_OF_CONDUCT.md). We are committed to providing a welcoming and inclusive environment for everyone.

---

## 🚀 Getting Started

1. **Fork the repository** on GitHub
2. **Clone your fork** locally:
   ```bash
   git clone https://github.com/your-username/loopy-agent.git
   cd loopy-agent
   ```
3. **Add upstream remote**:
   ```bash
   git remote add upstream https://github.com/Dream-Pixels-Forge/loopy-agent.git
   ```

---

## 🛠️ Development Setup

### Prerequisites

- Python 3.11+
- pip or poetry

### Installation

```bash
# Create virtual environment
python -m venv venv
source venv/bin/activate  # Linux/Mac
# or
venv\Scripts\activate  # Windows

# Install in development mode
pip install -e ".[dev]"

# Or install from PyPI
pip install loopy-agent[dev]

# Install pre-commit hooks (optional)
pip install pre-commit
pre-commit install
```

### Project Structure

```
loopy/
├── loopy/              # Source code
│   ├── __init__.py     # Public API exports
│   ├── loop.py         # Agentic loop engine
│   ├── gateway.py      # AI Gateway
│   ├── guardrails.py   # Guardrails
│   ├── evals.py        # Evals + EvalGate
│   ├── cache.py        # LLM Cache
│   ├── observe.py      # Observability
│   ├── mcp.py          # MCP Client
│   ├── agents.py       # Multi-Agent
│   ├── middleware.py    # Middleware
│   ├── cli.py          # CLI
│   └── plugins/        # First-party plugins
│       ├── __init__.py
│       ├── rag.py
│       ├── tools.py
│       ├── memory.py
│       ├── audio.py
│       └── marketplace.py
├── tests/              # Test suite
├── docs/               # Documentation
├── examples/           # Usage examples
└── pyproject.toml      # Project configuration
```

---

## ✏️ Making Changes

### Branch Naming

Use descriptive branch names:
- `feature/add-new-middleware`
- `fix/cache-eviction-bug`
- `docs/update-api-reference`
- `refactor/improve-gateway`

### Commit Messages

Follow [Conventional Commits](https://www.conventionalcommits.org/):
- `feat: add new RetryMiddleware`
- `fix: resolve cache eviction issue`
- `docs: update API reference`
- `refactor: improve gateway performance`
- `test: add tests for RAG plugin`

---

## 🧪 Testing

### Running Tests

```bash
# Run all tests
pytest

# Run with verbose output
pytest -v

# Run specific test file
pytest tests/test_loopy.py

# Run specific test class
pytest tests/test_loopy.py::TestAgentLoop

# Run with coverage
pytest --cov=loopy --cov-report=html
```

### Writing Tests

- Place tests in `tests/` directory
- Name test files `test_<module>.py`
- Use `pytest` fixtures when appropriate
- Aim for high coverage (80%+ target)

Example test:

```python
import asyncio
from loopy import AgentLoop, LoopConfig

def test_basic_loop():
    """Test basic agent loop execution."""
    async def planner(history):
        return "Test plan"
    
    async def actor(plan):
        return "Test action"
    
    loop = AgentLoop(LoopConfig(
        planner=planner,
        actor=actor,
        max_steps=1,
    ))
    
    async def run_test():
        results = await loop.run()
        assert len(results) == 1
        assert results[0].status == StepStatus.COMPLETE
    
    asyncio.run(run_test())
```

---

## 🔀 Pull Request Process

1. **Create a feature branch** from `main`
2. **Make your changes** with tests
3. **Run the test suite** to ensure everything passes
4. **Update documentation** if needed
5. **Submit a pull request** with:
   - Clear title and description
   - Link to related issues
   - Screenshots (if applicable)

### PR Checklist

- [ ] Tests pass locally
- [ ] New tests added for new features
- [ ] Documentation updated
- [ ] Type hints added/updated
- [ ] No breaking changes (or documented in CHANGELOG)
- [ ] Code follows style guidelines

---

## 📏 Style Guidelines

### Python Style

- Follow PEP 8
- Use type hints consistently
- Maximum line length: 100 characters
- Use f-strings for string formatting

### Docstrings

Use Google-style docstrings:

```python
def my_function(param1: str, param2: int = 10) -> bool:
    """
    Brief description of the function.

    Longer description if needed.

    Args:
        param1: Description of param1
        param2: Description of param2

    Returns:
        Description of return value

    Raises:
        ValueError: When something is wrong

    Example:
        >>> result = my_function("hello", 5)
        >>> print(result)
        True
    """
```

### Import Order

```python
# Standard library
import asyncio
import logging
from dataclasses import dataclass
from typing import Any

# Third-party
import httpx

# Local
from loopy.gateway import Gateway
```

---

## ➕ Adding Features

### Adding a New Module

1. Create `loopy/new_module.py`
2. Add exports to `loopy/__init__.py`
3. Add to `__all__` list
4. Write tests in `tests/test_new_module.py`
5. Update documentation

### Adding a New Plugin

1. Create `loopy/plugins/new_plugin.py`
2. Implement `Plugin` base class
3. Add lazy import to `loopy/plugins/__init__.py`
4. Write tests in `tests/test_loopy.py`
5. Document in docs/README.md

### Adding Middleware

1. Create class inheriting from `Middleware`
2. Implement `before()`, `after()`, and/or `on_error()`
3. Add to `loopy/middleware.py`
4. Export in `loopy/__init__.py`
5. Write tests

---

## 🐛 Bug Reports

When filing a bug report, please include:

1. **Environment** (Python version, OS)
2. **Steps to reproduce**
3. **Expected behavior**
4. **Actual behavior**
5. **Error messages/tracebacks**
6. **Minimal code example**

---

## 📚 Resources

- [Documentation](docs/README.md)
- [API Reference](docs/README.md#api-reference)
- [Examples](examples/)
- [Changelog](CHANGELOG.md)

---

## 🙏 Thank You!

Thank you for contributing to loopy-agent! Your help is appreciated.
