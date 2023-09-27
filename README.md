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
- `-r`: The desired video resolution height (default: highest available)
- `-f`: FFmpeg directory (default: try to use PATH)
- `-sn`: Specify which scene to download (default: disabled)
- `-c`: Set this flag to download the front and back covers (default: False)
- `-start`: Specify start segment (default: 1)
- `-end`: Specify end segment (default: total available)
- `-o`: Set this flag to overwrite existing video segments if present (default: False)
- `-k`: Set this flag to don't delete segments after downloading (default: False)
- `-h`, `--help`: Show the above information in the terminal
