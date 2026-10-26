# Claude Code taisyklės

## Projekto tikslas
Įgyvendinti šioje repozitorijoje aprašytą bakalauro darbo prototipą. Reikalavimų šaltiniai pagal prioritetą:
1. `ARCHITECTURE.md` – privaloma architektūra ir duomenų ribos.
2. `docs/IMPLEMENTATION_PLAN.md` – įgyvendinimo etapai ir jų priėmimo kriterijai.
3. `docs/EVALUATION_PLAN.md` – mokslinis vertinimas.
4. `docs/DATA_LABELING.md` – anotavimo susitarimai.
5. `README.md` – paleidimo ir naudotojo instrukcijos.

Jei dokumentai prieštarauja vienas kitam, nekurk naujų prielaidų: pažymėk prieštaravimą, pasiūlyk mažiausią sprendimą ir atnaujink atitinkamą dokumentą tik jei dabartinė užduotis tai leidžia.

## Taupūs darbo principai
- Prieš keičiant kodą vykdyk `git status --short` ir patikrink tik su dabartine užduotimi susijusius failus.
- Kiekvienam prašymui įgyvendink **tik vieną aiškiai nurodytą etapą**. Neįgyvendink visos sistemos vienu kartu.
- Neskaitinėk visų failų iš naujo, jei reikiamą kontekstą galima gauti iš README, šio failo, plano ir konkrečių modulių.
- Prieš kurdamas kodą, trumpai pateik 3–6 veiksmų planą. Po to iškart vykdyk darbus; neklausk patvirtinimo dėl įprastų techninių detalių.
- Pirmiausia naudok esamas priklausomybes. Naują priklausomybę pridėk tik jei ji būtina ir paaiškink, kodėl standartinės bibliotekos ar jau įdiegtos priemonės neužtenka.
- Nepridėk React/Vue, Node, Docker, ORM, Redis, task queue, LLM API ar mikroservisų, nebent naudotojas aiškiai pakeistų reikalavimus.
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
