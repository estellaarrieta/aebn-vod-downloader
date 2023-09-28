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

## Usage for Concurrent Downloads
You can use a `list.txt` file with multiple URL's (one per line) and pass it instead of a URL to the script, for example
```
python aebn_dl.py list.txt
```
It will download the videos in parallel with a default of 10 threads. The download queue will keep replenishing to the set maximum threads, until all the URL's are processed. You can change the threads with the `-t/--threads` argument.

**Please don't abuse this feature, hammering the servers with high concurrent downloads might throttle the http connections, or possibly get your IP blocked. So use with caution and try to stay under the radar.**

## Running the Script with Different Arguments

You can customize the behavior of the script by passing different arguments when running it. The available arguments are:

| Argument | Description |
| --- | --- |
|`-h, --help`|Show this help message and exit|
|`url` or `list.txt` file|The URL of the movie to download (required)|
|`-d, --download_dir DOWNLOAD_DIR`|Specify a target download directory|
|`-r RESOLUTION, --resolution RESOLUTION`|Target video resolution height. Use 0 to select the lowest. Default is the highest|
|`-f FFMPEG, --ffmpeg FFMPEG`|ffmpeg directory|
|`-sn SCENE, --scene SCENE`|Target scene to download|
|`-start SCENE_START, --scene_start SCENE_START`| Specify the start segment|
|`-end SCENE_END, --scene_end SCENE_END`|Specify the end segment|
|`-c, --covers`|Download covers|
|`-o, --overwrite`|Overwrite existing segments on the disk|
|`-k, --keep`|Keep segments after download|
|`-t, --threads`|Threads for concurrent downloads (default=10)|
