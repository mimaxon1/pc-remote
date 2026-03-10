# Testing Guide

## Running Tests

### Prerequisites
```bash
pip install -r requirements.txt
```

### Run All Tests
```bash
pytest
```

### Run Specific Test File
```bash
pytest test_auth.py -v
pytest test_main.py -v
pytest test_audio.py -v
```

### Run Specific Test
```bash
pytest test_auth.py::TestPasswordHash::test_password_hash_creation -v
```

### Run with Coverage
```bash
pip install pytest-cov
pytest --cov=. --cov-report=html
```

## Test Structure

### test_auth.py
- **TestPasswordHash**: Password hashing and verification
- **TestTokenStore**: Token generation, verification, and expiration
- **TestAuthManager**: Complete authentication lifecycle

### test_main.py
- **TestPortChecking**: Port availability verification
- **TestCORSSetup**: CORS middleware configuration
- **TestHealthEndpoint**: Health check endpoint validation
- **TestServerShutdown**: Graceful server shutdown

### test_audio.py
- **TestAudioHelpers**: Audio system COM initialization
- **TestAudioDevices**: Device enumeration and selection
- **TestAudioVolume**: Volume control operations
- **TestAudioErrorHandling**: Exception handling in audio operations

## Writing New Tests

Follow this pattern:

```python
import pytest
from unittest.mock import patch, MagicMock

class TestNewFeature:
    """Test description."""
    
    def setup_method(self):
        """Setup before each test."""
        pass
    
    def teardown_method(self):
        """Cleanup after each test."""
        pass
    
    def test_something(self):
        """Test case description."""
        # Arrange
        # Act
        # Assert
        pass
    
    @patch("module.function")
    def test_with_mock(self, mock_func):
        """Test with mocked dependencies."""
        pass
```

## CI/CD Integration

Tests are designed to run in CI pipelines:
- No external dependencies required (all mocked)
- No GUI initialization needed
- Fast execution (~1-2 seconds)
- Clear pass/fail output

## Troubleshooting

### ImportError when running tests
```bash
# Add current directory to PYTHONPATH
set PYTHONPATH=%CD%
pytest
```

### COM initialization errors
- These are expected to fail gracefully
- Tests mock COM interactions
- No actual Windows audio device needed

### Permission errors
- Run in project directory
- Ensure write access to test directories

## Success Criteria

- ✓ All tests pass with 0 failures
- ✓ No warnings during test execution  
- ✓ Coverage includes critical functions (auth, port checking, shutdown)
- ✓ Error handling validated
