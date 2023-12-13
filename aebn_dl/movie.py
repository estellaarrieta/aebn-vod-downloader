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
                 scene_padding=None, log_level="INFO", proxy=None, proxy_metadata_only=False, download_covers=False, overwrite_existing_files=False, 
                 keep_segments_after_download=False, aggressive_segment_cleaning = False,
                 resolution_force=False, include_performer_names=False, segment_validity_check=False):
        self.movie_url = url
        self._logger_setup(log_level)
        self.output_dir = output_dir or os.getcwd()
        self.work_dir = work_dir or os.getcwd()
        self.target_height = target_height
        self.resolution_force = resolution_force
        self.include_performer_names = include_performer_names
        self.start_segment = start_segment
        self.end_segment = end_segment
        self.ffmpeg_dir = ffmpeg_dir
        self.scene_n = scene_n
        self.download_covers = download_covers
        self.overwrite_existing_files = overwrite_existing_files
        self.aggressive_segment_cleaning = aggressive_segment_cleaning
        self.keep_segments_after_download = keep_segments_after_download
        self.scene_padding = scene_padding
        self.log_level = log_level
        self.segment_validity_check = segment_validity_check
        self.stream_map = []
        self.proxy = proxy
        self.proxy_metadata_only = proxy_metadata_only

    def _logger_setup(self, log_level):
        movie_logger = logging.getLogger(self.movie_url.split("/")[5])
        movie_logger.setLevel(log_level)
        formatter = logging.Formatter('%(asctime)s|%(levelname)s|%(message)s', datefmt='%H:%M:%S')
        main_handler = logging.StreamHandler()
        main_handler.setFormatter(formatter)
        movie_logger.addHandler(main_handler)

        self.logger = movie_logger
        self.is_silent = True if movie_logger.getEffectiveLevel() > logging.INFO else False

    def download(self):
        self.logger.info(f"Input URL: {self.movie_url}")
        self.logger.info(f"Proxy: {self.proxy}") if self.proxy else None
        self.logger.info(f"Output dir: {self.output_dir}")
        self.logger.info(f"Work dir: {self.work_dir}")
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
        self._scrape_info()
        self._construct_paths()
        self._get_new_manifest_url()
        self._get_manifest_content()
        self._parse_streams_from_manifest()
        self.file_name += f" Scene {self.scene_n}" if self.scene_n else ""
        if self.include_performer_names:
            if not self.performers and self.scene_n:
                self.logger.info(f"No performers listed for scene {self.scene_n}")
            if self.performers:
                self.file_name += " " + ", ".join(self.performers)
        self.file_name += f" {self.target_height}p"
        self.logger.info(self.file_name)
        if self.scene_n:
            self._calculate_scenes_boundaries()
        self._download_segments()
        self._join_segments_into_stream()
        self._ffmpeg_mux_streams(*[stream["path"] for stream in self.stream_map])
        self._work_folder_cleanup()
        self.logger.info(Path(self.output_path).as_uri())
        self.logger.info("All done!")
        self.logger.info(f"{self.file_name}.mp4")

    def _create_new_session(self, use_proxies=True):
        self.session = requests.Session()
        self.session.http_version = 2
        self.session.impersonate = "chrome110"
        self.session.headers["User-Agent"] = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/110.0.0.0 Safari/537.36"
        if self.proxy and use_proxies:
            self.session.proxies = {
                "http": self.proxy,
                "https": self.proxy
            }

    def _send_request(self, request_type, url, headers=None, data=None, max_retries=3):
        retry_timeout = 3
        if request_type.lower() == 'get':
            for _ in range(max_retries):
                try:
                    response = self.session.get(url, headers=headers)
                    return response
                except Exception as e:
                    self.logger.debug(f"Request failed: {e}")
                    time.sleep(retry_timeout)
            self.logger.debug("Max retries exceeded. Unable to complete the request.")
            raise Exception

        elif request_type.lower() == 'post':
            for _ in range(max_retries):
                try:
                    response = self.session.post(url, data=data, headers=headers)
                    return response
                except Exception as e:
                    self.logger.debug(f"Request failed: {e}")
                    time.sleep(retry_timeout)

            self.logger.debug("Max retries exceeded. Unable to complete the request.")
            raise Exception

        else:
            self.logger.debug("Invalid request type. Use 'get' or 'post'.")

    def _construct_paths(self):
        self.output_path = os.path.join(self.output_dir, f"{self.file_name}.mp4")
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
            sys.exit("ffmpeg not found! please add it to PATH, or provide it's directory as a parameter")

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

    def _add_stream(self, stream_name, stream_id):
        stream_type = stream_name[0].lower()
        new_stream = {
            'human_name': stream_name,
            'type': stream_type,
            'id': stream_id,
            'path': os.path.join(self.movie_work_dir, f"{stream_type}_{self.movie_id}.mp4")
        }
        self.stream_map.append(new_stream)

    def _parse_streams_from_manifest(self):
        # Parse the XML manifest
        root = ET.fromstring(self.manifest_content, None)
        self.total_number_of_data_segments = self._total_number_of_data_segments_calc(root, self.total_duration_seconds)
        video_adaptation_sets = root.xpath('.//*[local-name()="AdaptationSet" and @mimeType="video/mp4"]//*[local-name()="Representation"]')
        video_streams = self._sort_streams_by_video_height(video_adaptation_sets)
        streams_res_string = " ".join(str(video_stream[1]) for video_stream in video_streams)
        self.logger.info(f"Available video streams: {streams_res_string}")
        self._add_stream("audio", self._find_best_good_audio_stream(video_streams))
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
        self._add_stream("video", video_stream_id)

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
            self.logger.info("Deleting temp files...")
            for stream in self.stream_map:
                os.remove(stream['path']) if os.path.exists(stream['path']) else None
            for segment_path in self.segment_file_list:
                os.remove(segment_path) if os.path.exists(segment_path) else None

        os.rmdir(self.movie_work_dir) if not os.listdir(self.movie_work_dir) else None
        os.rmdir(self.movie_work_dir) if not os.listdir(self.work_dir) else None

    def _download_segments(self):
        if self.proxy and self.proxy_metadata_only:
            self.session.proxies = {}
        if self.scene_n:
            try:
                self.start_segment, self.end_segment = self.scenes_boundaries[self.scene_n - 1]
            except IndexError:
                sys.exit(f"Scene {self.scene_n} not found!")

        self.start_segment = self.start_segment or 0
        self.end_segment = self.end_segment or self.total_number_of_data_segments

        self.logger.info(f"Downloading segments {self.start_segment} - {self.end_segment}")

        for stream in self.stream_map:
            # downloading init segment
            init_segment_bytes = self._download_segment(stream['type'], stream['id'],
                                                        overwrite=self.overwrite_existing_files)

            # using tqdm object so we can manipulate progress
            # and display it as init segment was part of the loop

            segments_to_download = range(self.start_segment, self.end_segment + 1)
            download_bar = tqdm(total=len(segments_to_download) + 1, desc=stream['human_name'] + " download", disable=self.is_silent)
            download_bar.update()  # increment by 1
            for current_segment_number in segments_to_download:
                data_segment_bytes = self._download_segment(stream['type'], stream['id'],
                                                            segment_number=current_segment_number,
                                                            overwrite=self.overwrite_existing_files)

                if self.segment_validity_check and data_segment_bytes:
                    # slow
                    if not self._is_valid_media(init_segment_bytes + data_segment_bytes):
                        self.logger.info(f"{stream['type']} {current_segment_number} segment media error")
                        data_segment_bytes = self._download_segment(stream['type'], stream['id'],
                                                                    segment_number=current_segment_number,
                                                                    overwrite=True)
                        if not self._is_valid_media(init_segment_bytes + data_segment_bytes):
                            sys.exit(f"{stream['type']}_{stream['id']}_{current_segment_number} Segment not valid!")

                download_bar.update()
            download_bar.close()

    def _download_segment(self, stream_type, stream_id, save_to_disk=True, segment_number=None, overwrite=False, max_tries=2):
        if isinstance(segment_number, int):
            segment_name = f"{stream_type}_{stream_id}_{segment_number}"
        else:
            segment_name = f"{stream_type}i_{stream_id}"

        segment_url = f"{self.base_stream_url}/{segment_name}.mp4d"
        segment_path = os.path.join(self.movie_work_dir, f"{segment_name}.mp4")
        if os.path.exists(segment_path) and not overwrite:
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
                self._get_manifest_content()
                self._get_new_manifest_url()
                tries += 1

        if response:
            if response.ok:
                if save_to_disk:
                    if not os.path.exists(self.work_dir):
                        os.mkdir(self.work_dir)
                    with open(segment_path, 'wb') as f:
                        f.write(response.content)
                return response.content
            elif response.status_code == 404 and segment_number == self.total_number_of_data_segments:
                # just skip if the last segment does not exist
                # segment calc returns a rounded up float which is sometimes bigger than the actual number of segments
                self.logger.debug("Last segment is 404, skipping")
                self.end_segment -= 1
                return None
            else:
                sys.exit(f"{segment_name} Download error! Response Status : {response.status_code}")
        else:
            sys.exit(f"{segment_name} Download error! Failed to get a response")

    def _ffmpeg_mux_streams(self, stream_path_1, stream_path_2):
        cmd = f'ffmpeg -i "{stream_path_1}" -i "{stream_path_2}" -y -c copy "{self.output_path}"'
        cmd += " -loglevel warning" if self.logger.getEffectiveLevel() > logging.DEBUG else ""

        cwd = self.ffmpeg_dir if self.ffmpeg_dir else None
        out = subprocess.run(cmd, shell=True, cwd=cwd)
        assert out.returncode == 0

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

    def _join_segments_into_stream(self):
        self.segment_file_list = [] # only used for clean up
        for stream in self.stream_map:
            # delete old joined stream if exists
            os.remove(stream['path']) if os.path.exists(stream['path']) else None
            segment_files = []
            os.remove(stream['path']) if os.path.exists(stream['path']) else None
            init_path = os.path.join(self.movie_work_dir, f"{stream['type']}i_{stream['id']}.mp4")
            segment_files.append(init_path)
            self.segment_file_list.append(init_path)
            for num in range(self.start_segment, self.end_segment + 1):
                data_path = os.path.join(self.movie_work_dir, f"{stream['type']}_{stream['id']}_{num}.mp4")
                segment_files.append(data_path)
                self.segment_file_list.append(data_path)
            self._join_files(segment_files, stream['path'], tqdm_desc=f"{stream['human_name']} segments")
