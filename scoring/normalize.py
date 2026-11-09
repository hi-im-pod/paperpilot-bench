"""Text normalization and quote location. Every quote and cell comparison goes through here."""
import re
import unicodedata

from rapidfuzz import fuzz

QUOTE_THRESHOLD = 90
_PUNCT = str.maketrans({
    "‘": "'", "’": "'", "‚": "'", "‛": "'",
    "“": '"', "”": '"', "„": '"', "‟": '"',
    "–": "-", "—": "-", "−": "-", "­": None,
})
_NUM = re.compile(r"\d+(?:\.\d+)?")
_WORDS = {w: str(i) for i, w in enumerate(
    "two three four five six seven eight nine ten eleven twelve thirteen fourteen fifteen sixteen "
    "seventeen eighteen nineteen twenty".split(), start=2)}
_WORD_RE = re.compile(r"\b(" + "|".join(_WORDS) + r")\b")


def normalize(text):
    if not text:
        return ""
    t = unicodedata.normalize("NFKC", text)
    t = t.translate(_PUNCT)
    # PDF line wraps split words as "adver-\nsarial"; the agent may copy either form.
    t = re.sub(r"(\w)-[ \t]*\r?\n\s*(\w)", r"\1\2", t)
    return re.sub(r"\s+", " ", t).strip().lower()


def parse_number(s):
    if s is None:
        return None
    t = normalize(str(s)).split("±")[0]
    t = re.sub(r"(?<=\d),(?=\d{3})", "", t)
    m = re.search(r"-?\d+(?:\.\d+)?", t)
    return float(m.group()) if m else None


def numbers_in(text):
    """Numbers as digit strings, including the words two to twenty.

    Papers write small counts as words ("six tasks"), and a claim of "three
    formulations" against a passage saying "two" must be caught. "one" is left
    out: "one of the" is everywhere and rarely a count.
    """
    t = normalize(text)
    return _NUM.findall(t) + [_WORDS[w] for w in _WORD_RE.findall(t)]


def locate(quote, norm_paper):
    """Best fuzzy span for `quote` in an already-normalized paper text.

    Returns (score, start, end) with offsets into `norm_paper`, or None below threshold.
    """
    q = normalize(quote)
    if not q or not norm_paper:
        return None
    if q in norm_paper:
        start = norm_paper.index(q)
        return 100.0, start, start + len(q)
    al = fuzz.partial_ratio_alignment(q, norm_paper)
    if al is None or al.score < QUOTE_THRESHOLD:
        return None
    return al.score, al.dest_start, al.dest_end


def widen(norm_paper, start, end):
    """Grow a span to whole tokens, so a number cut at the span edge isn't misread."""
    while start > 0 and not norm_paper[start - 1].isspace():
        start -= 1
    while end < len(norm_paper) and not norm_paper[end].isspace():
        end += 1
    return start, end


def quote_match(quote, norm_paper):
    """The quote match rule: a fuzzy span exists and every number in the quote is in it.

    Fuzzy matching alone accepts "83.0" for "88.0" (one character off still
    scores above 90), so numbers must match exactly.
    Returns (start, end) of the widened span, or None.
    """
    loc = locate(quote, norm_paper)
    if loc is None:
        return None
    start, end = widen(norm_paper, loc[1], loc[2])
    span_numbers = set(numbers_in(norm_paper[start:end]))
    if any(n not in span_numbers for n in numbers_in(quote)):
        return None
    return start, end
