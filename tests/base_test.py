import unittest
from aebn_dl.movie import Movie


class DownloadTest(unittest.TestCase):
    def setUp(self):
        self.url = "https://straight.aebn.com/straight/movies/309021/hot-and-mean-37"

    def test_movie_dl(self):
        Movie(url=self.url).download()


if __name__ == "__main__":
    unittest.main()
