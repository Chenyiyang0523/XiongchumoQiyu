#!/usr/bin/env python3
"""Local-only checks for the streaming credential relay; never contacts BigModel."""
from contextlib import contextmanager
import io
import json
import threading
import unittest
from unittest.mock import patch
from urllib.request import Request, urlopen
from urllib.error import HTTPError

import run_glm_game as relay


class RelayTests(unittest.TestCase):
    def test_body_and_linux_model_parameters_are_not_rewritten(self):
        provider = relay.GLM.__new__(relay.GLM)
        provider.key = "test-secret"
        provider.slots = threading.BoundedSemaphore(3)
        payload = {"model": "glm-4.7-flashx", "stream": True, "messages": [{"role": "user", "content": "点子"}],
                   "temperature": 0.2, "top_p": 0.95, "max_tokens": 500, "thinking": {"type": "disabled"}}
        requests = []
        def upstream(req, **kwargs):
            requests.append(req)
            return io.BytesIO(b"data: [DONE]\n\n")
        with patch.object(relay, "urlopen", upstream):
            with provider.forward(payload) as response:
                self.assertTrue(response.read())
        self.assertEqual(json.loads(requests[0].data), payload)
        self.assertEqual(requests[0].get_header("Authorization"), "Bearer test-secret")

    def test_stream_arrives_before_upstream_finishes_and_closes_on_disconnect(self):
        proceed, closed = threading.Event(), threading.Event()
        payloads = []
        class Response:
            i = 0
            def readline(self):
                self.i += 1
                if self.i == 1:
                    return b"data: first\n"
                if self.i == 2:
                    return b"\n"
                proceed.wait(3)
                return b"data: later\n\n" if self.i < 20 else b""
        class Provider:
            @contextmanager
            def forward(self, payload):
                payloads.append(payload)
                try:
                    yield Response()
                finally:
                    closed.set()
        server = relay.ThreadingHTTPServer(("127.0.0.1", 0), relay.handler_for(Provider(), "test-token"))
        threading.Thread(target=server.serve_forever, daemon=True).start()
        try:
            payload = {"model": "glm-4.7", "stream": True, "messages": [{"role": "user", "content": "测试"}]}
            req = Request("http://127.0.0.1:%d/v1/chat/completions" % server.server_port,
                          data=json.dumps(payload).encode(), headers={"Authorization": "Bearer test-token"})
            with urlopen(req, timeout=2) as response:
                self.assertEqual(response.readline(), b"data: first\n")
                self.assertFalse(proceed.is_set())
            proceed.set()
            self.assertTrue(closed.wait(3))
            self.assertEqual(payloads, [payload])
        finally:
            proceed.set()
            server.shutdown()
            server.server_close()

    def test_auth_and_upstream_error_status_are_preserved(self):
        class Provider:
            @contextmanager
            def forward(self, payload):
                raise HTTPError("upstream", 429, "quota", {}, io.BytesIO(b'{"error":{"code":"1302"}}'))
                yield
        server = relay.ThreadingHTTPServer(("127.0.0.1", 0), relay.handler_for(Provider(), "test-token"))
        threading.Thread(target=server.serve_forever, daemon=True).start()
        try:
            for token, status in (("wrong", 401), ("test-token", 429)):
                req = Request("http://127.0.0.1:%d/v1/chat/completions" % server.server_port,
                              data=b'{"messages":[{}]}', headers={"Authorization": "Bearer " + token})
                with self.assertRaises(HTTPError) as caught:
                    urlopen(req, timeout=2)
                self.assertEqual(caught.exception.code, status)
                if status == 429:
                    self.assertEqual(json.loads(caught.exception.read())["error"]["code"], "1302")
        finally:
            server.shutdown()
            server.server_close()


if __name__ == "__main__":
    unittest.main(verbosity=2)
