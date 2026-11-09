from normalize import normalize, numbers_in, parse_number, quote_match


def test_ligatures_expand():
    assert normalize("modiﬁcation and ﬂow") == "modification and flow"


def test_line_break_hyphenation_joins():
    assert normalize("adver-\nsarial") == "adversarial"
    assert normalize("adver-\r\n  sarial") == "adversarial"


def test_curly_quotes_and_dashes():
    assert normalize("“it’s” – x — y") == "\"it's\" - x - y"


def test_whitespace_collapses_and_lowercases():
    assert normalize("  Two\n\tLines  ") == "two lines"


def test_parse_number():
    assert parse_number("88.0%") == 88.0
    assert parse_number("1,234") == 1234.0
    assert parse_number("12.3 ± 0.4") == 12.3
    assert parse_number("NOT_REPORTED") is None


def test_numbers_in():
    assert numbers_in("ASR 88.0% on 2 models") == ["88.0", "2"]


def test_number_cut_at_span_edge_still_matches():
    paper = normalize("the rate falls to 3.1% at a cost of 2 points")
    assert quote_match("falls to 3.1%", paper) is not None


def test_number_words_count_as_numbers():
    assert sorted(numbers_in("six tasks and 4 datasets")) == ["4", "6"]
    assert numbers_in("one of the methods") == []
    paper = normalize("We compare two RAG formulations.")
    assert quote_match("We compare two RAG formulations", paper) is not None
    assert quote_match("We compare three RAG formulations", paper) is None
