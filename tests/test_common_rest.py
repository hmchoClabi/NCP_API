import json
import logging
import unittest
from unittest.mock import Mock, patch

import requests

from utils.common_rest import NCPBaseClient, safe_exception_message
from utils.credentials import NCPCredentials


def make_response(
    status=200,
    body=b'{"ok": true}',
    content_type="application/json",
    url="https://api.example.test/resource",
):
    response = requests.Response()
    response.status_code = status
    response._content = body
    response.encoding = "utf-8"
    response.url = url
    if content_type is not None:
        response.headers["Content-Type"] = content_type
    return response


class NCPBaseClientTests(unittest.TestCase):
    def make_client(self, retry_count=3):
        return NCPBaseClient(
            access_key="ACCESS-VALUE",
            secret_key="SECRET-VALUE",
            base_url="https://api.example.test/base",
            timeout=10,
            retry_count=retry_count,
        )

    def test_merges_existing_query_and_signs_exact_transmitted_uri(self):
        client = self.make_client()
        client.session.request = Mock(return_value=make_response())
        client.auth.get_auth_headers = Mock(return_value={})

        client.get(
            "/resource?existing=one",
            params={"privateKey": "PRIVATE-VALUE", "page": 2},
        )

        request_call = client.session.request.call_args
        url = request_call.args[1]
        self.assertEqual(
            url,
            "https://api.example.test/base/resource"
            "?existing=one&privateKey=PRIVATE-VALUE&page=2",
        )
        client.auth.get_auth_headers.assert_called_once_with(
            "GET",
            "/base/resource?existing=one&privateKey=PRIVATE-VALUE&page=2",
            query_string=None,
        )

    def test_rejects_foreign_absolute_url_before_sending_credentials(self):
        client = self.make_client()
        client.session.request = Mock()

        with self.assertRaisesRegex(ValueError, "origin"):
            client.get("https://attacker.example/resource")

        client.session.request.assert_not_called()

    def test_accepts_absolute_url_on_same_origin(self):
        client = self.make_client()
        client.session.request = Mock(return_value=make_response())

        result = client.get("https://api.example.test/other")

        self.assertEqual(result, {"ok": True})
        self.assertEqual(
            client.session.request.call_args.args[1],
            "https://api.example.test/other",
        )

    def test_redirects_are_not_followed_or_returned_as_success(self):
        client = self.make_client()
        response = make_response(
            status=302,
            body=b"",
            content_type=None,
        )
        response.headers["Location"] = "https://attacker.example/resource"
        client.session.request = Mock(return_value=response)

        with self.assertRaisesRegex(requests.HTTPError, "redirect"):
            client.get("/resource")

        self.assertFalse(
            client.session.request.call_args.kwargs["allow_redirects"]
        )
        self.assertEqual(client.session.request.call_count, 1)

    def test_not_modified_response_keeps_existing_non_redirect_behavior(self):
        client = self.make_client()
        response = make_response(
            status=304,
            body=b"",
            content_type=None,
        )
        client.session.request = Mock(return_value=response)

        self.assertEqual(
            client.get("/resource"),
            {"status_code": 304, "empty": True},
        )
        self.assertFalse(
            client.session.request.call_args.kwargs["allow_redirects"]
        )

    def test_validates_timeout_retry_count_and_body_modes(self):
        for timeout in (0, -1, True, "10"):
            with self.subTest(timeout=timeout):
                with self.assertRaisesRegex(ValueError, "timeout"):
                    NCPBaseClient("a", "s", "https://api.example.test", timeout=timeout)

        for retry_count in (0, -1, True, 1.5):
            with self.subTest(retry_count=retry_count):
                with self.assertRaisesRegex(ValueError, "retry_count"):
                    NCPBaseClient(
                        "a",
                        "s",
                        "https://api.example.test",
                        retry_count=retry_count,
                    )

        client = self.make_client()
        with self.assertRaisesRegex(ValueError, "json_data"):
            client.post("/resource", json_data={"a": 1}, data={"b": 2})
        with self.assertRaisesRegex(ValueError, "json_data"):
            client.post("/resource", json_data={"a": 1}, files={"file": object()})
        with self.assertRaisesRegex(ValueError, "dict form data"):
            client.post("/resource", data="field=value", files={"file": object()})
        with self.assertRaisesRegex(ValueError, "timeout"):
            client.get("/resource", timeout=0)

    @patch("utils.common_rest.time.sleep")
    def test_retries_only_transient_idempotent_requests(self, sleep):
        client = self.make_client(retry_count=3)
        client.session.request = Mock(
            side_effect=[
                make_response(status=503),
                make_response(status=200),
            ]
        )

        self.assertEqual(client.get("/resource"), {"ok": True})
        self.assertEqual(client.session.request.call_count, 2)
        sleep.assert_called_once_with(1)

        client.session.request.reset_mock()
        sleep.reset_mock()
        client.session.request.side_effect = None
        client.session.request.return_value = make_response(status=400)
        with self.assertRaises(requests.HTTPError):
            client.get("/resource")
        self.assertEqual(client.session.request.call_count, 1)
        sleep.assert_not_called()

        client.session.request.reset_mock()
        client.session.request.return_value = make_response(status=503)
        with self.assertRaises(requests.HTTPError):
            client.post("/resource", json_data={"operation": "create"})
        self.assertEqual(client.session.request.call_count, 1)
        sleep.assert_not_called()

        client.session.request.reset_mock()
        client.session.request.side_effect = [
            make_response(status=503),
            make_response(status=200),
        ]
        self.assertEqual(
            client.post(
                "/read-only-search",
                json_data={"query": "value"},
                retry_safe=True,
            ),
            {"ok": True},
        )
        self.assertEqual(client.session.request.call_count, 2)

    @patch("utils.common_rest.time.sleep")
    def test_retries_connection_errors_for_get_but_not_post(self, sleep):
        client = self.make_client(retry_count=2)
        client.session.request = Mock(
            side_effect=[
                requests.ConnectionError("query secret must not be logged"),
                make_response(),
            ]
        )
        self.assertEqual(client.get("/resource"), {"ok": True})
        self.assertEqual(client.session.request.call_count, 2)

        client.session.request = Mock(
            side_effect=requests.ConnectionError("do not retry post")
        )
        with self.assertRaises(requests.ConnectionError):
            client.post("/resource", json_data={"name": "new"})
        self.assertEqual(client.session.request.call_count, 1)

    def test_multipart_keeps_form_fields_and_removes_content_type(self):
        client = self.make_client()
        client.session.request = Mock(return_value=make_response())

        client.post(
            "/upload",
            data={"description": "safe"},
            files={"file": ("name.txt", b"contents")},
        )

        kwargs = client.session.request.call_args.kwargs
        self.assertEqual(kwargs["data"], {"description": "safe"})
        self.assertIn("files", kwargs)
        self.assertNotIn("Content-Type", kwargs["headers"])

    def test_json_xml_text_empty_and_malformed_json_responses(self):
        client = self.make_client()
        responses = [
            make_response(body=b'[1, {"value": 2}]'),
            make_response(body=b"<root />", content_type="application/xml"),
            make_response(body=b"plain text", content_type="text/plain"),
            make_response(status=204, body=b"", content_type=None),
            make_response(body=b"{broken", content_type="application/json"),
        ]
        client.session.request = Mock(side_effect=responses)

        self.assertEqual(client.get("/json"), [1, {"value": 2}])
        self.assertEqual(
            client.get("/xml"),
            {"text": "<root />", "status_code": 200},
        )
        self.assertEqual(
            client.get("/text"),
            {"text": "plain text", "status_code": 200},
        )
        self.assertEqual(
            client.get("/empty"),
            {"status_code": 204, "empty": True},
        )
        with self.assertRaises(requests.exceptions.JSONDecodeError):
            client.get("/malformed")

    def test_logs_redact_request_and_response_secrets(self):
        client = self.make_client()
        response_body = json.dumps(
            {
                "password": "RESPONSE-PASSWORD",
                "nested": {"token": "RESPONSE-TOKEN", "visible": 1},
            }
        ).encode()
        response = make_response(
            body=response_body,
            url=(
                "https://api.example.test/resource"
                "?privateKey=RESPONSE-QUERY-SECRET"
            ),
        )
        response.headers["Set-Cookie"] = "RESPONSE-COOKIE"
        client.session.request = Mock(return_value=response)

        with self.assertLogs("utils.common_rest", level=logging.DEBUG) as captured:
            result = client.post(
                "/resource?privateKey=QUERY-SECRET",
                params={"token": "PARAM-TOKEN", "page": 1},
                json_data={
                    "password": "BODY-PASSWORD",
                    "nested": {"secretKey": "BODY-SECRET", "count": 1},
                },
                headers={"Authorization": "Bearer HEADER-TOKEN"},
            )

        self.assertEqual(result["password"], "RESPONSE-PASSWORD")
        logs = "\n".join(captured.output)
        for secret in (
            "ACCESS-VALUE",
            "SECRET-VALUE",
            "QUERY-SECRET",
            "PARAM-TOKEN",
            "BODY-PASSWORD",
            "BODY-SECRET",
            "HEADER-TOKEN",
            "RESPONSE-PASSWORD",
            "RESPONSE-TOKEN",
            "RESPONSE-QUERY-SECRET",
            "RESPONSE-COOKIE",
        ):
            with self.subTest(secret=secret):
                self.assertNotIn(secret, logs)
        self.assertIn("page=1", logs)
        info_request_lines = [
            line for line in captured.output if "[API Request]" in line
        ]
        self.assertEqual(len(info_request_lines), 1)
        self.assertNotIn("?", info_request_lines[0])

    def test_exception_message_removes_absolute_and_relative_url_queries(self):
        exception = requests.ConnectionError(
            "failed request=https://user:pass@example.test/x?token=ABSOLUTE "
            "with url='/resource?privateKey=RELATIVE#fragment'"
        )

        message = safe_exception_message(exception)

        for secret in ("user", "pass", "ABSOLUTE", "RELATIVE", "privateKey"):
            with self.subTest(secret=secret):
                self.assertNotIn(secret, message)
        self.assertIn("https://example.test/x", message)
        self.assertIn("/resource", message)


class CredentialsTests(unittest.TestCase):
    def test_secret_key_is_not_in_repr(self):
        credentials = NCPCredentials("ACCESS", "VERY-SECRET")

        rendered = repr(credentials)

        self.assertIn("ACCESS", rendered)
        self.assertNotIn("VERY-SECRET", rendered)
        self.assertNotIn("secret_key", rendered)


if __name__ == "__main__":
    unittest.main()
