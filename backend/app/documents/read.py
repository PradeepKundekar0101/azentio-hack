"""The model that reads supporting documents: classification and structured extraction with Claude.

The document is untrusted data: its text goes inside <untrusted_document> tags and the system prompt says its
content is never instructions. Every value must come with the exact text it was read from, which the provenance
check then looks for in the document. Tests replace DocumentReader with readers that return fixed answers.
"""

from typing import Any

import anthropic
from pydantic import BaseModel

from app.core.config import Settings
from app.documents.schemas import UNTRUSTED_NOTE, WIRE_SCHEMAS, DocumentClass, to_sourced

PROMPT_VERSION = "documents-2026-10-31.1"

CLASSIFY_SYSTEM = (
    "You sort supporting documents of Indian health and motor insurance claims. Label the document as invoice "
    "(a hospital, clinic, pharmacy or lab bill), discharge_summary (a hospital's summary of a stay: admission, "
    "discharge, diagnosis, procedures), repair_estimate (a workshop's estimate for a vehicle) or other. "
    + UNTRUSTED_NOTE
)

EXTRACT_SYSTEM = (
    "You extract one supporting document of an insurance claim into structured data. For every field that has a "
    "value, add an entry to sources with the field's name (lines[0].amount for a line's field, "
    "procedures_performed[1] for a list item), the exact text on the document it was read from (copied character "
    "for character, including commas and spacing as printed) and its page number. Never invent a value: when a "
    "field is not on the document, leave it null and list no source for it. Dates are YYYY-MM-DD in value "
    "(Indian documents print the day first); amounts are rupees with digits and a decimal point only in value. "
    "One line per billed row; subtotal, "
    "tax and total rows are not lines. " + UNTRUSTED_NOTE
)


class DocumentReader:
    def __init__(self, settings: Settings) -> None:
        self.model = settings.extraction_model
        key = settings.anthropic_api_key.get_secret_value() if settings.anthropic_api_key else ""
        self.client = anthropic.AsyncAnthropic(api_key=key, max_retries=2, timeout=120) if key else None

    @property
    def enabled(self) -> bool:
        return self.client is not None

    async def _parse(self, system: str, messages: list[dict[str, Any]], schema: type[BaseModel]) -> Any:
        assert self.client is not None
        response = await self.client.messages.parse(
            model=self.model, max_tokens=16000, system=system, messages=messages, output_format=schema
        )
        if response.stop_reason == "refusal" or response.parsed_output is None:
            raise ValueError(f"no structured output (stop reason {response.stop_reason})")
        return response.parsed_output

    async def classify(self, content: list[dict[str, Any]]) -> DocumentClass:
        return await self._parse(CLASSIFY_SYSTEM, [{"role": "user", "content": content}], DocumentClass)

    async def extract(self, doc_type: str, content: list[dict[str, Any]], feedback: list[str] | None = None) -> Any:
        messages: list[dict[str, Any]] = [{"role": "user", "content": content}]
        if feedback:
            messages.append({"role": "assistant", "content": "I will re-read the document and correct the extraction."})
            messages.append(
                {
                    "role": "user",
                    "content": "Your previous extraction failed these checks; re-read the document and correct it:\n- "
                    + "\n- ".join(feedback),
                }
            )
        wire = await self._parse(EXTRACT_SYSTEM, messages, WIRE_SCHEMAS[doc_type])
        return to_sourced(doc_type, wire)
