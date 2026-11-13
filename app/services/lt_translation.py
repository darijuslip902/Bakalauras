"""Lietuviškų klaidų aprašymų paruošimas ML modeliui (5C): kalbos atpažinimas ir žodyno vertimas.

Kodėl žodynas, o ne mašininio vertimo modelis. Klasifikavimo modelis yra TF-IDF (žodžių / žodžių
porų maišas) + LogisticRegression, mokytas iš angliškų GitHub issues. Jam reikia ne sklandaus
sakinio, o teisingų angliškų žodžių, todėl pakanka vertimo žodis po žodžio. Mašininio vertimo
modelis (pvz. Helsinki-NLP/opus-mt-lt-en per transformers + torch) reikalautų šimtų MB atsisiuntimo,
didelių priklausomybių (torch) ir sekundžių vienam tekstui, o sprendimas turi būti paprastas ir
veikti Windows aplinkoje be papildomo diegimo. Žodynas – keli šimtai programinės įrangos terminų
su lietuviškų galūnių (kaitybos) apdorojimu: veikia iš karto, be tinklo, milisekundėmis.

Apribojimai (aiškiai): tai NĖRA pilnas vertimas. Neįtraukti žodžiai lieka nepakeisti (modelio
žodyne jų nėra, todėl jie ignoruojami), žodžių tvarka ir gramatika nesvarbi. Nepažįstamos
terminijos tekstai bus klasifikuojami blogai, todėl tokios prognozės žymimos kaip nepatikimos.

Originalus pavadinimas ir aprašymas niekur nekeičiami; išverstas tekstas naudojamas tik kaip
modelio įvestis ir nesaugomas.
"""

import logging
import re
from dataclasses import dataclass

logger = logging.getLogger(__name__)

# Lietuviškos raidės be diakritikų (1:1, todėl ilgis nekeičiamas). Naudotojai dažnai rašo be jų.
_FOLD = str.maketrans("ąčęėįšųūž", "aceeisuuz")
_LT_DIACRITICS = set("ąčęėįšųūž")
_WORD = re.compile(r"[a-z0-9_]+")

# Dažni lietuviški tarnybiniai žodžiai (be diakritikų) – kalbos atpažinimui.
_LT_MARKERS = frozenset(
    "ir yra nes kad bet arba kai tai nera negalima nepavyksta neveikia su prie jau tik labai visi "
    "visada kartais norint paspaudus bandant kodel kaip kur mano mes buvo gali galima reikia turi "
    "turetu po kuris kuri kurie taip jei jeigu pries tada dabar vietoj nuo iki apie esu esame "
    "negaliu nesigauna neranda neatsidaro nerodo neisssaugo nereaguoja atsiranda ismeta".split()
)
_EN_MARKERS = frozenset(
    "the is are and when with not this that it to of in on for after if does doesn can cannot "
    "should would from has have was were but or an error".split()
)

# Frazės (regex normalizuotam tekstui be diakritikų) – turi pirmenybę prieš pavienius žodžius.
_PHRASES = (
    (r"duomen\w* baz\w*", "database"),
    (r"atminties nutekej\w*", "memory leak"),
    (r"nutekej\w* atmint\w*", "memory leak"),
    (r"nulin\w* nuorod\w*", "null pointer"),
    (r"klaidos pranesim\w*", "error message"),
    (r"sql injekc\w*", "sql injection"),
    (r"dviej\w* faktori\w*", "two factor authentication"),
    (r"vartotoj\w* sasaj\w*|naudotoj\w* sasaj\w*", "user interface ui"),
    (r"issklei\w* meniu", "dropdown menu"),
    (r"ilgai (?:uztrunka|vyksta|kraunasi)|uztrunka ilgai", "takes long time slow"),
    (r"nera atsako|negaunamas atsakas", "no response"),
)

# Pavieniai žodžiai: kamienas (be diakritikų, ≥ 5 raidžių) -> angliški atitikmenys. Atitinka
# žodžio pradžią, todėl apima lietuviškas galūnes (klaida, klaidos, klaidų, klaidingas...).
_STEMS = {
    # bendri gedimų požymiai
    "klaid": "error",
    "klaidin": "wrong incorrect",
    "nepavyk": "failed fails",
    "neveik": "not working does not work fails",
    "nustoj": "stopped working",
    "luzt": "crash",
    "luzo": "crash",
    "luzin": "crash",
    "uzstrig": "hangs freeze",
    "uzstring": "hangs freeze",
    "uzsala": "freezes hangs",
    "stringa": "hangs freeze",
    "sugedo": "broken",
    "sugedim": "broken",
    "nereaguoj": "not responding",
    "neatsidar": "does not open",
    "neikelia": "does not load",
    "neikelt": "does not load",
    "nesikrau": "does not load",
    "nerodo": "does not show",
    "nematom": "not visible",
    "neissaug": "does not save",
    "nesisaug": "does not save",
    "praranda": "lost",
    "dingsta": "disappears",
    "dingo": "disappeared",
    "isiuncia": "sends",
    "nesiun": "does not send",
    "problem": "problem issue",
    "gedim": "failure bug",
    "defekt": "bug defect",
    "isimtis": "exception",
    "isimtys": "exception",
    "grazina": "returns",
    "grazint": "returns",
    "ismeta": "throws error",
    "pasirod": "appears",
    "atsiran": "appears",
    "isvedam": "output",
    # naudotojo sąsaja
    "mygtuk": "button",
    "paspaud": "click",
    "spustel": "click",
    "spaust": "click press",
    "puslapi": "page",
    "meniu": "menu",
    "skirtuk": "tab",
    "nuorod": "link",
    "dialog": "dialog",
    "langel": "box dialog",
    "spalv": "color",
    "sriftas": "font",
    "srifto": "font",
    "isdestym": "layout",
    "ekran": "screen",
    "sasaj": "interface ui",
    "vaizdav": "display render",
    "dizain": "design ui",
    "klaviatur": "keyboard",
    "slinkt": "scroll",
    "slinkim": "scroll",
    "isskleid": "dropdown",
    "virsuj": "top",
    "ikon": "icon",
    "pele": "mouse",
    "tamsi": "dark theme",
    "temos": "theme",
    "mobil": "mobile",
    "narsykl": "browser",
    "pranesim": "message notification",
    "animac": "animation",
    "uzdeng": "overlaps covers",
    "persidengi": "overlap",
    "lenteles": "table",
    "centr": "center align",
    "isjung": "disable turn off",
    "ijung": "enable turn on",
    # serveris / API
    "serveri": "server",
    "serverio": "server",
    "serveryje": "server",
    "uzklaus": "request query",
    "atsakym": "response",
    "atsakas": "response",
    "marsrut": "route",
    "integrac": "integration",
    "endpoint": "endpoint api",
    "servis": "service",
    "paslaug": "service",
    "kliento": "client",
    "klientas": "client",
    "timeout": "timeout",
    "praleidzia": "skips",
    "parametr": "parameter argument",
    "argument": "argument",
    "funkcij": "function",
    "metod": "method",
    "objekt": "object",
    "reiksm": "value",
    "tuscia": "empty",
    "tuscias": "empty",
    "neteising": "invalid",
    "neteisin": "invalid",
    "formatas": "format",
    "formato": "format",
    "apdorojim": "processing",
    "sinchroniz": "sync",
    "eilej": "queue",
    "uzduot": "task job",
    # duomenų bazė ir duomenys
    "duomen": "data",
    "lentel": "table",
    "stulpel": "column",
    "eilut": "row line",
    "indeks": "index",
    "migrac": "migration",
    "irasas": "record row",
    "irasai": "records rows",
    "irasu": "records rows",
    "irasa": "record row",
    "dubliuoj": "duplicate",
    "dublik": "duplicate",
    "transakc": "transaction",
    "saugykl": "storage",
    "atsarg": "backup",
    "eksport": "export",
    "importuo": "import",
    "importav": "import",
    "kopij": "copy",
    "isrink": "select",
    "sujung": "join",
    "uzklausa": "query",
    "rikiav": "sort order",
    "filtr": "filter",
    "paieska": "search",
    "paieskos": "search",
    "skaiciav": "calculation",
    "ataskait": "report",
    # saugumas
    "saugum": "security",
    "pazeidziam": "vulnerability",
    "slaptazod": "password",
    "prisijung": "login authentication",
    "atsijung": "logout",
    "autentifik": "authentication",
    "autorizac": "authorization",
    "sesij": "session",
    "leidim": "permission access",
    "uzpuol": "attack",
    "ataka": "attack",
    "isilauz": "hack breach",
    "sifr": "encryption",
    "uzsifr": "encryption",
    "sertifikat": "certificate",
    "injekc": "injection",
    "prieig": "access",
    "slapuk": "cookie",
    "zetonas": "token",
    "zetono": "token",
    "raktas": "key",
    "rakto": "key",
    "neleistin": "unauthorized",
    "neteis": "unauthorized permission",
    "vartotoj": "user",
    "naudotoj": "user",
    "paskyr": "account user",
    "viesai": "public exposed",
    "nutekej": "leak exposed",
    "asmenin": "personal private",
    "apsaug": "protection security",
    # našumas
    "letai": "slow",
    "letas": "slow",
    "leta": "slow",
    "letesn": "slower slow",
    "letum": "slow performance",
    "nasum": "performance",
    "greitaveik": "performance",
    "atmint": "memory",
    "procesor": "cpu",
    "apkrov": "load",
    "uztrunk": "takes long time",
    "sekund": "seconds",
    "minut": "minutes",
    "optimiz": "optimization performance",
    "sunaudoj": "consumes uses",
    "padidej": "increases grows",
    "greit": "fast",
    "lasto": "slow",
    "keli": "several",
    "kraunas": "loading load",
    "krovim": "loading load",
    "kasdien": "every",
    # kompiliavimas, diegimas
    "diegim": "install deployment",
    "idieg": "install",
    "idiegt": "install",
    "kompiliav": "compile build",
    "kompil": "compile build",
    "surinkim": "build",
    "paket": "package",
    "priklausomyb": "dependency package",
    "konteiner": "docker container",
    "versij": "version",
    "atnaujin": "update upgrade",
    "konfiguraci": "configuration config",
    "aplinkos": "environment",
    "vamzdyn": "pipeline",
    "failas": "file",
    "failo": "file",
    "failai": "files",
    "katalog": "directory",
    "biblioteka": "library",
    "bibliotek": "library",
    "moduli": "module",
    "paleidim": "run start launch",
    "paleisti": "run start",
    "paleidzi": "run start",
    "isdieg": "deploy",
    "ikelim": "upload deploy",
    "vykdym": "execution run",
    # dokumentacija
    "dokument": "documentation docs",
    "instrukcij": "instructions docs",
    "vadov": "guide docs",
    "pavyzd": "example docs",
    "rasybos": "typo",
    "korektur": "typo",
    "neaktual": "outdated",
    "trukst": "missing",
    "skyri": "section",
    "aprasym": "description docs",
    "paaiskin": "explain docs",
    "nepaaiskin": "unclear docs",
    "neaisk": "unclear",
    "isverst": "translation",
    "vertim": "translation",
    "komentar": "comment",
    "pastab": "note docs",
    "pasenus": "outdated",
}

# Žodžiai, kuriuos reikia atitikti tiksliai (trumpi arba dviprasmiški kamienai).
_WORDS = {
    "langas": "window", "lango": "window", "langa": "window", "langai": "windows", "langu": "windows",
    "kodas": "code", "kodo": "code", "koda": "code", "kode": "code", "kodu": "code",
    "forma": "form", "formos": "form", "forme": "form", "formoje": "form", "formoj": "form",
    "laukas": "field", "lauko": "field", "laukai": "fields", "lauke": "field", "lauku": "fields",
    "teises": "permissions", "teisiu": "permissions", "teisems": "permissions",
    "serveris": "server", "serveri": "server", "serveryje": "server",
    "meta": "throws", "metama": "throws", "stack": "stack trace", "api": "api", "sql": "sql", "ui": "ui", "cpu": "cpu",
    "kai": "when", "nes": "because", "bet": "but", "arba": "or", "yra": "is",
    "neveikia": "not working does not work",
    "nera": "is not", "negalima": "cannot", "nepavyksta": "fails",
    "su": "with", "ir": "and", "po": "after", "prie": "at", "jei": "if", "jeigu": "if",
    "kodel": "why", "viskas": "all", "visi": "all", "visada": "always", "kartais": "sometimes",
    "dydis": "size", "dydzio": "size", "didelis": "large", "dideli": "large", "didelio": "large",
    "daug": "many", "labai": "very", "ilgai": "long", "ilgas": "long",
    "tekstas": "text", "teksto": "text", "pavadinimas": "title name", "pavadinimo": "title name",
    "duomenys": "data", "duomenu": "data", "failu": "files",
    "klaida": "error", "klaidos": "error", "klaidu": "errors", "klaidas": "errors",
    "puslapis": "page", "puslapio": "page", "puslapyje": "page",
    "tinklas": "network", "tinklo": "network", "rysys": "connection", "rysio": "connection",
    "prisijungimas": "login connection", "prisijungimo": "login connection",
    "isjungia": "turns off", "ijungia": "turns on", "uzdaro": "closes", "atidaro": "opens",
    "atidaryti": "open", "uzdaryti": "close", "issaugoti": "save", "saugoti": "save",
    "trinti": "delete", "istrinti": "delete", "naujas": "new", "nauja": "new",
    "pridet": "add", "prideti": "add", "pridejus": "after add",
    "redaguoti": "edit", "redagavimas": "edit", "redagavimo": "edit",
    "sukurti": "create", "kuriant": "creating", "sukuriant": "creating",
    "rodo": "shows", "rodyti": "show", "rodomas": "shown", "rodoma": "shown",
}

_WORD_CACHE: dict[str, str | None] = {}
_STEM_ITEMS = tuple(sorted(((fold, eng) for fold, eng in
                            ((k.translate(_FOLD), v) for k, v in _STEMS.items()) if len(fold) >= 4),
                           key=lambda item: -len(item[0])))
_WORDS_FOLDED = {k.translate(_FOLD): v for k, v in _WORDS.items()}
_PHRASE_RES = tuple((re.compile(pattern), english) for pattern, english in _PHRASES)


def fold(text: str) -> str:
    """Mažosios raidės be lietuviškų diakritikų (ilgis nekeičiamas)."""
    return text.lower().translate(_FOLD)


def _lookup(token: str) -> str | None:
    if token in _WORD_CACHE:
        return _WORD_CACHE[token]
    english = _WORDS_FOLDED.get(token)
    if english is None and len(token) >= 5:
        for stem, translation in _STEM_ITEMS:
            if token.startswith(stem):
                english = translation
                break
    _WORD_CACHE[token] = english
    return english


def detect_language(text: str) -> str:
    """`lt`, jei tekste vyrauja lietuviški požymiai (diakritikai, tarnybiniai ir žodyno žodžiai), kitu atveju `en`."""
    lowered = text.lower()
    lt_score = 2 * sum(1 for ch in lowered if ch in _LT_DIACRITICS)
    lt_score = min(lt_score, 6)
    en_score = 0
    for token in _WORD.findall(fold(text)):
        if token in _LT_MARKERS:
            lt_score += 1
        elif token in _EN_MARKERS:
            en_score += 1
        elif _lookup(token) is not None and token not in _EN_LOOKALIKES:
            lt_score += 1
    return "lt" if lt_score >= 1 and lt_score > en_score else "en"


# Žodyno žodžiai, kurie sutampa su angliškais: nelaikomi lietuvių kalbos požymiu.
_EN_LOOKALIKES = frozenset({"api", "sql", "ui", "cpu", "stack", "timeout", "endpoint", "dialog", "meniu"})


def translate_to_english(text: str) -> tuple[str, int]:
    """Žodyno vertimas modelio įvesčiai. Grąžina (tekstas, pakeistų žodžių / frazių skaičius)."""
    folded = fold(text)
    spans = sorted(
        (m.start(), m.end(), english) for pattern, english in _PHRASE_RES for m in pattern.finditer(folded)
    )
    pieces: list[str] = []
    replaced = 0
    position = 0
    for start, end, english in spans:
        if start < position:
            continue  # sutampanti frazė
        chunk, count = _translate_words(folded[position:start])
        pieces += [chunk, english]
        replaced += count + 1
        position = end
    chunk, count = _translate_words(folded[position:])
    pieces.append(chunk)
    return " ".join(piece for piece in pieces if piece), replaced + count


def _translate_words(chunk: str) -> tuple[str, int]:
    out: list[str] = []
    replaced = 0
    for token in _WORD.findall(chunk):
        english = _lookup(token)
        if english is None:
            out.append(token)
        else:
            out.append(english)
            replaced += 1
    return " ".join(out), replaced


@dataclass(frozen=True)
class PreparedText:
    text: str  # ML modelio įvestis
    language: str  # lt | en
    method: str  # none | glossary | unavailable
    terms: int = 0  # kiek lietuviškų žodžių / frazių išversta
    reliable: bool = True  # False – prognozė turi būti pažymėta kaip nepatikima
    note: str | None = None  # paaiškinimas naudotojui


MIN_TERMS_FOR_RELIABLE_TRANSLATION = 3


def prepare_model_text(title: str, description: str) -> PreparedText:
    """Paruošia modelio įvestį: angliškas tekstas nekeičiamas, lietuviškas verčiamas žodynu.

    Niekada nemeta klaidos: jei vertimas nepavyksta, naudojamas originalus tekstas, o prognozė
    pažymima kaip nepatikima.
    """
    original = f"{title.strip()}\n\n{(description or '').strip()}".strip()
    try:
        language = detect_language(original)
    except Exception:  # apsauga: kalbos atpažinimas neturi nutraukti pateikimo
        logger.exception("Kalbos atpažinimas nepavyko")
        language = "en"
    if language == "en":
        return PreparedText(original, "en", "none")
    try:
        translated, terms = translate_to_english(original)
    except Exception:
        logger.exception("Lietuviško teksto vertimas nepavyko")
        return PreparedText(
            original, "lt", "unavailable", 0, False,
            "Lietuviško teksto vertimas nepavyko: klasifikuota pagal originalų tekstą, prognozė nepatikima.",
        )
    if terms < MIN_TERMS_FOR_RELIABLE_TRANSLATION:
        return PreparedText(
            translated, "lt", "glossary", terms, False,
            f"Tekstas lietuvių kalba, atpažinta tik {terms} programinės įrangos terminų: prognozė nepatikima.",
        )
    return PreparedText(
        translated, "lt", "glossary", terms, True,
        f"Tekstas lietuvių kalba: klasifikuota pagal žodyno vertimą į anglų kalbą (atpažinta terminų: {terms}). "
        "Prognozė apytikslė.",
    )
