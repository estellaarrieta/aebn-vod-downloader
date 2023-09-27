# Download from AEBN for *FREE*

### This Python script allows you to download full movies from aebn.com without even having an account, all you need is a URL!  
Works by parsing a preview playlist to get full movie segment's urls, downloads them, and uses ffmpeg to mux video and audio.

## Dependencies

- FFmpeg (provide directory as a prameter or add to PATH)
- lxml (https://pypi.org/project/lxml/)
- requests (https://pypi.org/project/requests/)

## Usage

1. Install the required modules using pip:

```
pip install requests lxml
```
2. Run the script with the desired movie URL:
```
python aebn_dl.py https://*.aebn.com/*/movies/*
```
On some Linux distrubtions you may have to run the following instead:
```
python3 aebn_dl.py https://*.aebn.com/*/movies/*
```
3. The script will download the movie and save it in the current working directory.

## Running the Script with Different Arguments

You can customize the behavior of the script by passing different arguments when running it. The available arguments are:

- `url`: The URL of the movie to download (required)
- `-r, --resolution`: Set this flag to specify the desired video resolution by pixel height. Use 0 to select the lowest possible resolution. (default: highest available) (Note: Use only the _number_ of pixels, eg. `1080` rather than `1080p`.)
- `-f, --ffmpeg-directory`: Set this flag to use a specific ffmpeg directory (default: try to use PATH)
- `-sn, --scene-number`: Set this flag to specify which scene you want to download (default: downloads all available scenes as a single movie file)
- `-c, --covers`: Set this flag to download the front and back covers (default: False)
- `-start`: Set this flag to specify start segment (default: 1)
- `-end`: Set this flag to specify end segment (default: total available)
- `-o, --overwrite-segments`: Set this flag to overwrite existing audio and video segments if present on disk (default: False)
- `-k, --keep-segments`: Set this flag to keep audio and video segments on disk after downloading (default: False)
- `-h, --help`: Show the above information in the terminal
