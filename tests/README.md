# API Tests

This directory contains automated tests for the DonorIQ API.

## Running Tests

### Prerequisites
1. Make sure the API server is running:
   ```bash
   cd ../mtf-backend
   source venv/bin/activate
   python run.py
   ```

2. Ensure you have the required dependencies:
   ```bash
   pip install requests
   ```

### Run All Tests
```bash
python test_api.py
```

## Test Coverage

The test suite covers:

### ✅ Core Functionality
- Health check endpoint
- Authentication and login
- User management (admin only)
- Donor CRUD operations
- Document management

### ✅ Error Handling
- Unauthorized access (401)
- Invalid tokens (401)
- Non-existent resources (404)
- Duplicate data validation (400)

### ✅ Security
- Token validation
- Logout functionality
- Role-based access control

### ✅ Edge Cases
- Empty responses
- Invalid requests
- Boundary conditions

## Test Results

When all tests pass, you'll see:
```
📊 Test Results: 8/8 tests passed
🎉 All tests passed!
```

## Adding New Tests

To add new test cases:

1. Create a new test method in the `APITester` class
2. Add the test to the `tests` list in `run_all_tests()`
3. Follow the existing pattern for error handling and logging

Example:
```python
def test_new_endpoint(self) -> bool:
    """Test new endpoint functionality."""
    try:
        response = requests.get(f"{BASE_URL}/api/v1/new-endpoint", headers=self.headers)
        if response.status_code == 200:
            print("✅ New endpoint working")
            return True
        else:
            print(f"❌ New endpoint failed: {response.status_code}")
            return False
    except Exception as e:
        print(f"❌ New endpoint error: {e}")
        return False
```
