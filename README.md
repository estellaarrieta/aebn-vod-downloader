## Dependencies
- Python 3.6 or higher
- FFmpeg (provide directory as a prameter or add to PATH)

## Usage

1. Install or upgrade the package using pip:
   * Stable version:
    ```
    pip install git+https://github.com/estellaarrieta/aebn-vod-downloader -U
    ```
   * Dev version:
    ```
    pip install git+https://github.com/estellaarrieta/aebn-vod-downloader.git@dev -U
    ```
2. Run with the desired movie URL:
```
aebndl [URL] [Arguments]
```
3. The script will download the movie and save it in the current working directory.
#### Example Usage With Arguments
```
aebndl https://*.aebn.com/*/movies/* --resolution 720 --scene 2
```
To download scene 2 in 720p resolution

## Usage for Concurrent Downloads
You can use a `list.txt` file with multiple URL's (one per line) and pass it instead of a URL to the script, for example
```
aebndl list.txt [Arguments]
```
### list.txt example
Put a scene number after the url, separated by a `|` to download a single scene instead of a full movie
```
https://vod.aebn.com/straight/movies/****/****|3
https://vod.aebn.com/straight/movies/****/****
https://straight.aebn.com/straight/movies/****/****|1
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
| `-pfn` | `--include-performer-names` | Include performer names in the output filename |
| `-f` | `--ffmpeg` | Specify the location of your FFmpeg directory |
| `-sn` | `--scene` | Download a single scene using the relevant scene number on AEBN |
| `-p` | `--scene-padding` | Set padding for scene boundaries in seconds |
| `-ss` or `-start` | `--start-segment` | Specify the start segment |
| `-es` or `-end` | `--end-segment` | Specify the end segment |
| `-c` | `--covers` | Download front and back covers |
| `-ow` | `--overwrite` | Overwrite existing audio and video segments if already present |
| `-k` | `--keep` | Keep audio and video segments after downloading |
| `-v` |`--validate`| Validate segments as they download or found on disk|
| `-l` | `--log-level` | Set the logging level. Any level above INFO disables progress bars (default: INFO) |
| `-t` | `--threads` | Threads for concurrent downloads with list.txt (default: 5) |
| `-proxy` | | Proxy to use (format: `protocol://username:password@ip:port`) |
| `-pm` | `--proxy-metadata` | Use proxies for metadata only, and not for downloading. |

## External Libraries Used
- [lxml](https://pypi.org/project/lxml/)
- [curl-cffi](https://pypi.org/project/curl-cffi/)
- [tqdm](https://pypi.org/project/tqdm/)
