from app.pronunciation import compare_transcript


def test_perfect_match_ignores_case_and_punctuation():
    result = compare_transcript("I would like a coffee.", "i WOULD like a coffee")
    assert result.matched_words == result.total_words == 5
    assert result.differences == []


def test_reports_missing_word():
    result = compare_transcript("I would like a coffee", "I would like coffee")
    assert result.total_words == 5
    assert result.matched_words == 4
    assert [(d.expected, d.recognized) for d in result.differences] == [(["a"], [])]


def test_empty_transcript():
    result = compare_transcript("Hello world", "")
    assert result.matched_words == 0
    assert result.total_words == 2
    assert result.differences[0].expected == ["hello", "world"]
