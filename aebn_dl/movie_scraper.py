import math
from lxml import html

from . import utils
from .models import Scene
from .custom_session import CustomSession


class Movie:
    def __init__(self, url: str, session: CustomSession):
        self.input_url = url
        self.session = session
        self.url_content_type: str = None
        self.movie_id: str = None
        self.studio_name: str = None
        self.title: str = None
        self.total_duration_seconds: int = None
        self.performers: list = None
        self.scenes: list[Scene] = []
        self.cover_url_front: str = None
        self.cover_url_back: str = None
        self.scenes_boundaries = []
        self._scrape_info()

    def _scrape_info(self):
        """Scrape movie metadata from aebn.com"""
        content = html.fromstring(self.session.get(self.input_url).content)
        self.url_content_type = self.input_url.split("/")[3]
        self.movie_id = self.input_url.split("/")[5]
        self.studio_name = self._extract_studio_name(content)
        self.title = content.xpath('//*[@class="dts-section-page-heading-title"]/h1/text()')[0].strip()
        total_duration_string = content.xpath('//*[@class="section-detail-list-item-duration"][2]/text()')[0].strip()
        self.total_duration_seconds = utils.duration_to_seconds(total_duration_string)
        self.studio_name = utils.remove_chars(self.studio_name)
        self.title = utils.remove_chars(self.title)
        self.performers = content.xpath('//section[@id="dtsPanelStarsDetailMovie"]//a/@title')
        scene_elements = content.xpath('//section[@id[starts-with(., "scene")]]')
        for scene_element in scene_elements:
            scene_performers = scene_element.xpath('.//li[@class="dts-scene-strip-stars"]//a/text()')
            scene = Scene(performers=scene_performers)
            self.scenes.append(scene)
        cover_front = content.xpath('//*[@class="dts-movie-boxcover-front"]//img/@src')[0].strip()
        self.cover_url_front = "https:" + cover_front.split("?")[0]
        cover_back = content.xpath('//*[@class="dts-movie-boxcover-back"]//img/@src')[0].strip()
        self.cover_url_back = "https:" + cover_back.split("?")[0]

    def _extract_studio_name(self, content) -> str:
        studio_names = content.xpath('//*[@class="dts-studio-name-wrapper"]/a/text()')
        if len(studio_names) > 0:
            return studio_names[0].replace(",", "").strip()
        return ""

    def calculate_scenes_boundaries(self, segment_duration: float):
        """Calculate scene segment boundaries with data from m.aebn.net"""
        response = self.session.get(f"https://m.aebn.net/movie/{self.movie_id}")
        html_tree = html.fromstring(response.content)
        scene_elems = html_tree.xpath('//div[@class="scroller"]')
        for i, scene_el in enumerate(scene_elems):
            target_scene = self.scenes[i]
            target_scene.start_timing = int(scene_el.get("data-time-start"))
            target_scene.end_timing = target_scene.start_timing + int(scene_el.get("data-time-duration"))
            target_scene.start_segment = math.floor(int(target_scene.start_timing) / segment_duration)
            target_scene.end_segment = math.ceil(int(target_scene.end_timing) / segment_duration)
