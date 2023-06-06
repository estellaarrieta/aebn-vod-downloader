import argparse
import math
import os
import shutil
import sys

try:
    import lxml.etree as ET
    from lxml import html
except ModuleNotFoundError:
    print(
        "You need to install the lxml module. (https://pypi.org/project/lxml/)"
    )
    print(
        "If you have pip (normally installed with python), run this command in a terminal (cmd): pip install lxml"
    )
    sys.exit()

try:
    import requests
except ModuleNotFoundError:
    print(
        "You need to install the requests module. (https://pypi.org/project/requests/)"
    )
    print(
        "If you have pip (normally installed with python), run this command in a terminal (cmd): pip install requests"
    )
    sys.exit()

try:
    import ffmpeg
except ModuleNotFoundError:
    print(
        "You need to install the ffmpeg-python module. (https://pypi.org/project/ffmpeg-python/)"
    )
    print(
        "If you have pip (normally installed with python), run this command in a terminal (cmd): pip install ffmpeg-python"
    )
    sys.exit()


class Movie:
    def __init__(self, url, target_height=None, overwrite_existing_segmets=False, delete_segments_after_download = True):

        self.movie_url = url
        self.delete_segments_after_download = delete_segments_after_download
        self.overwrite_existing_segmets = overwrite_existing_segmets
        self.target_height = target_height
        self.stream_types = ["a", "v"]

    def download(self):
        self._scrape_info()
        self.download_dir_path = os.path.join(os.getcwd(), self.movie_id)
        self._download_segments()
        # self._validate_segmets()
        # asyncio.run(self._download_segments_a(10))
        print("download complete")
        self._join_segments()
        self._ffmpeg_mux_video_audio(self.video_stream_path, self.audio_stream_path)
        if self.delete_segments_after_download:
            print("deleting segment folder...")
            self._temp_folder_cleanup()
            print("all done!")

    def _scrape_info(self):
        content = html.fromstring(requests.get(self.movie_url).content)
        self.url_content_type = self.movie_url.split("/")[2].split(".")[0]
        self.movie_id = self.movie_url.split("/")[5]
        self.studio_name = content.xpath('//*[@class="dts-studio-name-wrapper"]/a/text()')[0].strip()
        self.movie_name = content.xpath('//*[@class="dts-section-page-heading-title"]/h1/text()')[0].strip()
        duration = content.xpath('//*[@class="section-detail-list-item-duration"][2]/text()')[0].strip()
        self.duration_seconds = self._time_string_to_seconds(duration)
        self._get_new_manifest_url()
        self._get_manifest_content()
        self._parse_manifest()
        self.file_name = f"{self.studio_name} - {self.movie_name} {self.target_height}p"
        print(self.file_name)


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

    def _get_best_video_stream_id(self, video_stream_elements):
        # Find the video stream element with the highest height
        highest_height = 0
        highest_height_id = None
        for element in video_stream_elements:
            height = int(element.get('height'))
            if height > highest_height:
                highest_height = height
                highest_height_id = element.get('id')
        self.target_height = highest_height
        self.video_stream_id = highest_height_id

    def _parse_manifest(self):
        # Parse the XML manifest
        root = ET.fromstring(self.manifest_content)
        self.number_of_segments = self._number_of_segments_calc(root, self.duration_seconds)

        self.audio_stream_id = root.xpath('.//*[local-name()="AdaptationSet" and @mimeType="audio/mp4"]//*[local-name()="Representation"]/@id')[0]

        if self.target_height:
            self.video_stream_id = root.xpath(f'.//*[local-name()="AdaptationSet" and @mimeType="video/mp4"]//*[local-name()="Representation"and @height="{self.target_height}"]/@id')[0]
            if not self.video_stream_id:
                print(f"desired video resolution height {self.target_height} not found, aborting")
                sys.exit()
        else:
            video_adaptation_sets = root.xpath('.//*[local-name()="AdaptationSet" and @mimeType="video/mp4"]//*[local-name()="Representation"]')
            self._get_best_video_stream_id(video_adaptation_sets)


    def _number_of_segments_calc(self, root, duration_seconds):
        # Get timescale
        timescale = float(root.xpath('.//*[local-name()="AdaptationSet" and @mimeType="video/mp4"]//*[local-name()="SegmentTemplate"]/@timescale')[0])
        duration = float(root.xpath('.//*[local-name()="AdaptationSet" and @mimeType="video/mp4"]//*[local-name()="SegmentTemplate"]/@duration')[0])
        # segment duration calc
        segment_duration = duration / timescale
        # number of segments calc
        number_of_segments = duration_seconds / segment_duration
        number_of_segments = math.ceil(number_of_segments)
        return number_of_segments

    def _temp_folder_cleanup(self):
        shutil.rmtree(self.download_dir_path)


    def _download_segments(self):
        self.base_stream_url = self.manifest_url.rsplit('/', 1)[0]
        max_segments = self.number_of_segments
        session = requests.Session()
        for stream_type in self.stream_types:
            current_segment_number = 0
            while current_segment_number <= max_segments:
                if stream_type == "a":
                    stream_id = self.audio_stream_id
                else:
                    stream_id = self.video_stream_id
                if self._download_segment(session, stream_type, current_segment_number, stream_id):
                    current_segment_number += 1
                else:
                    # segment download error, trying again with a new manifest
                    self._get_new_manifest_url()
                    self._get_manifest_content()
                    self.base_stream_url = self.manifest_url.rsplit('/', 1)[0]
                    if not self._download_segment(session, stream_type, current_segment_number, stream_id):
                        sys.exit(f"{stream_type}_{current_segment_number} download error")


    def _download_segment(self, session, segment_type, current_segment_number, stream_id):
        if current_segment_number == 0:
            segment_url = f"{self.base_stream_url}/{segment_type}i_{stream_id}.mp4d"
        else:
            segment_url = f"{self.base_stream_url}/{segment_type}_{stream_id}_{current_segment_number}.mp4d"
        print(f"downloading segment {segment_type}_{current_segment_number}")
        segment_file_name = f"{segment_type}_{current_segment_number}.mp4"
        segment_path = os.path.join(self.download_dir_path, segment_file_name)
        if os.path.exists(segment_path) and not self.overwrite_existing_segmets:
            print(f"found {segment_file_name}")
            return True
        try:
            response = session.get(segment_url)
        except:
            return False
        if response.status_code == 404 and current_segment_number==self.number_of_segments:
            # just skip if the last segment does not exists
            # segment calc returns a rouded up float which sometimes bigger that the actual number of segments
            return True
        if response.status_code >= 403 or not response.content:
            return False
        if not os.path.exists(self.download_dir_path):
            os.mkdir(self.download_dir_path)
        with open(segment_path, 'wb') as f:
            f.write(response.content)
        return True


    def _validate_segmets(self):
        missing = []
        for stream_type in self.stream_types:
            segment_number = 0
            while segment_number <= self.number_of_segments:
                segment_file_name = f"{stream_type}_{segment_number}.mp4"
                segment_path = os.path.join(self.download_dir_path, segment_file_name)
                if not os.path.exists(segment_path):
                    missing.append(segment_file_name)
                segment_number+=1
        if not missing:
            return True
        return missing


    def _ffmpeg_mux_video_audio(self, video_path, audio_path):
        input_video = ffmpeg.input(video_path)
        input_audio = ffmpeg.input(audio_path)
        output_file = f"{self.file_name}.mp4"

        output = ffmpeg.output(input_video, input_audio, output_file, shortest=None, codec='copy')
        output.run()

    def _join_files(self, files, output_path):
        with open(output_path, 'wb') as f:
            for segment_file_path in files:
                with open(segment_file_path, 'rb') as segment_file:
                    content = segment_file.read()
                    segment_file.close()
                    f.write(content)
                if self.delete_segments_after_download:
                    os.remove(segment_file_path)

    def _join_segments(self):
        print("joining files...")
        self.audio_stream_path = os.path.join(self.download_dir_path, "a_" + self.movie_id + ".mp4")
        self.video_stream_path = os.path.join(self.download_dir_path, "v_" + self.movie_id + ".mp4")
        # delete old joined streams if found
        if os.path.exists(self.audio_stream_path):
            os.remove(self.audio_stream_path)
        if os.path.exists(self.video_stream_path):
            os.remove(self.video_stream_path)

        # Create a list of video and audio files
        video_files = [os.path.join(self.download_dir_path, file) for file in os.listdir(self.download_dir_path)
                    if file.startswith('v_')]
        audio_files = [os.path.join(self.download_dir_path, file) for file in os.listdir(self.download_dir_path)
                    if file.startswith('a_')]
        video_files = sorted(video_files, key=lambda i: int(os.path.splitext(os.path.basename(i))[0].split("_")[1]))
        audio_files = sorted(audio_files, key=lambda i: int(os.path.splitext(os.path.basename(i))[0].split("_")[1]))

        # concat all audio segment data into a single file
        self._join_files(audio_files, self.audio_stream_path)
        
        # concat all video segment data into a single file
        self._join_files(video_files, self.video_stream_path)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("url", help="URL of the movie")
    parser.add_argument("--target_height", "--h", type=int, help="Target height of the video")
    parser.add_argument("--overwrite_existing_segmets", "--o",action="store_true", help="Overwrite existing segments")
    parser.add_argument("--delete_segments_after_download", "--s",action="store_true", help="Don't delete segments after download")
    args = parser.parse_args()
    movie_instance = Movie(
        url=args.url,
        target_height=args.target_height,
        overwrite_existing_segmets=args.overwrite_existing_segmets,
        delete_segments_after_download=args.delete_segments_after_download,
    )
    movie_instance.download()
    MOVIE_URL = sys.stdin.read()
    Movie(MOVIE_URL).download()
