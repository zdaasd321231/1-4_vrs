#!/usr/bin/env python3
import asyncio
import aiohttp
import json
import socket
import time
import os
from datetime import datetime
import unittest
import websockets
import logging
from urllib.parse import urljoin

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Get backend URL from environment
BACKEND_URL = os.environ.get('REACT_APP_BACKEND_URL', 'https://10ae72f5-187b-478a-856f-0de96a51723f.preview.emergentagent.com')
API_URL = urljoin(BACKEND_URL, '/api')

class VNCManagementSystemTest(unittest.TestCase):
    """Test suite for VNC Management System backend"""
    
    async def setUp(self):
        """Set up test environment"""
        self.session = aiohttp.ClientSession()
        self.connection_id = None
        self.installation_key = None
        
        # Create a test connection for use in tests
        await self.create_test_connection()
    
    async def tearDown(self):
        """Clean up after tests"""
        # Delete test connection if it exists
        if self.connection_id:
            try:
                await self.session.delete(f"{API_URL}/connections/{self.connection_id}")
            except Exception as e:
                logger.error(f"Error deleting test connection: {e}")
        
        await self.session.close()
    
    async def create_test_connection(self):
        """Create a test VNC connection for testing"""
        connection_data = {
            "name": f"Test Connection {datetime.now().strftime('%Y%m%d%H%M%S')}",
            "location": "Test Location",
            "country": "Russia",
            "city": "Moscow"
        }
        
        async with self.session.post(f"{API_URL}/connections", json=connection_data) as response:
            if response.status == 200:
                data = await response.json()
                self.connection_id = data.get("id")
                self.installation_key = data.get("installation_key")
                logger.info(f"Created test connection with ID: {self.connection_id}")
                return data
            else:
                text = await response.text()
                logger.error(f"Failed to create test connection: {text}")
                return None
    
    async def test_health_check(self):
        """Test the health check endpoint"""
        async with self.session.get(f"{API_URL}/health") as response:
            self.assertEqual(response.status, 200)
            data = await response.json()
            self.assertEqual(data["status"], "healthy")
            logger.info("Health check endpoint is working")
    
    async def test_get_connections(self):
        """Test retrieving all VNC connections"""
        async with self.session.get(f"{API_URL}/connections") as response:
            self.assertEqual(response.status, 200)
            data = await response.json()
            self.assertIsInstance(data, list)
            logger.info(f"Retrieved {len(data)} connections")
    
    async def test_get_connection_by_id(self):
        """Test retrieving a specific VNC connection"""
        if not self.connection_id:
            self.skipTest("No test connection available")
        
        async with self.session.get(f"{API_URL}/connections/{self.connection_id}") as response:
            self.assertEqual(response.status, 200)
            data = await response.json()
            self.assertEqual(data["id"], self.connection_id)
            logger.info(f"Retrieved connection: {data['name']}")
    
    async def test_update_connection_status(self):
        """Test updating a connection's status"""
        if not self.connection_id:
            self.skipTest("No test connection available")
        
        # Test each valid status
        for status in ["active", "inactive", "installing", "error"]:
            async with self.session.put(f"{API_URL}/connections/{self.connection_id}/status?status={status}") as response:
                self.assertEqual(response.status, 200)
                data = await response.json()
                self.assertEqual(data["message"], "Status updated successfully")
                logger.info(f"Updated connection status to {status}")
            
            # Verify the status was updated
            async with self.session.get(f"{API_URL}/connections/{self.connection_id}") as response:
                data = await response.json()
                self.assertEqual(data["status"], status)
    
    async def test_invalid_status_update(self):
        """Test updating with an invalid status"""
        if not self.connection_id:
            self.skipTest("No test connection available")
        
        async with self.session.put(f"{API_URL}/connections/{self.connection_id}/status?status=invalid") as response:
            self.assertEqual(response.status, 400)
            logger.info("Invalid status correctly rejected")
    
    async def test_generate_installer(self):
        """Test generating a PowerShell installer script"""
        if not self.connection_id:
            self.skipTest("No test connection available")
        
        async with self.session.get(f"{API_URL}/generate-installer/{self.connection_id}") as response:
            self.assertEqual(response.status, 200)
            content = await response.text()
            
            # Check if the script contains essential components
            self.assertIn("# VNC Auto-Installation Script", content)
            self.assertIn(self.installation_key, content)
            self.assertIn("TightVNC", content)
            logger.info("PowerShell installer generated successfully")
    
    async def test_register_machine(self):
        """Test registering a machine with an installation key"""
        if not self.installation_key:
            self.skipTest("No installation key available")
        
        registration_data = {
            "installation_key": self.installation_key,
            "machine_name": "Test Machine",
            "ip_address": "192.168.1.100",
            "status": "active"
        }
        
        async with self.session.post(f"{API_URL}/register-machine", json=registration_data) as response:
            self.assertEqual(response.status, 200)
            data = await response.json()
            self.assertEqual(data["message"], "Machine registered successfully")
            logger.info("Machine registered successfully")
            
            # Verify the connection was updated with the IP address
            async with self.session.get(f"{API_URL}/connections/{self.connection_id}") as conn_response:
                conn_data = await conn_response.json()
                self.assertEqual(conn_data["ip_address"], "192.168.1.100")
                self.assertEqual(conn_data["status"], "active")
    
    async def test_vnc_connection_check(self):
        """Test VNC connection status check by simulating a connection"""
        if not self.connection_id:
            self.skipTest("No test connection available")
        
        # First, register a machine with our test connection
        registration_data = {
            "installation_key": self.installation_key,
            "machine_name": "Test Machine",
            "ip_address": "127.0.0.1",  # Use localhost for testing
            "status": "inactive"  # Start as inactive
        }
        
        async with self.session.post(f"{API_URL}/register-machine", json=registration_data) as response:
            self.assertEqual(response.status, 200)
            
            # Start a mock VNC server on port 5900
            server_socket = None
            try:
                server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                server_socket.bind(('127.0.0.1', 5900))
                server_socket.listen(1)
                logger.info("Started mock VNC server on port 5900")
                
                # Wait for the background task to detect the connection (runs every 30 seconds)
                # For testing, we'll wait a bit and then check if the status was updated
                await asyncio.sleep(35)  # Wait slightly longer than the 30-second check interval
                
                # Check if the connection status was updated to active
                async with self.session.get(f"{API_URL}/connections/{self.connection_id}") as conn_response:
                    conn_data = await conn_response.json()
                    self.assertEqual(conn_data["status"], "active")
                    logger.info("VNC status auto-check system correctly detected active connection")
            
            except Exception as e:
                logger.error(f"Error in VNC connection test: {e}")
                self.fail(f"VNC connection test failed: {e}")
            
            finally:
                if server_socket:
                    server_socket.close()
    
    async def test_activity_logs(self):
        """Test activity logging functionality"""
        if not self.connection_id:
            self.skipTest("No test connection available")
        
        # Perform an action that generates a log
        await self.test_update_connection_status()
        
        # Check the logs for this connection
        async with self.session.get(f"{API_URL}/logs/{self.connection_id}") as response:
            self.assertEqual(response.status, 200)
            logs = await response.json()
            self.assertIsInstance(logs, list)
            self.assertGreater(len(logs), 0)
            
            # Verify log structure
            log = logs[0]
            self.assertIn("id", log)
            self.assertIn("connection_id", log)
            self.assertIn("action", log)
            self.assertIn("details", log)
            self.assertIn("timestamp", log)
            
            logger.info(f"Activity logging is working, found {len(logs)} logs")
    
    async def test_system_stats(self):
        """Test system statistics endpoint"""
        async with self.session.get(f"{API_URL}/stats") as response:
            self.assertEqual(response.status, 200)
            stats = await response.json()
            
            # Verify stats structure
            self.assertIn("total_connections", stats)
            self.assertIn("active_connections", stats)
            self.assertIn("inactive_connections", stats)
            self.assertIn("recent_activity_24h", stats)
            
            logger.info(f"System stats: {stats}")
    
    async def test_system_info(self):
        """Test system info endpoint"""
        async with self.session.get(f"{API_URL}/system/info") as response:
            self.assertEqual(response.status, 200)
            info = await response.json()
            
            # Verify info structure
            self.assertIn("vnc_management_version", info)
            self.assertIn("total_websocket_connections", info)
            self.assertIn("system_time", info)
            self.assertIn("features", info)
            
            logger.info(f"System info retrieved successfully")

async def run_tests():
    """Run all tests"""
    # Create test suite
    test_suite = unittest.TestSuite()
    test_loader = unittest.TestLoader()
    
    # Add test methods to the suite
    test_case = VNCManagementSystemTest()
    test_methods = [
        test_case.test_health_check,
        test_case.test_get_connections,
        test_case.test_get_connection_by_id,
        test_case.test_update_connection_status,
        test_case.test_invalid_status_update,
        test_case.test_generate_installer,
        test_case.test_register_machine,
        test_case.test_vnc_connection_check,
        test_case.test_activity_logs,
        test_case.test_system_stats,
        test_case.test_system_info
    ]
    
    # Run setup
    await test_case.setUp()
    
    # Run each test
    results = {"passed": [], "failed": []}
    for test_method in test_methods:
        test_name = test_method.__name__
        try:
            logger.info(f"Running test: {test_name}")
            await test_method()
            results["passed"].append(test_name)
            logger.info(f"✅ Test passed: {test_name}")
        except Exception as e:
            results["failed"].append({"name": test_name, "error": str(e)})
            logger.error(f"❌ Test failed: {test_name} - {e}")
    
    # Run teardown
    await test_case.tearDown()
    
    return results

if __name__ == "__main__":
    # Set up event loop
    loop = asyncio.get_event_loop()
    
    # Run tests
    logger.info("Starting VNC Management System backend tests...")
    results = loop.run_until_complete(run_tests())
    
    # Print summary
    print("\n=== TEST RESULTS ===")
    print(f"Passed: {len(results['passed'])}/{len(results['passed']) + len(results['failed'])}")
    
    if results["passed"]:
        print("\n✅ PASSED TESTS:")
        for test in results["passed"]:
            print(f"  - {test}")
    
    if results["failed"]:
        print("\n❌ FAILED TESTS:")
        for test in results["failed"]:
            print(f"  - {test['name']}: {test['error']}")
    
    # Exit with appropriate code
    exit_code = 0 if not results["failed"] else 1
    exit(exit_code)