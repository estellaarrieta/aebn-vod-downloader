#!/usr/bin/env python3
import argparse
import concurrent.futures
import logging
import signal
import sys
from urllib.parse import urlparse

from .movie import Movie


def download_movie(args):
    movie_instance = Movie(
        url=args.url,
        output_dir=args.output_dir,
        work_dir=args.work_dir,
        target_height=args.resolution,
        resolution_force=args.resolution_force,
        include_performer_names=args.include_performer_names,
        ffmpeg_dir=args.ffmpeg,
        scene_n=args.scene,
        scene_padding=args.scene_padding,
        start_segment=args.start_segment,
        end_segment=args.end_segment,
        download_covers=args.covers,
        overwrite_existing_files=args.overwrite,
        keep_segments_after_download=args.keep,
        log_level=args.log_level,
        semgent_validity_check=args.validate,
        proxy=args.proxy,
        proxy_metadata_only=args.proxy_metadata
    )
    movie_instance.download()


def logger_setup(log_level):
    main_logger = logging.getLogger('main_logger')
    main_logger.setLevel(log_level)
    formatter = logging.Formatter('%(asctime)s|%(levelname)s|%(message)s', datefmt='%H:%M:%S')
    main_handler = logging.StreamHandler()
    main_handler.setFormatter(formatter)
    main_logger.addHandler(main_handler)
    return main_logger


def convert_line_endings(file_path):
    # replacement strings
    WINDOWS_LINE_ENDING = b'\r\n'
    UNIX_LINE_ENDING = b'\n'

    with open(file_path, 'rb') as open_file:
        content = open_file.read()

    # Windows to Unix
    if WINDOWS_LINE_ENDING in content:
        content = content.replace(WINDOWS_LINE_ENDING, UNIX_LINE_ENDING)
        with open(file_path, 'wb') as open_file:
            open_file.write(content)


def log_error(future):
    try:
        future.result()
    except Exception as e:
        logging.error(f"Exception occurred: {e}")


def main():
    # Make Ctrl-C work when deamon threads are running
    signal.signal(signal.SIGINT, signal.SIG_DFL)

    parser = argparse.ArgumentParser()
    parser.add_argument("url", help="URL of the movie")
    parser.add_argument("-o", "--output_dir", type=str, help="Specify the output directory")
    parser.add_argument("-w", "--work_dir", type=str, help="Specify the work diretory to store downloaded temporary segments in")
    parser.add_argument("-r", "--resolution", type=int,
                        help="Desired video resolution by pixel height. "
                        "If not found, the nearest lower resolution will be used. "
                        "Use 0 to select the lowest available resolution. "
                        "(default: highest available)")
    parser.add_argument("-rf", "--resolution-force", action="store_true", help="If the target resolution not available, exit with an error")
    parser.add_argument("-pfn", "--include-performer-names", action="store_true", help="Include performer names in the output filename")
    parser.add_argument("-f", "--ffmpeg", type=str, help="Specify the location of your ffmpeg directory")
    parser.add_argument("-sn", "--scene", type=int, help="Download a single scene using the relevant scene number on AEBN")
    parser.add_argument("-p", "--scene-padding", type=int, help="Set padding for scenes boundaries in seconds")
    parser.add_argument("-ss", "-start", "--start-segment", type=int, help="Specify the start segment")
    parser.add_argument("-es", "-end", "--end-segment", type=int, help="Specify the end segment")
    parser.add_argument("-c", "--covers", action="store_true", help="Download front and back covers")
    parser.add_argument("-ow", "--overwrite", action="store_true", help="Overwrite existing audio and video segments, if already present")
    parser.add_argument("-k", "--keep", action="store_true", help="Keep audio and video segments after downloading")
    parser.add_argument("-v", "--validate", action="store_true", help="Validate segments as they download or found on disk")
    parser.add_argument('-l', '--log-level', choices=['DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL'],
                        default='INFO', help='Set the logging level (default: INFO)'
                                            'Any level above INFO would also disable progress bars')
    parser.add_argument("-t", "--threads", type=int, help="Threads for concurrent downloads (default=5)")
    parser.add_argument("-proxy", type=str, help="Proxy to use (format: protocol://username:password@ip:port)")
    parser.add_argument("-pm", "--proxy-metadata", action="store_true", help="Use proxies for metadata only, and not for downloading")
    args = parser.parse_args()

    main_logger = logger_setup(args.log_level)
    # validate the url
    result = urlparse(args.url)
    if result.scheme and result.netloc:
        download_movie(args)
    # if missing or invalid, check for a list.txt and download concurrently
    elif args.url == "list.txt":
        if sys.platform == 'linux':
            convert_line_endings("list.txt")  # important to have the proper newlines for linux
            main_logger.degub('Converted list.txt to unix line endings, important for linux processing')
        file = open("list.txt")
        urllist = file.read().splitlines()  # remove the newlines
        file.close()
        while "" in urllist:  # remove empty strings from the list (resulted from empty lines)
            urllist.remove("")

        main_logger.info('''
\033[0;31m\033[1mWARNING: An excessive concurrent download of scenes/movies
may result in throttling and/or get your IP blocked.
HTTP requests to servers usually have rate limits, so hammering a server
will throttle your connections and cause temporary timeouts.
Be reasonable and use with caution!\033[0m''')

        default_max_threads = 3
        max_threads = args.threads or (len(urllist) if len(urllist) < default_max_threads else default_max_threads)
        main_logger.info(f"Threads: {max_threads}")

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

            # for future in concurrent.futures.as_completed(futures):
            #     pass

    else:
        main_logger.error("Invalid URL or list.txt not passed")


if __name__ == "__main__":
    main()
