from dataclasses import dataclass, field
from typing import List, Optional, Dict, Any
from pathlib import Path
import asyncio
import logging
from datetime import datetime
import io
from PIL import Image
import moondream as md
from playwright.async_api import async_playwright, Page, Browser, BrowserContext
import json

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

@dataclass
class Config:
    model_path: Path
    screenshot_dir: Path
    default_viewport: dict[str, int] = field(
        default_factory=lambda: {'width': 1280, 'height': 720}
    )
    default_timeout: int = 30000
    retry_attempts: int = 3
    retry_delay: int = 1000  # ms
    
    def __post_init__(self):
        """Ensure directories exist and model file is present"""
        if not self.model_path.exists():
            raise FileNotFoundError(f"Model not found at {self.model_path}")
        self.screenshot_dir.mkdir(parents=True, exist_ok=True)

@dataclass
class UIQuery:
    question: str
    expected_response: str
    screenshot_interval_ms: Optional[int] = None
    tolerance: float = 0.8

@dataclass
class UITest:
    name: str
    url: str
    queries: List[UIQuery]
    viewport: Optional[dict[str, int]] = None

@dataclass
class QueryResult:
    query: UIQuery
    actual_response: str
    screenshots: List[Path]
    passed: Optional[bool] = None
    error: Optional[str] = None

@dataclass
class TestResult:
    test: UITest
    query_results: List[QueryResult]
    start_time: datetime
    end_time: Optional[datetime] = None
    error: Optional[str] = None

    def to_dict(self) -> dict:
        return {
            'test_name': self.test.name,
            'url': self.test.url,
            'start_time': self.start_time.isoformat(),
            'end_time': self.end_time.isoformat() if self.end_time else None,
            'error': self.error,
            'queries': [
                {
                    'question': qr.query.question,
                    'expected': qr.query.expected_response,
                    'actual': qr.actual_response,
                    'passed': qr.passed,
                    'error': qr.error,
                    'screenshots': [str(s) for s in qr.screenshots]
                }
                for qr in self.query_results
            ]
        }

class ScreenshotManager:
    def __init__(self, config: Config):
        self.config = config
        
    async def _setup_browser(self) -> tuple[Browser, BrowserContext, Page]:
        """Initialize browser with retry logic"""
        for attempt in range(self.config.retry_attempts):
            try:
                playwright = await async_playwright().start()
                browser = await playwright.chromium.launch()
                context = await browser.new_context(
                    viewport=self.config.default_viewport,
                    record_video_dir=self.config.screenshot_dir / "videos"
                )
                page = await context.new_page()
                return browser, context, page
            except Exception as e:
                if attempt == self.config.retry_attempts - 1:
                    raise
                logger.warning(f"Browser setup failed, attempt {attempt + 1}: {e}")
                await asyncio.sleep(self.config.retry_delay / 1000)

    async def capture(self, test: UITest, query: UIQuery) -> List[Path]:
        """Capture screenshots for a query"""
        browser, context, page = await self._setup_browser()
        screenshots: List[Path] = []
        
        try:
            await page.goto(test.url, wait_until="networkidle")
            
            if query.screenshot_interval_ms:
                # Dynamic content - multiple screenshots
                duration = query.screenshot_interval_ms * 5  # Take 5 screenshots by default
                for i in range(0, duration, query.screenshot_interval_ms):
                    screenshot_path = self._get_screenshot_path(test, query, i)
                    await page.screenshot(path=screenshot_path)
                    screenshots.append(screenshot_path)
                    await asyncio.sleep(query.screenshot_interval_ms / 1000)
            else:
                # Static content - single screenshot
                screenshot_path = self._get_screenshot_path(test, query)
                await page.screenshot(path=screenshot_path)
                screenshots.append(screenshot_path)
                
        finally:
            await context.close()
            await browser.close()
            
        return screenshots

    def _get_screenshot_path(self, test: UITest, query: UIQuery, index: Optional[int] = None) -> Path:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"{test.name}_{timestamp}"
        if index is not None:
            filename += f"_{index}"
        return self.config.screenshot_dir / f"{filename}.png"

class VisionAnalyzer:
    def __init__(self, config: Config):
        try:
            self.model = md.vl(model=str(config.model_path))
        except Exception as e:
            logger.error(f"Failed to load model: {e}")
            raise

    def analyze(self, screenshots: List[Path], query: UIQuery) -> str:
        answers = []
        
        for screenshot_path in screenshots:
            try:
                with Image.open(screenshot_path) as image:
                    encoded_image = self.model.encode_image(image)
                    result = self.model.query(encoded_image, query.question)
                    answers.append(result["answer"])
            except Exception as e:
                logger.error(f"Failed to analyze screenshot {screenshot_path}: {e}")
                raise

        return answers[-1] if answers else ""

class TestRunner:
    def __init__(self, config: Config):
        self.config = config
        self.screenshot_manager = ScreenshotManager(config)
        self.analyzer = VisionAnalyzer(config)

    async def run(self, test: UITest) -> TestResult:
        logger.info(f"Starting test: {test.name}")
        start_time = datetime.now()
        
        result = TestResult(
            test=test,
            query_results=[],
            start_time=start_time
        )
        
        try:
            for query in test.queries:
                logger.info(f"Running query: {query.question}")
                
                screenshots = await self.screenshot_manager.capture(test, query)
                actual_response = self.analyzer.analyze(screenshots, query)
                
                query_result = QueryResult(
                    query=query,
                    actual_response=actual_response,
                    screenshots=screenshots,
                )
                result.query_results.append(query_result)
                
                logger.info(f"Query complete. Expected: {query.expected_response}, "
                          f"Actual: {actual_response}")
                
        except Exception as e:
            logger.error(f"Test failed: {e}")
            result.error = str(e)
        finally:
            result.end_time = datetime.now()
            self._save_results(result)
            
        return result

    def _save_results(self, result: TestResult):
        results_file = self.config.screenshot_dir / "results.json"
        try:
            if results_file.exists():
                with open(results_file, 'r') as f:
                    results = json.load(f)
            else:
                results = []
                
            results.append(result.to_dict())
            
            with open(results_file, 'w') as f:
                json.dump(results, f, indent=2)
        except Exception as e:
            logger.error(f"Failed to save results: {e}")