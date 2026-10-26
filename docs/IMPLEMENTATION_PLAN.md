# Įgyvendinimo planas

Laikytis etapų eilės. Kiekvieno etapo pabaigoje paleisti susijusius testus ir trumpai aprašyti rezultatą. Claude Code sesijai nurodyti vieną etapą, o ne visą planą. Jei darbą reikia tęsti kitoje sesijoje, perduoti tik šį planą, CLAUDE.md ir paskutinės sesijos santrauką.

## 0 etapas – minimalus projekto pagrindas
**Tikslas:** pakartojama aplinka, maža priklausomybių aibė, paleidžiamas FastAPI karkasas.

Darbai:
- pridėti `requirements.txt`, `.gitignore`, `.env.example`;
- pridėti `app/main.py` su FastAPI programos kūrimo funkcija ir paprastu sveikatos patikrinimo maršrutu;
- pridėti minimalų Jinja2 pagrindinį HTML puslapį ir CSS, jei tai reikalinga jau šiame etape;
- aprašyti lokalią venv instaliaciją README;
- pridėti vieną paleidimo ir vieną sveikatos patikrinimo testą.

Priėmimas: priklausomybes galima įdiegti švarioje venv; `uvicorn app.main:app` paleidžia serverį; health maršrutas ir pytest veikia.

## 1 etapas – SQLite ir GitHub importas
**Tikslas:** importuoti viešos repozitorijos issues, išvengiant dublikatų.

Darbai:
- sukurti DB inicializaciją ir `issues` schemą pagal ARCHITECTURE.md;
- GitHub klientas priima tik normalizuotą `owner/repo`, naudoja HTTPS GitHub API, paginaciją ir ribotą importą;
- atpažinti pull request ir neįtraukti jų;
- upsert metu atnaujinti šaltinio laukus, bet išsaugoti žmogaus anotacijas;
- UI leidžia įvesti repo, paleisti importą, matyti klaidas ir importuotų issue sąrašą;
- naudoti mock'us HTTP testams; nedaryti gyvų interneto užklausų automatinio testavimo metu.

Priėmimas: testai patvirtina puslapiavimą, klaidų atvejus, PR filtro veikimą, idempotentiškumą ir anotacijų išsaugojimą. Savavališki hostai atmetami.

## 2 etapas – rankinis žymėjimas
**Tikslas:** sukurti patikimą mokymo duomenų pagrindą.

Darbai:
- issue detalių puslapyje leidžiama atskirai pasirinkti category, complexity ir priority;
- nežinomos žymos lieka NULL, jokio automatinio užpildymo iš spėlionių;
- išsaugoti anotavimo šaltinį ir laiką;
- pateikti žymų reikšmes iš bendros konfigūracijos / enumų, ne dubliuoti tarp šablonų ir servisų;
- rodyti, kiek anotacijų yra kiekvienam laukui ir kiekvienai klasei.

Priėmimas: forma ir POST endpointas validuoja leistinas reikšmes; galima išsaugoti ir vėl atverti žymas; vieno lauko redagavimas netrina kitų laukų.

## 3 etapas – mokymas ir prognozavimas
**Tikslas:** sukurti patikrinamą ML bazinį modelį.

Darbai:
- sujungti title ir body viename deterministiniame tekste;
- sukurti atskirą scikit-learn Pipeline kiekvienam iš trijų laukų: TF-IDF + LogisticRegression;
- naudoti tik atitinkamo lauko ne NULL, žmogaus patvirtintas žymas;
- validuoti klasių ir įrašų pakankamumą prieš mokymą; jei nepakanka, grąžinti struktūruotą `insufficient_data` būseną;
- fiksuoti random seed ir modelio versijos metaduomenis;
- saugoti prognozes atskirai nuo anotacijų; nerodyti nevaliduotos taisyklės kaip ML modelio rezultato;
- numatyti saugų nepatikimo HTML/Markdown turinio atvaizdavimą šablonuose.

Priėmimas: vienetiniai testai tikrina paruošimą, mokymo sąlygas, prognozės formatą, išsaugotų anotacijų apsaugą ir deterministinį rezultatų apdorojimą. Jokio modelio mokymo iš testų.

## 4 etapas – vertinimas ir vartotojo sąsajos užbaigimas
**Tikslas:** pateikti rezultatą, kurį galima pagrįsti bakalauro darbe.

Darbai:
- sukurti atskirą vertinimo srautą, kuriame užfiksuojami split nustatymai;
- palyginti majority-class baseline su TF-IDF + LogisticRegression tuo pačiu split;
- pateikti per lauką duomenų kiekį, class distribution, precision, recall, F1, macro-F1 ir confusion matrix, kai duomenų kiekis leidžia;
- UI pridėti anotacijų/prognozių būsenas, vertinimo puslapį, klaidų pranešimus ir nuorodas į šaltinį;
- README aprašyti paleidimą, GitHub tokeną (pasirinktinį), žymėjimą, ribas ir vertinimą.

Priėmimas: vertinimo testai patvirtina, kad mokymas/vertinimas nesimaišo; per mažo dataset'o atveju rodomas įspėjimas, o ne išgalvotos metrikos.

## 5 etapas – užbaigimas
**Tikslas:** kokybinė patikra, ne naujos funkcijos.

Darbai:
- paleisti visą testų rinkinį ir pataisyti realius defektus;
- patikrinti švarios instaliacijos instrukcijas;
- patikrinti logus/slaptažodžių saugumą ir tai, kad jokie duomenys, tokenai, modeliai ar DB netyčia necommittinami;
- atnaujinti žinomų apribojimų sąrašą;
- nerašyti išgalvotų rezultatų ar pildyti tyrimo duomenų sintetiniu turiniu, kurį pristatytum kaip realų.

Priėmimas: visi automatizuoti testai praeina; nėra nepaaiškintų klaidų; README ir vertinimo metodika atitinka faktinį kodą.

## Bendros taisyklės
- Vienu metu įgyvendinti tik nurodytą etapą.
- Jei etapo apimtis tampa per didelė, įgyvendinti jo pirmą end-to-end vertę ir papildyti etapų kontrolinį sąrašą; nekurti alternatyvios architektūros.
- Nepakeisti viešos GitHub issue būsenų ar metaduomenų.
- Nenaudoti tikrų GitHub prisijungimų automatiniuose testuose.
- Kiekviename atsakyme išskirti testų, kurie tikrai paleisti, rezultatus.
