# Pirmoji užklausa Claude Code

Įklijuok šį tekstą Claude Code, atsidaręs šią repozitoriją. Architektūros specifikacijos jau yra repozitorijoje, todėl nekopijuok jų visų į pokalbį.

---

Dirbk tiesiogiai šiame projekte. Pirmiausia perskaityk `CLAUDE.md` ir tik aktualias `ARCHITECTURE.md bei `docs/IMPLEMENTATION_PLAN.md` dalis. Patikrink `git status --short` ir išsaugok visus esamus pakeitimus.

Įgyvendink tik **0 etapą** iš `docs/IMPLEMENTATION_PLAN.md`: minimalų FastAPI karkasą, paleidimo / sveikatos patikrinimo maršrutą, minimalų Jinja2 puslapį ir testą(-us), kad būtų galima patikrinti priėmimo kriterijus. Kai kurie konfigūracijos failai jau sukurti – juos peržiūrėk ir papildyk tik jei būtina, neperrašyk be reikalaus.

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
