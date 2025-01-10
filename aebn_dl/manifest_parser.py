import math
from typing import Optional
import lxml.etree as ET

from . import utils
from .models import AudioStream, VideoStream
from .custom_session import CustomSession


class Manifest:
    def __init__(self, url: str, total_duration_seconds: int, session: CustomSession, target_height: Optional[int] = 1, force_resolution: Optional[bool] = False):
        self.input_url = url
        self.total_duration_seconds = total_duration_seconds
        self.session = session
        self.target_height = target_height
        self.force_resolution = force_resolution
        self.base_stream_url: str = None
        self.segment_duration: float = None
        self.total_number_of_data_segments: int = None
        self.video_stream: VideoStream = None
        self.audio_stream: AudioStream = None
        self.avaliable_resulutions: list[int] = None

    def parse_content(self, manifest_content: str) -> None:
        """Parse the XML manifest content"""
        root = ET.fromstring(manifest_content, None)
        self.total_number_of_data_segments = self._total_number_of_data_segments_calc(root, self.total_duration_seconds)
        video_streams = self._parse_and_sort_video_streams(root)
        self.avaliable_resulutions = [video_stream[1] for video_stream in video_streams]
        audio_stream_id = self._find_best_good_audio_stream(video_streams)
        self.audio_stream = AudioStream(audio_stream_id)
        if self.target_height == 0:
            # lowest resolution
            stream_id, height = video_streams[0]
            self.video_stream = VideoStream(stream_id=stream_id, height=height)
            return
        if self.target_height is None:
            # highest resolution
            stream_id, height = video_streams[-1]
            self.video_stream = VideoStream(stream_id=stream_id, height=height)
            return
        if self.target_height:
            # other resolution
            video_stream_id = next((sublist[0] for sublist in video_streams if sublist[1] == self.target_height), None)
            if not video_stream_id and self.force_resolution:
                raise RuntimeError(f"Target video resolution height {self.target_height} not found")
            video_stream_id, target_height = next((sublist for sublist in reversed(video_streams) if sublist[1] <= self.target_height), None)
            self.video_stream = VideoStream(stream_id=video_stream_id, height=target_height)

    def _total_number_of_data_segments_calc(self, root, total_duration_seconds):
        """Calculate total number of segments"""
        # Get timescale
        timescale = float(root.xpath('.//*[local-name()="AdaptationSet" and @mimeType="video/mp4"]//*[local-name()="SegmentTemplate"]/@timescale')[0])
        duration = float(root.xpath('.//*[local-name()="AdaptationSet" and @mimeType="video/mp4"]//*[local-name()="SegmentTemplate"]/@duration')[0])
        # segment duration calc
        self.segment_duration = duration / timescale
        # number of segments calc
        total_number_of_data_segments = total_duration_seconds / self.segment_duration
        total_number_of_data_segments = math.ceil(total_number_of_data_segments)
        return total_number_of_data_segments

    def _find_best_good_audio_stream(self, video_streams: list[tuple[str, int]]) -> str:
        """Find a valid HQ audio stream with ffmpeg, as they can be corrupted"""
        for stream_id, _ in reversed(video_streams):
            init_segment_name = f"ai_{stream_id}"
            init_segment_url = f"{self.base_stream_url}/{init_segment_name}.mp4d"
            init_segment_bytes = self.session.get(init_segment_url).content
            # grab audio segment from the middle of the stream
            data_segment_number = int(self.total_number_of_data_segments / 2)
            data_segment_name = f"a_{stream_id}_{data_segment_number}"
            data_segment_url = f"{self.base_stream_url}/{data_segment_name}.mp4d"
            data_segment_bytes = self.session.get(data_segment_url).content
            if utils.is_valid_media(init_segment_bytes + data_segment_bytes):
                return stream_id
            # skip if not valid
        raise RuntimeError("No valid audio stream found")

    def _parse_and_sort_video_streams(self, root) -> list[tuple[str, int]]:
        video_adaptation_sets = root.xpath('.//*[local-name()="AdaptationSet" and @mimeType="video/mp4"]//*[local-name()="Representation"]')
        video_streams = [(element.get("id"), int(element.get("height"))) for element in video_adaptation_sets]
        sorted_video_streams = sorted(video_streams, key=lambda video_stream: video_stream[1])
        return sorted_video_streams

    def _get_new_manifest_url(self) -> str:
        url_content_type = self.input_url.split("/")[3]
        movie_id = self.input_url.split("/")[5]
        headers = {}
        headers["content-type"] = "application/x-www-form-urlencoded"
        data = f"movieId={movie_id}&isPreview=true&format=DASH"
        url = f"https://{url_content_type}.aebn.com/{url_content_type}/deliver"
        content = self.session.post(url, headers=headers, data=data).json()
        return content["url"]

    def process_manifest(self):
        manifest_url = self._get_new_manifest_url()
        self.base_stream_url = manifest_url.rsplit("/", 1)[0]
        manifest_content = self.session.get(manifest_url).content
        self.parse_content(manifest_content)
