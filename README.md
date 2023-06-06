# Download from AEBN for *FREE*

### This Python script allows you to download full movies from aebn.com without even having an account, all you need is a URL!  
Works by parsing a preview playlist to get full movie segment's urls, downloads them, and uses ffmpeg to mux video and audio.

It requires the following modules to be installed:

- lxml (https://pypi.org/project/lxml/)
- requests (https://pypi.org/project/requests/)
- ffmpeg-python (https://pypi.org/project/ffmpeg-python/)

## Usage

1. Install the required modules using pip:

```
pip install requests lxml ffmpeg-python
```
2. Run the script with the desired movie URL:
```
python aebn_dl.py https://*.aebn.com/*/movies/*
```

3. The script will download the movie and save it in the current working directory.

## Running the Script with Different Arguments

You can customize the behavior of the script by passing different arguments when running it. The available arguments are:

- `url`: The URL of the movie to download (required)
- `--h`: The desired video resolution height (default: highest available)
- `--o`: Set this flag to overwrite existing video segments if present (default: False)
- `--s`: Set this flag to don't delete segments after downloading (default: False)
