"""
Amazon Bedrock Augmented LLM wrapper.

Provides a BedrockAugmentedLLM class that integrates with the mcp-agent
workflow interface, translating between Anthropic-style messages and the
Bedrock InvokeModel / InvokeModelWithResponseStream APIs.
"""

import asyncio
import json
import logging
import uuid
from typing import Any, AsyncIterator, Dict, List, Optional

from botocore.exceptions import ClientError

from utils.bedrock_utils import get_bedrock_session, map_model_id

logger = logging.getLogger(__name__)

# Default model when none is specified
DEFAULT_MODEL = "claude-3-5-sonnet"

# Retry configuration
MAX_RETRIES = 3
INITIAL_BACKOFF = 1.0  # seconds
BACKOFF_MULTIPLIER = 2.0

# Retryable error codes from Bedrock
RETRYABLE_ERRORS = {"ThrottlingException", "ServiceUnavailableException", "ModelTimeoutException"}


class BedrockAugmentedLLM:
    """Augmented LLM wrapper for Amazon Bedrock.

    Implements the mcp-agent LLM interface, converting between the
    Anthropic-style message format used internally and Bedrock's
    InvokeModel API (which uses the Anthropic Messages API format
    for Claude models).

    Args:
        api_key: Optional dict with AWS credentials (aws_access_key_id,
            aws_secret_access_key, aws_region, etc.) or None to use IAM roles.
        model: Model name or fully-qualified Bedrock model ID.
        **kwargs: Additional configuration (aws_region, aws_profile, etc.).
    """

    def __init__(
        self,
        api_key: Optional[Dict[str, str]] = None,
        model: Optional[str] = None,
        **kwargs: Any,
    ):
        self.model = model or DEFAULT_MODEL
        self.bedrock_model_id = map_model_id(self.model)

        # Build config for session creation
        config: Dict[str, Any] = {}
        if isinstance(api_key, dict):
            config.update(api_key)
        config.update(kwargs)

        self._region = config.get("aws_region", "us-east-1")
        self._session = get_bedrock_session(config)
        self._client = self._session.client("bedrock-runtime", region_name=self._region)

        logger.info(
            "BedrockAugmentedLLM initialised with model=%s (bedrock_id=%s, region=%s)",
            self.model,
            self.bedrock_model_id,
            self._region,
        )

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    async def create_message(
        self,
        messages: List[Dict[str, Any]],
        tools: Optional[List[Dict]] = None,
        model: Optional[str] = None,
        max_tokens: int = 4096,
        temperature: float = 1.0,
        system: Optional[str] = None,
        stream: bool = False,
        **kwargs: Any,
    ) -> Dict[str, Any]:
        """Send a message to Bedrock and return an Anthropic-compatible response.

        Args:
            messages: List of message dicts with ``role`` and ``content`` keys.
            tools: Optional tool definitions in Anthropic format.
            model: Override model for this request.
            max_tokens: Maximum tokens to generate.
            temperature: Sampling temperature.
            system: System prompt string.
            stream: If True, return a streaming async iterator.
            **kwargs: Passed through to the Bedrock request body.

        Returns:
            Dict with keys: content (list of blocks), stop_reason, usage, model.
        """
        bedrock_model_id = map_model_id(model) if model else self.bedrock_model_id
        body = self._build_request_body(
            messages=messages,
            tools=tools,
            max_tokens=max_tokens,
            temperature=temperature,
            system=system,
            **kwargs,
        )

        if stream:
            return await self._invoke_stream(bedrock_model_id, body)

        return await self._invoke_with_retry(bedrock_model_id, body)

    # ------------------------------------------------------------------
    # Internal: request building
    # ------------------------------------------------------------------

    def _build_request_body(
        self,
        messages: List[Dict[str, Any]],
        tools: Optional[List[Dict]],
        max_tokens: int,
        temperature: float,
        system: Optional[str] = None,
        **kwargs: Any,
    ) -> Dict[str, Any]:
        """Build the Bedrock InvokeModel request body (Anthropic Messages format).

        Bedrock's Claude models accept the Anthropic Messages API payload
        directly, so we only need to ensure message format compliance.
        """
        converted_messages = self._convert_messages(messages)

        body: Dict[str, Any] = {
            "anthropic_version": "bedrock-2023-05-31",
            "messages": converted_messages,
            "max_tokens": max_tokens,
            "temperature": temperature,
        }

        if system:
            body["system"] = system

        if tools:
            body["tools"] = self._convert_tools(tools)

        body.update(kwargs)
        return body

    @staticmethod
    def _convert_messages(messages: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Ensure messages follow the Anthropic Messages format for Bedrock.

        Handles common variations:
        - String content → wrapped in text block
        - Role validation (user/assistant only in messages)
        """
        converted = []
        for msg in messages:
            role = msg.get("role", "user")
            content = msg.get("content", "")

            # Only user and assistant roles allowed in messages array
            if role not in ("user", "assistant"):
                role = "user"

            # Normalise content to block format
            if isinstance(content, str):
                content = [{"type": "text", "text": content}]
            elif isinstance(content, list):
                # Already in block format; pass through
                content = content
            else:
                content = [{"type": "text", "text": str(content)}]

            converted.append({"role": role, "content": content})

        return converted

    @staticmethod
    def _convert_tools(tools: List[Dict]) -> List[Dict[str, Any]]:
        """Convert tool definitions to Bedrock/Anthropic tool format.

        Expected input format (mcp-agent style):
            {"name": str, "description": str, "input_schema": dict}

        Bedrock Claude expects the same Anthropic format so this is mostly
        pass-through with validation.
        """
        converted = []
        for tool in tools:
            converted.append({
                "name": tool["name"],
                "description": tool.get("description", ""),
                "input_schema": tool.get("input_schema", {"type": "object", "properties": {}}),
            })
        return converted

    # ------------------------------------------------------------------
    # Internal: invocation with retry
    # ------------------------------------------------------------------

    async def _invoke_with_retry(
        self, model_id: str, body: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Invoke the model with exponential backoff on retryable errors."""
        last_error: Optional[Exception] = None
        backoff = INITIAL_BACKOFF

        for attempt in range(1, MAX_RETRIES + 1):
            try:
                return await self._invoke(model_id, body)
            except ClientError as exc:
                error_code = exc.response["Error"]["Code"]
                if error_code in RETRYABLE_ERRORS and attempt < MAX_RETRIES:
                    logger.warning(
                        "Bedrock %s on attempt %d/%d, retrying in %.1fs",
                        error_code,
                        attempt,
                        MAX_RETRIES,
                        backoff,
                    )
                    last_error = exc
                    await asyncio.sleep(backoff)
                    backoff *= BACKOFF_MULTIPLIER
                else:
                    raise

        # Should not reach here, but guard anyway
        raise last_error  # type: ignore[misc]

    async def _invoke(self, model_id: str, body: Dict[str, Any]) -> Dict[str, Any]:
        """Call Bedrock invoke_model and parse the response."""
        response = await asyncio.get_event_loop().run_in_executor(
            None,
            lambda: self._client.invoke_model(
                modelId=model_id,
                contentType="application/json",
                accept="application/json",
                body=json.dumps(body),
            ),
        )

        response_body = json.loads(response["body"].read())
        return self._parse_response(response_body)

    # ------------------------------------------------------------------
    # Internal: streaming
    # ------------------------------------------------------------------

    async def _invoke_stream(
        self, model_id: str, body: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Call Bedrock invoke_model_with_response_stream and assemble the response."""
        response = await asyncio.get_event_loop().run_in_executor(
            None,
            lambda: self._client.invoke_model_with_response_stream(
                modelId=model_id,
                contentType="application/json",
                accept="application/json",
                body=json.dumps(body),
            ),
        )

        return await self._assemble_stream(response["body"])

    async def _assemble_stream(self, event_stream: Any) -> Dict[str, Any]:
        """Consume a Bedrock response stream and build the final response dict.

        The stream yields events with a ``chunk`` key containing ``bytes``.
        For Anthropic models on Bedrock the streamed JSON follows the
        Anthropic streaming event format (message_start, content_block_start,
        content_block_delta, message_delta, message_stop).
        """
        content_blocks: List[Dict[str, Any]] = []
        current_block: Optional[Dict[str, Any]] = None
        stop_reason: Optional[str] = None
        usage: Dict[str, int] = {"input_tokens": 0, "output_tokens": 0}
        model_id = ""

        for event in event_stream:
            chunk_bytes = event.get("chunk", {}).get("bytes", b"")
            if not chunk_bytes:
                continue

            data = json.loads(chunk_bytes)
            event_type = data.get("type", "")

            if event_type == "message_start":
                msg = data.get("message", {})
                model_id = msg.get("model", "")
                msg_usage = msg.get("usage", {})
                usage["input_tokens"] = msg_usage.get("input_tokens", 0)

            elif event_type == "content_block_start":
                block = data.get("content_block", {})
                block_type = block.get("type", "text")
                if block_type == "text":
                    current_block = {"type": "text", "text": ""}
                elif block_type == "tool_use":
                    current_block = {
                        "type": "tool_use",
                        "id": block.get("id", str(uuid.uuid4())),
                        "name": block.get("name", ""),
                        "input": "",
                    }

            elif event_type == "content_block_delta":
                delta = data.get("delta", {})
                delta_type = delta.get("type", "")
                if delta_type == "text_delta" and current_block and current_block["type"] == "text":
                    current_block["text"] += delta.get("text", "")
                elif delta_type == "input_json_delta" and current_block and current_block["type"] == "tool_use":
                    current_block["input"] += delta.get("partial_json", "")

            elif event_type == "content_block_stop":
                if current_block:
                    # Parse accumulated JSON for tool_use blocks
                    if current_block["type"] == "tool_use" and isinstance(current_block["input"], str):
                        try:
                            current_block["input"] = json.loads(current_block["input"]) if current_block["input"] else {}
                        except json.JSONDecodeError:
                            current_block["input"] = {}
                    content_blocks.append(current_block)
                    current_block = None

            elif event_type == "message_delta":
                delta = data.get("delta", {})
                stop_reason = delta.get("stop_reason", stop_reason)
                delta_usage = data.get("usage", {})
                usage["output_tokens"] = delta_usage.get("output_tokens", usage["output_tokens"])

            elif event_type == "message_stop":
                pass  # End of stream

        return {
            "content": content_blocks,
            "stop_reason": stop_reason or "end_turn",
            "usage": usage,
            "model": model_id,
        }

    # ------------------------------------------------------------------
    # Internal: response parsing
    # ------------------------------------------------------------------

    @staticmethod
    def _parse_response(response_body: Dict[str, Any]) -> Dict[str, Any]:
        """Parse a Bedrock InvokeModel response into a standardised dict.

        For Anthropic models on Bedrock the response body is already in
        Anthropic Messages format, so this is largely pass-through.
        """
        return {
            "content": response_body.get("content", []),
            "stop_reason": response_body.get("stop_reason", "end_turn"),
            "usage": response_body.get("usage", {}),
            "model": response_body.get("model", ""),
        }

    # ------------------------------------------------------------------
    # Convenience helpers
    # ------------------------------------------------------------------

    async def generate_str(
        self,
        message: str,
        system: Optional[str] = None,
        max_tokens: int = 4096,
        temperature: float = 1.0,
        **kwargs: Any,
    ) -> str:
        """Simple string-in, string-out generation helper."""
        response = await self.create_message(
            messages=[{"role": "user", "content": message}],
            system=system,
            max_tokens=max_tokens,
            temperature=temperature,
            **kwargs,
        )

        # Extract text from content blocks
        parts = []
        for block in response.get("content", []):
            if isinstance(block, dict) and block.get("type") == "text":
                parts.append(block["text"])
        return "\n".join(parts)

    def extract_tool_calls(self, response: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Extract tool calls from a create_message response.

        Returns a list of dicts matching the workflow format:
            [{"id": str, "name": str, "input": dict}, ...]
        """
        tool_calls = []
        for block in response.get("content", []):
            if isinstance(block, dict) and block.get("type") == "tool_use":
                tool_calls.append({
                    "id": block.get("id", ""),
                    "name": block.get("name", ""),
                    "input": block.get("input", {}),
                })
        return tool_calls

    def extract_text(self, response: Dict[str, Any]) -> str:
        """Extract concatenated text from a create_message response."""
        parts = []
        for block in response.get("content", []):
            if isinstance(block, dict) and block.get("type") == "text":
                parts.append(block["text"])
        return "\n".join(parts)
