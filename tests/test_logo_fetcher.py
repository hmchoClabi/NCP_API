import base64
import socket
import threading
import unittest
from unittest.mock import patch

from webapp.logo_fetcher import fetch_customer_logo_from_url


_PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwC"
    "AAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII="
)


class _FakeSocket:
    def __init__(self):
        self.timeouts = []

    def settimeout(self, timeout):
        self.timeouts.append(timeout)


class _FakeResponse:
    def __init__(self, status=200, headers=None, body=b""):
        self.status = status
        self.headers = {key.casefold(): value for key, value in (headers or {}).items()}
        self.body = body
        self.offset = 0
        self.closed = False

    def getheader(self, name, default=None):
        return self.headers.get(name.casefold(), default)

    def read(self, amount):
        chunk = self.body[self.offset:self.offset + amount]
        self.offset += len(chunk)
        return chunk

    def close(self):
        self.closed = True


class _FakeConnection:
    def __init__(self, response):
        self.response = response
        self.sock = _FakeSocket()
        self.request_args = None
        self.closed = False

    def request(self, *args, **kwargs):
        self.request_args = (args, kwargs)

    def getresponse(self):
        return self.response

    def close(self):
        self.closed = True


def _dns_result(ip):
    family = socket.AF_INET6 if ":" in ip else socket.AF_INET
    address = (ip, 443, 0, 0) if family == socket.AF_INET6 else (ip, 443)
    return (family, socket.SOCK_STREAM, socket.IPPROTO_TCP, "", address)


class CustomerLogoUrlFetcherTests(unittest.TestCase):
    def test_public_https_image_uses_validated_pinned_ip(self):
        factory_calls = []
        response = _FakeResponse(
            headers={"Content-Type": "image/png", "Content-Length": str(len(_PNG))},
            body=_PNG,
        )

        def resolver(hostname, *_args, **_kwargs):
            self.assertEqual(hostname, "logo.example.com")
            return [_dns_result("93.184.216.34")]

        def factory(hostname, resolved_ip, port, timeout):
            factory_calls.append((hostname, resolved_ip, port, timeout))
            return _FakeConnection(response)

        logo = fetch_customer_logo_from_url(
            "https://logo.example.com/assets/logo.png?v=1",
            resolver=resolver,
            connection_factory=factory,
        )

        self.assertEqual(logo.content, _PNG)
        self.assertEqual(logo.content_type, "image/png")
        self.assertEqual(factory_calls[0][:3], (
            "logo.example.com", "93.184.216.34", 443,
        ))

    def test_private_loopback_link_local_and_mixed_dns_are_rejected(self):
        blocked_sets = [
            ["10.0.0.5"],
            ["127.0.0.1"],
            ["169.254.169.254"],
            ["::1"],
            ["fe80::1"],
            ["93.184.216.34", "192.168.1.10"],
        ]
        for ips in blocked_sets:
            with self.subTest(ips=ips):
                connected = []

                def resolver(*_args, **_kwargs):
                    return [_dns_result(ip) for ip in ips]

                def factory(*args):
                    connected.append(args)
                    raise AssertionError("차단 주소에 연결하면 안 됩니다.")

                with self.assertRaisesRegex(ValueError, "내부망·루프백·링크 로컬"):
                    fetch_customer_logo_from_url(
                        "https://logo.example.com/logo.png",
                        resolver=resolver,
                        connection_factory=factory,
                    )
                self.assertEqual(connected, [])

    def test_redirect_target_is_resolved_and_revalidated(self):
        resolved_hosts = []
        connections = []
        responses = [
            _FakeResponse(
                status=302,
                headers={"Location": "https://cdn.example.net/final.png"},
            ),
            _FakeResponse(headers={"Content-Type": "image/png"}, body=_PNG),
        ]

        def resolver(hostname, *_args, **_kwargs):
            resolved_hosts.append(hostname)
            return [_dns_result({
                "logo.example.com": "93.184.216.34",
                "cdn.example.net": "142.250.72.14",
            }[hostname])]

        def factory(hostname, resolved_ip, port, timeout):
            connections.append((hostname, resolved_ip, port))
            return _FakeConnection(responses.pop(0))

        logo = fetch_customer_logo_from_url(
            "https://logo.example.com/logo.png",
            resolver=resolver,
            connection_factory=factory,
        )

        self.assertEqual(logo.content, _PNG)
        self.assertEqual(resolved_hosts, ["logo.example.com", "cdn.example.net"])
        self.assertEqual(connections, [
            ("logo.example.com", "93.184.216.34", 443),
            ("cdn.example.net", "142.250.72.14", 443),
        ])

    def test_redirect_to_private_address_is_blocked_before_second_request(self):
        responses = [
            _FakeResponse(
                status=302,
                headers={"Location": "https://internal.example.net/logo.png"},
            ),
        ]
        connections = []

        def resolver(hostname, *_args, **_kwargs):
            ip = "93.184.216.34" if hostname == "logo.example.com" else "10.0.0.8"
            return [_dns_result(ip)]

        def factory(hostname, resolved_ip, port, timeout):
            connections.append((hostname, resolved_ip))
            return _FakeConnection(responses.pop(0))

        with self.assertRaisesRegex(ValueError, "내부망·루프백·링크 로컬"):
            fetch_customer_logo_from_url(
                "https://logo.example.com/logo.png",
                resolver=resolver,
                connection_factory=factory,
            )

        self.assertEqual(connections, [("logo.example.com", "93.184.216.34")])

    def test_scheme_credentials_port_mime_and_truncated_image_are_rejected(self):
        invalid_urls = [
            "http://logo.example.com/logo.png",
            "https://user:password@logo.example.com/logo.png",
            "https://logo.example.com:8443/logo.png",
        ]
        for url in invalid_urls:
            with self.subTest(url=url), self.assertRaises(ValueError):
                fetch_customer_logo_from_url(url)

        def resolver(*_args, **_kwargs):
            return [_dns_result("93.184.216.34")]

        for content_type, body in [
            ("text/html", b"<html>not an image</html>"),
            ("image/png", _PNG[:33]),
        ]:
            with self.subTest(content_type=content_type):
                response = _FakeResponse(
                    headers={"Content-Type": content_type},
                    body=body,
                )
                with self.assertRaises(ValueError):
                    fetch_customer_logo_from_url(
                        "https://logo.example.com/logo.png",
                        resolver=resolver,
                        connection_factory=lambda *_args: _FakeConnection(response),
                    )

    def test_declared_or_streamed_oversize_image_is_rejected(self):
        def resolver(*_args, **_kwargs):
            return [_dns_result("93.184.216.34")]

        for response in [
            _FakeResponse(
                headers={
                    "Content-Type": "image/png",
                    "Content-Length": str(512 * 1024 + 1),
                },
            ),
            _FakeResponse(
                headers={"Content-Type": "image/png"},
                body=b"x" * (512 * 1024 + 1),
            ),
        ]:
            with self.subTest(headers=response.headers), self.assertRaisesRegex(
                ValueError, "512KB"
            ):
                fetch_customer_logo_from_url(
                    "https://logo.example.com/logo.png",
                    resolver=resolver,
                    connection_factory=lambda *_args, response=response: (
                        _FakeConnection(response)
                    ),
                )

    def test_slow_dns_lookup_is_bounded_by_timeout(self):
        release_resolver = threading.Event()

        def resolver(*_args, **_kwargs):
            release_resolver.wait(1)
            return [_dns_result("93.184.216.34")]

        try:
            with patch(
                "webapp.logo_fetcher.CUSTOMER_LOGO_DNS_TIMEOUT_SECONDS",
                0.01,
            ), self.assertRaisesRegex(ValueError, "DNS 확인 시간이 초과"):
                fetch_customer_logo_from_url(
                    "https://logo.example.com/logo.png",
                    resolver=resolver,
                )
        finally:
            release_resolver.set()


if __name__ == "__main__":
    unittest.main()
