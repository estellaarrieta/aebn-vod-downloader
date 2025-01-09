import unittest
from aebn_dl.movie import Downloader


class DownloadTest(unittest.TestCase):
    def setUp(self):
        self.url = "https://straight.aebn.com/straight/movies/309021/hot-and-mean-37"
        self.proxy = "socks5://localhost:56567"

    def test_movie_dl(self):
        Downloader(
            url=self.url,
            proxy=self.proxy,
            download_covers=True,
            log_level="DEBUG",
        ).run()


if __name__ == "__main__":
    unittest.main()
