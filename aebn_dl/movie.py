#!/usr/bin/env python3
import datetime
import email.utils as eut
import logging
import math
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

import lxml.etree as ET
from curl_cffi import requests
from lxml import html
from tqdm import tqdm


class Movie:
    def __init__(self, url, target_height=None, start_segment=None, end_segment=None, ffmpeg_dir=None, scene_n=None, output_dir=None, work_dir=None,
                 scene_padding=None, log_level="INFO", proxy=None, proxy_metadata_only=False, download_covers=False,
                 overwrite_existing_files=False, target_stream=None,
                 keep_segments_after_download=False, aggressive_segment_cleaning=False,
                 resolution_force=False, include_performer_names=False, segment_validity_check=False, keep_logs=False):
        """
        Parameters:
        - url: The URL of the movie.
        - target_height: The desired height of the movie.
        - start_segment: The starting segment of the movie.
        - end_segment: The ending segment of the movie.
        - ffmpeg_dir: The directory for FFMPEG.
        - scene_n: The scene number of the movie.
        - output_dir: The directory for output.
        - work_dir: The directory to store temp files in.
        - scene_padding: Padding in seconds.
        - log_level: Logging level (default is "INFO").
        - proxy: Proxy.
        - proxy_metadata_only: Use proxy for metadata only.
        - download_covers: Flag to download covers.
        - overwrite_existing_files: Flag to overwrite existing files.
        - target_stream: Download only the specified stream.
        - keep_segments_after_download: Flag to keep segments after download.
        - aggressive_segment_cleaning: Flag for aggressive segment cleaning.
        - resolution_force: Flag to force resolution.
        - include_performer_names: Flag to include performer names in output file name.
        - segment_validity_check: Flag for segment validity check.
        - keep_logs: Flag to keep logs.
        """

        self.movie_url = url
        self.output_dir = output_dir or os.getcwd()
        self.work_dir = work_dir or os.getcwd()
        self.audio_stream = None
        self.video_stream = None
        self.target_height = target_height
        self.resolution_force = resolution_force
        self.include_performer_names = include_performer_names
        self.start_segment = start_segment
        self.end_segment = end_segment
        self.ffmpeg_dir = ffmpeg_dir
        self.scene_n = scene_n
        self.download_covers = download_covers
        self.overwrite_existing_files = overwrite_existing_files
        self.target_stream = target_stream
        self.aggressive_segment_cleaning = aggressive_segment_cleaning
        self.keep_segments_after_download = keep_segments_after_download
        self.scene_padding = scene_padding
        self.log_level = log_level
        self.keep_logs = keep_logs
        self.segment_validity_check = segment_validity_check
        self.proxy = proxy
        self.proxy_metadata_only = proxy_metadata_only
        self._logger_setup(log_level)

    class _Media_stream:
        def __init__(self, human_name, id, movie_work_dir):
            self.human_name = human_name
            self.type = self.human_name[0].lower()
            self.id = id
            self.path = os.path.join(movie_work_dir, f"{self.type}_{self.id}.mp4")
            self.downloaded_segments = []

    def _logger_setup(self, log_level):
        logger_name = self.movie_url.split("/")[5] + "_" + str(self.scene_n) if self.scene_n else self.movie_url.split("/")[5]
        movie_logger = logging.getLogger(logger_name)
        movie_logger.setLevel(logging.DEBUG)  # Set the logger level to the lowest (DEBUG)

        formatter = logging.Formatter('%(asctime)s|%(levelname)s|%(message)s', datefmt='%H:%M:%S')

        # Console handler with user set level
        console_handler = logging.StreamHandler()
        console_handler.setLevel(log_level)
        console_handler.set_name("console_handler")
        console_handler.setFormatter(formatter)
        movie_logger.addHandler(console_handler)

        # File handler with DEBUG level
        file_handler = logging.FileHandler(f'{logger_name}.log')
        file_handler.setLevel(logging.DEBUG)
        file_handler.set_name("file_handler")
        file_handler.setFormatter(formatter)
        movie_logger.addHandler(file_handler)

        # https://stackoverflow.com/questions/6234405/
        def log_uncaught_exceptions(exctype, value, tb):
            self.logger.critical("Uncaught exception", exc_info=(exctype, value, tb))

        # Set the exception hook to log uncaught exceptions
        sys.excepthook = log_uncaught_exceptions

        self.logger = movie_logger
        self.is_silent = True if movie_logger.getEffectiveLevel() > logging.INFO else False

    def _get_handler_level(self, handler_name):
        for handler in self.logger.handlers:
            if handler.name == handler_name: 
                return handler.level
        return None

    def _delete_log(self):
        for handler in self.logger.handlers:
            if isinstance(handler, logging.FileHandler):
                handler.close()  # Close the file handler before deleting the file
        os.remove(f"{self.logger.name}.log")

    def _log_version(self):
        try:
            import pkg_resources
            version = pkg_resources.require("aebndl")[0].version
            self.logger.debug(f"Version: {version}")
        except Exception as e:
            self.logger.debug(f"Unknown version, {e}")

    def download(self):
        self._log_version()
        self.logger.info(f"Input URL: {self.movie_url}")
        self.logger.info(f"Proxy: {self.proxy}") if self.proxy else None
        self.logger.info(f"Output dir: {self.output_dir}")
        self.logger.info(f"Work dir: {self.work_dir}")
        self.logger.info(f"Target stream: {self.target_stream}") if self.target_stream else None
        self.logger.info(f"Segment validity check: {self.segment_validity_check}")
        if self.aggressive_segment_cleaning:
            self.logger.info("Aggressive cleanup enabled, segments will be deleted before stream muxing")
        if self.scene_padding:
            if self.scene_n:
                self.logger.info(f"Scene padding: {self.scene_padding} seconds")
            else:
                self.logger.info("Downloading the full movie, scene padding will be ignored")
        if self.target_height is None:
            self.logger.info("Target resolution: Highest")
        elif self.target_height > 0:
            self.logger.info(f"Target resolution: {self.target_height}")
        elif self.target_height == 0:
            self.logger.info("Target resolution: Lowest")
        self._ffmpeg_check()
        self._create_new_session()
        try:
            self._scrape_info()
        except Exception as e:
            self.logger.error(e)
            raise Exception("Failed to scrape aebn.com, make sure your isp not blocking it, or use proxy/vpn")
        self._construct_paths()
        self._get_new_manifest_url()
        self._get_manifest_content()
        self._parse_streams_from_manifest()
        self.file_name = f"{self.target_stream}_{self.file_name}" if self.target_stream else self.file_name
        self.file_name += f" Scene {self.scene_n}" if self.scene_n else ""
        if self.include_performer_names:
            if not self.performers and self.scene_n:
                self.logger.info(f"No performers listed for scene {self.scene_n}")
            self.file_name += " " + ", ".join(self.performers) if self.performers else ""
        self.file_name += f" {self.target_height}p" if self.video_stream else ''
        self.output_path = os.path.join(self.output_dir, f"{self.file_name}.mp4")
        self.logger.info(self.file_name)
        self._calculate_scenes_boundaries() if self.scene_n else None
        self._download_segments()
        self._join_stream_segmetns()
        if all([self.audio_stream, self.video_stream]):
            self.logger.info("Muxing streams with ffmpeg")
            self._ffmpeg_mux_streams(self.audio_stream.path, self.video_stream.path)
        else:
            os.remove(self.output_path) if os.path.exists(self.output_path) else None
            os.rename(self.audio_stream.path, self.output_path) if self.audio_stream else None
            os.rename(self.video_stream.path, self.output_path) if self.video_stream else None

        self._work_folder_cleanup()
        self.logger.info(Path(self.output_path).as_uri())
        self.logger.info(f"{self.file_name}.mp4")
        self.logger.info("Success!")
        self._delete_log() if not self.keep_logs else None

    def _create_new_session(self, use_proxies=True):
        self.session = requests.Session()
        self.session.http_version = 2
        self.session.impersonate = "chrome110"
        self.session.headers["User-Agent"] = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/110.0.0.0 Safari/537.36"
        self.session.headers["Connection"] = "keep-alive"
        if self.proxy and use_proxies:
            self.session.proxies = {
                "http": self.proxy,
                "https": self.proxy
            }

    def _send_request(self, request_type, url, headers=None, data=None, max_retries=3):
        retry_timeout = 3
        supported_methods = ['get', 'post']

        if request_type.lower() not in supported_methods:
            raise Exception("Invalid request type. Use 'get' or 'post'.")
        
        cookies = {
            'ageGated': '',
            'terms': ''
        }

        for _ in range(max_retries):
            try:
                if request_type.lower() == 'get':
                    response = self.session.get(url, headers=headers, cookies=cookies)
                else:
                    response = self.session.post(url, data=data, headers=headers, cookies=cookies)
                return response

            except Exception as e:
                self.logger.debug(f"{url} Request failed: {e}")
                time.sleep(retry_timeout)

        raise Exception(f"{url} Max retries exceeded. Unable to complete the request.")

    def _construct_paths(self):
        if not os.path.exists(self.output_dir):
            os.makedirs(self.output_dir)

        self.movie_work_dir = os.path.join(self.work_dir, self.movie_id)

        if not os.path.exists(self.movie_work_dir):
            os.makedirs(self.movie_work_dir)

    def _remove_chars(self, text):
        for ch in ['#', '?', '!', ':', '<', '>', '"', '/', '\\', '|', '*']:
            if ch in text:
                text = text.replace(ch, '')
        return text

    def _scrape_info(self):
        content = html.fromstring(self._send_request('get', self.movie_url).content)
        self.url_content_type = self.movie_url.split("/")[3]
        self.movie_id = self.movie_url.split("/")[5]
        self.studio_name = content.xpath('//*[@class="dts-studio-name-wrapper"]/a/text()')[0].strip()
        self.movie_name = content.xpath('//*[@class="dts-section-page-heading-title"]/h1/text()')[0].strip()
        total_duration_string = content.xpath('//*[@class="section-detail-list-item-duration"][2]/text()')[0].strip()
        self.total_duration_seconds = self._time_string_to_seconds(total_duration_string)
        self.studio_name = self._remove_chars(self.studio_name)
        self.movie_name = self._remove_chars(self.movie_name)
        self.file_name = f"{self.studio_name} - {self.movie_name}"
        if self.include_performer_names:
            if self.scene_n:
                self.performers = content.xpath(f'(//li[@class="dts-scene-strip-stars"])[{self.scene_n}]//a/text()')
            else:
                self.performers = content.xpath(f'//section[@id="dtsPanelStarsDetailMovie"]//a/@title')
        if self.download_covers:
            try:
                self.cover_front = content.xpath('//*[@class="dts-movie-boxcover-front"]//img/@src')[0].strip()
                self.cover_front = 'https:' + self.cover_front.split("?")[0]
                self.cover_back = content.xpath('//*[@class="dts-movie-boxcover-back"]//img/@src')[0].strip()
                self.cover_back = 'https:' + self.cover_back.split("?")[0]
                self._get_covers(self.cover_front, 'cover-a')
                self._get_covers(self.cover_back, 'cover-b')
            except Exception as e:
                self.logger.warning("Error fetching cover urls: ", e)

    def _get_covers(self, cover_url, cover_name):
        cover_extension = os.path.splitext(cover_url)[1]
        output = os.path.join(self.output_dir, f'{self.file_name} {cover_name}{cover_extension}')

        if os.path.isfile(output):
            return

        # Save file from http with server timestamp https://stackoverflow.com/a/58814151/3663357
        r = self._send_request('get', cover_url)
        f = open(output, "wb")
        f.write(r.content)
        f.close()
        last_modified = r.headers["last-modified"]
        modified = time.mktime(datetime.datetime(*eut.parsedate(last_modified)[:6]).timetuple())  # type: ignore
        now = time.mktime(datetime.datetime.today().timetuple())
        os.utime(output, (now, modified))

        if os.path.isfile(output):
            self.logger.info("Saved cover:", output)

    def _calculate_scenes_boundaries(self):
        # using data from m.aebn.net to calculate scene segment boundaries
        self.scenes_boundaries = []
        response = self._send_request('get', f"https://m.aebn.net/movie/{self.movie_id}")
        html_tree = html.fromstring(response.content)
        scene_elems = html_tree.xpath('//div[@class="scroller"]')
        for scene_el in scene_elems:
            start_timing = int(scene_el.get("data-time-start"))
            end_timing = start_timing + int(scene_el.get("data-time-duration"))
            if self.scene_padding and self.scene_n:
                start_timing_padded = start_timing - self.scene_padding
                start_timing = start_timing_padded if start_timing_padded >= 0 else 0
                end_timing_padded = end_timing + self.scene_padding
                end_timing = end_timing_padded if end_timing_padded <= self.total_duration_seconds else self.total_duration_seconds
            start_segment = math.floor(int(start_timing) / self.segment_duration)
            end_segment = math.ceil(int(end_timing) / self.segment_duration)
            self.scenes_boundaries.append([start_segment, end_segment])

    def _ffmpeg_check(self):
        # check if ffmpeg is available
        ffmpeg_exe = shutil.which("ffmpeg") is not None
        if not ffmpeg_exe and self.ffmpeg_dir is None:
            raise Exception("ffmpeg not found! please add it to PATH, or provide it's directory as a parameter")

    def _time_string_to_seconds(self, time_string):
        time_parts = list(map(int, time_string.split(':')))
        time_parts.reverse()  # Reverse the list to start from seconds
        total_seconds = 0
        for i, part in enumerate(time_parts):
            if i == 0:  # Seconds
                total_seconds += part
            elif i == 1:  # Minutes
                total_seconds += part * 60
            elif i == 2:  # Hours
                total_seconds += part * 3600
        return total_seconds

    def _get_manifest_content(self):
        # Make HTTP request to get the manifest
        response = self._send_request('get', self.manifest_url)
        self.manifest_content = response.content

    def _get_new_manifest_url(self):
        headers = {}
        headers["content-type"] = "application/x-www-form-urlencoded"
        data = f"movieId={self.movie_id}&isPreview=true&format=DASH"
        url = f"https://{self.url_content_type}.aebn.com/{self.url_content_type}/deliver"
        content = self._send_request('post', url, headers=headers, data=data).json()
        self.manifest_url = content["url"]
        self.logger.debug(f"Manifest URL: {self.manifest_url}")
        self.base_stream_url = self.manifest_url.rsplit('/', 1)[0]

    def _sort_streams_by_video_height(self, video_stream_elements):
        video_streams = [(element.get('id'), int(element.get('height'))) for element in video_stream_elements]
        sorted_video_streams = sorted(video_streams, key=lambda video_stream: video_stream[1])
        return sorted_video_streams

    def _is_valid_media(self, media_bytes):
        cmd = 'ffmpeg -f mp4 -i pipe:0 -f null -'

        # Use subprocess.Popen with PIPE to create a pipe for input
        process = subprocess.Popen(cmd, shell=True, stdin=subprocess.PIPE, stderr=subprocess.PIPE)

        # Write the media bytes to the stdin of the FFmpeg process
        _, stderr_data = process.communicate(input=media_bytes)
        # self.logger.debug(stderr_data.decode())

        # Check if FFmpeg found any errors
        if b"Multiple frames in a packet" in stderr_data or b"Error" in stderr_data:
            return False  # Not Valid
        return True  # Valid

    def _find_best_good_audio_stream(self, video_streams):
        # some audio streams can be corrupted, using ffmpeg to test
        for stream_id, _ in reversed(video_streams):
            init_segment_bytes = self._download_segment("a", stream_id, save_to_disk=False)
            # grab audio segment from the middle of the stream
            data_segment_number = int(self.total_number_of_data_segments / 2)
            data_segment_bytes = self._download_segment("a", stream_id, save_to_disk=False, segment_number=data_segment_number)
            if self._is_valid_media(init_segment_bytes + data_segment_bytes):
                return stream_id
            self.logger.debug("Skipping a bad audio stream")

    def _parse_streams_from_manifest(self):
        # Parse the XML manifest
        root = ET.fromstring(self.manifest_content, None)
        self.total_number_of_data_segments = self._total_number_of_data_segments_calc(root, self.total_duration_seconds)
        video_adaptation_sets = root.xpath('.//*[local-name()="AdaptationSet" and @mimeType="video/mp4"]//*[local-name()="Representation"]')
        video_streams = self._sort_streams_by_video_height(video_adaptation_sets)
        streams_res_string = " ".join(str(video_stream[1]) for video_stream in video_streams)
        self.logger.info(f"Available video streams: {streams_res_string}")
        if self.target_stream and self.target_stream == 'audio' or not self.target_stream:
            audio_stream_id = self._find_best_good_audio_stream(video_streams)
            self.audio_stream = self._Media_stream("audio", audio_stream_id, self.movie_work_dir)
        if self.target_stream and self.target_stream == 'video' or not self.target_stream:
            if self.target_height == 0:
                video_stream_id, self.target_height = video_streams[0]
            elif self.target_height is None:
                video_stream_id, self.target_height = video_streams[-1]
            elif self.target_height:
                video_stream_id = next((sublist[0] for sublist in video_streams if sublist[1] == self.target_height), None)
                if not video_stream_id and self.resolution_force:
                    raise RuntimeError(f"Target video resolution height {self.target_height} not found")
                else:
                    video_stream_id, self.target_height = next((sublist for sublist in reversed(video_streams) if sublist[1] <= self.target_height), None)
            self.video_stream = self._Media_stream("video", video_stream_id, self.movie_work_dir)

    def _total_number_of_data_segments_calc(self, root, total_duration_seconds):
        # Get timescale
        timescale = float(root.xpath('.//*[local-name()="AdaptationSet" and @mimeType="video/mp4"]//*[local-name()="SegmentTemplate"]/@timescale')[0])
        duration = float(root.xpath('.//*[local-name()="AdaptationSet" and @mimeType="video/mp4"]//*[local-name()="SegmentTemplate"]/@duration')[0])
        # segment duration calc
        self.segment_duration = duration / timescale
        # number of segments calc
        total_number_of_data_segments = total_duration_seconds / self.segment_duration
        total_number_of_data_segments = math.ceil(total_number_of_data_segments)
        self.logger.info(f"Total segments: {total_number_of_data_segments+1}")  # +1 to include init segment
        return total_number_of_data_segments

    def _work_folder_cleanup(self):
        if not self.keep_segments_after_download:
            for stream in [self.audio_stream, self.video_stream]:
                if stream is None:
                    continue
                os.remove(stream.path) if os.path.exists(stream.path) else None
                for segment_path in stream.downloaded_segments:
                    os.remove(segment_path) if os.path.exists(segment_path) else None
            self.logger.info("Deleted temp files")

        os.rmdir(self.movie_work_dir) if not os.listdir(self.movie_work_dir) else None
        os.rmdir(self.movie_work_dir) if not os.listdir(self.work_dir) else None

    def _download_segments(self):
        if self.proxy and self.proxy_metadata_only:
            self.session.proxies = {}
        if self.scene_n:
            try:
                self.start_segment, self.end_segment = self.scenes_boundaries[self.scene_n - 1]
            except IndexError:
                raise IndexError(f"Scene {self.scene_n} not found!")

        self.start_segment = self.start_segment or 0
        self.end_segment = self.end_segment or self.total_number_of_data_segments

        self.logger.info(f"Downloading segments {self.start_segment} - {self.end_segment}")

        for stream in [self.audio_stream, self.video_stream]:
            if stream == None:
                continue
            self.logger.debug(f"Downloading {stream.human_name} stream ID: {stream.id}")
            # downloading init segment
            init_segment_bytes = self._download_segment(stream.type, stream.id,
                                                        overwrite=self.overwrite_existing_files,
                                                        media_stream=stream)

            # using tqdm object so we can manipulate progress
            # and display it as init segment was part of the loop

            segments_to_download = range(self.start_segment, self.end_segment + 1)
            download_bar = tqdm(total=len(segments_to_download) + 1, desc=stream.human_name.capitalize() + " download", disable=self.is_silent)
            download_bar.update()  # increment by 1
            for current_segment_number in segments_to_download:
                data_segment_bytes = self._download_segment(stream.type, stream.id,
                                                            segment_number=current_segment_number,
                                                            overwrite=self.overwrite_existing_files,
                                                            media_stream=stream)

                if self.segment_validity_check and data_segment_bytes:
                    # slow
                    if not self._is_valid_media(init_segment_bytes + data_segment_bytes):
                        self.logger.info(f"{stream.human_name.capitalize()} segment {current_segment_number} media error")
                        data_segment_bytes = self._download_segment(stream.type, stream.id,
                                                                    segment_number=current_segment_number,
                                                                    overwrite=True)
                        if not self._is_valid_media(init_segment_bytes + data_segment_bytes):
                            raise Exception(f"{stream.type}_{stream.id}_{current_segment_number} Segment not valid!")

                download_bar.update()
            download_bar.close()

    def _download_segment(self, stream_type, stream_id, save_to_disk=True, segment_number=None, overwrite=False, max_tries=2, media_stream=None):
        if isinstance(segment_number, int):
            segment_name = f"{stream_type}_{stream_id}_{segment_number}"
        else:
            segment_name = f"{stream_type}i_{stream_id}"

        segment_url = f"{self.base_stream_url}/{segment_name}.mp4d"
        segment_path = os.path.join(self.movie_work_dir, f"{segment_name}.mp4")
        if os.path.exists(segment_path) and not overwrite:
            self.logger.debug(f"{segment_name} found on disk")
            media_stream.downloaded_segments.append(segment_path) if media_stream else None
            with open(segment_path, 'rb') as segment_file:
                segment_bytes = segment_file.read()
                segment_file.close()
                return segment_bytes

        response = None
        tries = 0
        while response is None and tries < max_tries:
            try:
                response = self._send_request('get', segment_url)
            except Exception as e:
                self.logger.debug("Segment download error: {}".format(e))
                self._create_new_session(use_proxies=not self.proxy_metadata_only)
                self._get_new_manifest_url()
                self._get_manifest_content()
                tries += 1

        if response:
            if response.ok:
                if save_to_disk:
                    if not os.path.exists(self.work_dir):
                        os.mkdir(self.work_dir)
                    with open(segment_path, 'wb') as f:
                        f.write(response.content)
                    media_stream.downloaded_segments.append(segment_path) if media_stream else None
                    self.logger.debug(f"{segment_name} saved to disk")
                return response.content
            elif response.status_code == 404 and segment_number == self.total_number_of_data_segments:
                # just skip if the last segment does not exist
                # segment calc returns a rounded up float which is sometimes bigger than the actual number of segments
                self.logger.debug("Last segment is 404, skipping")
                self.end_segment -= 1
                return None
            else:
                raise Exception(f"{segment_name} Download error! Response Status : {response.status_code}")
        else:
            raise Exception(f"{segment_name} Download error! Failed to get a response")

    def _ffmpeg_mux_streams(self, stream_path_1, stream_path_2):
        cmd = f'ffmpeg -i "{stream_path_1}" -i "{stream_path_2}" -y -c copy "{self.output_path}"'

        if self._get_handler_level("console_handler") > logging.DEBUG:
            cmd += " -loglevel warning"

        cwd = self.ffmpeg_dir if self.ffmpeg_dir else None
        out = subprocess.run(cmd, shell=True, cwd=cwd, capture_output=True, text=True)
        self.logger.warning(f"ffmpeg stderr: {out.stderr}") if out.stderr else None
        assert out.returncode == 0
        self.logger.info(f"ffmpeg muxing success")

    def _join_files(self, files, output_path, tqdm_desc):
        # concats segments into a single file
        join_bar = tqdm(files, desc=f"Joining {tqdm_desc}", disable=self.is_silent)
        with open(output_path, 'wb') as f:
            for segment_file_path in files:
                with open(segment_file_path, 'rb') as segment_file:
                    content = segment_file.read()
                    segment_file.close()
                    f.write(content)
                    join_bar.update()
                if self.aggressive_segment_cleaning:
                    os.remove(segment_file_path)
        join_bar.close()

    def _join_stream_segmetns(self):
        for stream in [self.audio_stream, self.video_stream]:
            if stream is None:
                continue
            # delete old joined stream if exists
            os.remove(stream.path) if os.path.exists(stream.path) else None
            self._join_files(stream.downloaded_segments, stream.path, tqdm_desc=f"{stream.human_name} segments")
