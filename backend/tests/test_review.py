import pytest

from app.review import schedule


def test_failure_resets_and_comes_back_soon():
    interval, ease, repetitions, lapses = schedule(0, interval_days=10, ease=2.5, repetitions=4, lapses=1)
    assert interval == pytest.approx(10 / (24 * 60))
    assert ease == pytest.approx(2.3)
    assert repetitions == 0
    assert lapses == 2


def test_first_successful_reviews():
    assert schedule(2, repetitions=0)[0] == 1.0
    assert schedule(2, repetitions=1, interval_days=1.0)[0] == 3.0
    assert schedule(3, repetitions=0)[0] == 2.0
    assert schedule(3, repetitions=1, interval_days=2.0)[0] == 5.0


def test_ease_is_bounded():
    assert schedule(1, ease=1.3)[1] == 1.3
    assert schedule(3, ease=3.0)[1] == 3.0


def test_result_is_clamped():
    assert schedule(-5) == schedule(0)
    assert schedule(99) == schedule(3)
