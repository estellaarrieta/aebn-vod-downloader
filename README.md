## Dependencies

- Python 3.10 or higher
- FFmpeg in system PATH. Recommended Version > 5

## Installation

```
pip install https://github.com/estellaarrieta/aebn-vod-downloader/archive/refs/heads/main.zip -U
```
Or
```
pip install git+https://github.com/estellaarrieta/aebn-vod-downloader -U
```

### Example Usage With Arguments

```
aebndl https://*.aebn.com/*/movies/* --resolution 720 --scene 2
```

To download scene 2 in 720p resolution

## Usage

```bash
aebndl [-h] [-o OUTPUT_DIR] [-w WORK_DIR] [-r RESOLUTION] [-f] [-n] [-s SCENE] [-p PROXY] [-pm] [-c] [-ow] [-ts {audio,video}] [-ks] [-kl] [-ac] [-t THREADS] [-l {DEBUG,INFO,WARNING,ERROR,CRITICAL}] url
```

## Arguments

| Flags | Argument                | Description                                                                                                                                                                                                                                                        |
| ----- | ----------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
|       | `URL`                   | URL of the movie or list.txt                                                                                                                                                                                                                                       |
| `-o`  | `--output_dir`          | Specify the output directory                                                                                                                                                                                                                                       |
| `-w`  | `--work_dir`            | Specify the work diretory to store downloaded temporary segments in                                                                                                                                                                                                |
| `-r`  | `--resolution`          | Desired video resolution by pixel height. If not found, the nearest lower resolution will be used. Use 0 to select the lowest available resolution. (default: highest available)                                                                                   |
| `-f`  | `--force-resolution`    | If the target resolution not available, exit with an error                                                                                                                                                                                                         |
| `-n`  | `--names`               | Include performer names in the output filename                                                                                                                                                                                                                     |
| `-nm`  | `--no-metadata`               | Disable adding title and chapter markers to the output video                                                                                                                                                                                                                     |
| `-s`  | `--scene`               | Download a single scene using the relevant scene number on AEBN                                                                                                                                                                                                    |
| `-ss` | `--start-segment`       | Specify the start segment                                                                                                                                                                                                                                          |
| `-es` | `--end-segment`         | Specify the end segment                                                                                                                                                                                                                                            |
| `-p`  | `--proxy`               | Proxy to use (format: protocol://username:password@ip:port)                                                                                                                                                                                                        |
| `-pm` | `--proxy-metadata`      | Use proxies for metadata only, and not for downloading                                                                                                                                                                                                             |
| `-c`  | `--covers`              | Download front and back covers                                                                                                                                                                                                                                     |
| `-ow` | `--overwrite`           | Overwrite existing audio and video segments, if already present                                                                                                                                                                                                    |
| `-ts` | `--target-stream`       | Download just video or just audio stream                                                                                                                                                                                                                           |
| `-ks` | `--keep-segments`       | Keep audio and video segments after downloading                                                                                                                                                                                                                    |
| `-kl` | `--keep-logs`           | Keep logs after successful exit                                                                                                                                                                                                                                    |
| `-ac` | `--aggressive-cleaning` | Delete segments instantly after a successful join into stream. By default, segments are deleted on success, after stream muxing. If you are really low on disk space, you can use this option, but in case of muxing error you would have to download it all again |
| `-t`  | `--threads`             | Threads for concurrent downloads with list.txt (default=5)                                                                                                                                                                                                         |
| `-l`  | `--log-level`           | Set the logging level (default: INFO) Any level above INFO would also disable progress bars                                                                                                                                                                        |

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
