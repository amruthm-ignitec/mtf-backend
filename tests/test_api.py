#!/usr/bin/env python3
"""
API Test Suite for DonorIQ Backend
Usage: python tests/test_api.py
"""
import requests
import json
import sys
from typing import Dict, Any

BASE_URL = "http://localhost:8000"

class APITester:
    def __init__(self):
        self.token = None
        self.headers = {}
    
    def login(self, email: str = "admin@donoriq.com", password: str = "admin123") -> bool:
        """Login and get authentication token."""
        login_data = {"email": email, "password": password}
        
        try:
            response = requests.post(f"{BASE_URL}/api/v1/auth/login", json=login_data)
            if response.status_code == 200:
                token_data = response.json()
                self.token = token_data.get("access_token")
                self.headers = {"Authorization": f"Bearer {self.token}"}
                print(f"✅ Authentication successful!")
                return True
            else:
                print(f"❌ Authentication failed: {response.text}")
                return False
        except Exception as e:
            print(f"❌ Authentication error: {e}")
            return False
    
    def test_health_check(self) -> bool:
        """Test health check endpoint."""
        try:
            response = requests.get(f"{BASE_URL}/health")
            if response.status_code == 200:
                print("✅ Health check passed")
                return True
            else:
                print(f"❌ Health check failed: {response.status_code}")
                return False
        except Exception as e:
            print(f"❌ Health check error: {e}")
            return False
    
    def test_current_user(self) -> bool:
        """Test current user endpoint."""
        try:
            response = requests.get(f"{BASE_URL}/api/v1/auth/me", headers=self.headers)
            if response.status_code == 200:
                user_data = response.json()
                print(f"✅ Current user: {user_data['full_name']} ({user_data['role']})")
                return True
            else:
                print(f"❌ Current user test failed: {response.status_code}")
                return False
        except Exception as e:
            print(f"❌ Current user error: {e}")
            return False
    
    def test_donor_crud(self) -> bool:
        """Test donor CRUD operations."""
        try:
            # Create donor with unique ID
            import time
            unique_id = f"TEST{int(time.time())}"
            donor_data = {
                "unique_donor_id": unique_id,
                "name": "Test Donor",
                "age": 30,
                "gender": "Female",
                "is_priority": False
            }
            
            response = requests.post(f"{BASE_URL}/api/v1/donors/", json=donor_data, headers=self.headers)
            if response.status_code != 200:
                print(f"❌ Create donor failed: {response.text}")
                return False
            
            donor = response.json()
            donor_id = donor["id"]
            print(f"✅ Created donor: {donor['name']} (ID: {donor_id})")
            
            # Get donor
            response = requests.get(f"{BASE_URL}/api/v1/donors/{donor_id}", headers=self.headers)
            if response.status_code != 200:
                print(f"❌ Get donor failed: {response.status_code}")
                return False
            
            print(f"✅ Retrieved donor: {response.json()['name']}")
            
            # Update priority
            priority_data = {"is_priority": True}
            response = requests.put(f"{BASE_URL}/api/v1/donors/{donor_id}/priority", json=priority_data, headers=self.headers)
            if response.status_code != 200:
                print(f"❌ Update priority failed: {response.status_code}")
                return False
            
            print(f"✅ Updated donor priority")
            
            # List donors
            response = requests.get(f"{BASE_URL}/api/v1/donors/", headers=self.headers)
            if response.status_code != 200:
                print(f"❌ List donors failed: {response.status_code}")
                return False
            
            donors = response.json()
            print(f"✅ Listed {len(donors)} donors")
            
            return True
            
        except Exception as e:
            print(f"❌ Donor CRUD error: {e}")
            return False
    
    def test_users_endpoint(self) -> bool:
        """Test users endpoint (admin only)."""
        try:
            response = requests.get(f"{BASE_URL}/api/v1/users/", headers=self.headers)
            if response.status_code == 200:
                users = response.json()
                print(f"✅ Listed {len(users)} users")
                return True
            else:
                print(f"❌ Users endpoint failed: {response.status_code}")
                return False
        except Exception as e:
            print(f"❌ Users endpoint error: {e}")
            return False
    
    def test_error_handling(self) -> bool:
        """Test error handling scenarios."""
        try:
            # Test unauthorized access
            response = requests.get(f"{BASE_URL}/api/v1/auth/me")
            if response.status_code != 401:
                print(f"❌ Unauthorized access test failed: {response.status_code}")
                return False
            print("✅ Unauthorized access properly rejected")
            
            # Test invalid token
            invalid_headers = {"Authorization": "Bearer invalid_token"}
            response = requests.get(f"{BASE_URL}/api/v1/auth/me", headers=invalid_headers)
            if response.status_code != 401:
                print(f"❌ Invalid token test failed: {response.status_code}")
                return False
            print("✅ Invalid token properly rejected")
            
            # Test non-existent donor
            response = requests.get(f"{BASE_URL}/api/v1/donors/999", headers=self.headers)
            if response.status_code != 404:
                print(f"❌ Non-existent donor test failed: {response.status_code}")
                return False
            print("✅ Non-existent donor properly handled")
            
            # Test duplicate donor creation
            duplicate_donor = {
                "unique_donor_id": "TEST001",  # This should already exist
                "name": "Duplicate Donor",
                "age": 30,
                "gender": "Male",
                "is_priority": False
            }
            response = requests.post(f"{BASE_URL}/api/v1/donors/", json=duplicate_donor, headers=self.headers)
            if response.status_code != 400:
                print(f"❌ Duplicate donor test failed: {response.status_code}")
                return False
            print("✅ Duplicate donor properly rejected")
            
            return True
            
        except Exception as e:
            print(f"❌ Error handling test error: {e}")
            return False
    
    def test_security(self) -> bool:
        """Test security features."""
        try:
            # Test logout
            response = requests.post(f"{BASE_URL}/api/v1/auth/logout", headers=self.headers)
            if response.status_code != 200:
                print(f"❌ Logout test failed: {response.status_code}")
                return False
            print("✅ Logout endpoint working")
            
            # Test that token still works after logout (logout is client-side)
            response = requests.get(f"{BASE_URL}/api/v1/auth/me", headers=self.headers)
            if response.status_code != 200:
                print(f"❌ Token validation after logout failed: {response.status_code}")
                return False
            print("✅ Token remains valid after logout (as expected)")
            
            return True
            
        except Exception as e:
            print(f"❌ Security test error: {e}")
            return False
    
    def test_documents_endpoint(self) -> bool:
        """Test documents endpoint."""
        try:
            # Test documents list
            response = requests.get(f"{BASE_URL}/api/v1/documents/", headers=self.headers)
            if response.status_code != 200:
                print(f"❌ Documents list failed: {response.status_code}")
                return False
            print("✅ Documents list endpoint working")
            
            # Test documents for specific donor
            response = requests.get(f"{BASE_URL}/api/v1/documents/donor/1", headers=self.headers)
            if response.status_code != 200:
                print(f"❌ Donor documents failed: {response.status_code}")
                return False
            print("✅ Donor documents endpoint working")
            
            return True
            
        except Exception as e:
            print(f"❌ Documents test error: {e}")
            return False
    
    def run_all_tests(self) -> bool:
        """Run all API tests."""
        print("🧪 Starting API Test Suite")
        print("=" * 50)
        
        tests = [
            ("Health Check", self.test_health_check),
            ("Authentication", lambda: self.login()),
            ("Current User", self.test_current_user),
            ("Donor CRUD", self.test_donor_crud),
            ("Users Endpoint", self.test_users_endpoint),
            ("Error Handling", self.test_error_handling),
            ("Security Tests", self.test_security),
            ("Documents Endpoint", self.test_documents_endpoint),
        ]
        
        passed = 0
        total = len(tests)
        
        for test_name, test_func in tests:
            print(f"\n🔍 Testing: {test_name}")
            try:
                if test_func():
                    passed += 1
                else:
                    print(f"❌ {test_name} failed")
            except Exception as e:
                print(f"❌ {test_name} error: {e}")
        
        print("\n" + "=" * 50)
        print(f"📊 Test Results: {passed}/{total} tests passed")
        
        if passed == total:
            print("🎉 All tests passed!")
            return True
        else:
            print("⚠️  Some tests failed!")
            return False

if __name__ == "__main__":
    tester = APITester()
    success = tester.run_all_tests()
    sys.exit(0 if success else 1)
