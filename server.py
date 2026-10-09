"""Quran Morphology MCP server.

Serves word-by-word morphology of the Quran from the Quranic Arabic Corpus
(v0.4, revised fork at github.com/mustafa0x/quran-morphology, GPL).
The data file is downloaded once into ./data on first run.
"""

from __future__ import annotations

import re
import urllib.request
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

from mcp.server.mcpserver import MCPServer

DATA_URL = "https://raw.githubusercontent.com/mustafa0x/quran-morphology/master/quran-morphology.txt"
DATA_FILE = Path(__file__).resolve().parent / "data" / "quran-morphology.txt"

TAGS = {
    # segment markers
    "PREF": "prefix", "SUFF": "suffix",
    # parts of speech
    "PN": "proper noun", "ADJ": "adjective", "PRON": "pronoun", "DEM": "demonstrative pronoun",
    "REL": "relative pronoun", "T": "time adverb", "LOC": "location adverb", "VN": "verbal noun (masdar)",
    "NV": "verbal noun of action (ism fi'l)", "ACT_PCPL": "active participle", "PASS_PCPL": "passive participle",
    "DET": "determiner (al-)", "CONJ": "coordinating conjunction", "SUB": "subordinating conjunction",
    "ACC": "accusative particle / accusative case", "AMD": "amendment particle", "ANS": "answer particle",
    "AVR": "aversion particle", "CAUS": "particle of cause", "CERT": "particle of certainty",
    "CIRC": "circumstantial particle", "COND": "conditional particle", "EQ": "equalization particle",
    "EXH": "exhortation particle", "EXL": "explanation particle", "EXP": "exceptive particle",
    "FUT": "future particle", "INC": "inceptive particle", "INT": "particle of interpretation",
    "INTG": "interrogative particle", "NEG": "negative particle", "PREV": "preventive particle",
    "PRO": "prohibition particle", "REM": "resumption particle", "RES": "restriction particle",
    "RET": "retraction particle", "RSLT": "result particle", "SUP": "supplemental particle",
    "SUR": "surprise particle", "VOC": "vocative particle", "INL": "Quranic initials (muqatta'at)",
    "EMPH": "emphatic prefix/suffix", "IMPN": "imperative verbal noun", "PRP": "purpose particle",
    "ATT": "attention particle (ha)", "ADDR": "addressee suffix", "DIST": "distance marker",
    "P": "preposition",
    # verb aspect / voice / mood
    "PERF": "perfect (past)", "IMPF": "imperfect (present)", "IMPV": "imperative",
    "PASS": "passive voice", "IND": "indicative mood", "SUBJ": "subjunctive mood", "JUS": "jussive mood",
    # case / state
    "NOM": "nominative", "GEN": "genitive", "INDEF": "indefinite",
    # gender / number (person prefixes 1/2/3 are expanded separately)
    "M": "masculine", "F": "feminine",
}
KINDS = {"N": "nominal", "V": "verb", "P": "particle"}
_PGN = re.compile(r"^([123])?([MF])?([SDP])$")
_PERSON = {"1": "1st person", "2": "2nd person", "3": "3rd person"}
_GENDER = {"M": "masculine", "F": "feminine"}
_NUMBER = {"S": "singular", "D": "dual", "P": "plural"}
_FORMS = "I II III IV V VI VII VIII IX X XI XII".split()

_DIACRITICS = re.compile(r"[ؐ-ًؚ-ٰٟۖ-ۭـ]")
_ALEFS = str.maketrans({"أ": "ا", "إ": "ا", "آ": "ا", "ٱ": "ا", "ى": "ي", "ؤ": "و", "ئ": "ي", "ة": "ه"})


def normalize(text: str) -> str:
    """Diacritic- and hamza-seat-insensitive form for matching."""
    return _DIACRITICS.sub("", text).translate(_ALEFS).replace(" ", "").replace("ء", "")


@dataclass
class Segment:
    form: str
    kind: str  # N / V / P
    tags: list[str]
    attrs: dict[str, str]

    def describe(self) -> dict:
        out: dict = {"form": self.form, "type": KINDS.get(self.kind, self.kind)}
        for k in ("ROOT", "LEM"):
            if k in self.attrs:
                out["root" if k == "ROOT" else "lemma"] = self.attrs[k]
        if "VF" in self.attrs:
            vf = self.attrs["VF"]
            out["verb_form"] = _FORMS[int(vf) - 1] if vf.isdigit() and 0 < int(vf) <= 12 else vf
        if "MOOD" in self.attrs:
            out["mood"] = TAGS.get(self.attrs["MOOD"], self.attrs["MOOD"])
        if "FAM" in self.attrs:
            out["family"] = self.attrs["FAM"]
        out["tags"] = self.tags
        out["features"] = [gloss(t) for t in self.tags if t]
        return out


@dataclass
class Word:
    ref: str  # s:a:w
    segments: list[Segment] = field(default_factory=list)

    @property
    def text(self) -> str:
        return "".join(s.form for s in self.segments)

    @property
    def root(self) -> str | None:
        return next((s.attrs["ROOT"] for s in self.segments if "ROOT" in s.attrs), None)

    @property
    def stem(self) -> Segment:
        """The segment that carries the lemma (not a prefix/suffix), falling back to the first."""
        for s in self.segments:
            if "PREF" not in s.tags and "SUFF" not in s.tags:
                return s
        return self.segments[0]

    def summary(self) -> dict:
        st = self.stem
        out = {"ref": self.ref, "text": self.text, "pos": KINDS.get(st.kind, st.kind), "tags": st.tags}
        if st.attrs.get("LEM"):
            out["lemma"] = st.attrs["LEM"]
        if self.root:
            out["root"] = self.root
        return out

    def describe(self) -> dict:
        return {**self.summary(), "segments": [s.describe() for s in self.segments]}


def gloss(tag: str) -> str:
    if tag in TAGS:
        return f"{tag}: {TAGS[tag]}"
    m = _PGN.match(tag)
    if m and any(m.groups()):
        p, g, n = m.groups()
        parts = [_PERSON.get(p or ""), _GENDER.get(g or ""), _NUMBER.get(n)]
        return f"{tag}: " + " ".join(x for x in parts if x)
    return tag


@lru_cache(maxsize=1)
def corpus() -> tuple[dict[str, Word], dict[tuple[int, int], list[Word]]]:
    if not DATA_FILE.exists():
        DATA_FILE.parent.mkdir(parents=True, exist_ok=True)
        urllib.request.urlretrieve(DATA_URL, DATA_FILE)
    words: dict[str, Word] = {}
    verses: dict[tuple[int, int], list[Word]] = defaultdict(list)
    with DATA_FILE.open(encoding="utf-8") as fh:
        for line in fh:
            parts = line.rstrip("\n").split("\t")
            if len(parts) != 4:
                continue
            loc, form, kind, feats = parts
            s, a, w, _ = loc.split(":")
            ref = f"{s}:{a}:{w}"
            tags, attrs = [], {}
            for f in feats.split("|"):
                if ":" in f:
                    k, v = f.split(":", 1)
                    attrs[k] = v
                elif f:
                    tags.append(f)
            if ref not in words:
                words[ref] = Word(ref)
                verses[(int(s), int(a))].append(words[ref])
            words[ref].segments.append(Segment(form, kind, tags, attrs))
    return words, dict(verses)


def _filter(surah: int | None):
    return (lambda w: True) if surah is None else (lambda w: w.ref.split(":")[0] == str(surah))


mcp = MCPServer("quran-morphology")


@mcp.tool()
def get_word_morphology(surah: int, ayah: int, word: int) -> dict:
    """Full morphological breakdown of one Quranic word: every segment (prefixes, stem,
    suffixes) with its part of speech, root, lemma, verb form, mood, case, person/gender/number.
    Word numbers are 1-based within the ayah."""
    words, _ = corpus()
    w = words.get(f"{surah}:{ayah}:{word}")
    if not w:
        return {"error": f"No word at {surah}:{ayah}:{word}"}
    return w.describe()


@mcp.tool()
def get_verse_morphology(surah: int, ayah: int, detailed: bool = False) -> dict:
    """Word-by-word morphology of a whole ayah. With detailed=False each word gets a short
    summary (text, POS, lemma, root); detailed=True includes every segment and feature."""
    _, verses = corpus()
    ws = verses.get((surah, ayah))
    if not ws:
        return {"error": f"No ayah {surah}:{ayah}"}
    return {
        "ref": f"{surah}:{ayah}",
        "text": " ".join(w.text for w in ws),
        "words": [w.describe() if detailed else w.summary() for w in ws],
    }


@mcp.tool()
def search_root(root: str, surah: int | None = None, limit: int = 50) -> dict:
    """Every occurrence of a triliteral/quadriliteral root (Arabic letters, e.g. "رحم" or "ر ح م";
    hamza seats and diacritics are ignored). Returns total count, a breakdown by lemma with counts,
    and up to `limit` occurrences. Optionally restrict to one surah."""
    words, _ = corpus()
    key, keep = normalize(root), _filter(surah)
    hits = [w for w in words.values() if w.root and normalize(w.root) == key and keep(w)]
    lemmas = Counter(w.stem.attrs.get("LEM", "?") for w in hits)
    return {
        "root": hits[0].root if hits else root,
        "total_occurrences": len(hits),
        "surah_count": len({w.ref.split(":")[0] for w in hits}),
        "lemmas": [{"lemma": l, "count": c} for l, c in lemmas.most_common()],
        "occurrences": [w.summary() for w in hits[:limit]],
        "truncated": len(hits) > limit,
    }


@mcp.tool()
def search_lemma(lemma: str, surah: int | None = None, limit: int = 50) -> dict:
    """Every occurrence of a lemma (dictionary form, e.g. "رَحْمٰن" or just "رحمن";
    matching ignores diacritics and hamza seats). Returns count, the distinct surface forms,
    and up to `limit` occurrences."""
    words, _ = corpus()
    key, keep = normalize(lemma), _filter(surah)
    hits = [w for w in words.values() if keep(w) and any(normalize(s.attrs.get("LEM", "")) == key for s in w.segments)]
    found = sorted({s.attrs["LEM"] for w in hits for s in w.segments if normalize(s.attrs.get("LEM", "")) == key})
    return {
        "query": lemma,
        "matched_lemmas": found,
        "total_occurrences": len(hits),
        "surface_forms": [{"text": t, "count": c} for t, c in Counter(w.text for w in hits).most_common()],
        "occurrences": [w.summary() for w in hits[:limit]],
        "truncated": len(hits) > limit,
    }


@mcp.tool()
def find_words(
    tags: list[str] | None = None,
    root: str | None = None,
    verb_form: int | None = None,
    surah: int | None = None,
    limit: int = 50,
) -> dict:
    """Grammatical search: words whose segments (together) carry ALL the given tags,
    e.g. tags=["V","IMPV"] for imperative verbs, ["PASS","PERF"] for perfect passives,
    ["N","ACT_PCPL"] for active participles, ["3FS"] for 3rd fem. singular.
    Optionally combine with a root, a verb form number (1-12) and a surah.
    Use explain_tags to see the tag inventory."""
    words, _ = corpus()
    want = set(tags or [])
    rkey, keep = (normalize(root) if root else None), _filter(surah)
    hits = []
    for w in words.values():
        if not keep(w):
            continue
        if rkey and (not w.root or normalize(w.root) != rkey):
            continue
        have = {t for s in w.segments for t in s.tags} | {s.kind for s in w.segments}
        if not want <= have:
            continue
        if verb_form and not any(s.attrs.get("VF") == str(verb_form) for s in w.segments):
            continue
        hits.append(w)
    return {
        "total_matches": len(hits),
        "matches": [w.summary() for w in hits[:limit]],
        "truncated": len(hits) > limit,
    }


@mcp.tool()
def explain_tags(tags: list[str] | None = None) -> dict:
    """Meaning of morphology tags (e.g. "ACT_PCPL", "3MP", "VF"). With no argument, returns
    the full tag inventory."""
    if not tags:
        return {
            "segment_types": KINDS,
            "tags": TAGS,
            "person_gender_number": "Combined tags like 3MP = 3rd person masculine plural, 2FS = 2nd person feminine singular, MD = masculine dual",
            "attributes": {
                "ROOT": "consonantal root", "LEM": "lemma (dictionary form)",
                "VF": "verb form I-XII", "MOOD": "IND/SUBJ/JUS", "FAM": "family (e.g. kana and sisters)",
            },
        }
    return {t: gloss(t) for t in tags}


if __name__ == "__main__":
    mcp.run()
