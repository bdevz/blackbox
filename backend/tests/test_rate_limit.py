import asyncio
import json
import pytest
from unittest.mock import patch, MagicMock

from app.agents.base import BaseAgent, _api_semaphore


class TestRateLimiting:
    def test_semaphore_exists(self):
        """Module-level semaphore is created."""
        assert isinstance(_api_semaphore, asyncio.Semaphore)

    @pytest.mark.asyncio
    async def test_semaphore_bounds_concurrent_calls(self):
        """No more than max_concurrent calls run simultaneously."""
        active = 0
        max_active = 0
        lock = asyncio.Lock()

        async def mock_create(**kwargs):
            nonlocal active, max_active
            async with lock:
                active += 1
                if active > max_active:
                    max_active = active
            await asyncio.sleep(0.05)
            async with lock:
                active -= 1
            resp = MagicMock()
            resp.content = [MagicMock(text='{"confidence": 0.5}')]
            resp.usage = MagicMock(input_tokens=10, output_tokens=10)
            return resp

        class DummyAgent(BaseAgent):
            agent_type = "test"
            def build_prompt(self, context):
                return "system", "user"
            def validate_output(self, raw):
                return json.loads(raw)

        with patch("app.agents.base._api_semaphore", asyncio.Semaphore(2)):
            agent = DummyAgent.__new__(DummyAgent)
            agent.model = "claude-sonnet-4-6"
            agent.max_tokens = 100
            agent.temperature = 0.1
            agent.client = MagicMock()
            agent.client.messages = MagicMock()
            agent.client.messages.create = mock_create

            with patch("app.agents.base.SessionLocal") as mock_session:
                mock_db = MagicMock()
                mock_session.return_value = mock_db

                tasks = [agent.run({"test": True}) for _ in range(6)]
                await asyncio.gather(*tasks)

        assert max_active <= 2
