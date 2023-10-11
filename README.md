## Dependencies
- Python 3.6 or higher
- FFmpeg (provide directory as a prameter or add to PATH)
- lxml (https://pypi.org/project/lxml/)
- requests (https://pypi.org/project/requests/)
- tqdm (https://pypi.org/project/tqdm/)
- fake-useragent (https://pypi.org/project/fake-useragent/)

## Usage

1. Install the required modules using pip:

```
pip install requests lxml tqdm fake-useragent
or
pip3 install requests lxml tqdm fake-useragent
```
2. Run the script with the desired movie URL:
```
python aebn_dl.py https://*.aebn.com/*/movies/*
or
python3 aebn_dl.py https://*.aebn.com/*/movies/*
```

3. The script will download the movie and save it in the current working directory.

## Usage for Concurrent Downloads
You can use a `list.txt` file with multiple URL's (one per line) and pass it instead of a URL to the script, for example
```
python aebn_dl.py list.txt
```
It will download the videos in parallel with a default of 5 threads (concurrent downloads). The download queue will keep replenishing to the set maximum threads, until all the URL's are processed. You can change the threads with the `-t/--threads` argument.

**Please don't abuse this feature, hammering the servers with high concurrent downloads might throttle the http connections, or possibly get your IP blocked. So use with caution and try to stay under the radar.**

## Running the Script with Different Arguments

You can customize the behavior of the script by passing different arguments when running it. The available arguments are:

| Short Argument | Long Argument | Description |
| --- | --- | --- |
| `-h` | `--help` | Show this help message and exit |
| URL or list.txt file | | The URL of the movie to download (required) |
| `-o` | `--output_dir` | Specify the output directory (default: current directory) |
| `-w` | `--work_dir` | Specify the work directory to store downloaded temporary segments in (default: current directory)|
| `-r` | `--resolution` | Desired video resolution by pixel height. If not found, the nearest lower resolution will be used. Use 0 to select the lowest available resolution (default: 1, highest available). For example, to select 720p resolution, use `-r 720` |
| `-rf` | `--resolution-force` | If the target resolution is not available, exit with an error |
| `-f` | `--ffmpeg` | Specify the location of your FFmpeg directory |
| `-sn` | `--scene` | Download a single scene using the relevant scene number on AEBN |
| `-p` | `--scene-padding` | Set padding for scene boundaries in seconds |
| `-ss` or `-start` | `--start-segment` | Specify the start segment |
| `-es` or `-end` | `--end-segment` | Specify the end segment |
| `-c` | `--covers` | Download front and back covers |
| `-ow` | `--overwrite` | Overwrite existing audio and video segments if already present |
| `-k` | `--keep` | Keep audio and video segments after downloading |
| `-s` | `--silent` | Run the script in silent mode |
| `-t` | `--threads` | Threads for concurrent downloads (default: 5) |
