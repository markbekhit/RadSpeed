"""Contract tests for the OpenAI-compatible mock used by browser E2E."""
import asyncio
import json
import unittest

from starlette.requests import Request
from starlette.responses import StreamingResponse

from web.mock_routes import mock_chat


class MockStreamingContractTests(unittest.TestCase):
    def test_streaming_chat_returns_openai_sse_chunks(self):
        body = json.dumps({"stream": True, "messages": []}).encode()
        sent = False

        async def receive():
            nonlocal sent
            if sent:
                return {"type": "http.disconnect"}
            sent = True
            return {"type": "http.request", "body": body, "more_body": False}

        request = Request(
            {
                "type": "http",
                "method": "POST",
                "path": "/mock/v1/chat/completions",
                "headers": [(b"content-type", b"application/json")],
            },
            receive,
        )
        response = asyncio.run(mock_chat(request))
        self.assertIsInstance(response, StreamingResponse)

        async def collect():
            chunks = [chunk async for chunk in response.body_iterator]
            return "".join(
                chunk.decode() if isinstance(chunk, bytes) else chunk for chunk in chunks
            )

        payload = asyncio.run(collect())
        self.assertIn('"object": "chat.completion.chunk"', payload)
        self.assertIn("No acute cardiopulmonary abnormality", payload)
        self.assertTrue(payload.rstrip().endswith("data: [DONE]"))


if __name__ == "__main__":
    unittest.main()
