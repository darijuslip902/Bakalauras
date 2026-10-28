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

Įgyvendintas 0 etapas: FastAPI karkasas, `GET /health` ir minimalus Jinja2 pagrindinis puslapis `GET /`. Likę etapai kuriami pagal docs/IMPLEMENTATION_PLAN.md.

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

Testai:

```bash
python -m pytest
```

## Saugumas ir apribojimai

- Pradinė versija skirta vietiniam akademiniam prototipui, o ne viešai diegiamai daugiavartotojų sistemai. Vieša forma priima pranešimus be paskyros, tačiau visi pranešimų sąrašo ir valdymo puslapiai turi būti apsaugoti programuotojo / koordinatoriaus prisijungimu.
- GitHub prieigos žetonas, jei reikalingas, pateikiamas per aplinkos kintamąjį GITHUB_TOKEN; jo negalima įrašyti į kodą, duomenų bazę, žurnalus ar Git istoriją.
- Sistema nekeičia GitHub Issues, jų etikečių ar priskirtų programuotojų.
- Kategorijos, prioritetas ir sudėtingumas yra rekomendacijos, o ne automatiškai patvirtinti faktai.
