import pytest
import threading
import http.server
import socketserver
from pathlib import Path
import time
import os
import logging
from contextlib import contextmanager
from moontest import Config, TestRunner

logger = logging.getLogger(__name__)

class TestServer:
    def __init__(self, port=8000):
        self.port = port
        # Updated path to reflect new structure
        self.directory = Path(__file__).parent / "test_pages"
        self.httpd = None
        self.server_thread = None
        
        # Change to the test_pages directory
        self._original_dir = Path.cwd()
        os.chdir(self.directory)

    def start(self):
        """Start the server in a separate thread"""
        handler = http.server.SimpleHTTPRequestHandler
        self.httpd = socketserver.TCPServer(("", self.port), handler)
        
        self.server_thread = threading.Thread(target=self.httpd.serve_forever)
        self.server_thread.daemon = True
        self.server_thread.start()
        
        # Give the server a moment to start
        time.sleep(1)
        logger.info(f"Server started at http://localhost:{self.port}")

    def stop(self):
        """Stop the server"""
        if self.httpd:
            self.httpd.shutdown()
            self.httpd.server_close()
            # Restore original directory
            os.chdir(self._original_dir)
            logger.info("Server stopped")

@pytest.fixture(scope="session")
def test_server():
    """Fixture that starts the server before tests and stops it after"""
    server = TestServer()
    server.start()
    yield server
    server.stop()

@pytest.fixture
def config():
    return Config(
        model_path=Path("models/moondream-0.5b-int8.mf"),
        screenshot_dir=Path("artifacts/screenshots")
    )

@pytest.fixture
def runner(config):
    return TestRunner(config)