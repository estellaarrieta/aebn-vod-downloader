import unittest
import os

from aebn_dl import Downloader


class DownloadTest(unittest.TestCase):
    def setUp(self):
        self.url = "https://straight.aebn.com/straight/movies/309021/hot-and-mean-37"
        self.proxy = "socks5://localhost:56567"
        self.work_dir = os.path.join(os.getcwd(), "work_dir")
        self.output_dir = os.path.join(os.getcwd(), "output_dir")

    def test_movie_dl(self):
        Downloader(
            url=self.url,
            proxy=self.proxy,
            work_dir=self.work_dir,
            output_dir=self.output_dir,
            download_covers=True,
            target_height=0,
            log_level="DEBUG",
            start_segment=0,
            end_segment=20,
        ).run()


if __name__ == "__main__":
    unittest.main()
