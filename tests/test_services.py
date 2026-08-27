import base64
import tempfile
import unittest
from datetime import datetime
from pathlib import Path

from modem_reset.constants import (
    MODEM_LOGIN_COMMAND_ID,
    STATUS_REBOOTING,
)
from modem_reset.i18n import Translator
from modem_reset.ip_checker import PublicIpChecker
from modem_reset.log_exporter import LogExporter
from modem_reset.models import LogEntry
from modem_reset.modem_client import ModemClient


class FakeResponse:
    def __init__(self, *, text: str = "", json_data: object = None):
        self.text = text
        self._json_data = json_data

    def raise_for_status(self) -> None:
        return None

    def json(self) -> object:
        return self._json_data


class FakeSession:
    def __init__(self, responses: list[FakeResponse]):
        self.headers: dict[str, str] = {}
        self.responses = iter(responses)
        self.requests: list[tuple[str, dict[str, str], int]] = []

    def post(self, url: str, *, data: dict[str, str], timeout: int) -> FakeResponse:
        self.requests.append((url, data, timeout))
        return next(self.responses)


class ServiceTests(unittest.TestCase):
    def test_public_ip_checker_parses_valid_json(self) -> None:
        def fake_get(_url: str, **_kwargs: object) -> FakeResponse:
            return FakeResponse(json_data={"ip": " 203.0.113.10 "})

        result = PublicIpChecker(get=fake_get).check()

        self.assertTrue(result.connected)
        self.assertEqual("203.0.113.10", result.value)

    def test_modem_client_logs_in_then_reboots(self) -> None:
        session = FakeSession(
            [
                FakeResponse(text='{"result":"0"}'),
                FakeResponse(text='{"result":"0"}'),
            ]
        )
        statuses: list[str] = []
        client = ModemClient(session=session)

        outcome = client.reboot("secret", statuses.append)

        self.assertEqual(STATUS_REBOOTING, outcome.status)
        self.assertEqual(2, len(session.requests))
        login_payload = session.requests[0][1]
        self.assertEqual(MODEM_LOGIN_COMMAND_ID, login_payload["goformId"])
        self.assertEqual(
            base64.b64encode(b"secret").decode("utf-8"),
            login_payload["password"],
        )

    def test_log_exporter_writes_translated_entries(self) -> None:
        translator = Translator("vi")
        entry = LogEntry(
            entry_id=1,
            timestamp=datetime(2026, 8, 27, 12, 30, 45),
            public_ip="203.0.113.10",
            status="status_normal",
        )
        with tempfile.TemporaryDirectory() as directory:
            target = LogExporter().export(
                [entry],
                directory,
                translator.text,
                translator.status_text,
            )
            content = Path(target).read_text(encoding="utf-8")

        self.assertIn("Thời gian\tIP\tTrạng thái", content)
        self.assertIn("203.0.113.10\tHoạt động bình thường", content)


if __name__ == "__main__":
    unittest.main()
