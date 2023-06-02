import datetime
import pathlib
import tempfile
from urllib.parse import urljoin
from xml.etree import ElementTree as ET

import ffmpeg
import lxml.etree as ET
import requests
from lxml import html


target_height = 1080 #leave blank to let ffmpeg choose the best
MOVIE_URL = "" # "https://straight.aebn.com/straight/movies/*"

def modify_manifest(manifest_content, base_url, duration_seconds, target_height):
    # Namespace register
    prefix = 'mpd'
    uri = 'urn:mpeg:dash:schema:mpd:2011'
    ET.register_namespace(prefix, uri)
    ns = {prefix: uri}

    # Parse the XML manifest
    root = ET.fromstring(manifest_content)

    # Update the mediaPresentationDuration attribute
    root.set('mediaPresentationDuration', f'PT{duration_seconds}S')

    # Remove streams that do not match the target height or get the larger height value
    max_height = 0
    adaptation_sets = root.findall('.//mpd:AdaptationSet', namespaces=ns)
    for adaptation_set in adaptation_sets:
        representations = adaptation_set.findall('mpd:Representation', namespaces=ns)
        for representation in representations:
            height = representation.get('height')
            if target_height:
                if height is not None and int(height) != target_height:
                    adaptation_set.remove(representation)
            else:
                if height is not None and int(height) > max_height:
                    max_height = int(height)

    # Update startNumber attribute in SegmentTemplate elements to 1
    # Update initialization and media paths to absolute URLs
    segment_templates = root.findall('.//mpd:SegmentTemplate', namespaces=ns)
    for template in segment_templates:
        template.set('startNumber', '1')

        initialization = template.get('initialization')
        media = template.get('media')

        if initialization is not None:
            template.set('initialization', urljoin(base_url, initialization))

        if media is not None:
            template.set('media', urljoin(base_url, media))

    # Convert the modified XML back to a string
    modified_manifest_content = ET.tostring(root, encoding='utf-8').decode('utf-8')
    if max_height:
        return modified_manifest_content, max_height
    else:
        return modified_manifest_content, target_height

def download_media(modified_manifest_content, output_path):
    # Create a temporary file to store the modified manifest
    with tempfile.NamedTemporaryFile(suffix='.mpd', delete=False) as temp_manifest:
        temp_manifest.write(modified_manifest_content.encode('utf-8'))
        temp_manifest_path = pathlib.Path(temp_manifest.name)

    # Execute FFmpeg command
    (
        ffmpeg.input(str(temp_manifest_path), f='dash')
        .output(str(output_path), codec='copy')
        .run(overwrite_output=True)
    )

    # Remove the modified manifest file
    temp_manifest_path.unlink()

def movie_scrape(MOVIE_URL):
    content = html.fromstring(requests.get(MOVIE_URL).content)
    movie_id = MOVIE_URL.split("/")[5]
    manifest_url = get_manifest_url(movie_id)
    studio_name = content.xpath('//*[@class="dts-studio-name-wrapper"]/a/text()')[0].strip()
    movie_name = content.xpath('//*[@class="dts-section-page-heading-title"]/h1/text()')[0].strip()
    duration = content.xpath('//*[@class="section-detail-list-item-duration"][2]/text()')[0].strip()
    time_obj = datetime.datetime.strptime(duration, "%H:%M:%S")
    duration_seconds = time_obj.hour * 3600 + time_obj.minute * 60 + time_obj.second
    name = f"{studio_name} - {movie_name}"
    return name, duration_seconds, manifest_url

def get_manifest_content(manifest_url):
    # Make HTTP request to get the manifest
    response = requests.get(manifest_url)
    response.raise_for_status()  # Raise an exception for non-2xx status codes
    return response.content

def get_manifest_url(movie_id):
    headers = {}
    headers["content-type"] = "application/x-www-form-urlencoded"
    data = f"movieId={movie_id}&isPreview=true&format=DASH"
    content = requests.post("https://straight.aebn.com/straight/deliver", headers=headers, data=data).json()
    manifest_url = content["url"]
    return manifest_url

def main(MOVIE_URL):
    name, duration_seconds, manifest_url = movie_scrape(MOVIE_URL)
    manifest_content = get_manifest_content(manifest_url)
    base_url = manifest_url.rsplit('/', 1)[0]
    modified_manifest_content, height = modify_manifest(manifest_content, base_url, duration_seconds, target_height)
    name = f"{name} {height}p"
    print(name)
    output_path = pathlib.Path(f"{name}.mp4")
    download_media(modified_manifest_content, output_path)


if __name__ == "__main__":
    main(MOVIE_URL)
