import random
from time import sleep
from functools import partialmethod
from typing import Literal

from curl_cffi import requests as cc_requests

from .exceptions import NetworkError


class CustomSession(cc_requests.Session):
    """Custom curl_cffi session with retries"""

    def __init__(self, max_retries: int = 3, initial_retry_delay: int = 1, backoff_factor: int = 2, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.max_retries = max_retries
        self.initial_retry_delay = initial_retry_delay
        self.backoff_factor = backoff_factor

    def custom_request(self, method: Literal["GET", "POST", "PUT", "DELETE", "OPTIONS", "HEAD", "TRACE"], url: str, *args, **kwargs) -> cc_requests.Response:
        """request wrapper with retries"""
        attempt = 0
        while True:
            try:
                return super().request(method, url, *args, **kwargs)
            except cc_requests.RequestsError as e:
                attempt += 1
                if attempt >= self.max_retries:
                    raise NetworkError from e
                # Calculate the backoff delay
                backoff_delay = self.initial_retry_delay * (self.backoff_factor ** (attempt - 1))
                backoff_delay += random.uniform(0, 1)  # Adding randomness for jitter
                sleep(backoff_delay)  # Wait before retrying

    # replace `request` with `custom_request`
    head = partialmethod(custom_request, "HEAD")
    get = partialmethod(custom_request, "GET")
    post = partialmethod(custom_request, "POST")
    put = partialmethod(custom_request, "PUT")
    patch = partialmethod(custom_request, "PATCH")
    delete = partialmethod(custom_request, "DELETE")
    options = partialmethod(custom_request, "OPTIONS")
