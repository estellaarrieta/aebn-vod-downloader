#!/usr/bin/env python3
import argparse
import datetime
import email.utils as eut
import math
import os
import shutil
import subprocess
import sys
import time

try:
    from tqdm import tqdm
except ModuleNotFoundError:
    print("You need to install the lxml module. (https://pypi.org/project/tqdm/)")
    print("If you have pip (normally installed with python), run this command in a terminal (cmd): pip install tqdm")
    sys.exit()

try:
    import lxml.etree as ET
    from lxml import html
except ModuleNotFoundError:
    print("You need to install the lxml module. (https://pypi.org/project/lxml/)")
    print("If you have pip (normally installed with python), run this command in a terminal (cmd): pip install lxml")
    sys.exit()

try:
    import requests
except ModuleNotFoundError:
    print("You need to install the requests module. (https://pypi.org/project/requests/)")
    print("If you have pip (normally installed with python), run this command in a terminal (cmd): pip install requests")
    sys.exit()


class Movie:
    def __init__(self, url, target_height=None, start_segment=None, end_segment=None, ffmpeg_dir=None, scene_n=None, download_covers=False, overwrite_existing_segmets=False, keep_segments_after_download=False):

        self.movie_url = url
        self.target_height = target_height
        self.start_segment = start_segment
        self.end_segment = end_segment
        self.ffmpeg_dir = ffmpeg_dir
        self.scene_n = scene_n
        self.download_covers = download_covers
        self.overwrite_existing_segmets = overwrite_existing_segmets
        self.keep_segments_after_download = keep_segments_after_download
        self.stream_types = ["a", "v"]

    def _construct_paths(self):
        self.download_dir_path = os.path.join(os.getcwd(), self.movie_id)
        self.audio_stream_path = os.path.join(self.download_dir_path, f"a_{self.movie_id}.mp4")
        self.video_stream_path = os.path.join(self.download_dir_path, f"v_{self.movie_id}.mp4")

    def download(self):
        print(f"Input URL: {self.movie_url}")
        self._scrape_info()
        self._ffmpeg_check()
        self._construct_paths()
        self._download_segments()
        print("Download complete")
        self._join_segments()
        self._ffmpeg_mux_video_audio(self.video_stream_path, self.audio_stream_path)
        if not self.keep_segments_after_download:
            self._temp_folder_cleanup()
        print("All done!")

    def _remove_chars(self, text):
        for ch in ['#', '?', '!', ':', '<', '>', '"', '/', '\\', '|', '*']:
            if ch in text:
                text = text.replace(ch, '')
        return text

    def _scrape_info(self):
        content = html.fromstring(requests.get(self.movie_url).content)
        self.url_content_type = self.movie_url.split("/")[2].split(".")[0]
        self.movie_id = self.movie_url.split("/")[5]
        self.studio_name = content.xpath('//*[@class="dts-studio-name-wrapper"]/a/text()')[0].strip()
        self.movie_name = content.xpath('//*[@class="dts-section-page-heading-title"]/h1/text()')[0].strip()
        total_duration_string = content.xpath('//*[@class="section-detail-list-item-duration"][2]/text()')[0].strip()
        self.total_duration_seconds = self._time_string_to_seconds(total_duration_string)
        self._get_new_manifest_url()
        self._get_manifest_content()
        self._parse_manifest()
        self._calcualte_scenes_segments(content)
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
        if self.scene_n:
            self.file_name += f" Scene {self.scene_n}"
        self.file_name += f" {self.target_height}p"
        print(self.file_name)

    def _get_covers(self, cover_url, cover_name):
        cover_extension = os.path.splitext(cover_url)[1]
        output = f'{self.file_name} {cover_name}{cover_extension}'

        # Save file from http with server timestamp https://stackoverflow.com/a/58814151/3663357
        r = requests.get(cover_url)
        f = open(output, "wb")
        f.write(r.content)
        f.close()
        last_modified = r.headers["last-modified"]
        modified = time.mktime(datetime.datetime(*eut.parsedate(last_modified)[:6]).timetuple())  # type: ignore
        now = time.mktime(datetime.datetime.today().timetuple())
        os.utime(output, (now, modified))

        if os.path.isfile(output):
            print("Saved cover:", output)

    def _broaden_scene_boundaries(self, scenes_timecodes):
        scenes_boundaries = []
        for i in range(0, len(scenes_timecodes)):
            # Replaces the first element with the last element of the previous sublist
            # and the last element with the first element of the next sublist
            if i == 0 and i == len(scenes_timecodes) - 1:
                scene_boundaries = [0, self.total_number_of_segments]
            elif i == 0:
                scene_boundaries = [0, scenes_timecodes[i + 1][0] - 1]
            elif i == len(scenes_timecodes) - 1:
                scene_boundaries = [scenes_timecodes[i - 1][1] + 1, self.total_number_of_segments]
            else:
                scene_boundaries = [scenes_timecodes[i - 1][1] + 1, scenes_timecodes[i + 1][0] - 1]
            scenes_boundaries.append(scene_boundaries)
        return scenes_boundaries

    def _calcualte_scenes_segments(self, content):
        # aebn does not have exact timings on the page, but
        # we can use target scene's neighbors to roughly assume target's length
        scenes_segments = []
        scenes_elems = content.xpath("//section[contains(@id, 'scene-')]")
        for scene_el_n, scene_el in enumerate(scenes_elems):
            if scene_el_n == 0:
                start_segment = 1
            else:
                start_timing = scene_el.xpath('.//div[@class="dts-scene-result-image-group"]/@id')[0]
                start_timing = start_timing.split("-")[-1]
                start_segment = math.ceil(int(start_timing) / self.segment_duration)
            if scene_el_n == len(scenes_elems) - 1:
                end_segment = self.total_number_of_segments
            else:
                end_timing = scene_el.xpath('.//div[@data-time-code-seconds]/@data-time-code-seconds')[-1]
                end_segment = math.ceil(int(end_timing) / self.segment_duration)
            scenes_segments.append([int(start_segment), int(end_segment)])
        self.scenes_boundaries = self._broaden_scene_boundaries(scenes_segments)

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
        response = requests.get(self.manifest_url)
        response.raise_for_status()  # Raise an exception for non-2xx status codes
        self.manifest_content = response.content

    def _get_new_manifest_url(self):
        headers = {}
        headers["content-type"] = "application/x-www-form-urlencoded"
        data = f"movieId={self.movie_id}&isPreview=true&format=DASH"
        content = requests.post(f"https://{self.url_content_type}.aebn.com/{self.url_content_type}/deliver", headers=headers, data=data).json()
        self.manifest_url = content["url"]

    def _sort_video_streams(self, video_stream_elements):
        video_streams = []
        for element in video_stream_elements:
            video_streams.append([element.get('id'), int(element.get('height'))])
        video_streams = sorted(video_streams, key=lambda x: x[1])
        return video_streams

    def _parse_manifest(self):
        # Parse the XML manifest
        root = ET.fromstring(self.manifest_content, None)
        self.total_number_of_segments = self._total_number_of_segments_calc(root, self.total_duration_seconds)

        self.audio_stream_id = root.xpath('.//*[local-name()="AdaptationSet" and @mimeType="audio/mp4"]//*[local-name()="Representation"]/@id')[0]
        video_adaptation_sets = root.xpath('.//*[local-name()="AdaptationSet" and @mimeType="video/mp4"]//*[local-name()="Representation"]')
        video_streams = self._sort_video_streams(video_adaptation_sets)
        print("Avaliable video streams:")
        for video_stream in video_streams:
            print(video_stream[1])
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
        print("Deleting segment folder")
        if os.path.islink(self.download_dir_path):
            raise RuntimeError("Symlink detected! Refusing to remove.")
        elif os.path.isdir(self.download_dir_path):
            shutil.rmtree(self.download_dir_path)
        else:
            print(f"Unexpected path type: {self.download_dir_path}")

    def _download_segments(self):
        self.base_stream_url = self.manifest_url.rsplit('/', 1)[0]
        if self.scene_n:
            self.start_segment, self.end_segment = self.scenes_boundaries[self.scene_n - 1]

        session = requests.Session()
        for stream_type in self.stream_types:
            if not self.start_segment:
                self.start_segment = 1
            if not self.end_segment:
                self.end_segment = self.total_number_of_segments
            if stream_type == "a":
                stream_id = self.audio_stream_id
                tqdm_desc = "Audio download"
            elif stream_type == "v":
                stream_id = self.video_stream_id
                tqdm_desc = "Video download"
            self._download_segment(session, stream_type, 0, stream_id)
            segments_to_download = range(self.start_segment, self.end_segment + 1)
            for current_segment_number in tqdm(segments_to_download, desc=tqdm_desc):
                if not self._download_segment(session, stream_type, current_segment_number, stream_id):
                    # segment download error, trying again with a new manifest
                    self._get_new_manifest_url()
                    self._get_manifest_content()
                    self.base_stream_url = self.manifest_url.rsplit('/', 1)[0]
                    if not self._download_segment(session, stream_type, current_segment_number, stream_id):
                        sys.exit(f"{stream_type}_{stream_id}_{current_segment_number} download error")

    def _download_segment(self, session, segment_type, current_segment_number, stream_id):
        if current_segment_number == 0:
            segment_url = f"{self.base_stream_url}/{segment_type}i_{stream_id}.mp4d"
        else:
            segment_url = f"{self.base_stream_url}/{segment_type}_{stream_id}_{current_segment_number}.mp4d"
        segment_file_name = f"{segment_type}_{stream_id}_{current_segment_number}.mp4"
        segment_path = os.path.join(self.download_dir_path, segment_file_name)
        if os.path.exists(segment_path) and not self.overwrite_existing_segmets:
            # print(f"found {segment_file_name}")
            return True
        try:
            response = session.get(segment_url)
        except:
            return False
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
        output_file = f"{self.file_name}.mp4"
        output_path = os.path.join(os.getcwd(), output_file)
        cmd = f'ffmpeg -i "{video_path}" -i "{audio_path}" -c copy "{output_path}"'
        if self.ffmpeg_dir:
            out = subprocess.run(cmd, shell=True, cwd=self.ffmpeg_dir)
        else:
            out = subprocess.run(cmd, shell=True)
        assert out.returncode == 0

    def _join_files(self, files, output_path, tqdm_desc):
        with open(output_path, 'wb') as f:
            for segment_file_path in tqdm(files, desc=tqdm_desc):
                with open(segment_file_path, 'rb') as segment_file:
                    content = segment_file.read()
                    segment_file.close()
                    f.write(content)
                if not self.keep_segments_after_download:
                    os.remove(segment_file_path)

    def _join_segments(self):
        # delete old joined streams if found
        if os.path.exists(self.audio_stream_path):
            os.remove(self.audio_stream_path)
        if os.path.exists(self.video_stream_path):
            os.remove(self.video_stream_path)

        audio_files = []
        video_files = []
        audio_files.append(os.path.join(self.download_dir_path, f"a_{self.audio_stream_id}_0.mp4"))
        video_files.append(os.path.join(self.download_dir_path, f"v_{self.video_stream_id}_0.mp4"))
        for num in range(self.start_segment, self.end_segment):
            audio_files.append(os.path.join(self.download_dir_path, f"a_{self.audio_stream_id}_{num}.mp4"))
            video_files.append(os.path.join(self.download_dir_path, f"v_{self.video_stream_id}_{num}.mp4"))
        video_files = sorted(video_files, key=lambda i: int(os.path.splitext(os.path.basename(i))[0].split("_")[1]))
        audio_files = sorted(audio_files, key=lambda i: int(os.path.splitext(os.path.basename(i))[0].split("_")[1]))

        # concat all audio segment data into a single file
        self._join_files(audio_files, self.audio_stream_path, tqdm_desc='Joining audio files')

        # concat all video segment data into a single file
        self._join_files(video_files, self.video_stream_path, tqdm_desc='Joining video files')


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("url", help="URL of the movie")
    parser.add_argument("-r", type=int, default=1, help="Target video resolution height. Use 0 to select the lowest. Default is the highest")
    parser.add_argument("-f", type=str, help="ffmpeg directory")
    parser.add_argument("-sn", type=int, help="Target scene to download")
    parser.add_argument("-start", type=int, help="Specify the start segment")
    parser.add_argument("-end", type=int, help="Specify the end segment")
    parser.add_argument("-c", action="store_true", help="Download covers")
    parser.add_argument("-o", action="store_true", help="Overwrite existing segments on the disk")
    parser.add_argument("-k", action="store_true", help="Keep segments after download")
    args = parser.parse_args()
    movie_instance = Movie(
        url=args.url,
        ffmpeg_dir=args.f,
        target_height=args.r,
        scene_n=args.sn,
        start_segment=args.start,
        end_segment=args.end,
        download_covers=args.c,
        overwrite_existing_segmets=args.o,
        keep_segments_after_download=args.k,
    )
    movie_instance.download()
