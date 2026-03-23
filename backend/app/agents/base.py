import asyncio
import hashlib
import re
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass

from anthropic import AsyncAnthropic

from app.config import settings
from app.models.database import SessionLocal, AgentRun

_api_semaphore = asyncio.Semaphore(settings.max_concurrent_api_calls)


@dataclass
class AgentResult:
    output: dict
    confidence: float
    model: str
    prompt_hash: str
    input_tokens: int
    output_tokens: int
    duration_ms: int


class BaseAgent(ABC):
    agent_type: str = "base"
    model: str = "claude-sonnet-4-20250514"
    max_retries: int = 2
    temperature: float = 0.3
    max_tokens: int = 4096

    def __init__(self, model: str = None):
        if model:
            self.model = model
        self.client = AsyncAnthropic(api_key=settings.anthropic_api_key)

    @abstractmethod
    def build_prompt(self, context: dict) -> tuple[str, str]:
        """Return (system_prompt, user_prompt)."""
        ...

    @abstractmethod
    def validate_output(self, raw: str) -> dict:
        """Parse and validate LLM output. Raise ValueError if invalid."""
        ...

    @staticmethod
    def _extract_json(text: str) -> str:
        """Extract JSON object from LLM output, handling fences and trailing text."""
        text = text.strip()
        # Strip markdown fences
        text = re.sub(r"^```(?:json)?\s*\n?", "", text, count=1)
        text = re.sub(r"\n?```\s*$", "", text)
        text = text.strip()
        # Find the JSON object boundaries (first { to its matching })
        start = text.find("{")
        if start == -1:
            return text
        depth = 0
        in_string = False
        escape = False
        for i in range(start, len(text)):
            c = text[i]
            if escape:
                escape = False
                continue
            if c == "\\":
                escape = True
                continue
            if c == '"' and not escape:
                in_string = not in_string
                continue
            if in_string:
                continue
            if c == "{":
                depth += 1
            elif c == "}":
                depth -= 1
                if depth == 0:
                    return text[start:i + 1]
        return text[start:]

    def inject_context(self, context: dict, db=None) -> dict:
        """Override to inject agent-specific data from DB."""
        return context

    async def run(self, context: dict, proposal_id: str = None) -> AgentResult:
        db = SessionLocal()
        try:
            context = self.inject_context(context, db)
            system_prompt, user_prompt = self.build_prompt(context)
            prompt_hash = hashlib.sha256(system_prompt.encode()).hexdigest()[:16]

            async with _api_semaphore:
                start = time.monotonic()
                response = await self.client.messages.create(
                    model=self.model,
                    max_tokens=self.max_tokens,
                    temperature=self.temperature,
                    system=system_prompt,
                    messages=[{"role": "user", "content": user_prompt}],
                )
                duration_ms = int((time.monotonic() - start) * 1000)

            raw_text = response.content[0].text
            raw_text = self._extract_json(raw_text)
            output = self.validate_output(raw_text)

            result = AgentResult(
                output=output,
                confidence=output.get("confidence", 0.0),
                model=self.model,
                prompt_hash=prompt_hash,
                input_tokens=response.usage.input_tokens,
                output_tokens=response.usage.output_tokens,
                duration_ms=duration_ms,
            )

            if proposal_id:
                run = AgentRun(
                    proposal_id=proposal_id,
                    agent_type=self.agent_type,
                    model_used=self.model,
                    prompt_hash=prompt_hash,
                    input_tokens=result.input_tokens,
                    output_tokens=result.output_tokens,
                    duration_ms=duration_ms,
                    status="ok",
                )
                db.add(run)
                db.commit()

            return result

        except Exception as e:
            if proposal_id:
                run = AgentRun(
                    proposal_id=proposal_id,
                    agent_type=self.agent_type,
                    model_used=self.model,
                    prompt_hash="error",
                    status="error",
                    error_message=str(e),
                )
                db.add(run)
                db.commit()
            raise
        finally:
            db.close()

    async def retry(self, context: dict, error: str, proposal_id: str = None) -> AgentResult:
        context["_retry_error"] = error
        context["_retry_instruction"] = f"Previous attempt failed: {error}. Adjust your approach."
        return await self.run(context, proposal_id)
