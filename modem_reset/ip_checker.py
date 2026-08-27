import logging
from collections.abc import Callable

import requests

from .constants import (
    IP_CHECK_URL,
    IP_FETCH_TIMEOUT_SECONDS,
    STATUS_IP_PARSE_ERROR,
    STATUS_IP_TIMEOUT,
    STATUS_IP_UNKNOWN,
)
from .models import IpCheckResult


class PublicIpChecker:
    def __init__(
        self,
        url: str = IP_CHECK_URL,
        timeout: int = IP_FETCH_TIMEOUT_SECONDS,
        get: Callable[..., requests.Response] = requests.get,
    ):
        self.url = url
        self.timeout = timeout
        self._get = get

    def check(self) -> IpCheckResult:
        headers = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/98.0.4758.102 Safari/537.36"
            )
        }
        try:
            response = self._get(self.url, timeout=self.timeout, headers=headers)
            response.raise_for_status()
            try:
                data = response.json()
            except (requests.exceptions.JSONDecodeError, ValueError) as error:
                logging.error("Could not parse public IP response: %s", error)
                return IpCheckResult(STATUS_IP_PARSE_ERROR, False)

            ip_address = data.get("ip") if isinstance(data, dict) else None
            if isinstance(ip_address, str) and ip_address.strip():
                return IpCheckResult(ip_address.strip(), True)

            logging.error("Public IP response did not contain a valid 'ip' value: %r", data)
            return IpCheckResult(STATUS_IP_PARSE_ERROR, False)
        except requests.exceptions.Timeout:
            logging.warning("Public IP request to %s timed out", self.url)
            return IpCheckResult(STATUS_IP_TIMEOUT, False)
        except requests.exceptions.RequestException as error:
            logging.error("Public IP request to %s failed: %s", self.url, error)
            return IpCheckResult(STATUS_IP_UNKNOWN, False)
        except Exception:
            logging.exception("Unexpected public IP check failure")
            return IpCheckResult(STATUS_IP_UNKNOWN, False)
