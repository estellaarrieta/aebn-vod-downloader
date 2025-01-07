import logging
import sys


def remove_chars(text: str) -> str:
    """Remove characters from string"""
    for ch in ["#", "?", "!", ":", "<", ">", '"', "/", "\\", "|", "*"]:
        if ch in text:
            text = text.replace(ch, "")
    return text


def get_version() -> str | None:
    """Get `aebndl` package version"""
    try:
        import pkg_resources

        version = pkg_resources.require("aebndl")[0].version
        return version
    except Exception:
        pass


def new_logger(name: str, log_level: str) -> logging.Logger:
    logger = logging.getLogger(name)
    logger.setLevel(logging.DEBUG)  # Set the logger level to the lowest (DEBUG)

    formatter = logging.Formatter("%(asctime)s|%(levelname)s|%(message)s", datefmt="%H:%M:%S")

    # Console handler with user set level
    console_handler = logging.StreamHandler()
    console_handler.setLevel(log_level)
    console_handler.set_name("console_handler")
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)

    # File handler with DEBUG level
    file_handler = logging.FileHandler(f"{name}.log")
    file_handler.setLevel(logging.DEBUG)
    file_handler.set_name("file_handler")
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)

    # https://stackoverflow.com/questions/6234405/
    def log_uncaught_exceptions(exctype, value, tb):
        logger.critical("Uncaught exception", exc_info=(exctype, value, tb))

    # Set the exception hook to log uncaught exceptions
    sys.excepthook = log_uncaught_exceptions
    return logger
