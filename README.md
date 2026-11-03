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

Pilnas pagrindimas ir komponentų sąveika aprašyti [ARCHITECTURE.md](ARCHITECTURE.md). Claude Code veikimo taisyklės pateiktos [CLAUDE.md](CLAUDE.md), pirmoji ir vėlesnės užklausos – [docs/CLAUDE_PROMPT.md](docs/CLAUDE_PROMPT.md), darbų etapai – [docs/IMPLEMENTATION_PLAN.md](docs/IMPLEMENTATION_PLAN.md), anotavimo gairės – [docs/DATA_LABELING.md](docs/DATA_LABELING.md), o vertinimo metodika – [docs/EVALUATION_PLAN.md](docs/EVALUATION_PLAN.md).

## Duomenų kokybės principas

GitHub etiketės nėra automatiškai laikomos teisingomis kategorijos, prioriteto ar sudėtingumo žymomis. Naudotojas turi galėti patvirtinti žymas sistemoje. Kiekvienam laukui modelis mokomas tik tada, kai duomenų kiekis ir klasių pasiskirstymas atitinka iš anksto aprašytas sąlygas. Kitu atveju sistema rodo, kad duomenų nepakanka, arba atskirai pažymėtą taisyklių pasiūlymą. Nežymėtos ir sintetiniu būdu sukurtos demonstracinės eilutės negali būti pateikiamos kaip realaus modelio vertinimo duomenys.

## Įgyvendinimo būsena

Įgyvendinti 0–3 etapai:

- **0 etapas:** FastAPI karkasas, `GET /health`, pagrindinis puslapis `GET /`.
- **1 etapas:** SQLite schema (`bug_reports`, `github_issues`) ir viešų GitHub issues importas per `/import` (`owner/repo` arba `https://github.com/owner/repo`, kiekis iki `GITHUB_IMPORT_LIMIT`). Pull request įrašai praleidžiami, pakartotinis importas nedubliuoja įrašų ir neperrašo žmogaus patvirtintų žymų.
- **2 etapas:** vieša klaidos pateikimo forma `/report` be paskyros (pavadinimas iki 200, aprašymas iki 10000 simbolių, validacija serverio pusėje); įrašas išsaugomas su būsena `new`, naudotojui rodomas tik patvirtinimas.
- **3 etapas:** programuotojo prisijungimas (`/login`, `/logout`) ir vidinė aplinka: klaidų sąrašas `/dashboard` su paieška ir filtrais, detalių puslapis `/dashboard/reports/{id}`, būsenų keitimas `new` → `in_progress` → `resolved` (išspręsti įrašai lieka istorijoje, juos galima atidaryti iš naujo). `/import` taip pat pasiekiamas tik prisijungus.

Duomenų bazė kuriama automatiškai (`DATABASE_PATH`, pagal nutylėjimą `data/bakalauras.sqlite3`; failas nėra committinamas). Kategorija, prioritetas ir sudėtingumas kol kas rodomi kaip „Dar nenustatyta“ – rankinis žymėjimas ir automatinis klasifikavimas bus 4–5 etapuose. Likę etapai kuriami pagal docs/IMPLEMENTATION_PLAN.md.

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
- **GitHub importas** (`/import`) ir **Atsijungti** – viršutinėje navigacijoje.
- Sesija galioja 8 valandas. Visi būseną keičiantys veiksmai (būsenos keitimas, importas, atsijungimas) apsaugoti CSRF žetonu.

## Saugumas ir apribojimai

- Pradinė versija skirta vietiniam akademiniam prototipui, o ne viešai diegiamai daugiavartotojų sistemai. Vieša forma priima pranešimus be paskyros, o visi vidiniai puslapiai apsaugoti programuotojo / koordinatoriaus prisijungimu (automatinis testas tikrina, kad kiekvienas ne viešas maršrutas be prisijungimo nukreipiamas į `/login`).
- Sesija saugoma pasirašytame (HMAC-SHA256) `HttpOnly`, `SameSite=Lax` slapuke be serverio pusės saugyklos: atsijungus slapukas ištrinamas naršyklėje, bet jei kas nors būtų jį pavogęs anksčiau, jis galiotų iki 8 val. pabaigos (arba kol nepakeistas slaptažodis / `SESSION_SECRET_KEY`).
- Nėra apsaugos nuo daugkartinių slaptažodžio spėjimų (užrakinimo / ribojimo); prieš viešą diegimą ją reikėtų pridėti. Prototipas skirtas vietiniam naudojimui.
- GitHub prieigos žetonas, jei reikalingas, pateikiamas per aplinkos kintamąjį GITHUB_TOKEN; jo negalima įrašyti į kodą, duomenų bazę, žurnalus ar Git istoriją.
- Sistema nekeičia GitHub Issues, jų etikečių ar priskirtų programuotojų.
- Kategorijos, prioritetas ir sudėtingumas yra rekomendacijos, o ne automatiškai patvirtinti faktai.
