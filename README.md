# quran-morphology

An MCP server that gives Claude (or any MCP client) word-by-word morphology of the Quran:
segments, part of speech, root, lemma, verb form, mood, case, and person/gender/number.

The data comes from the [Quranic Arabic Corpus](http://corpus.quran.com) v0.4, via the
revised fork at [mustafa0x/quran-morphology](https://github.com/mustafa0x/quran-morphology),
which adds missing roots, fixes many lemmas, and uses Arabic script instead of Buckwalter.
It covers every word of the Quran (130,030 segments).

## Setup

Requires Python 3.10+.

```bash
cd ~/mcp-servers/quran-morphology
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
claude mcp add -s user quran-morphology -- ~/mcp-servers/quran-morphology/.venv/bin/python ~/mcp-servers/quran-morphology/server.py
```

`-s user` makes the server available in all projects. Check it with `claude mcp get quran-morphology`.

If `data/quran-morphology.txt` is missing, the server downloads it (about 6 MB) the first time a tool is called.

## Tools

| Tool | Arguments | Returns |
|---|---|---|
| `get_word_morphology` | `surah`, `ayah`, `word` | Full breakdown of one word: each segment (prefix, stem, suffix) with its tags explained |
| `get_verse_morphology` | `surah`, `ayah`, `detailed=false` | Every word in an ayah, as a short summary or (with `detailed=true`) the full breakdown |
| `search_root` | `root`, `surah?`, `limit=50` | Total count, number of surahs, a count per lemma, and the occurrences |
| `search_lemma` | `lemma`, `surah?`, `limit=50` | Count, the lemmas matched, the surface forms with counts, and the occurrences |
| `find_words` | `tags?`, `root?`, `verb_form?`, `surah?`, `limit=50` | Words whose segments together carry all the given tags |
| `explain_tags` | `tags?` | What each tag means; with no argument, the full tag list |

Word numbers start at 1 within each ayah. Results longer than `limit` are cut off and marked `"truncated": true`; the totals always count every match.

### Matching

Root and lemma searches ignore diacritics, tatweel, hamza seats (أ إ آ ٱ → ا, ؤ → و, ئ → ي),
alef maqsura, ta marbuta and spaces. So `رحمن` finds `رَحْمٰن`, `ر ح م` finds the root `رحم`,
and `اله` finds `أله`.

### Example output

`get_word_morphology(1, 1, 3)`:

```json
{
  "ref": "1:1:3",
  "text": "ٱلرَّحْمَٰنِ",
  "pos": "nominal",
  "tags": ["MS", "GEN", "ADJ"],
  "lemma": "رَحْمٰن",
  "root": "رحم",
  "segments": [
    {"form": "ٱل", "type": "particle", "lemma": "ال", "tags": ["DET", "PREF"],
     "features": ["DET: determiner (al-)", "PREF: prefix"]},
    {"form": "رَّحْمَٰنِ", "type": "nominal", "root": "رحم", "lemma": "رَحْمٰن", "tags": ["MS", "GEN", "ADJ"],
     "features": ["MS: masculine singular", "GEN: genitive", "ADJ: adjective"]}
  ]
}
```

### `find_words` examples

| Query | Finds |
|---|---|
| `tags=["V","IMPV"]` | Imperative verbs |
| `tags=["V","IMPV"], verb_form=4` | Form IV imperatives (297 words) |
| `tags=["PASS","PERF"]` | Perfect (past) passive verbs |
| `tags=["N","ACT_PCPL"], root="علم"` | Active participles of علم |
| `tags=["3FS"], surah=19` | 3rd person feminine singular forms in Maryam |

`N`, `V` and `P` match the segment type (nominal, verb, particle). Every other tag matches the segment's features.

## Tag reference

Common tags (call `explain_tags()` for the full list):

- **Segment types:** `N` nominal, `V` verb, `P` particle
- **Segment role:** `PREF` prefix, `SUFF` suffix
- **Nominals:** `PN` proper noun, `ADJ` adjective, `PRON` pronoun, `DEM` demonstrative, `REL` relative pronoun, `VN` verbal noun (masdar), `ACT_PCPL` / `PASS_PCPL` active / passive participle, `T` time adverb, `LOC` location adverb
- **Verbs:** `PERF` perfect, `IMPF` imperfect, `IMPV` imperative, `PASS` passive; the verb form (I–XII) is in `verb_form`, the mood (`IND`, `SUBJ`, `JUS`) in `mood`
- **Case and state:** `NOM`, `ACC`, `GEN`, `INDEF`, `DET` (the al- prefix)
- **Person/gender/number:** combined tags such as `3MP` (3rd person masculine plural), `2FS`, `MD` (masculine dual), `1S`
- **Particles:** `P` preposition, `CONJ`, `SUB`, `NEG`, `INTG`, `COND`, `VOC`, `EMPH`, `REM`, `RES`, `INL` (muqatta'at letters), and others

`ACC` means accusative case on nominals, and accusative particle (inna and its sisters) on particles.

## Files

```
server.py                  the server; all tools are in this file
requirements.txt           mcp>=2.0
data/quran-morphology.txt  the corpus (downloaded on first use)
```

The server uses MCP Python SDK v2 (`mcp.server.mcpserver.MCPServer`), not the v1 `FastMCP` import.

## License

The morphology data is from the Quranic Arabic Corpus and is licensed under the GNU GPL.
If you redistribute the data, keep its attribution and license terms.
