import re
from urllib.parse import urlparse


def normalize_name(value: str | None) -> str:
    if not value:
        return ""
    cleaned = re.sub(r"[^a-z0-9]+", " ", value.lower())
    cleaned = re.sub(r"\b(pvt|ltd|limited|inc|llc|llp|co|company|private|corp|corporation)\b", " ", cleaned)
    return re.sub(r"\s+", " ", cleaned).strip()


# Legal-form words that don't distinguish one business from another, including
# the UAE's free-zone and establishment suffixes.
_COMPANY_SUFFIXES = re.compile(
    r"\b(pvt|ltd|limited|inc|llc|llp|co|company|private|corp|corporation|fze|fzco|fzc|fz|fzllc|est|establishment|plc|gmbh)\b"
)


def normalize_company(value: str | None) -> str:
    """Company-name key for duplicate detection: "Gulf Garage L.L.C." == "Gulf Garage LLC" == "Gulf Garage".

    Separate from normalize_name, which keys catalogue lines and must stay stable."""
    if not value:
        return ""
    cleaned = re.sub(r"[^a-z0-9]+", " ", value.lower().replace(".", ""))  # l.l.c. -> llc
    cleaned = _COMPANY_SUFFIXES.sub(" ", cleaned)
    return re.sub(r"\s+", " ", cleaned).strip()


def names_compatible(a: str | None, b: str | None) -> bool:
    """Whether two company names plausibly mean the same business.

    "ABC_Autocare" ~ "Abc Autocare LLC" ~ "ABC Autocare Trading" are compatible;
    "ABC_Autocare" and "bhatia brothers" are not. A missing name is compatible
    with anything (there is nothing to contradict the other evidence).
    """
    na, nb = normalize_company(a), normalize_company(b)
    if not na or not nb:
        return True
    if na == nb or na.replace(" ", "") == nb.replace(" ", ""):
        return True
    ta, tb = set(na.split()), set(nb.split())
    if ta <= tb or tb <= ta:
        return True
    return len(ta & tb) / len(ta | tb) >= 0.5


def normalize_domain(url_or_domain: str | None) -> str | None:
    if not url_or_domain:
        return None
    text = url_or_domain.strip().lower()
    if not text:
        return None
    if "://" not in text:
        text = "https://" + text
    parsed = urlparse(text)
    host = (parsed.netloc or parsed.path).split("/")[0]
    host = host.removeprefix("www.")
    return host or None


def email_domain(email: str | None) -> str | None:
    if not email or "@" not in email:
        return None
    domain = email.split("@", 1)[1].strip().lower()
    generic = {
        "gmail.com",
        "yahoo.com",
        "outlook.com",
        "hotmail.com",
        "icloud.com",
        "live.com",
        "aol.com",
        "protonmail.com",
    }
    if domain in generic:
        return None
    return domain


def sanitize_excel_value(value) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    if text.startswith(("=", "+", "-", "@")):
        text = "'" + text
    return text


# Common words that carry no meaning for matching. Without this, "and", "the",
# "for" etc. count as shared keywords and inflate every score.
STOPWORDS = {
    "and", "the", "for", "with", "from", "that", "this", "are", "our", "your", "you",
    "has", "have", "was", "were", "will", "can", "all", "any", "not", "but", "into",
    "per", "its", "their", "they", "them", "also", "more", "other", "such", "than",
    "who", "which", "what", "when", "where", "how", "use", "used", "using", "via",
    "www", "http", "https", "com", "llc", "ltd", "fze", "fzc", "fzco", "est", "co",
    "please", "need", "want", "would", "like", "hello", "regards", "thanks", "thank",
}


def _stem(word: str) -> str:
    """Light plural folding so "garages"/"garage", "facilities"/"facility",
    "retailers"/"retailer" compare equal. Deliberately simple and predictable."""
    if len(word) > 4 and word.endswith("ies"):
        return word[:-3] + "y"
    if len(word) > 4 and word.endswith(("sses", "shes", "ches", "xes")):
        return word[:-2]
    if len(word) > 3 and word.endswith("s") and not word.endswith(("ss", "us", "is")):
        return word[:-1]
    return word


def tokenize(text: str | None) -> set[str]:
    if not text:
        return set()
    return {_stem(t) for t in re.findall(r"[a-z0-9]{3,}", text.lower()) if t not in STOPWORDS}


def digits_only(value: str | None) -> str:
    if not value:
        return ""
    return re.sub(r"\D+", "", value)
