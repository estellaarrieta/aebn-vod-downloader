# Download from AEBN for *FREE*

### This Python script allows you to download full movies from aebn.com without even having an account, all you need is a URL!  
Works by parsing a preview playlist to get full movie segment's urls, downloads them, and uses ffmpeg to mux video and audio.

## Dependencies

- FFmpeg (provide directory as a prameter or add to PATH)
- lxml (https://pypi.org/project/lxml/)
- requests (https://pypi.org/project/requests/)
- tqdm (https://pypi.org/project/tqdm/)

## Usage

1. Install the required modules using pip:

```
pip install requests lxml tqdm
or
pip3 install requests lxml tqdm
```
2. Run the script with the desired movie URL:
```
python aebn_dl.py https://*.aebn.com/*/movies/*
```

3. The script will download the movie and save it in the current working directory.

## Running the Script with Different Arguments

You can customize the behavior of the script by passing different arguments when running it. The available arguments are:

| Argument | Description |
| --- | --- |
|`-h, --help`|Show this help message and exit|
|`url`|The URL of the movie to download (required)|
|`-r RESOLUTION, --resolution RESOLUTION`|Target video resolution height. Use 0 to select the lowest. Default is the highest|
|`-f FFMPEG, --ffmpeg FFMPEG`|ffmpeg directory|
|`-sn SCENE, --scene SCENE`|Target scene to download|
|`-start SCENE_START, --scene_start SCENE_START`| Specify the start segment|
|`-end SCENE_END, --scene_end SCENE_END`|Specify the end segment|
|`-c, --covers`|Download covers|
|`-o, --overwrite`|Overwrite existing segments on the disk|
|`-k, --keep`|Keep segments after download|
