# Programinės įrangos klaidų automatinio klasifikavimo ir prioritizavimo sistema

Bakalauro darbo prototipas – klaidų registravimo ir valdymo svetainė su automatiniu teksto klasifikavimu. Klientas / testuotojas be paskyros pateikia klaidą viešoje formoje. Sistema bando automatiškai nustatyti jos kategoriją, prioritetą ir sudėtingumą. Programuotojas / koordinatorius prisijungęs peržiūri, filtruoja ir tvarko pranešimus, keičia jų būsenas ir mato išspręstų klaidų istoriją. Vieši GitHub Issues importuojami atskirai modelio mokymui ir vertinimui.

## Tikslas

Automatiškai pasiūlyti klaidos **kategoriją**, **sudėtingumo lygį** ir **prioritetą**. Sistema turi parodyti, kokiu būdu gautas rezultatas, jo pasitikėjimo įvertį ir aiškiai pažymėti atvejus, kai patikimų prognozių dar negalima teikti. Atsakingo programuotojo parinkimas sąmoningai neįtrauktas į pirmąją versiją.

## Pagrindinis funkcionalumas

- Vieša klaidos pateikimo forma be kliento paskyros; klientas mato tik pateikimo patvirtinimą.
- Vidinė, prisijungimu apsaugota programuotojo / koordinatoriaus aplinka.
- Visų pranešimų sąrašas, paieška ir filtravimas pagal būseną, kategoriją, prioritetą bei sudėtingumą.
- Būsenos new, in_progress, resolved; išspręstos klaidos lieka istorijoje.
- Automatinė klasifikacija veikia tik kai yra tinkamas apmokytas modelis; kitu atveju sistema vis tiek išsaugo pranešimą ir aiškiai parodo, kad prognozės nėra.
- Programuotojas gali pataisyti prognozę; modelio prognozė ir žmogaus patvirtinta žyma saugomos atskirai.
- Vieši GitHub Issues naudojami kaip atskiras mokymo duomenų šaltinis, o GitHub pusėje sistema nieko nekeičia.

## Architektūros sprendimai

- Python 3.12+
- FastAPI – HTTP API ir serverio pusėje generuojama HTML sąsaja.
- Jinja2 – HTML šablonai; atskiro React/Vue projekto nėra.
- SQLite – lokali duomenų bazė, valdoma standartiniu Python sqlite3 moduliu.
- scikit-learn – TF-IDF teksto požymiai ir atskiras prižiūrimo klasifikavimo modelis kiekvienam laukui.
- GitHub REST API – tik skaitymo režimu importuojami viešos repozitorijos issues; pull request įrašai atmetami.
- pytest – vienetiniai ir integraciniai testai.
- Anthropic Claude API (`anthropic` SDK) – **tik** vienkartiniam mokymo duomenų žymėjimui atskiru scenarijumi `tools/ai_label.py`; svetainė DI API nenaudoja.

Pilnas pagrindimas ir komponentų sąveika aprašyti [ARCHITECTURE.md](ARCHITECTURE.md). Claude Code veikimo taisyklės pateiktos [CLAUDE.md](CLAUDE.md), pirmoji ir vėlesnės užklausos – [docs/CLAUDE_PROMPT.md](docs/CLAUDE_PROMPT.md), darbų etapai – [docs/IMPLEMENTATION_PLAN.md](docs/IMPLEMENTATION_PLAN.md), anotavimo gairės – [docs/DATA_LABELING.md](docs/DATA_LABELING.md), o vertinimo metodika – [docs/EVALUATION_PLAN.md](docs/EVALUATION_PLAN.md).

## Duomenų kokybės principas

GitHub etiketės nėra automatiškai laikomos teisingomis kategorijos, prioriteto ar sudėtingumo žymomis. Naudotojas turi galėti patvirtinti žymas sistemoje. Kiekvienam laukui modelis mokomas tik tada, kai duomenų kiekis ir klasių pasiskirstymas atitinka iš anksto aprašytas sąlygas. Kitu atveju sistema rodo, kad duomenų nepakanka, arba atskirai pažymėtą taisyklių pasiūlymą. Nežymėtos ir sintetiniu būdu sukurtos demonstracinės eilutės negali būti pateikiamos kaip realaus modelio vertinimo duomenys.

## Įgyvendinimo būsena

Įgyvendinti 0–4, 5A, 5B (programinė dalis) ir 5C etapai:

- **0 etapas:** FastAPI karkasas, `GET /health`, pagrindinis puslapis `GET /`.
- **1 etapas:** SQLite schema (`bug_reports`, `github_issues`) ir viešų GitHub issues importas per `/import` (`owner/repo` arba `https://github.com/owner/repo`, kiekis iki `GITHUB_IMPORT_LIMIT`). Pull request įrašai praleidžiami, pakartotinis importas nedubliuoja įrašų ir neperrašo žmogaus patvirtintų žymų.
- **2 etapas:** vieša klaidos pateikimo forma `/report` be paskyros (pavadinimas iki 200, aprašymas iki 10000 simbolių, validacija serverio pusėje); įrašas išsaugomas su būsena `new`, naudotojui rodomas tik patvirtinimas.
- **3 etapas:** programuotojo prisijungimas (`/login`, `/logout`) ir vidinė aplinka: klaidų sąrašas `/dashboard` su paieška ir filtrais, detalių puslapis `/dashboard/reports/{id}`, būsenų keitimas `new` → `in_progress` → `resolved` (išspręsti įrašai lieka istorijoje, juos galima atidaryti iš naujo). `/import` taip pat pasiekiamas tik prisijungus.
- **4 etapas:** mokymo duomenų (importuotų GitHub issues) peržiūra ir rankinis žymėjimas `/dashboard/training-data`: kategorija, sudėtingumas, prioritetas ir tinkamumas mokymui, žymėjimo eigos statistika, „Kitas nepažymėtas“.
- **5A etapas:** mokymo duomenų paruošimo ir ML mokymo įrankiai komandinėje eilutėje (`tools/`): masinis importas, kokybės patikra, žmogaus testavimo rinkinys, DI žymėjimas su biudžeto kontrole, trijų modelių mokymas ir vertinimas. Svetainė jų nenaudoja.
- **5C etapas:** apmokyti vietiniai ML modeliai integruoti į svetainę – pateikus naują klaidą automatiškai prognozuojama kategorija, sudėtingumas ir prioritetas (žr. skyrių „Automatinė klasifikacija svetainėje“). Be DI API ir be tinklo.
- **5B etapas (programinė dalis):** visa duomenų paruošimo eiga – projektų šaltinių failas ir jo patikra, rinkimas viena komanda, filtras pagal ne klaidų etiketes, atskiri bandomasis ir galutinis testavimo rinkiniai, klasių analizė visoms trims užduotims su tiksliniu papildymu, galutinė Markdown ataskaita su pasikliautinaisiais intervalais. Realus rinkimas, DI žymėjimas ir mokymas vykdomi naudotojo kompiuteryje; modelių prijungimas prie svetainės – 5C etape.

**Duomenų būklė (2026-11-09):** surinkta 2 906 GitHub issues iš 13 `base` šaltinių (`sources.json` 25 šaltiniai = 13 `base` + 12 `augment`; `augment` naudojamas tik su `--augment`, kai jau yra žymų). 2 884 įrašai praėjo kokybės patikrą (po etikečių filtro pataisos; anksčiau 2 774); žmogaus žymų, DI žymų ir testavimo / bandomojo rinkinių dar nėra. Išsami analizė, kainos įvertis ir rekomendacijos – [docs/DATA_QUALITY_REPORT.md](docs/DATA_QUALITY_REPORT.md).

Duomenų bazė kuriama automatiškai (`DATABASE_PATH`, pagal nutylėjimą `data/bakalauras.sqlite3`; failas nėra committinamas). Klientų pranešimų (`/dashboard`) kategorija, prioritetas ir sudėtingumas rodomi iš programuotojo patvirtintų žymų, o jei jų nėra – iš automatinės prognozės (pilkesniu kursyvu, kol nepatvirtinta); jei modelių nėra, rodoma „Dar nenustatyta“. Senesnė DB paleidimo metu automatiškai papildoma nauju stulpeliu `github_issues.training_suitability` (esami įrašai ir žymos išlieka). Likę etapai kuriami pagal docs/IMPLEMENTATION_PLAN.md.

## Vietinis paleidimas

Rekomenduojamas Python 3.12 ar naujesnis palaikomas leidimas.

```bash
python -m venv .venv
# Linux/macOS:
source .venv/bin/activate
# Windows PowerShell:
# .venv\Scripts\Activate.ps1

python -m pip install -r requirements.txt
uvicorn app.main:app --reload
```

Vietinis adresas: http://127.0.0.1:8000 (sveikatos patikrinimas: http://127.0.0.1:8000/health).

Testai (naudoja laikiną duomenų bazę ir netikrą GitHub, todėl vietinio `data/` failo nekeičia):

```bash
python -m pytest
```

## Programuotojo prisijungimo konfigūravimas

Vidinė aplinka turi vieną paskyrą. Numatytojo slaptažodžio nėra: kol nenustatyti žemiau esantys kintamieji, prisijungti neįmanoma (puslapis `/login` parodo pranešimą „Prisijungimas nesukonfigūruotas“).

| Kintamasis | Paskirtis |
|---|---|
| `ADMIN_USERNAME` | Prisijungimo vardas, pvz., `admin`. |
| `ADMIN_PASSWORD_HASH` | Slaptažodžio PBKDF2-SHA256 maišas (ne pats slaptažodis!). |
| `SESSION_SECRET_KEY` | Atsitiktinis bent 32 simbolių raktas, kuriuo pasirašomas sesijos slapukas. |
| `SESSION_COOKIE_SECURE` | `true` produkcinėje HTTPS aplinkoje. Lokaliai per HTTP palikti tuščią (per HTTPS atėjusioms užklausoms `Secure` įjungiamas automatiškai). |

Žingsniai (Windows PowerShell, projekto kataloge, aktyvavus `.venv`):

1. Sukurkite `.env` failą iš pavyzdžio:
   ```powershell
   Copy-Item .env.example .env
   ```
2. Sugeneruokite slaptažodžio maišą ir sesijos raktą. Komanda paprašys slaptažodžio du kartus (bent 10 simbolių; rašant jis nerodomas):
   ```powershell
   python -m app.auth
   ```
3. Atidarykite `.env` (pvz., `notepad .env`), įrašykite `ADMIN_USERNAME=admin` ir įklijuokite dvi komandos išvestas eilutes `ADMIN_PASSWORD_HASH=...` bei `SESSION_SECRET_KEY=...` vietoje tuščių. Išsaugokite failą.
4. Paleiskite serverį `uvicorn app.main:app --reload` ir atidarykite http://127.0.0.1:8000/login.

Programa `.env` failą nuskaito pati paleidimo metu; jei kintamasis jau nustatytas aplinkoje, jis turi pirmenybę. `.env` yra `.gitignore` sąraše, todėl į GitHub nepatenka. Niekada neįrašykite tikrų reikšmių į `.env.example`, kodą ar Git istoriją. Pakeitus slaptažodį (naujas maišas), visos senos sesijos nustoja galioti; pakeitus `SESSION_SECRET_KEY` – taip pat.

## Vidinės aplinkos naudojimas

- **Klaidų sąrašas** (`/dashboard`): visi pranešimai, įskaitant išspręstus, naujausi viršuje. Paieška ieško pavadinime ir aprašyme (didžiosios / mažosios raidės nesvarbu). Filtrai pagal būseną, kategoriją, prioritetą ir sudėtingumą; reikšmė „Dar nenustatyta“ randa įrašus be žymos.
- **Klaidos detalės** (paspaudus pavadinimą): visas aprašymas, laikai (UTC) ir žymos. Čia keičiama būsena: Nauja (`new`), Taisoma (`in_progress`), Išspręsta (`resolved`). Perėjus į „Išspręsta“ užpildomas išsprendimo laikas; atidarius iš naujo jis išvalomas. Įrašai niekada netrinami.
- **Mokymo duomenys**, **GitHub importas** (`/import`) ir **Atsijungti** – viršutinėje navigacijoje.
- Sesija galioja 8 valandas. Visi būseną keičiantys veiksmai (būsenos keitimas, importas, atsijungimas) apsaugoti CSRF žetonu.

## Mokymo duomenų žymėjimas

GitHub issues savaime nėra patikimi mokymo duomenys: GitHub etiketės (`bug`, `priority: high` ir pan.) skirtingose repozitorijose reiškia skirtingus dalykus, o dalis issues yra ne klaidos, bet funkcijų pasiūlymai ar klausimai. Todėl modelio mokymui naudojamos tik **žmogaus rankiniu būdu priskirtos** žymos (gairės – [docs/DATA_LABELING.md](docs/DATA_LABELING.md)); GitHub etiketės rodomos tik informacijai.

1. Importuokite issues puslapyje **GitHub importas** (`/import`).
2. Atidarykite **Mokymo duomenys** (`/dashboard/training-data`). Viršuje matyti eiga: iš viso importuota, visiškai pažymėta (visi trys laukai), iš dalies pažymėta (1–2 laukai), nepažymėta, paruošta mokymui. Išskleidus „Anotacijų skaičius pagal lauką ir klasę“ matyti kiekvienos klasės pavyzdžių skaičius.
3. Sąrašą galima filtruoti pagal žymėjimo būseną, tinkamumą mokymui ir repozitoriją, ieškoti pavadinime / aprašyme, rikiuoti nuo naujausių arba seniausių (pagal GitHub sukūrimo datą); rodoma po 25 įrašus puslapyje.
4. Spauskite **Kitas nepažymėtas** arba įrašo pavadinimą. Detaliame puslapyje perskaitykite aprašymą ir pasirinkite:
   - **Tinkamumas mokymui:** Neįvertinta (numatyta) / Tinka mokymui / Netinka mokymui (pvz., funkcijos pasiūlymas ar klausimas);
   - **Kategoriją**, **Sudėtingumą**, **Prioritetą** – neaiškų lauką palikite „Nežinoma / nepažymėta“ (saugoma kaip `NULL`).
5. **Išsaugoti** – lieka tame pačiame įraše; **Išsaugoti ir kitas** – pereina prie kito nepažymėto įrašo. „Kitas nepažymėtas“ praleidžia visiškai pažymėtus ir „Netinka mokymui“ įrašus.

Žymos saugomos tik šios sistemos `github_issues` lentelėje kartu su šaltiniu (`annotation_source = manual`) ir laiku (`annotated_at`); GitHub nekeičiamas. Pakartotinis importas atnaujina tik GitHub duomenis (pavadinimą, aprašymą, etiketes), bet ne žmogaus žymas. 5 etape mokymui bus naudojami tik įrašai, pažymėti „Tinka mokymui“ ir turintys visas tris reikšmes (statistikoje – „Paruošta mokymui“). Klientų pranešimai (`bug_reports`) į mokymo duomenis nepatenka.

## Mokymo duomenų paruošimas ir modelių mokymas (5A–5B)

Šie įrankiai paleidžiami komandinėje eilutėje, ne svetainėje. Visos komandos – **Windows CMD**, projekto kataloge, aktyvavus aplinką (`.venv\Scripts\activate.bat`). Pažymėtos **MOKAMA** – siunčia užklausas į Claude API (tik su `--execute` ir patvirtinimu „taip“); visos kitos nemokamos.

**Kodėl DI žymėjimas.** Rankiniu būdu pažymėti 2 000–3 000 issues per daug laiko, todėl (darbo vadovui pritarus) žymas vieną kartą sugeneruoja Claude modelis (numatytasis – pigiausias `claude-haiku-5-5`). GitHub etiketės nėra patikimos žymos, o DI žymos taip pat gali klysti – todėl:
- **bandomasis rinkinys** (~30 įrašų) – žmogus pažymi, DI pažymi, palyginama → pasirenkamas DI modelis ir matoma faktinė kaina. Šie įrašai **nenaudojami galutiniam vertinimui** (jie panaudoti sprendimui);
- **galutinis testavimo rinkinys** (~120 įrašų, atrenkamas prieš DI žymėjimą, proporcingai pagal projektus) – **niekada nenaudojamas mokymui**. Rankinio žymėjimo atsisakyta, todėl jo etalonas yra Claude žymos (žmogaus žyma, jei yra, turi pirmenybę). Metrikos tada rodo atitikimą DI žymoms, ne žmogaus patvirtintai tiesai; ataskaita tai nurodo. Pilot rinkinyje DI ir žmogaus žymų sutapimas (2026-11-10, 29 įrašai): kategorija 62 %, sudėtingumas 55 %, prioritetas 72 %;
- žmogaus žyma visada turi pirmenybę prieš DI žymą; klasės niekada nepriskiriamos dirbtinai.

### 0. Pasiruošimas

1. `.env` faile: `ANTHROPIC_API_KEY=` (raktas iš console.anthropic.com; Claude Pro prenumerata nėra API kreditas), `AI_TOTAL_BUDGET_USD=10` (bendras DI išlaidų limitas). `GITHUB_TOKEN` palikite tuščią – viešiems issues jo nereikia, rinkimo įrankiai jo pagal nutylėjimą nenaudoja.
2. Atsarginė DB kopija:

```bat
copy data\bakalauras.sqlite3 data\bakalauras.backup.sqlite3
```

### 1. Patikrinti šaltinius (nemokama)

Projektų sąrašas – `tools\sources.json` (13 įvairių sričių projektų: redaktorius, UI biblioteka, duomenų analizė, DB, stebėsena, konteineriai, infrastruktūra, Python, debesų saugykla, paieška, BI). Kiekvieno projekto „bug“ etiketė vadinasi skirtingai, todėl pirmiausia:

```bat
python -m tools.collect --check
```

Eilutės su `!!` – etiketė negrąžina issues arba projektas nepasiekiamas: pataisykite etiketę arba pašalinkite eilutę (`notepad tools\sources.json`) ir patikrinkite dar kartą.

### 2. Rinkimas, filtravimas ir rinkinių atranka (nemokama)

```bat
python -m tools.pipeline
```

Importuoja ~3 000 issues (be autentifikacijos), atmeta dublikatus, per trumpus ir ne klaidų etiketėmis (enhancement, question, duplicate…) pažymėtus įrašus, atrenka testavimo (120) ir bandomąjį (30) rinkinius ir parodo DI žymėjimo kainos įvertį. Jei matote „užklausų limitas“ – GitHub leidžia ~60 užklausų per valandą be paskyros; po valandos paleiskite tą pačią komandą. Rinkimas tęstinis: visiškai surinkti šaltiniai (repozitorija + etiketė) įsimenami DB lentelėje `collection_progress` ir kitą kartą praleidžiami (rodoma „praleistas – jau surinktas“), todėl tęsiama nuo neužbaigto šaltinio, o API užklausos nešvaistomos. Ta pati repozitorija su skirtingomis etiketėmis (pvz. `bug` ir `security`) vedama atskirai. Jei DB buvo sukurta anksčiau (be šios lentelės), šaltinis laikomas surinktu, kai DB jau turi bent `limit` jį atitinkančių issues; esami duomenys nekeičiami ir nedubliuojami. Jei limitą šaltiniui padidinsite `tools\sources.json`, jis bus surinktas dar kartą, o viską iš naujo galima surinkti su `python -m tools.collect --refresh`.

### 3. Pažymėti bandomąjį rinkinį (svetainėje, ~30 įrašų)

`uvicorn app.main:app --reload` → prisijungti → **Mokymo duomenys** → **Kitas nepažymėtas** (pirmiausia siūlo bandomąjį rinkinį; filtras „Žmogaus rinkiniai → Tik bandomasis rinkinys“).

### 4. Bandomasis DI žymėjimas (MOKAMA, apie centus)

```bat
python -m tools.ai_label --subset pilot --limit 40 --max-cost-usd 0.10 --execute
```

```bat
python -m tools.class_report
```

`class_report` parodo DI ir jūsų žymų sutapimą bei **faktinę** vienos užklausos kainą. Jei sutapimas nepakankamas, galima išbandyti kitą modelį (pridėti `--model claude-sonnet-5-5` abiem komandoms) arba patikslinti taisykles (tada keičiama prompt versija; bandomasis rinkinys vis tiek lieka nenaudojamas galutiniam vertinimui).

### 5. Testavimo rinkinio DI žymėjimas (MOKAMA, apie 3 centai)

Rankinis testavimo rinkinio žymėjimas nebereikalingas. Pirmiausia dry-run (nemokama), tada žymėjimas:

```bat
python -m tools.ai_label --subset test --limit 120
```

```bat
python -m tools.ai_label --subset test --limit 120 --max-cost-usd 0.20 --workers 3 --execute
```

### 6. Masinis DI žymėjimas (MOKAMA)

Pirmiausia kainos įvertis pagal faktinę bandomojo paleidimo kainą (nemokama), tada žymėjimas:

```bat
python -m tools.ai_label --subset training --limit 3000
```

Pirmiausia nedidelė partija (kaina ir užklausų limitai), tada likusieji; `--workers` 1–8 (rekomenduojama 3–4). Programa rodo pažangą (pažymėta / liko / likęs laikas):

```bat
python -m tools.ai_label --subset training --limit 100 --max-cost-usd 0.20 --execute
```

```bat
python -m tools.ai_label --subset training --limit 3000 --max-cost-usd 1.50 --workers 4 --execute
```

Jei pasirinkote kitą modelį, pridėkite `--model ...` ir atitinkamai didesnį `--max-cost-usd`. Nutrūkus – paleiskite tą pačią komandą (tęsia nuo nepažymėtų, jau pažymėti neapmokami dar kartą).

### 7. Klasių analizė ir tikslinis papildymas

```bat
python -m tools.class_report
```

Rodo kiekvienos kategorijos, sudėtingumo ir prioriteto klasės mokymo bei testo pavyzdžių skaičių ir trūkumą iki tikslo (numatyta 40). Jei trūksta:

```bat
python -m tools.collect --augment
```

```bat
python -m tools.ai_label --limit 2000 --max-cost-usd 2 --execute
```

```bat
python -m tools.class_report
```

`--augment` importuoja papildomus issues tik iš `tools\sources.json` „augment“ šaltinių trūkstamoms klasėms (pažymimi `source_kind = augmentation`; į bandomąjį ir testavimo rinkinius nepatenka). Klasę vis tiek nustato DI – jei jos pavyzdžių nepadaugėja arba šaltinio nėra (pvz. sudėtingumui), trūkumas lieka ir aiškiai nurodomas ataskaitoje.

### 8. Modelių mokymas ir galutinė ataskaita (nemokama)

```bat
python -m tools.train_models
```

Sukuriami `models\category_label.joblib`, `models\complexity_label.joblib`, `models\priority_label.joblib`, `models\training_report.md` (skaitoma ataskaita: duomenų kilmė, DI metodika ir kaina, klasių pasiskirstymas, accuracy, macro-F1 su 95 % intervalais, kiekvienos klasės precision / recall / F1, klaidų matricos, daugumos klasės baseline, apribojimai) ir `models\training_report.json`. Jei duomenų per mažai, laukas pažymimas `insufficient_data`. Bet kada eigą galima peržiūrėti `python -m tools.check_data`. Modelių failai ir DB į GitHub nekeliami.

**DI sąnaudų saugikliai:** dry-run pagal nutylėjimą; `--limit`; šio paleidimo riba `--max-cost-usd`; bendras `AI_TOTAL_BUDGET_USD` (skaičiuojamas iš DB); prieš kiekvieną užklausą tikrinama blogiausio atvejo kaina; faktinė kaina iš API `usage`; netinkamas atsakymas kartojamas daugiausia kartą; po API klaidos sustojama. Kainos įverčiai nėra garantija – patikimiausias yra faktinis bandomojo paleidimo rezultatas.

## Papildomas duomenų importas (5D – paruošimas)

5D tikslas – gerokai padidinti mokymo rinkinį (≥ 15 000 tinkamų pavyzdžių, ≥ 1 000 kiekvienai kategorijai) ir iš naujo apmokyti **tuos pačius** TF-IDF + LogisticRegression modelius. Šiame žingsnyje paruoštas tik importas; **mokamas žymėjimas ir mokymas dar nepradėti**. Esami `models/*` lieka kaip atskaitos taškas (modelio versija `20261110-143223`, Git žyma ar šaka `main`).

Kas pakeista infrastruktūroje (naujo įrankio nekurta):
- `tools\sources_5d.json` – 64 šaltiniai (repozitorija + etiketė), suskirstyti pagal kategorijas ir P0 (laukas `hint` tik planavimui; galutinę klasę nustato Claude žymėjimas). Etiketės **nepatikrintos gyvai** (mano aplinka negali kviesti GitHub API kitoms repozitorijoms) – patikrinkite `--check`;
- vieno šaltinio limitas padidintas nuo 1 000 iki 3 000 (30 puslapių po 100);
- `--check --counts` papildomai parodo bendrą issues skaičių (Search API) ir įspėja, jei jo mažiau nei `limit`;
- prieš importą automatiškai kuriama DB kopija `data\backups\bakalauras-<laikas>.sqlite3` (esamas failas nekeičiamas; išjungti: `--no-backup`);
- mokymo tekstai, beveik vienodi (kosinuso panašumas ≥ 0,9) testo tekstams, pašalinami iš mokymo (`excluded_test_near_duplicates` ataskaitoje); testo rinkinys nekeičiamas.

Ką paleisti (Windows CMD, projekto kataloge, aktyvavus `.venv`):

```bat
git fetch origin
git checkout claude/phase-5d-dataset-expansion
git pull
copy data\bakalauras.sqlite3 data\bakalauras.backup.sqlite3
```

1. Sukurkite **tik skaitymo** GitHub žetoną be jokių teisių (github.com → Settings → Developer settings → Personal access tokens → Tokens (classic) → nepažymėkite jokių „scopes“) ir įrašykite į `.env`: `GITHUB_TOKEN=ghp_...`. Be žetono limitas ~60 užklausų per valandą, todėl 15 000 issues užtruktų daug valandų; su žetonu – 5 000 per valandą (visam importui reikia ~400 užklausų). Žetonas niekada nerodomas žurnaluose.
2. Patikra (nemokama, nieko neįrašo į DB, ~5 min.):

```bat
python -m tools.collect --sources tools\sources_5d.json --check --counts --use-token
```

Eilutės su `!!` – etiketė neteisinga arba šaltinis nepasiekiamas: pataisykite `tools\sources_5d.json` (`notepad tools\sources_5d.json`) arba pašalinkite šaltinį ir kartokite. Atsiųskite man šią išvestį – pagal ją sutvarkysiu šaltinių sąrašą.
3. Importas (nemokama, tęstinis – nutrūkus paleiskite tą pačią komandą):

```bat
python -m tools.collect --sources tools\sources_5d.json --use-token
```

4. Kokybės patikra, testavimo rinkinio papildymas iki ~1 120 ir DI žymėjimo kainos įvertis (dry-run, API nekviečiamas):

```bat
python -m tools.check_data
python -m tools.pipeline --skip-import --test-size 1120
```

Testo rinkinys atrenkamas atsitiktinai (su seed, proporcingai pagal repozitorijas) iš naujai importuotų įrašų; senieji 120 testo ir 30 bandomojo įrašų nekeičiami. Dėl to retų kategorijų (dokumentacija, saugumas) teste gali būti per mažai pavyzdžių; pažymėjus DI žymas pasiūlysiu, ar atrinkti papildomą kategorijų balansuotą testo dalį.

Tolesni žingsniai (mokami / mokymas) – tik gavus Jūsų patvirtinimą po 4 žingsnio rezultatų.

## Automatinė klasifikacija svetainėje (5C)

Pateikus klaidą viešoje formoje (`/report`), svetainė išsaugo pranešimą ir iškart paleidžia tris vietinius modelius (`models/category_label.joblib`, `complexity_label.joblib`, `priority_label.joblib`, sukurti `python -m tools.train_models`). Kiekvieno lauko prognozė išsaugoma SQLite lentelėje `prediction_runs` (prognozuota reikšmė, modelio įvertis, ar rekomenduojama peržiūra, metodas, modelio versija, laikas). Žmogaus patvirtintos žymos (`bug_reports.category_label` ir kt.) **niekada neperrašomos**. Klientas mato tik patvirtinimą, o ne prognozes.

Programuotojas po prisijungimo:
- `/dashboard` – stulpeliuose „Kategorija“, „Prioritetas“, „Sudėtingumas“ rodoma patvirtinta žyma, o jos nesant – prognozė (pilkesniu kursyvu); stulpelis „Klasifikacija“ turi vieną būsenos žymą: „Patvirtinta“ (visos trys žymos nustatytos), „Laukia patvirtinimo“ arba „Neklasifikuota“. Filtrai veikia pagal rodomą reikšmę (patvirtinta turi pirmenybę);
- `/dashboard/reports/{id}` – kortelė „Klasifikacija“: patvirtinta klasifikacija (kas ir kada patvirtino), automatinė prognozė, forma „Patvirtinti klasifikaciją“, patvirtinimų istorija. Modelio įverčiai pagrindiniame vaizde **nerodomi**; jie (su slenksčiais, metodu, modelio versija, teksto kalba) pasiekiami sutraukiamoje skiltyje „Techninė informacija apie prognozę“, kur yra ir mygtukas „Klasifikuoti iš naujo“ (nekeičia patvirtintų žymų).

### Klasifikacijos patvirtinimas (5C)
Prisijungęs programuotojas detalių puslapyje mato formą, užpildytą ML prognoze (jei jos nėra – tuščią). Gali patvirtinti visas tris reikšmes arba pakeisti bet kurią (kategorija: `ui`, `backend_api`, `database_data`, `security`, `performance`, `build_deployment`, `documentation`, `other`; sudėtingumas: `low`, `medium`, `high`; prioritetas: `P0_critical`, `P1_high`, `P2_medium`, `P3_low`). Mygtukas įrašo reikšmes į `bug_reports.category_label / complexity_label / priority_label`, o lentelėje `classification_confirmations` išsaugo, kas, kada, ankstesnes patvirtintas reikšmes ir tuo metu buvusią ML prognozę. Jau patvirtinus forma rodo patvirtintas, o ne naujausias ML reikšmes. Serveris tikrina prisijungimą, CSRF žetoną ir kad visos trys reikšmės yra leistinos (kitaip 400 ir klaidos žinutė); tos pačios reikšmės pakartotinai istorijos neprideda. Sistemoje yra viena vidinė paskyra, todėl „įgaliotas“ = prisijungęs. Automatinis klasifikavimas patvirtintų žymų niekada neperrašo.

### Lietuviškas tekstas (5C)
Modeliai mokyti anglų kalba, todėl prieš prognozę tekstas aptinkamas ir, jei lietuviškas, išverčiamas **vietiniu žodynu** (`app/services/lt_translation.py`: ~230 programinės įrangos terminų kamienų, frazės, be mašininio vertimo modelio). Anglų tekstas neverčiamas. DB originalus pavadinimas ir aprašymas nekeičiami; vertimas naudojamas tik modelio įvesčiai, o kalba ir būdas išsaugomi `prediction_runs.input_language / translation_method`. Papildomų paketų, atsisiuntimų ar papildomos atminties nereikia (veikia Windows). Pasirinkta žodynas, o ne vertimo modelis (pvz. Marian/NLLB – šimtai MB ir `torch`), nes projekto priklausomybių rinkinys liktų tas pats, o rezultatas deterministinis.
**Apribojimai:** vertimas žodynu nėra pilnas vertimas – atpažįstami tik žinomi terminai. Jei atpažinta mažiau nei 3 terminai, prognozė žymima „apytiksle / nepatikima“ (visada rekomenduojama peržiūra). Ne lietuvių ir ne anglų kalbos nepalaikomos. Vertinimas mano paties sukurtais pavyzdžiais (autorius tas pats kaip žodyno, žymas parinkau pats, imtys mažos): 38 lietuviški pavyzdžiai – kategorijos sutapimas su laukiama 0.18 be vertimo → 0.82 su žodynu; 12 laisvos formos kontrolinių – 0.17 → 0.50. Tai rodo, kad žodynas padeda, bet neįrodo tokio paties tikslumo realiems naudotojų tekstams; sudėtingumo prognozės nepagerėjo.

Svarbu:
- **Modelio įvertis nėra tikimybė ir negarantuoja tikslumo.** Tai didžiausia `predict_proba` reikšmė, kalibracija netikrinta. „Rekomenduojama peržiūra“ rodoma, kai įvertis žemesnis už lauko slenkstį (kategorija 0.40, sudėtingumas 0.60, prioritetas 0.60; `REVIEW_THRESHOLDS` faile `app/services/prediction_service.py`). Slenksčiai parinkti pagal 112 testo įrašų su Claude žymomis, todėl yra orientaciniai.
- **Modelių kokybė** (testas, etalonas – Claude žymos, ne žmogaus): macro-F1 kategorija 0.49, sudėtingumas 0.61, prioritetas 0.59 (`models/training_report.md`). Prognozės yra rekomendacijos ir dažnai klysta, todėl jas turi peržiūrėti programuotojas. Prioriteto modelis neturi klasės `P0_critical` (per mažai pavyzdžių).
- **Jei modelių failų nėra arba jų nepavyksta įkelti** (pvz. kita scikit-learn versija), pranešimas vis tiek išsaugomas, o detalių puslapyje rodoma aiški priežastis ir komanda `python -m tools.train_models`. Svetainė veikia toliau.
- Modelių katalogas keičiamas per `MODELS_DIR` (`.env`). Modelių failai įkeliami tik iš šio vietinio katalogo (joblib naudoja pickle – nenaudokite svetimų failų).

Greita patikra: paleiskite `uvicorn app.main:app --reload`, atidarykite http://127.0.0.1:8000/report, pateikite klaidą (pvz. pavadinimas „Login button does nothing“, aprašymas anglų kalba), prisijunkite ir atidarykite `/dashboard` bei pranešimo detales.

## Saugumas ir apribojimai

- Pradinė versija skirta vietiniam akademiniam prototipui, o ne viešai diegiamai daugiavartotojų sistemai. Vieša forma priima pranešimus be paskyros, o visi vidiniai puslapiai apsaugoti programuotojo / koordinatoriaus prisijungimu (automatinis testas tikrina, kad kiekvienas ne viešas maršrutas be prisijungimo nukreipiamas į `/login`).
- Sesija saugoma pasirašytame (HMAC-SHA256) `HttpOnly`, `SameSite=Lax` slapuke be serverio pusės saugyklos: atsijungus slapukas ištrinamas naršyklėje, bet jei kas nors būtų jį pavogęs anksčiau, jis galiotų iki 8 val. pabaigos (arba kol nepakeistas slaptažodis / `SESSION_SECRET_KEY`).
- Nėra apsaugos nuo daugkartinių slaptažodžio spėjimų (užrakinimo / ribojimo); prieš viešą diegimą ją reikėtų pridėti. Prototipas skirtas vietiniam naudojimui.
- GitHub prieigos žetonas, jei reikalingas, pateikiamas per aplinkos kintamąjį GITHUB_TOKEN; jo negalima įrašyti į kodą, duomenų bazę, žurnalus ar Git istoriją.
- Sistema nekeičia GitHub Issues, jų etikečių ar priskirtų programuotojų.
- Kategorijos, prioritetas ir sudėtingumas yra rekomendacijos, o ne automatiškai patvirtinti faktai.

## Apmokyti modeliai repozitorijoje
`models/*.joblib` (modelio versija `20261110-143223`) ir `models/training_report.*` įkelti į Git, kad projektą būtų galima tęsti be ZIP failų. Failai priklauso nuo scikit-learn versijos; jei jų nepavyksta įkelti, permokykite: `python -m tools.train_models`. `joblib` naudoja pickle – nenaudokite svetimų modelių failų. SQLite duomenų bazė (`data/`) į Git **neįkeliama**.
