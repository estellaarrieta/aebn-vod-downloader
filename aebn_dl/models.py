from dataclasses import dataclass, field


@dataclass
class Scene:
    performers: list
    start_timing: int = field(init=False)
    end_timing: int = field(init=False)
    start_segment: int = field(init=False)
    end_segment: int = field(init=False)


@dataclass
class MediaStream:
    stream_id: str
    human_name: str
    media_type: str
    path: str = field(init=False)
    downloaded_segments: list[str] = field(default_factory=list)


@dataclass
class AudioStream(MediaStream):
    human_name: str = "audio"
    media_type: str = "a"


@dataclass
class VideoStream(MediaStream):
    human_name: str = "video"
    media_type: str = "v"
    height: int = 0
