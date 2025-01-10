class CustomException(Exception):
    pass


class NetworkError(CustomException):
    pass


class Forbidden(CustomException):
    pass


class FFmpegError(CustomException):
    pass
