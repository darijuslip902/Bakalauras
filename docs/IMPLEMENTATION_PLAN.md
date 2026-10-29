# Įgyvendinimo planas

Laikytis etapų eilės. Vienoje Claude Code sesijoje įgyvendinti tik vieną etapą, paleisti su juo susijusius testus ir užrašyti faktinius rezultatus. Neperrašyti jau veikiančio 0 etapo karkaso.

## 0 etapas – minimalus projekto pagrindas (ATLIKTA)
**Tikslas:** pakartojama aplinka ir paleidžiamas FastAPI karkasas.

Atlikta: FastAPI programos kūrimo funkcija create_app(), GET /health, Jinja2 pagrindinis puslapis GET /, CSS, pytest konfigūracija ir pradiniai testai.

## 1 etapas – SQLite ir GitHub importas
**Tikslas:** paruošti duomenų saugyklą ir importuoti viešus GitHub issues mokymo duomenims.

Darbai:
- sukurti SQLite inicializaciją ir atskirti lenteles sistemos pranešimams (bug_reports) bei iš GitHub importuotiems mokymo įrašams (github_issues);
- GitHub klientas priima tik normalizuotą owner/repo, naudoja HTTPS, paginaciją ir ribotą importą;
- atpažinti pull request ir jų neimportuoti;
- pakartotinis importas nedubliuoja įrašų ir neperrašo žmogaus patvirtintų žymų;
- UI leidžia įvesti repozitoriją, paleisti importą, matyti rezultatą ir klaidų pranešimus;
- automatiniuose testuose naudoti mock'us, ne gyvą GitHub tinklą.

Priėmimas: testai tikrina paginaciją, HTTP klaidas, PR filtrą, dublikatų prevenciją, anotacijų išsaugojimą ir savavališkų hostų atmetimą.

## 2 etapas – vieša klaidos pateikimo forma
**Tikslas:** klientas / testuotojas gali pateikti klaidą be paskyros.

Darbai:
- sukurti viešą HTML formą su pavadinimu ir išsamiu aprašymu;
- validuoti privalomus laukus ir teksto ilgius serverio pusėje;
- išsaugoti pateiktą įrašą bug_reports lentelėje, priskirti new būseną ir sukūrimo laiką;
- parodyti pateikimo patvirtinimą, bet neatskleisti kitų įrašų;
- viešai nerodyti vidinio sąrašo, prognozių ar anotavimo veiksmų.

Priėmimas: teisingas įrašas išsaugomas, neteisinga forma atmetama su aiškiu pranešimu, o po pateikimo klientas negali pasiekti kitų pranešimų.

## 3 etapas – programuotojo prisijungimas ir klaidų valdymo aplinka
**Tikslas:** programuotojas / koordinatorius gali saugiai tvarkyti pateiktas klaidas.

Darbai:
- sukurti vieną administratoriaus / koordinatoriaus prisijungimą, tinkamą vietiniam bakalauro prototipui; slaptažodį imti iš aplinkos kintamojo arba tikrinti saugų maišą, niekada nelaikyti atviro teksto kode;
- apsaugoti visus vidinius sąrašo, detalių, būsenų keitimo, anotavimo, mokymo ir vertinimo maršrutus;
- sukurti vidinį klaidų sąrašą, detalių puslapį, paiešką ir filtrus pagal būseną, kategoriją, prioritetą ir sudėtingumą;
- leisti keisti būseną new, in_progress, resolved; išspręsti įrašai lieka istorijoje;
- rodyti aiškias būsenas ir klaidų pranešimus.

Priėmimas: neautentifikuoti prašymai į vidinius maršrutus nukreipiami į prisijungimą arba atmetami; prisijungęs naudotojas gali peržiūrėti ir keisti būsenas; išspręsti įrašai nedingsta iš istorijos. Testuoti autentifikavimą ir leidimus.

## 4 etapas – rankinis GitHub įrašų žymėjimas
**Tikslas:** sukurti patikimą mokymo duomenų pagrindą.

Darbai:
- GitHub issue detalių puslapyje atskirai pasirinkti kategoriją, sudėtingumą ir prioritetą;
- nežinomas žymas palikti NULL;
- saugoti anotavimo šaltinį ir laiką;
- rodyti anotacijų skaičių kiekvienam laukui ir klasei;
- neleisti automatiškai laikyti GitHub etikečių teisingomis žymomis be žmogaus patvirtinimo.

Priėmimas: galima išsaugoti ir vėl atverti žymas; vieno lauko redagavimas netrina kitų; sistemos klientų pateikti pranešimai netampa mokymo duomenimis be patvirtinimo.

## 5 etapas – mokymas ir automatinis klasifikavimas
**Tikslas:** sistema automatiškai pasiūlo kategoriją, prioritetą ir, jei duomenų pakanka, sudėtingumą.

Darbai:
- sujungti pavadinimą ir aprašymą į deterministinį tekstą;
- sukurti atskirą scikit-learn Pipeline kiekvienam laukui: TF-IDF + LogisticRegression;
- naudoti tik žmogaus patvirtintas konkretaus lauko žymas;
- prieš mokymą patikrinti įrašų skaičių ir klasių pakankamumą; kitu atveju grąžinti insufficient_data;
- po naujo viešo pranešimo išsaugojimo paleisti paruošto modelio prognozę ir išsaugoti ją atskirai nuo žmogaus patvirtintų žymų;
- kiekvienai prognozei išsaugoti modelio pateiktą pasitikėjimo įvertį, aiškiai atskiriant jį nuo patvirtinto tikslumo; jei įvertis nėra kalibruotas, sąsajoje jo nepateikti kaip garantuotos teisingumo tikimybės;
- nustatyti ir dokumentuoti peržiūros slenkstį: kai prognozės pasitikėjimo įvertis žemesnis už slenkstį, automatiškai pažymėti įrašą „Rekomenduojama peržiūra“, bet neatimti iš sistemos automatinio klasifikavimo galimybės;
- vertinti kiekvieną lauką (kategoriją, prioritetą, sudėtingumą) atskirai, nes vieno lauko prognozė gali būti patikimesnė už kito;
- jei modelis dar neapmokytas arba trūksta duomenų, vis tiek priimti pranešimą ir parodyti, kad automatinė prognozė dar negalima;
- programuotojui leisti pataisyti prognozę, išsaugant prognozę ir patvirtintą reikšmę atskirai;
- fiksuoti modelio versiją, treniravimo metaduomenis ir deterministinį seed.

Priėmimas: testai patikrina mokymo sąlygas, insufficient_data, prognozės formatą, automatinį naujo pranešimo klasifikavimą, prognozės ir anotacijos atskyrimą bei žemo pasitikėjimo žymos nustatymą. Neteigiama, kad score yra kalibruota tikimybė, jei kalibracija nepatikrinta.

## 6 etapas – vertinimas ir sąsajos užbaigimas
**Tikslas:** parengti atkuriamą, bakalauro darbui tinkamą modelio vertinimą.

Darbai:
- palyginti daugumos klasės baseline su TF-IDF + LogisticRegression tuo pačiu duomenų split;
- pateikti per lauką duomenų kiekį, klasių pasiskirstymą, precision, recall, F1, macro-F1 ir confusion matrix, kai imtis leidžia;
- vidiniame puslapyje pateikti modelio būseną, prognozės metodą, vertinimo ataskaitą ir aiškius duomenų nepakankamumo pranešimus;
- klaidų sąraše ir detalėse rodyti pasitikėjimo įvertį bei aiškią žymą „Automatinė klasifikacija“ arba „Rekomenduojama peržiūra“ pagal dokumentuotą slenkstį;
- patikrinti, ar peržiūros slenkstis pagrįstai parinktas vertinimo duomenimis; ataskaitoje nurodyti, kiek prognozių pažymima peržiūrai ir kokia jų faktinė klasifikavimo kokybė, jei duomenų imtis leidžia;
- parodyti aktyvių ir išspręstų pranešimų skaičius;
- CSV eksportą įgyvendinti tik jei tai naudinga realiam vertinimui ir nepadidina apimties neproporcingai;
- README suderinti su faktiškai įgyvendintu funkcionalumu.

Priėmimas: testai įrodo, kad mokymo ir testavimo duomenys nesimaišo; esant mažai imčiai rodomas įspėjimas, o ne išgalvotos metrikos; peržiūros žyma veikia pagal nustatytą slenkstį ir sąsaja nevadina nepatikrinto score tikslumo garantija.

## 7 etapas – užbaigimas
**Tikslas:** kokybinė patikra, ne naujos funkcijos.

Darbai:
- paleisti visą testų rinkinį ir taisyti realius defektus;
- patikrinti švarios aplinkos diegimą, autentifikavimą, serverio validaciją, logus ir paslapčių apsaugą;
- patikrinti, kad DB, modeliai, tokenai ir privatūs duomenys netyčia necommittinami;
- atnaujinti žinomų apribojimų sąrašą;
- užfiksuoti tik realiai gautus testų ir modelio vertinimo rezultatus.

Priėmimas: visi automatiniai testai praeina; dokumentai atitinka kodą; nėra išgalvotų rezultatų.

## Bendros taisyklės
- Vienu metu įgyvendinti tik nurodytą etapą.
- Nenaudoti naujų priklausomybių, jei funkciją galima paprastai įgyvendinti esamu rinkiniu arba standartine biblioteka.
- Nenaudoti React/Vue, Node, Docker, ORM, Redis, task queue, mokamos LLM API ar mikroservisų.
- GitHub integracija lieka tik skaitymo režimu.
- Automatiniuose testuose nenaudoti tikro tinklo.
- Kiekvieno etapo pabaigoje aiškiai atskirti paleistus testus nuo tų, kurie tik numatyti.
