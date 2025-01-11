import argparse
import concurrent.futures
import logging
import signal
import sys
from urllib.parse import urlparse
from typing import Literal

from . import Downloader


def download_movie(args):
    Downloader(
        url=args.url,
        output_dir=args.output_dir,
        work_dir=args.work_dir,
        target_height=args.resolution,
        force_resolution=args.force_resolution,
        include_performer_names=args.names,
        scene_n=args.scene,
        start_segment=args.start_segment,
        end_segment=args.end_segment,
        download_covers=args.covers,
        overwrite_existing_files=args.overwrite,
        target_stream=args.target_stream,
        keep_segments_after_download=args.keep_segments,
        aggressive_segment_cleaning=args.aggressive_cleaning,
        log_level=args.log_level,
        keep_logs=args.keep_logs,
        proxy=args.proxy,
        proxy_metadata_only=args.proxy_metadata,
    ).run()


def new_logger(log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]) -> logging.Logger:
    """Set un and return a logger with given log level"""
    main_logger = logging.getLogger("main_logger")
    main_logger.setLevel(log_level)
    formatter = logging.Formatter("%(asctime)s|%(levelname)s|%(message)s", datefmt="%H:%M:%S")
    main_handler = logging.StreamHandler()
    main_handler.setFormatter(formatter)
    main_logger.addHandler(main_handler)
    return main_logger


def convert_line_endings(file_path):
    """Replace windows line endings with unix"""
    windows_line_ending = b"\r\n"
    unix_line_ending = b"\n"

    with open(file_path, "rb") as open_file:
        content = open_file.read()

    # Windows to Unix
    if windows_line_ending in content:
        content = content.replace(windows_line_ending, unix_line_ending)
        with open(file_path, "wb") as open_file:
            open_file.write(content)


def log_error(future):
    """Log future error"""
    try:
        future.result()
    except Exception as e:
        logging.error(f"Exception occurred: {e}")


def process_list_txt(logger: logging.Logger, args: argparse.Namespace) -> None:
    if sys.platform == "linux":
        convert_line_endings("list.txt")  # important to have the proper newlines for linux
        logger.debug("Converted list.txt to unix line endings, important for linux processing")
    with open("list.txt", encoding="utf-8") as f:
        urllist = f.read().splitlines()  # remove the newlines
    while "" in urllist:  # remove empty strings from the list (resulted from empty lines)
        urllist.remove("")

    logger.info("""
\033[0;31m\033[1mWARNING: An excessive concurrent download of scenes/movies
may result in throttling and/or get your IP blocked.
HTTP requests to servers usually have rate limits, so hammering a server
will throttle your connections and cause temporary timeouts.
Be reasonable and use with caution!\033[0m""")

    default_max_threads = 3
    max_threads = args.threads or (len(urllist) if len(urllist) < default_max_threads else default_max_threads)
    logger.info(f"Threads: {max_threads}")

    with concurrent.futures.ThreadPoolExecutor(max_workers=max_threads) as executor:
        futures = []
        for line in urllist:
            if line.startswith("#"):
                continue
            task_args = argparse.Namespace(**vars(args))  # Create a copy of args
            if "|" in line:
                task_args.url = line.split("|")[0]
                task_args.scene = int(line.split("|")[1])
            else:
                task_args.url = line
            future = executor.submit(download_movie, task_args)
            future.add_done_callback(log_error)
            futures.append(future)


def main():
    # Make Ctrl-C work when deamon threads are running
    signal.signal(signal.SIGINT, signal.SIG_DFL)

    parser = argparse.ArgumentParser()
    parser.add_argument("url", help="URL of the movie or list.txt")
    parser.add_argument("-o", "--output_dir", type=str, help="Specify the output directory")
    parser.add_argument("-w", "--work_dir", type=str, help="Specify the work diretory to store downloaded temporary segments in")
    parser.add_argument("-r", "--resolution", type=int, help="Desired video resolution by pixel height. If not found, the nearest lower resolution will be used. Use 0 to select the lowest available resolution. (default: highest available)")
    parser.add_argument("-f", "--force-resolution", action="store_true", help="If the target resolution not available, exit with an error")
    parser.add_argument("-n", "--names", action="store_true", help="Include performer names in the output filename")
    parser.add_argument("-s", "--scene", type=int, help="Download a single scene using the relevant scene number on AEBN")
    parser.add_argument("-ss", "--start-segment", type=int, help="Specify the start segment")
    parser.add_argument("-es", "--end-segment", type=int, help="Specify the end segment")
    parser.add_argument("-p", "--proxy", type=str, help="Proxy to use (format: protocol://username:password@ip:port)")
    parser.add_argument("-pm", "--proxy-metadata", action="store_true", help="Use proxies for metadata only, and not for downloading")
    parser.add_argument("-c", "--covers", action="store_true", help="Download front and back covers")
    parser.add_argument("-ow", "--overwrite", action="store_true", help="Overwrite existing audio and video segments, if already present")
    parser.add_argument("-ts", "--target-stream", choices=["audio", "video"], help="Download just video or just audio stream")
    parser.add_argument("-ks", "--keep-segments", action="store_true", help="Keep audio and video segments after downloading")
    parser.add_argument("-kl", "--keep-logs", action="store_true", help="Keep logs after successful exit")
    parser.add_argument(
        "-ac",
        "--aggressive-cleaning",
        action="store_true",
        help="Delete segments instantly after a successful join into stream."
        "By default, segments are deleted on success, after stream muxing"
        "If you are really low on disk space, you can use this option but"
        "in case of muxing error you would have to download it all again",
    )
    parser.add_argument("-t", "--threads", type=int, help="Threads for concurrent downloads with list.txt (default=5)")
    parser.add_argument("-l", "--log-level", choices=["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"], default="INFO", help="Set the logging level (default: INFO) Any level above INFO would also disable progress bars")
    args = parser.parse_args()

    # validate the url
    result = urlparse(args.url)
    if result.scheme and result.netloc:
        download_movie(args)
        return

    main_logger = new_logger(args.log_level)

    # if invalid, check for a list.txt and download concurrently
    if args.url == "list.txt":
        process_list_txt(main_logger, args=args)
    else:
        main_logger.error("Invalid URL or list.txt not passed")


if __name__ == "__main__":
    main()
