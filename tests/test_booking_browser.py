import pytest

from app.booking_browser import _assert_booking_form_loaded, _page_has_error


class FakeLocator:
    def __init__(self, count=0, text=""):
        self._count = count
        self._text = text

    def count(self):
        return self._count

    def inner_text(self, timeout=0):
        return self._text


class FakePage:
    def __init__(self, body_text):
        self.body_text = body_text

    def locator(self, selector):
        if selector == "#main_ddlLibrary":
            return FakeLocator(count=0)
        return FakeLocator(text=self.body_text)


def test_assert_booking_form_loaded_reports_expired_login() -> None:
    page = FakePage("HKUL Authentication Registered library users only.")

    with pytest.raises(RuntimeError, match="login-hkul"):
        _assert_booking_form_loaded(page)


def test_page_has_error_detects_booking_error_text() -> None:
    page = FakePage("This facility is not available for booking.")

    assert _page_has_error(page) is not None
