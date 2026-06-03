from __future__ import annotations

import logging

from app.scheduler import run_scheduler


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    run_scheduler()


if __name__ == "__main__":
    main()
