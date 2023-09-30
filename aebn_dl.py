#!/usr/bin/env python3
import argparse
import datetime
import email.utils as eut
import math
import os
import queue
import shutil
import signal
import subprocess
import sys
import threading
import time
from urllib.parse import urlparse

from urllib3.util.retry import Retry

try:
    import lxml.etree as ET
    import requests
    from fake_useragent import UserAgent
    from lxml import html
    from requests.adapters import HTTPAdapter
    from tqdm import tqdm
except ModuleNotFoundError:
    print("""
You need to install required modules:
    lxml (https://pypi.org/project/lxml/)
    requests (https://pypi.org/project/requests/)
    fake-useragent (https://pypi.org/project/fake-useragent/)
    tqdm (https://pypi.org/project/tqdm/)

If you have pip (normally installed with python), run this command in a terminal (cmd):
    pip install lxml requests tqdm fake-useragent
    or
    pip3 install lxml requests tqdm fake-useragent
          """)
    sys.exit()


class Movie:
    def __init__(self, url, target_height, start_segment, end_segment, ffmpeg_dir, scene_n, target_download_dir,
                 scene_padding, download_covers=False, overwrite_existing_segments=False, keep_segments_after_download=False):

        self.movie_url = url
        self.target_height = target_height
        self.start_segment = start_segment
        self.end_segment = end_segment
        self.ffmpeg_dir = ffmpeg_dir
        self.scene_n = scene_n
        self.download_covers = download_covers
        self.overwrite_existing_segments = overwrite_existing_segments
        self.keep_segments_after_download = keep_segments_after_download
        self.scene_padding = scene_padding
        self.stream_types = ["a", "v"]
        if target_download_dir:
            self.target_download_dir = target_download_dir
        else:
            self.target_download_dir = os.getcwd()

    def download(self):
        print(f"Input URL: {self.movie_url}")
        print(f"Saving to: {self.target_download_dir or os.getcwd()}")
        if self.scene_padding:
            if self.scene_n:
                print(f"Scene padding: {self.scene_padding} seconds")
            else:
                print(f"Downloading the full movie, scene padding will be ignored")
        self._session_prep()
        self._scrape_info()
        self._construct_paths()
        self._get_new_manifest_url()
        self._get_manifest_content()
        self._parse_manifest()
        self.file_name += f" Scene {self.scene_n}" if self.scene_n else ""
        self.file_name += f" {self.target_height}p"
        print(self.file_name)
        self._calcualte_scenes_boundaries()
        self._ffmpeg_check()
        self._download_segments()
        self._join_segments()
        self._ffmpeg_mux_video_audio(self.video_stream_path, self.audio_stream_path)
        self._temp_folder_cleanup()
        print("All done!")
        print(self.file_name + ".mp4")

    def _session_prep(self):
        # https://stackoverflow.com/a/47475019/14931505
        self.session = requests.Session()
        retry = Retry(connect=3, backoff_factor=0.5)
        adapter = HTTPAdapter(max_retries=retry)
        self.session.mount('http://', adapter)
        self.session.mount('https://', adapter)

        # setting random user agent
        user_agent = UserAgent()
        random_user_agent = user_agent.random
        self.session.headers["User-Agent"] = random_user_agent

    def _construct_paths(self):
        if not os.path.exists(self.target_download_dir):
            os.makedirs(self.target_download_dir)

        self.download_dir_path = os.path.join(self.target_download_dir, self.movie_id)
        self.audio_stream_path = os.path.join(self.download_dir_path, f"a_{self.movie_id}.mp4")
        self.video_stream_path = os.path.join(self.download_dir_path, f"v_{self.movie_id}.mp4")

    def _remove_chars(self, text):
        for ch in ['#', '?', '!', ':', '<', '>', '"', '/', '\\', '|', '*']:
            if ch in text:
                text = text.replace(ch, '')
        return text

    def _scrape_info(self):
        content = html.fromstring(self.session.get(self.movie_url).content)
        self.url_content_type = self.movie_url.split("/")[3]
        self.movie_id = self.movie_url.split("/")[5]
        self.studio_name = content.xpath('//*[@class="dts-studio-name-wrapper"]/a/text()')[0].strip()
        self.movie_name = content.xpath('//*[@class="dts-section-page-heading-title"]/h1/text()')[0].strip()
        total_duration_string = content.xpath('//*[@class="section-detail-list-item-duration"][2]/text()')[0].strip()
        self.total_duration_seconds = self._time_string_to_seconds(total_duration_string)
        self.studio_name = self._remove_chars(self.studio_name)
        self.movie_name = self._remove_chars(self.movie_name)
        self.file_name = f"{self.studio_name} - {self.movie_name}"
        if self.download_covers:
            try:
                self.cover_front = content.xpath('//*[@class="dts-movie-boxcover-front"]//img/@src')[0].strip()
                self.cover_front = 'https:' + self.cover_front.split("?")[0]
                self.cover_back = content.xpath('//*[@class="dts-movie-boxcover-back"]//img/@src')[0].strip()
                self.cover_back = 'https:' + self.cover_back.split("?")[0]
                self._get_covers(self.cover_front, 'cover-a')
                self._get_covers(self.cover_back, 'cover-b')
            except Exception as e:
                print("Error fetching cover urls: ", e)

    def _get_covers(self, cover_url, cover_name):
        cover_extension = os.path.splitext(cover_url)[1]
        output = os.path.join(self.target_download_dir, f'{self.file_name} {cover_name}{cover_extension}')

        if os.path.isfile(output):
            return

        # Save file from http with server timestamp https://stackoverflow.com/a/58814151/3663357
        r = self.session.get(cover_url)
        f = open(output, "wb")
        f.write(r.content)
        f.close()
        last_modified = r.headers["last-modified"]
        modified = time.mktime(datetime.datetime(*eut.parsedate(last_modified)[:6]).timetuple())  # type: ignore
        now = time.mktime(datetime.datetime.today().timetuple())
        os.utime(output, (now, modified))

        if os.path.isfile(output):
            print("Saved cover:", output)

    def _calcualte_scenes_boundaries(self):
        self.scenes_boundaries = []
        response = html.fromstring(self.session.get(f"https://m.aebn.net/movie/{self.movie_id}").content)
        scene_elems = response.xpath('//div[@class="scroller"]')
        for scene_el in scene_elems:
            start_timing = int(scene_el.get("data-time-start"))
            end_timing = start_timing + int(scene_el.get("data-time-duration"))
            if self.scene_padding and self.scene_n:
                start_timing_padded = start_timing - self.scene_padding
                start_timing = start_timing_padded if start_timing_padded >= 0 else 0
                end_timing_padded = end_timing + self.scene_padding
                end_timing = end_timing_padded if end_timing_padded <= self.total_duration_seconds else self.total_duration_seconds
            start_segment = math.ceil(int(start_timing) / self.segment_duration)
            end_segment = math.ceil(int(end_timing) / self.segment_duration)
            self.scenes_boundaries.append([start_segment, end_segment])

    def _ffmpeg_check(self):
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
        response = self.session.get(self.manifest_url)
        response.raise_for_status()  # Raise an exception for non-2xx status codes
        self.manifest_content = response.content

    def _get_new_manifest_url(self):
        headers = {}
        headers["content-type"] = "application/x-www-form-urlencoded"
        data = f"movieId={self.movie_id}&isPreview=true&format=DASH"
        content = self.session.post(f"https://{self.url_content_type}.aebn.com/{self.url_content_type}/deliver", headers=headers, data=data).json()
        self.manifest_url = content["url"]
        self.base_stream_url = self.manifest_url.rsplit('/', 1)[0]

    def _sort_video_streams_by_height(self, video_stream_elements):
        video_streams = []
        for element in video_stream_elements:
            video_streams.append([element.get('id'), int(element.get('height'))])
        video_streams = sorted(video_streams, key=lambda x: x[1])
        return video_streams

    def _find_best_good_audio_stream(self, video_streams):
        def ffmpeg_error_check(audio_bytes):
            cmd = 'ffmpeg -f mp4 -i pipe:0 -f null -'

            # Use subprocess.Popen with PIPE to create a pipe for input
            process = subprocess.Popen(cmd, shell=True, stdin=subprocess.PIPE, stderr=subprocess.PIPE)

            # Write the audio bytes to the stdin of the FFmpeg process
            _, stderr_data = process.communicate(input=audio_bytes)
            # print(stderr_data.decode())

            # Check if FFmpeg found any errors
            if b"Multiple frames in a packet" in stderr_data or b"Error" in stderr_data:
                return True  # Errors found
            else:
                return False  # No errors found
        for stream_id, _ in reversed(video_streams):
            seg_0 = self._download_segment("a", 0, stream_id, return_bytes=True)
            # grab audio segment from the middle of the stream
            data_segment_number = int(self.total_number_of_segments / 2)
            seg_data = self._download_segment("a", data_segment_number, stream_id, return_bytes=True)
            if not ffmpeg_error_check(seg_0 + seg_data):  # type: ignore
                return stream_id
            else:
                print("Skipping bad audio stream")

    def _parse_manifest(self):
        # Parse the XML manifest
        root = ET.fromstring(self.manifest_content, None)
        self.total_number_of_segments = self._total_number_of_segments_calc(root, self.total_duration_seconds)
        video_adaptation_sets = root.xpath('.//*[local-name()="AdaptationSet" and @mimeType="video/mp4"]//*[local-name()="Representation"]')
        video_streams = self._sort_video_streams_by_height(video_adaptation_sets)
        print("Available video streams:")
        for video_stream in video_streams:
            print(video_stream[1], end=" ")
        print()
        self.audio_stream_id = self._find_best_good_audio_stream(video_streams)
        if self.target_height == 0:
            self.video_stream_id, self.target_height = video_streams[0]
        elif self.target_height == 1:
            self.video_stream_id, self.target_height = video_streams[-1]
        elif self.target_height:
            self.video_stream_id = next((sublist[0] for sublist in video_streams if sublist[1] == self.target_height), None)
            if not self.video_stream_id:
                raise RuntimeError(f"Target video resolution height {self.target_height} not found")

    def _total_number_of_segments_calc(self, root, total_duration_seconds):
        # Get timescale
        timescale = float(root.xpath('.//*[local-name()="AdaptationSet" and @mimeType="video/mp4"]//*[local-name()="SegmentTemplate"]/@timescale')[0])
        duration = float(root.xpath('.//*[local-name()="AdaptationSet" and @mimeType="video/mp4"]//*[local-name()="SegmentTemplate"]/@duration')[0])
        # segment duration calc
        self.segment_duration = duration / timescale
        # number of segments calc
        total_number_of_segments = total_duration_seconds / self.segment_duration
        total_number_of_segments = math.ceil(total_number_of_segments)
        print(f"total segments: {total_number_of_segments}")
        return total_number_of_segments

    def _temp_folder_cleanup(self):
        if not self.keep_segments_after_download:
            self._delete_joined_streams()
        if not os.listdir(self.download_dir_path):
            os.rmdir(self.download_dir_path)

    def _download_segments(self):
        if self.scene_n:
            try:
                self.start_segment, self.end_segment = self.scenes_boundaries[self.scene_n - 1]
            except IndexError:
                sys.exit(f"Scene {self.scene_n} not found!")

        if not self.start_segment:
            self.start_segment = 1
        if not self.end_segment:
            self.end_segment = self.total_number_of_segments

        print(f"Downloading segments {self.start_segment} - {self.end_segment}")

        for stream_type in self.stream_types:
            stream_id = ""
            tqdm_desc = ""
            if stream_type == "a":
                stream_id = self.audio_stream_id
                tqdm_desc = "Audio download"
            elif stream_type == "v":
                stream_id = self.video_stream_id
                tqdm_desc = "Video download"
            self._download_segment(stream_type, 0, stream_id)
            segments_to_download = range(self.start_segment, self.end_segment + 1)
            # using tqdm object so we can manipulate progress
            # and display it as segment 0 was part of the loop
            download_bar = tqdm(total=len(segments_to_download) + 1, desc=tqdm_desc)
            download_bar.update(1)
            for current_segment_number in segments_to_download:
                if not self._download_segment(stream_type, current_segment_number, stream_id):
                    # segment download error, trying again with a new manifest
                    self._session_prep()
                    self._get_new_manifest_url()
                    self._get_manifest_content()
                    if not self._download_segment(stream_type, current_segment_number, stream_id):
                        sys.exit(f"{stream_type}_{stream_id}_{current_segment_number} download error")
                download_bar.update(1)
            download_bar.close()

    def _download_segment(self, segment_type, current_segment_number, stream_id, return_bytes=False):
        segment_file_name = f"{segment_type}_{stream_id}_{current_segment_number}.mp4"
        segment_path = os.path.join(self.download_dir_path, segment_file_name)
        if os.path.exists(segment_path) and not self.overwrite_existing_segments:
            if return_bytes:
                with open(segment_path, 'rb') as segment_file:
                    content = segment_file.read()
                    segment_file.close()
                    return content
            return True
        if current_segment_number == 0:
            segment_url = f"{self.base_stream_url}/{segment_type}i_{stream_id}.mp4d"
        else:
            segment_url = f"{self.base_stream_url}/{segment_type}_{stream_id}_{current_segment_number}.mp4d"
        try:
            response = self.session.get(segment_url)
        except:
            return False
        if return_bytes:
            return response.content

        if response.status_code == 404 and current_segment_number == self.total_number_of_segments:
            # just skip if the last segment does not exists
            # segment calc returns a rouded up float which sometimes bigger that the actual number of segments
            self.end_segment -= 1
            return True
        if response.status_code >= 403 or not response.content:
            return False
        if not os.path.exists(self.download_dir_path):
            os.mkdir(self.download_dir_path)
        with open(segment_path, 'wb') as f:
            f.write(response.content)
        return True

    def _ffmpeg_mux_video_audio(self, video_path, audio_path):
        output_path = os.path.join(self.target_download_dir, f"{self.file_name}.mp4")
        cmd = f'ffmpeg -i "{video_path}" -i "{audio_path}" -c copy "{output_path}" -loglevel warning'

        if self.ffmpeg_dir:
            out = subprocess.run(cmd, shell=True, cwd=self.ffmpeg_dir)
        else:
            out = subprocess.run(cmd, shell=True)
        assert out.returncode == 0

    def _join_files(self, files, output_path, tqdm_desc):
        with open(output_path, 'wb') as f:
            for segment_file_path in tqdm(files, desc=f"Joining {tqdm_desc}"):
                with open(segment_file_path, 'rb') as segment_file:
                    content = segment_file.read()
                    segment_file.close()
                    f.write(content)
        if not self.keep_segments_after_download:
            for segment_file_path in tqdm(files, desc=f"Deleting {tqdm_desc}"):
                os.remove(segment_file_path)

    def _delete_joined_streams(self):
        if os.path.exists(self.audio_stream_path):
            os.remove(self.audio_stream_path)
        if os.path.exists(self.video_stream_path):
            os.remove(self.video_stream_path)

    def _join_segments(self):
        # delete old joined streams if found
        self._delete_joined_streams()

        audio_files = []
        video_files = []
        audio_files.append(os.path.join(self.download_dir_path, f"a_{self.audio_stream_id}_0.mp4"))
        video_files.append(os.path.join(self.download_dir_path, f"v_{self.video_stream_id}_0.mp4"))
        for num in range(self.start_segment, self.end_segment + 1):
            audio_files.append(os.path.join(self.download_dir_path, f"a_{self.audio_stream_id}_{num}.mp4"))
            video_files.append(os.path.join(self.download_dir_path, f"v_{self.video_stream_id}_{num}.mp4"))
        # video_files = sorted(video_files, key=lambda i: int(os.path.splitext(os.path.basename(i))[0].split("_")[1]))
        # audio_files = sorted(audio_files, key=lambda i: int(os.path.splitext(os.path.basename(i))[0].split("_")[1]))

        # concat all audio segment data into a single file
        self._join_files(audio_files, self.audio_stream_path, tqdm_desc='audio segments')

        # concat all video segment data into a single file
        self._join_files(video_files, self.video_stream_path, tqdm_desc='video segments')


def download_movie(url):
    movie_instance = Movie(
        url,
        target_download_dir=args.download_dir,
        ffmpeg_dir=args.ffmpeg,
        target_height=args.resolution,
        scene_n=args.scene,
        start_segment=args.start_segment,
        end_segment=args.end_segment,
        download_covers=args.covers,
        overwrite_existing_segments=args.overwrite,
        keep_segments_after_download=args.keep,
        scene_padding=args.padding
    )
    movie_instance.download()


def worker(q):
    while True:
        value = q.get()
        # subtract 1 because the main thread is included
        print(f"Total threads {threading.active_count() - 1} | Processing {value}")
        download_movie(value)
        q.task_done()


def convert_line_endings(file_path):
    # replacement strings
    WINDOWS_LINE_ENDING = b'\r\n'
    UNIX_LINE_ENDING = b'\n'

    with open(file_path, 'rb') as open_file:
        content = open_file.read()

    # Windows to Unix
    if WINDOWS_LINE_ENDING in content:
        content = content.replace(WINDOWS_LINE_ENDING, UNIX_LINE_ENDING)
        with open(file_path, 'wb') as open_file:
            open_file.write(content)
        print('Converted list.txt to unix line endings, important for linux processing')


if __name__ == "__main__":
    # Make Ctrl-C work when deamon threads are running
    signal.signal(signal.SIGINT, signal.SIG_DFL)

    parser = argparse.ArgumentParser()
    parser.add_argument("url", help="URL of the movie")
    parser.add_argument("-d", "--download_dir", type=str, help="Specify a download directory")
    parser.add_argument("-r", "--resolution", type=int, default=1, help="Desired video resolution by pixel height. Use 0 to select the lowest available resolution. (default: highest available)")
    parser.add_argument("-f", "--ffmpeg", type=str, help="Specify the location of your ffmpeg directory")
    parser.add_argument("-sn", "--scene", type=int, help="Download a single scene using the relevant scene number on AEBN")
    parser.add_argument("-start", "--start_segment", type=int, help="Specify the start segment")
    parser.add_argument("-end", "--end_segment", type=int, help="Specify the end segment")
    parser.add_argument("-c", "--covers", action="store_true", help="Download front and back covers")
    parser.add_argument("-o", "--overwrite", action="store_true", help="Overwrite existing audio and video segments if already present")
    parser.add_argument("-k", "--keep", action="store_true", help="Keep audio and video segments after downloading")
    parser.add_argument("-t", "--threads", type=int, help="Threads for concurrent downloads (default=5)")
    parser.add_argument("-p", "--padding", type=int, help="Set padding for scenes boundaries in seconds")
    args = parser.parse_args()

    q = queue.Queue()
    # validate the url
    result = urlparse(args.url)
    if result.scheme and result.netloc:
        download_movie(args.url)
    # if missing or invalid, check for a list.txt and download concurrently
    elif args.url == "list.txt":
        if sys.platform == 'linux':
            convert_line_endings("list.txt")  # important to have the proper newlines for linux
        file = open("list.txt")
        urllist = file.read().splitlines()  # remove the newlines
        file.close()
        while ("" in urllist):  # remove empty strings from the list (resulted from empty lines)
            urllist.remove("")

        if args.threads:
            while True:
                answer = input('''
\033[0;31m\033[1mWARNING: An excessive concurrent download of scenes/movies
may result in throttling and/or get your IP blocked.
HTTP requests to servers usually have rate limits, so hammering a server
will throttle your connections and cause temporary timeouts.
Be reasonable and use with caution!\033[0m
                               
Are you sure you want to continue? (Y/n) ''').casefold()
                if answer == "y" or answer == "":
                    print()
                    break
                elif answer == "n":
                    sys.exit()
                else:
                    print("Please enter y or n")
        max_threads = args.threads or 5
        # print("Using max threads", max_threads)

        for x in range(max_threads):
            t = threading.Thread(target=worker, args=(q,))
            t.daemon = True
            t.start()

        for url in urllist:
            q.put(url)

        q.join()  # wait for all the threads to finish, then continue below

        if q.empty():
            print("Download queue complete")
    else:
        print("Invalid URL or list.txt not passed")
