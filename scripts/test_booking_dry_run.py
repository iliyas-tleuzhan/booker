import _bootstrap  # noqa: F401

from app.main import _book_now


if __name__ == "__main__":
    _book_now(dry_run=True)
