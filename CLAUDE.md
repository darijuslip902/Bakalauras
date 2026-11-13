# Claude Code taisyklės

## Dabartinė būklė (2026-11-13, po 5D)

0–5D etapai baigti, PR #11 sujungtas į main. Modelių versija `20261113-125330`. 6 etapas nepradėtas: laukiama darbo vadovo pastabų; statistikos puslapis nėra patvirtintas reikalavimas. P0 paliekamas, nors jo atpažinimas silpnas.

- 40 024 importuoti GitHub įrašai; 23 884 sėkmingos DI anotacijos (19 412 tinkamų, 4 472 netinkamų).
- 18 267 mokymo ir validacijos pavyzdžiai; 1 120 atrinktų testo įrašų, iš jų 901 tinkamas (visi 901 su DI etalonu); 30 pilotinių įrašų.
- 243 artimi testo dublikatai pašalinti iš mokymo. Bendra DI žymėjimo kaina 4,5948 USD.
- Trys apmokyti modeliai ir jų ataskaitos saugomi GitHub; SQLite DB, jos kopijos, .env ir .venv – tik lokaliai.
- Testo accuracy / macro-F1: kategorija 64,26 % / 62,22 %; sudėtingumas 69,70 % / 69,14 %; prioritetas 65,93 % / 48,20 %. P0 F1 = 0. Metrikos rodo atitikimą Claude žymoms, ne nepriklausomai žmogaus patvirtintai tiesai. Ankstesnio ir naujo modelio metrikos iš skirtingų testų nėra tiesiogiai palyginamos.

## Projekto tikslas
Įgyvendinti šioje repozitorijoje aprašytą bakalauro darbo prototipą. Reikalavimų šaltiniai pagal prioritetą:
1. `ARCHITECTURE.md` – privaloma architektūra ir duomenų ribos.
2. `docs/IMPLEMENTATION_PLAN.md` – įgyvendinimo etapai ir jų priėmimo kriterijai.
3. `docs/EVALUATION_PLAN.md` – mokslinis vertinimas.
4. `docs/DATA_LABELING.md` – anotavimo susitarimai.
5. `README.md` – paleidimo ir naudotojo instrukcijos.

Jei dokumentai prieštarauja vienas kitam, nekurk naujų prielaidų: pažymėk prieštaravimą, pasiūlyk mažiausią sprendimą ir atnaujink atitinkamą dokumentą tik jei dabartinė užduotis tai leidžia.

## Įgyvendintas produkto funkcionalumas
- Vieša forma leidžia klientui / testuotojui be paskyros pateikti klaidos pavadinimą ir aprašymą.
- Programuotojas / koordinatorius prisijungia prie vidinės aplinkos, mato visus pranešimus, filtruoja / ieško, keičia būsenas new, in_progress, resolved ir peržiūri išspręstų klaidų istoriją.
- Naujas pranešimas automatiškai klasifikuojamas tik jei paruoštas tinkamas modelis. Jei duomenų nepakanka, pranešimas vis tiek išsaugomas, o prognozės trūkumas aiškiai rodomas.
- Prognozė ir žmogaus pataisyta / patvirtinta žyma visada saugomos atskirai.
- Vieši GitHub Issues naudojami atskirai mokymo duomenims; integracija nekeičia GitHub pusėje esančių issues.
- Klientui nereikia paskyros ir jis negali peržiūrėti kitų pranešimų. Atsakingo programuotojo automatinis parinkimas neįtrauktas.
- Įgyvendinimo etapus skaityti iš docs/IMPLEMENTATION_PLAN.md. 0–5D baigti; 6 etapą pradėti tik gavus naują naudotojo užduotį. Viena vidinė paskyra, atskirų testuotojų paskyrų nėra. Modelių statistikos puslapis neprivalomas. Nekeisti modelių, DB ar funkcionalumo atliekant vien dokumentacijos darbus.

## Taupūs darbo principai
- Prieš keičiant kodą vykdyk `git status --short` ir patikrink tik su dabartine užduotimi susijusius failus.
- Kiekvienam prašymui įgyvendink **tik vieną aiškiai nurodytą etapą**. Neįgyvendink visos sistemos vienu kartu.
- Neskaitinėk visų failų iš naujo, jei reikiamą kontekstą galima gauti iš README, šio failo, plano ir konkrečių modulių.
- Prieš kurdamas kodą, trumpai pateik 3–6 veiksmų planą. Po to iškart vykdyk darbus; neklausk patvirtinimo dėl įprastų techninių detalių.
- Pirmiausia naudok esamas priklausomybes. Naują priklausomybę pridėk tik jei ji būtina ir paaiškink, kodėl standartinės bibliotekos ar jau įdiegtos priemonės neužtenka.
- Nepridėk React/Vue, Node, Docker, ORM, Redis, task queue, LLM API ar mikroservisų, nebent naudotojas aiškiai pakeistų reikalavimus.
- Išimtis (naudotojo ir darbo vadovo sprendimas, 5A etapas): Anthropic Claude API naudojamas tik vienkartiniam mokymo duomenų žymėjimui per `tools/` CLI (`app/ml/`). Svetainė (`app/routes`, `app/services`) DI API neimportuoja ir nekviečia; jokių mokymo ar mokamo žymėjimo mygtukų svetainėje. Mokamas užklausas vykdyti tik naudotojui aiškiai leidus; testuose API visada imituojamas.
- Nekurk iš anksto tuščių abstrakcijų ar katalogų, kurių dar nepasiekė įgyvendinimo etapas.
- Nekeisk failų, nesusijusių su dabartiniu etapu. Neperrašinėk viso failo mažam pakeitimui.
- Nenaudok interneto prieigos testuose; GitHub API atskirk nuo verslo logikos ir testuose ją mock'ink.
- Neįrašyk fiktyvių rezultatų, neegzistuojančių API atsakymų ar išgalvotų mokslinių metrikų.

## Kokybė ir saugumas
- Prieš keisdamas failą patikrink dabartinę jo versiją ir išsaugok naudotojo pakeitimus.
- Naudok tipų anotacijas ten, kur jos padeda suprantamumui, prasmingus pavadinimus ir trumpas funkcijas.
- SQL užklausos privalo būti parametrizuotos.
- GitHub integracija yra tik skaitymo. Nepridėk issue kūrimo, žymų rašymo ar assignee keitimo.
- Priimk tik normalizuotą viešos GitHub repozitorijos identifikatorių; neleisk savavališko URL fetch, kad būtų išvengta SSRF.
- Tokenai skaitomi tik iš aplinkos, niekada jų nerodyk loguose ar klaidų pranešimuose.
- Modelio duomenų split turi įvykti prieš Pipeline fit. Testų žymos negali būti panaudotos nei požymių žodynui kurti, nei hiperparametrams parinkti.
- Nežymėtos eilutės negali būti naudojamos prižiūrimo modelio mokymui. Jei duomenų mažai, aiškiai grąžink `insufficient_data`.
- Nevadink LogisticRegression `confidence` kalibruota tikimybe nepatikrinęs kalibravimo. Išsaugok prognozės metodą ir modelio versiją.
- Jei testas sugenda, išsiaiškink ir taisyk priežastį; nešalink testo ir nemažink jo kriterijų vien tam, kad praeitų.
- Nedaryk plačios refaktorizacijos be aiškios naudos dabartinei užduočiai.

## Darbo pabaigos atsakymas
Pateik tik:
1. kas įgyvendinta;
2. kokie failai pakeisti;
3. kokios testų komandos paleistos ir rezultatas;
4. tikros likusios problemos / kitas etapas.
Neskelbk, kad testai praėjo, jei jų nepaleidai. Nedubliuok ilgo projekto aprašymo.
