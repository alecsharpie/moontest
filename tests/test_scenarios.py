import pytest
from pathlib import Path
from src.ui_tester import UITest, UIQuery

@pytest.mark.asyncio
async def test_simple_button(test_server, runner):
    test = UITest(
        name="Simple Button Test",
        url=f"http://localhost:{test_server.port}/static/passing/simple_button/",
        queries=[
            UIQuery(
                question="Is there a blue button labeled 'Submit' in the center?",
                expected_response="Yes"
            ),
            UIQuery(
                question="What color is the button?",
                expected_response="The button is blue"
            )
        ]
    )
    
    result = await runner.run(test)
    assert result.error is None
    assert len(result.query_results) == 2
    assert all(qr.error is None for qr in result.query_results)

@pytest.mark.asyncio
async def test_broken_animation(test_server, runner):
    test = UITest(
        name="Broken Animation Test",
        url=f"http://localhost:{test_server.port}/static/failing/broken_animation/",
        queries=[
            UIQuery(
                question="Is there a green button labeled 'Click Me'?",
                expected_response="Yes"
            ),
            UIQuery(
                question="Does the loading spinner complete its animation?",
                expected_response="No, the spinner freezes after starting",
                screenshot_interval_ms=500
            )
        ]
    )
    
    result = await runner.run(test)
    assert result.error is None
    assert len(result.query_results) == 2