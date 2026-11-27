# Claude Code darbo užklausos

0–5D etapai baigti, PR #11 sujungtas į main. 6 etapas patvirtintas darbo vadovo aptarimu: viena organizacija, paskyros ir rolės (6A), kategorijų paskirstymas (6B), klaidų prisiėmimas (6C), išbaigtas dizainas (6D), apžvalgos (6E). Kodu šie etapai dar nepradėti. Toliau pateikta aktuali užklausos forma, o ankstesnės užklausos išsaugotos kaip istorija.

## Aktualus darbo principas

Dirbk tik pagal naują naudotojo užduotį. Perskaityk CLAUDE.md, ARCHITECTURE.md ir aktualią docs/IMPLEMENTATION_PLAN.md dalį. Patikrink git status, pradėk nuo naujausios main versijos ir naudok atskirą šaką. Nekeisk apmokytų modelių, vietinės DB, autentifikacijos ar svetainės be aiškaus reikalavimo. Mokamų API užklausų nevykdyk be leidimo. Testų rezultatus pateik tik faktiškai juos paleidęs. Jei užduotis tik dokumentacinė, keisk tik esamus dokumentus.

## Nauja artimiausia užklausa

6A: įdiegti SQLite users, saugią tik tester registraciją, prisijungimą kelioms paskyroms, esamo .env admin perėjimą, `reporter_user_id` naujiems prisijungusių testuotojų įrašams, tik savo pranešimų peržiūrą, rolėmis saugomus esamus maršrutus ir testus. Techniniai saugumo bei migracijos kriterijai išdėstyti `ARCHITECTURE.md` 13 skyriuje ir `docs/IMPLEMENTATION_PLAN.md` 6A punkte. Tai tik 6A, be kategorijų paskirstymo / komentarų / pilno dizaino (vėlesni etapai).

## Istorinės užklausos (nebevykdyti)

### Pirmoji užklausa Claude Code

Įklijuok šį tekstą Claude Code, atsidaręs šią repozitoriją. Architektūros specifikacijos jau yra repozitorijoje, todėl nekopijuok jų visų į pokalbį.

---

Dirbk tiesiogiai šiame projekte. Pirmiausia perskaityk `CLAUDE.md` ir tik aktualias `ARCHITECTURE.md` bei `docs/IMPLEMENTATION_PLAN.md` dalis. Patikrink `git status --short` ir išsaugok visus esamus pakeitimus.

Įgyvendink tik **0 etapą** iš `docs/IMPLEMENTATION_PLAN.md`: minimalų FastAPI karkasą, paleidimo / sveikatos patikrinimo maršrutą, minimalų Jinja2 puslapį ir testą(-us), kad būtų galima patikrinti priėmimo kriterijus. Kai kurie konfigūracijos failai jau sukurti – juos peržiūrėk ir papildyk tik jei būtina, neperrašyk be reikalo.

Taupydamas laiką ir tokenus:
- nesukurk visos sistemos vienu kartu ir neįgyvendink 1–5 etapų;
- nekurk nenaudojamų failų ar abstrakcijų;
- nepridėk naujų priklausomybių, jei esamų pakanka;
- neskaityk iš naujo visos repozitorijos po kiekvieno pakeitimo;
- nepaleisk gyvų GitHub API ar kitų interneto užklausų testuose;
- nesukurk fiktyvių issues ar dirbtinių mokymo rezultatų;
- nedaryk commit ar push.

Prieš pakeitimus pateik trumpą planą, tada įgyvendink. Paleisk tik svarbius etapo testus ir pabaigoje trumpai nurodyk, kurie failai pakeisti, kokios komandos tikrai paleistos, testų rezultatus ir vieną kitą etapą. Jei testai nepraeina, pataisyk priežastį. Neklausk nereikalingų klausimų; priimk paprastus, architektūrą atitinkančius techninius sprendimus.

---

## Kitos užklausos po sėkmingo 0 etapo

Kiekvienam etapui atskira užklausa – taip lengviau tikrinti rezultatus ir išvengti didelės, nepatikrinamos vienkartinės generacijos.

- **1 etapas:** „Įgyvendink tik 1 etapą iš docs/IMPLEMENTATION_PLAN.md. Laikykis CLAUDE.md ir ARCHITECTURE.md. Paleisk etapui skirtus testus, taisyk klaidas, neužsiimk kitais etapais.“
- **2 etapas:** „Įgyvendink tik 2 etapą iš docs/IMPLEMENTATION_PLAN.md. Laikykis CLAUDE.md ir ARCHITECTURE.md. Paleisk etapui skirtus testus, taisyk klaidas, neužsiimk kitais etapais.“
- **3 etapas:** „Įgyvendink tik 3 etapą iš docs/IMPLEMENTATION_PLAN.md. Laikykis CLAUDE.md, ARCHITECTURE.md ir docs/EVALUATION_PLAN.md. Paleisk etapui skirtus testus; neleisk duomenų nutekėjimo.“
- **4 etapas:** „Įgyvendink tik 4 etapą iš docs/IMPLEMENTATION_PLAN.md. Palygink modelį su baseline, bet nerašyk neišmatuotų metrikų. Paleisk testus.“
- **5 etapas:** „Atlik tik 5 etapo užbaigimo patikrą. Nekeisk architektūros ir nepridėk funkcijų be reikalo. Paleisk visus testus, peržiūrėk saugumą ir atnaujink README pagal faktinį kodą.“
