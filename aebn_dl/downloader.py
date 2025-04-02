import datetime
import email.utils as eut
import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from threading import Lock

import os
import time
from typing import Literal

from tqdm.auto import tqdm

from . import utils
from .custom_session import CustomSession
from .models import MediaStream
from .movie_scraper import Movie
from .manifest_parser import Manifest
from .exceptions import Forbidden


class Downloader:
    def __init__(
        self,
        url: str,
        target_height: int | None = None,
        scene_n: int | None = None,
        start_segment: int = 0,
        end_segment: int | None = None,
        output_dir: str = "",
        work_dir: str = "",
        proxy: str = "",
        threads: int = 5,
        proxy_metadata_only: bool = False,
        download_covers: bool = False,
        overwrite_existing_files: bool = False,
        target_stream: Literal["audio", "video", None] = None,
        keep_segments_after_download: bool = False,
        aggressive_segment_cleaning: bool = False,
        force_resolution: bool = False,
        include_performer_names: bool = False,
        log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = "INFO",
        keep_logs: bool = False,
    ):
        """
        Args:
            url: The URL of the movie.
            target_height: The desired height of the movie in pixels.
            scene_n: The scene number of the movie.
            start_segment: Set the start segment.
            end_segment: Set the end segment.
            output_dir: The directory where the output file will be saved.
            work_dir: The directory to store temporary files during processing.
            log_level: The logging level ("DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"). Defaults to "INFO".
            proxy: The proxy server address to use for network requests.
            threads: Threads for concurrent downloads. Default 5.
            proxy_metadata_only: If True, use the proxy only for metadata requests, otherwise use it for all requests. Defaults to False.
            download_covers: If True, download cover images. Defaults to False.
            overwrite_existing_files: If True, overwrite existing files in the output directory. Defaults to False.
            target_stream: The target stream to download ("audio", "video", or None for both). Defaults to None.
            keep_segments_after_download: If True, keep the downloaded segments after processing. Defaults to False.
            aggressive_segment_cleaning: If True, aggressively clean up segments during processing. Defaults to False.
            force_resolution: If True, force the specified resolution even if it's not available. Defaults to False.
            include_performer_names: If True, include performer names in the output file name. Defaults to False.
            keep_logs: If True, keep log files after processing. Defaults to False.
        """

        self.input_url = url
        self.output_dir = output_dir or os.getcwd()
        self.work_dir = work_dir or os.getcwd()
        self.target_height = target_height
        self.force_resolution = force_resolution
        self.include_performer_names = include_performer_names
        self.scene_n = scene_n
        self.download_covers = download_covers
        self.overwrite_existing_files = overwrite_existing_files
        self.target_stream = target_stream
        self.start_segment = start_segment
        self.end_segment = end_segment
        self.aggressive_segment_cleaning = aggressive_segment_cleaning
        self.keep_segments_after_download = keep_segments_after_download
        self.log_level = log_level
        self.keep_logs = keep_logs
        self.proxy = proxy
        self.threads = threads
        self.proxy_metadata_only = proxy_metadata_only
        self.logger = utils.new_logger(name=self._movie_logger_name(), log_level=log_level)
        self.is_silent = self.logger.getEffectiveLevel() > logging.INFO
        self.movie_work_dir: str | None = None
        self.manifest: Manifest | None = None
        self.session: CustomSession | None = None

    def run(self) -> None:
        """Executes the movie download process."""
        self._initialize_download()
        scraped_movie = self._scrape_movie_info()
        self._process_manifest(scraped_movie)
        output_file_name = self._generate_output_name(scraped_movie)
        self._create_dirs(scraped_movie.movie_id)
        self._set_stream_paths()
        if self.download_covers:
            self._download_movie_covers(scraped_movie)
        output_path = os.path.join(self.output_dir, output_file_name)
        self.logger.info(f"Output file name: {output_file_name}")
        self._download_streams(scraped_movie)
        self._process_streams(output_path)
        self._cleanup()

    def _init_new_session(self, use_proxies: bool = True) -> None:
        """Init new curl_cffi session"""
        self.session = CustomSession(impersonate="chrome")
        self.session.timeout = 30
        self.session.headers["User-Agent"] = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36"
        self.session.headers["Connection"] = "keep-alive"
        self.session.cookies.update({"ageGated": "", "terms": ""})
        if self.proxy and use_proxies:
            self.session.proxies = {"http": self.proxy, "https": self.proxy}

    def _movie_logger_name(self) -> str:
        """Generate logger name from movie url"""
        name = self.input_url.split("/")[5]
        if self.scene_n:
            return f"{name}_{self.scene_n}"
        return name

    def _get_handler_level(self, handler_name: str) -> int | None:
        for handler in self.logger.handlers:
            if handler.name == handler_name:
                return handler.level
        return None

    def _delete_log(self) -> None:
        for handler in self.logger.handlers:
            if isinstance(handler, logging.FileHandler):
                handler.close()  # Close the file handler before deleting the file
        os.remove(f"{self.logger.name}.log")

    def _log_init_state(self) -> None:
        """Log input arguments"""
        self.logger.info(f"Input URL: {self.input_url}")
        self.logger.info(f"Proxy: {self.proxy}")
        self.logger.info(f"Threads: {self.threads}")
        self.logger.info(f"Output dir: {self.output_dir}")
        self.logger.info(f"Work dir: {self.work_dir}")
        self.logger.info(f"Target stream: {self.target_stream or 'both'}")
        if self.aggressive_segment_cleaning:
            self.logger.info("Aggressive cleanup enabled, segments will be deleted before stream muxing")
        if self.target_height is None:
            self.logger.info("Target resolution: Highest")
        elif self.target_height > 0:
            self.logger.info(f"Target resolution: {self.target_height}")
        elif self.target_height == 0:
            self.logger.info("Target resolution: Lowest")

    def _generate_output_name(self, scraped_movie: Movie) -> str:
        """Generate output file name from movie metadata"""
        output_file_name = []
        if self.target_stream:
            output_file_name.append(f"[{self.target_stream}]")
        output_file_name.append(scraped_movie.studio_name)
        output_file_name.append("-")
        output_file_name.append(scraped_movie.title)
        if self.scene_n:
            output_file_name.append(f"Scene {self.scene_n}")
        if self.include_performer_names:
            if self.scene_n:
                scene = scraped_movie.scenes[self.scene_n - 1]
                performers = scene.performers
            else:
                performers = scraped_movie.performers
            if performers:
                output_file_name.append(", ".join(performers))
        if self.target_stream != "audio":
            output_file_name.append(f"{self.manifest.video_stream.height}p")
        return " ".join(filter(None, output_file_name)) + ".mp4"

    def _cleanup(self) -> None:
        """Cleans up the work directory and potentially deletes logs."""
        self._work_folder_cleanup()
        if not self.keep_logs:
            self._delete_log()

    def _concat_stream(self, stream: MediaStream) -> None:
        """Concat stream segments into a single file"""
        if os.path.exists(stream.path):
            os.remove(stream.path)
        utils.concat_segments(
            files=stream.downloaded_segments,
            output_path=stream.path,
            tqdm_desc=f"{stream.human_name} segments",
            aggressive_cleaning=self.aggressive_segment_cleaning,
            silent=self.is_silent,
        )

    def _concat_streams(self) -> None:
        """Concatenate streams concurrently using thread pool"""
        streams_to_concat = [stream for stream in (self.manifest.audio_stream, self.manifest.video_stream) if stream.human_name == self.target_stream or not self.target_stream]

        with ThreadPoolExecutor(max_workers=len(streams_to_concat)) as executor:
            futures = []
            for stream in streams_to_concat:
                future = executor.submit(self._concat_stream, stream)
                futures.append(future)

            for future in futures:
                future.result()

    def _process_streams(self, output_path: str) -> None:
        """Processes the downloaded streams, concatinating, and either muxing or renaming based on target stream."""
        self._concat_streams()
        if not self.target_stream:
            self._mux_streams(output_path)
        else:
            self._rename_stream(output_path)

    def _mux_streams(self, output_path: str) -> None:
        """Muxes audio and video streams using ffmpeg."""
        self.logger.info("Muxing streams with ffmpeg")
        utils.ffmpeg_mux_streams(self.manifest.audio_stream.path, self.manifest.video_stream.path, output_path)
        self.logger.info("Muxing success")

    def _rename_stream(self, output_path: str) -> None:
        """Renames the target stream to the output path."""
        for stream in (self.manifest.audio_stream, self.manifest.video_stream):
            if stream.human_name == self.target_stream:
                if os.path.exists(output_path):
                    os.remove(output_path)
                os.rename(stream.path, output_path)

    def _download_movie_covers(self, scraped_movie: Movie) -> None:
        """Downloads the movie covers."""
        full_name = f"{scraped_movie.studio_name} - {scraped_movie.title}"
        self._download_cover(full_name, scraped_movie.cover_url_front, front=True)
        self._download_cover(full_name, scraped_movie.cover_url_back, front=False)

    def _set_stream_paths(self) -> None:
        """Sets the file paths for the audio and video streams."""
        for stream in (self.manifest.audio_stream, self.manifest.video_stream):
            stream.path = os.path.join(self.movie_work_dir, f"{stream.media_type}_{stream.stream_id}.mp4")

    def _create_dirs(self, movie_id: str) -> None:
        os.makedirs(self.output_dir, exist_ok=True)
        self.movie_work_dir = os.path.join(self.work_dir, movie_id)
        os.makedirs(self.movie_work_dir, exist_ok=True)

    def _process_manifest(self, scraped_movie: Movie) -> None:
        """Processes the movie manifest."""
        self.logger.info("Processing manifest")
        self.manifest = Manifest(
            self.input_url,
            scraped_movie.total_duration_seconds,
            self.session,
            target_height=self.target_height,
            force_resolution=self.force_resolution,
        )
        self.manifest.process_manifest()
        scraped_movie.calculate_scenes_boundaries(self.manifest.segment_duration)

    def _scrape_movie_info(self) -> Movie:
        """Scrapes movie information from the input URL."""
        self.logger.info("Scraping movie info")
        return Movie(self.input_url, self.session)

    def _initialize_download(self) -> None:
        """Initializes the download process, checks for ffmpeg, and initializes a new session."""
        self._log_init_state()
        utils.ffmpeg_check()
        self._init_new_session()

    def _download_cover(self, movie_title: str, cover_url: str, front: bool) -> None:
        """Save cover image to disk with server timestamp"""
        cover_extension = os.path.splitext(cover_url)[1]
        if front:
            output = os.path.join(self.output_dir, f"{movie_title} front{cover_extension}")
        else:
            output = os.path.join(self.output_dir, f"{movie_title} back{cover_extension}")

        if os.path.isfile(output):
            return

        # Save file from http with server timestamp https://stackoverflow.com/a/58814151/3663357
        response = self.session.get(cover_url)
        with open(output, "wb") as f:
            f.write(response.content)
        last_modified = response.headers["last-modified"]
        modified = time.mktime(datetime.datetime(*eut.parsedate(last_modified)[:6]).timetuple())  # type: ignore
        now = time.mktime(datetime.datetime.today().timetuple())
        os.utime(output, (now, modified))

        if os.path.isfile(output):
            self.logger.info(f"Saved cover: {output}")

    def _work_folder_cleanup(self) -> None:
        if not self.keep_segments_after_download:
            for stream in (self.manifest.audio_stream, self.manifest.video_stream):
                if stream.human_name != self.target_stream:
                    if os.path.exists(stream.path):
                        os.remove(stream.path)
                for segment_path in stream.downloaded_segments:
                    if os.path.exists(segment_path):
                        os.remove(segment_path)
            self.logger.info("Deleted temp files")

        if not os.listdir(self.movie_work_dir):
            os.rmdir(self.movie_work_dir)

    def _download_streams(self, scraped_movie: Movie) -> None:
        """Download movie streams concurrently"""
        if self.proxy and self.proxy_metadata_only:
            # disable proxies in session
            self.session.proxies = None

        if self.scene_n:
            try:
                scene = scraped_movie.scenes[self.scene_n - 1]
                segment_range = (scene.start_segment, scene.end_segment)
            except IndexError as e:
                raise IndexError(f"Scene {self.scene_n} not found!") from e
        else:
            start_segment = self.start_segment or 0
            end_segment = self.end_segment or self.manifest.total_number_of_data_segments
            segment_range = (start_segment, end_segment)

        self.logger.info(f"Downloading segments {segment_range[0]} - {segment_range[1]}")

        # Determine which streams to download
        streams_to_download = []
        for stream in (self.manifest.audio_stream, self.manifest.video_stream):
            if stream.human_name == self.target_stream or not self.target_stream:
                streams_to_download.append(stream)

        # Download streams in parallel
        with ThreadPoolExecutor(max_workers=2) as executor:
            futures = {executor.submit(self._download_stream, stream, segment_range): stream for stream in streams_to_download}
            for future in as_completed(futures):
                stream = futures[future]
                try:
                    future.result()
                except Exception as e:
                    self.logger.error(f"Failed to download {stream.human_name} stream: {str(e)}")
                    raise

    def _download_stream(self, stream: MediaStream, segment_range: tuple[int, int]) -> None:
        """Download stream segments in given range using threadpool"""
        self.logger.debug(f"Downloading {stream.human_name} stream ID: {stream.stream_id}")

        # Download init segment (single thread)
        self._download_segment(stream, segment_number=None)

        segments_to_download = range(segment_range[0], segment_range[1] + 1)
        download_bar = tqdm(total=len(segments_to_download) + 1, desc=stream.human_name.capitalize() + " download", disable=self.is_silent)
        download_bar.update()  # increment by 1 for init segment

        # Lock for thread-safe manifest refresh
        manifest_lock = Lock()

        def download_task(segment_num):
            try:
                self._download_segment(stream, segment_number=segment_num)
            except Forbidden:
                with manifest_lock:
                    self.manifest.process_manifest()
                    self.logger.debug("Manifest refreshed")
                    self._download_segment(stream, segment_number=segment_num)
            return segment_num

        with ThreadPoolExecutor(max_workers=self.threads) as executor:
            futures = {executor.submit(download_task, i): i for i in segments_to_download}

            for future in as_completed(futures):
                try:
                    future.result()  # This will re-raise any exceptions
                except Exception as e:
                    self.logger.error(f"Failed to download segment {futures[future]}: {str(e)}")
                    raise
                download_bar.update()

        download_bar.close()

    def _download_segment(self, stream: MediaStream, segment_number: int | None = None) -> None:
        """Download and save stream segment"""
        if isinstance(segment_number, int):
            segment_name = f"{stream.media_type}_{stream.stream_id}_{segment_number}"
        else:
            segment_name = f"{stream.media_type}i_{stream.stream_id}"

        segment_url = f"{self.manifest.base_stream_url}/{segment_name}.mp4d"
        segment_path = os.path.join(self.movie_work_dir, f"{segment_name}.mp4")
        if os.path.exists(segment_path) and not self.overwrite_existing_files:
            self.logger.debug(f"{segment_name} found on disk")
            stream.downloaded_segments.append(segment_path)
            return

        response = self.session.get(segment_url)

        if response.ok:
            with open(segment_path, "wb") as f:
                f.write(response.content)
            stream.downloaded_segments.append(segment_path)
            self.logger.debug(f"{segment_name} saved to disk")
        elif response.status_code == 404 and segment_number == self.manifest.total_number_of_data_segments:
            # just skip if the last segment does not exist
            # segment calc returns a rounded up float which is sometimes bigger than the actual number of segments
            self.logger.debug("Last segment is 404, skipping")
        elif response.status_code == 403:
            raise Forbidden
        else:
            raise RuntimeError(f"{segment_name} Download error! Response Status : {response.status_code}")
