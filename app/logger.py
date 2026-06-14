import logging
import sys
import os


def setup_logger(name: str = "channel-cloner") -> logging.Logger:
    logger = logging.getLogger(name)
    logger.setLevel(logging.DEBUG)
    if logger.handlers:
        return logger

    fmt = logging.Formatter(
        "%(asctime)s | %(levelname)-8s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    ch = logging.StreamHandler(sys.stdout)
    ch.setFormatter(fmt)
    logger.addHandler(ch)

    try:
        os.makedirs("/data", exist_ok=True)
        fh = logging.FileHandler("/data/cloner.log", encoding="utf-8")
        fh.setFormatter(fmt)
        logger.addHandler(fh)
    except Exception:
        pass

    return logger


logger = setup_logger()
