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

Įgyvendinti 0–4 ir 5A etapai:

- **0 etapas:** FastAPI karkasas, `GET /health`, pagrindinis puslapis `GET /`.
- **1 etapas:** SQLite schema (`bug_reports`, `github_issues`) ir viešų GitHub issues importas per `/import` (`owner/repo` arba `https://github.com/owner/repo`, kiekis iki `GITHUB_IMPORT_LIMIT`). Pull request įrašai praleidžiami, pakartotinis importas nedubliuoja įrašų ir neperrašo žmogaus patvirtintų žymų.
- **2 etapas:** vieša klaidos pateikimo forma `/report` be paskyros (pavadinimas iki 200, aprašymas iki 10000 simbolių, validacija serverio pusėje); įrašas išsaugomas su būsena `new`, naudotojui rodomas tik patvirtinimas.
- **3 etapas:** programuotojo prisijungimas (`/login`, `/logout`) ir vidinė aplinka: klaidų sąrašas `/dashboard` su paieška ir filtrais, detalių puslapis `/dashboard/reports/{id}`, būsenų keitimas `new` → `in_progress` → `resolved` (išspręsti įrašai lieka istorijoje, juos galima atidaryti iš naujo). `/import` taip pat pasiekiamas tik prisijungus.
- **4 etapas:** mokymo duomenų (importuotų GitHub issues) peržiūra ir rankinis žymėjimas `/dashboard/training-data`: kategorija, sudėtingumas, prioritetas ir tinkamumas mokymui, žymėjimo eigos statistika, „Kitas nepažymėtas“.
- **5A etapas:** mokymo duomenų paruošimo ir ML mokymo įrankiai komandinėje eilutėje (`tools/`): masinis importas, kokybės patikra, žmogaus testavimo rinkinys, DI žymėjimas su biudžeto kontrole, trijų modelių mokymas ir vertinimas. Svetainė jų nenaudoja; realus žymėjimas ir mokymas – 5B etape.

Duomenų bazė kuriama automatiškai (`DATABASE_PATH`, pagal nutylėjimą `data/bakalauras.sqlite3`; failas nėra committinamas). Klientų pranešimų (`/dashboard`) kategorija, prioritetas ir sudėtingumas kol kas rodomi kaip „Dar nenustatyta“ – automatinis klasifikavimas bus 5 etape. Senesnė DB paleidimo metu automatiškai papildoma nauju stulpeliu `github_issues.training_suitability` (esami įrašai ir žymos išlieka). Likę etapai kuriami pagal docs/IMPLEMENTATION_PLAN.md.

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

## Mokymo duomenų paruošimas ir modelių mokymas (5A)

Šie įrankiai paleidžiami komandinėje eilutėje, ne svetainėje. Visos komandos – **Windows CMD**, projekto kataloge, aktyvavus aplinką (`.venv\Scripts\activate.bat`).

**Kodėl DI žymėjimas.** Rankiniu būdu pažymėti 2 000–3 000 issues per daug laiko, todėl (darbo vadovui pritarus) žymas vieną kartą sugeneruoja pigiausias dabartinis Claude modelis `claude-haiku-5-5`. GitHub etiketės nėra patikimos žymos, o DI žymos taip pat gali klysti – todėl jų kokybė tikrinama atskiru, žmogaus pažymėtu testavimo rinkiniu, o žmogaus žyma visada turi pirmenybę.

**1. Importuoti issues iš kelių projektų** (rekomenduojama filtruoti klaidas etikete, pvz. `bug`; vienai repozitorijai iki 1000):

```bat
python -m tools.import_issues --repo pallets/flask --repo psf/requests --limit 500 --label bug
```

Neautentifikuotai GitHub leidžia 60 užklausų per valandą (100 issues vienai užklausai). Didesniam kiekiui `.env` faile nustatykite `GITHUB_TOKEN`.

**2. Patikrinti duomenų kokybę** (kiek tinka, kiek per trumpų, kiek dublikatų, žymėjimo eiga ir DI išlaidos):

```bat
python -m tools.check_data
```

**3. Atrinkti žmogaus testavimo rinkinį** (pvz. 200 atsitiktinių įrašų; juos pažymite patys svetainėje „Mokymo duomenys“ – „Kitas nepažymėtas“ pasiūlo juos pirmus):

```bat
python -m tools.select_test_set --size 200
```

**4. DI žymėjimas.** `.env` faile nustatykite `ANTHROPIC_API_KEY` (raktą sukuria console.anthropic.com; Claude Pro prenumerata nėra API kreditas) ir `AI_TOTAL_BUDGET_USD` (bendras limitas, numatyta 10 USD). Pirmiausia visada **dry-run** – API nekviečiamas, tik parodoma, kiek įrašų ir kiek kainuotų:

```bat
python -m tools.ai_label --limit 3000
```

Tikras (mokamas) žymėjimas – tik su `--execute`; programa dar paklaus patvirtinimo („taip“). `--max-cost-usd` – šio paleidimo išlaidų riba:

```bat
python -m tools.ai_label --limit 50 --max-cost-usd 0.20 --execute
```

Saugikliai: prieš kiekvieną užklausą tikrinama blogiausio atvejo kaina ir abu limitai; faktinė kaina pagal API `usage` saugoma DB; pakartotinis paleidimas tęsia nuo nepažymėtų (jau pažymėti neapmokami dar kartą); netinkamas atsakymas kartojamas daugiausia 1 kartą; po API klaidos paleidimas sustoja. Apytikslė kaina 2 500 issues (vidutiniškai ~2 000 simbolių aprašymas): `claude-haiku-5-5` ~0,6 USD (blogiausiu atveju ~1,9 USD); `--model claude-sonnet-5-5` ~12 USD (blogiausiu ~38 USD).

**5. Modelių mokymas ir vertinimas:**

```bat
python -m tools.train_models
```

Sukuriami `models\category_label.joblib`, `models\complexity_label.joblib`, `models\priority_label.joblib` ir `models\training_report.json` (duomenų kiekiai, klasių pasiskirstymas, seed, precision / recall / F1 / macro-F1 / confusion matrix modeliui ir daugumos klasės baseline: DI validacijos daliai, žmogaus testavimo rinkiniui ir DI bei žmogaus žymų sutapimui). Jei duomenų per mažai, laukas pažymimas `insufficient_data` ir modelis nesukuriamas. Modelių failai ir DB į GitHub nekeliami.

## Saugumas ir apribojimai

- Pradinė versija skirta vietiniam akademiniam prototipui, o ne viešai diegiamai daugiavartotojų sistemai. Vieša forma priima pranešimus be paskyros, o visi vidiniai puslapiai apsaugoti programuotojo / koordinatoriaus prisijungimu (automatinis testas tikrina, kad kiekvienas ne viešas maršrutas be prisijungimo nukreipiamas į `/login`).
- Sesija saugoma pasirašytame (HMAC-SHA256) `HttpOnly`, `SameSite=Lax` slapuke be serverio pusės saugyklos: atsijungus slapukas ištrinamas naršyklėje, bet jei kas nors būtų jį pavogęs anksčiau, jis galiotų iki 8 val. pabaigos (arba kol nepakeistas slaptažodis / `SESSION_SECRET_KEY`).
- Nėra apsaugos nuo daugkartinių slaptažodžio spėjimų (užrakinimo / ribojimo); prieš viešą diegimą ją reikėtų pridėti. Prototipas skirtas vietiniam naudojimui.
- GitHub prieigos žetonas, jei reikalingas, pateikiamas per aplinkos kintamąjį GITHUB_TOKEN; jo negalima įrašyti į kodą, duomenų bazę, žurnalus ar Git istoriją.
- Sistema nekeičia GitHub Issues, jų etikečių ar priskirtų programuotojų.
- Kategorijos, prioritetas ir sudėtingumas yra rekomendacijos, o ne automatiškai patvirtinti faktai.
