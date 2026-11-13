# Įgyvendinimo planas

Laikytis etapų eilės. Vienoje Claude Code sesijoje įgyvendinti tik vieną etapą, paleisti su juo susijusius testus ir užrašyti faktinius rezultatus. Neperrašyti jau veikiančio 0 etapo karkaso.

## 0 etapas – minimalus projekto pagrindas (ATLIKTA)
**Tikslas:** pakartojama aplinka ir paleidžiamas FastAPI karkasas.

Atlikta: FastAPI programos kūrimo funkcija create_app(), GET /health, Jinja2 pagrindinis puslapis GET /, CSS, pytest konfigūracija ir pradiniai testai.

## 1 etapas – SQLite ir GitHub importas (ATLIKTA)
**Tikslas:** paruošti duomenų saugyklą ir importuoti viešus GitHub issues mokymo duomenims.

Darbai:
- sukurti SQLite inicializaciją ir atskirti lenteles sistemos pranešimams (bug_reports) bei iš GitHub importuotiems mokymo įrašams (github_issues);
- GitHub klientas priima tik normalizuotą owner/repo, naudoja HTTPS, paginaciją ir ribotą importą;
- atpažinti pull request ir jų neimportuoti;
- pakartotinis importas nedubliuoja įrašų ir neperrašo žmogaus patvirtintų žymų;
- UI leidžia įvesti repozitoriją, paleisti importą, matyti rezultatą ir klaidų pranešimus;
- automatiniuose testuose naudoti mock'us, ne gyvą GitHub tinklą.

Priėmimas: testai tikrina paginaciją, HTTP klaidas, PR filtrą, dublikatų prevenciją, anotacijų išsaugojimą ir savavališkų hostų atmetimą.

## 2 etapas – vieša klaidos pateikimo forma (ATLIKTA)
**Tikslas:** klientas / testuotojas gali pateikti klaidą be paskyros.

Darbai:
- sukurti viešą HTML formą su pavadinimu ir išsamiu aprašymu;
- validuoti privalomus laukus ir teksto ilgius serverio pusėje;
- išsaugoti pateiktą įrašą bug_reports lentelėje, priskirti new būseną ir sukūrimo laiką;
- parodyti pateikimo patvirtinimą, bet neatskleisti kitų įrašų;
- viešai nerodyti vidinio sąrašo, prognozių ar anotavimo veiksmų.

Priėmimas: teisingas įrašas išsaugomas, neteisinga forma atmetama su aiškiu pranešimu, o po pateikimo klientas negali pasiekti kitų pranešimų.

## 3 etapas – programuotojo prisijungimas ir klaidų valdymo aplinka (ATLIKTA)
**Tikslas:** programuotojas / koordinatorius gali saugiai tvarkyti pateiktas klaidas.

Darbai:
- sukurti vieną administratoriaus / koordinatoriaus prisijungimą, tinkamą vietiniam bakalauro prototipui; slaptažodį imti iš aplinkos kintamojo arba tikrinti saugų maišą, niekada nelaikyti atviro teksto kode;
- apsaugoti visus vidinius sąrašo, detalių, būsenų keitimo, anotavimo, mokymo ir vertinimo maršrutus;
- sukurti vidinį klaidų sąrašą, detalių puslapį, paiešką ir filtrus pagal būseną, kategoriją, prioritetą ir sudėtingumą;
- leisti keisti būseną new, in_progress, resolved; išspręsti įrašai lieka istorijoje;
- rodyti aiškias būsenas ir klaidų pranešimus.

Priėmimas: neautentifikuoti prašymai į vidinius maršrutus nukreipiami į prisijungimą arba atmetami; prisijungęs naudotojas gali peržiūrėti ir keisti būsenas; išspręsti įrašai nedingsta iš istorijos. Testuoti autentifikavimą ir leidimus.

## 4 etapas – rankinis GitHub įrašų žymėjimas (ATLIKTA)
**Tikslas:** sukurti patikimą mokymo duomenų pagrindą.

Darbai:
- GitHub issue detalių puslapyje atskirai pasirinkti kategoriją, sudėtingumą ir prioritetą;
- nežinomas žymas palikti NULL;
- saugoti anotavimo šaltinį ir laiką;
- rodyti anotacijų skaičių kiekvienam laukui ir klasei;
- neleisti automatiškai laikyti GitHub etikečių teisingomis žymomis be žmogaus patvirtinimo.

Priėmimas: galima išsaugoti ir vėl atverti žymas; vieno lauko redagavimas netrina kitų; sistemos klientų pateikti pranešimai netampa mokymo duomenimis be patvirtinimo.

## 5A etapas – mokymo duomenų paruošimas, DI žymėjimas ir mokymo infrastruktūra (ATLIKTA)
**Tikslas:** paruošti 2 000–3 000 kokybiškų GitHub issues mokymo rinkinį ir mokymo / vertinimo CLI, nekeičiant svetainės veikimo. Sprendimą mokymo duomenis žymėti išoriniu DI API patvirtino darbo vadovas.

Atlikta:
- masinis importas iš kelių repozitorijų su GitHub etikečių filtru (`python -m tools.import_issues`);
- kokybės patikra (per trumpas aprašymas, dublikatai) ir ataskaita (`python -m tools.check_data`);
- žmogaus testavimo rinkinio atsitiktinė atranka (`python -m tools.select_test_set`, `github_issues.is_test_set`); svetainėje – filtras ir „Kitas nepažymėtas“ šiuos įrašus siūlo pirmus;
- DI žymėjimas (`python -m tools.ai_label`): `claude-haiku-5-5`, JSON schema, `effort: low`, prompt caching, dry-run pagal nutylėjimą, `--limit`, paleidimo ir bendras biudžetas, kaina iš `usage`, pakartotinis paleidimas be dublikatų, žymos atskiroje `ai_annotations` lentelėje;
- trijų TF-IDF + LogisticRegression modelių mokymas, išsaugojimas (`models/*.joblib`) ir vertinimas su baseline, DI validacijos dalimi ir žmogaus testavimo rinkiniu (`python -m tools.train_models`);
- testai be tikrų API užklausų.

Realus mokamas žymėjimas ir modelių mokymas – 5B etape, tik naudotojui leidus.

## 5B etapas – automatizuotas duomenų paruošimas, DI žymėjimas ir modelių mokymas (PROGRAMINĖ DALIS ATLIKTA)
**Tikslas:** kuo mažiau rankinio darbo surinkti 2 000–3 000 kokybiškų GitHub issues, juos pažymėti DI, išmokyti ir įvertinti tris modelius.

Atlikta (programinė dalis):
- `tools/sources.json` – 13 įvairių projektų su jų „bug“ etiketėmis ir papildymo šaltiniai retoms klasėms; `python -m tools.collect --check` – nemokama etikečių patikra;
- tęstinis rinkimas: `tools.collect` neberenka iš naujo jau surinktų šaltinių. Problema: kiekvienas paleidimas iš naujo apdorojo visus šaltinius (pvz. 2 299 atnaujinti, 28 nauji) ir sunaudojęs GitHub API limitą (~60 užklausų per valandą be paskyros) sustodavo ties `elastic/elasticsearch`. Sprendimas: nauja lentelė `collection_progress` (repozitorija + etiketė → pasiektas `limit`), įrašoma tik po sėkmingo viso šaltinio importo; kitas paleidimas tokius šaltinius praleidžia ir tęsia nuo neužbaigto, o nepavykę šaltiniai renkami iš naujo. Ta pati repozitorija su skirtingomis etiketėmis vedama atskirai; didesnis `limit` sukelia pakartotinį rinkimą. Senesnėje DB (be lentelės) šaltinis laikomas surinktu, kai DB jau turi bent `limit` atitinkančių issues. Esami duomenys nekeičiami (lentelė tik pridedama), `--refresh` surenka viską iš naujo. Testai: `tests/test_ml_pipeline.py` (praleidimas, tęsimas po limito, etiketės, senos DB įrašai, migracija, CLI);
- `python -m tools.pipeline` – rinkimas be autentifikacijos, filtras (dublikatai, per trumpi, ne klaidų etiketės), galutinio testavimo (~120) ir atskiro bandomojo (~30) rinkinių atranka proporcingai pagal projektus prieš DI žymėjimą, kainos įvertis;
- bandomasis rinkinys (`is_pilot_set`) DI modelio pasirinkimui ir faktinei kainai; galutiniam vertinimui nenaudojamas;
- `python -m tools.class_report` – visų trijų užduočių klasių kiekiai, trūkumai, DI ir žmogaus žymų sutapimas bandomajame rinkinyje;
- `python -m tools.collect --augment` – tikslinis papildymas tik trūkstamoms klasėms (`source_kind = augmentation`, į bandomąjį / testavimo rinkinius nepatenka); klasės dirbtinai nepriskiriamos;
- `models/training_report.md` – duomenų kilmė, DI metodika ir kaina, metrikos su bootstrap 95 % intervalais, klaidų matricos, baseline, automatiniai apribojimai.

Atlikta naudotojo kompiuteryje: pagrindinis rinkimas (13 `base` šaltinių, 2 906 įrašai; 25 šaltiniai `sources.json` = 13 `base` + 12 `augment`, o `augment` naudojamas tik su `--augment`). Duomenų analizė (2026-11-09, žr. [DATA_QUALITY_REPORT.md](DATA_QUALITY_REPORT.md)): 2 774 įrašai praėjo kokybės patikrą; žmogaus žymų, DI žymų ir testavimo / bandomojo rinkinių dar nėra; DI žymėjimas visam rinkiniui su `claude-haiku-5-5` įvertintas ~$0.7–1.4.

Etikečių filtro pataisa atlikta (2026-11-09): komponentų etiketės `feature: ...`, `Needs Discussion` / `under-discussion` ir `*-unsupported` nebelaikomos ne klaidos požymiu; tinkamų įrašų dabar 2 884 (buvo 2 774). Likę žingsniai (nepradėti): patikrinti pataisą naudotojo kompiuteryje, tada atrinkti testavimo / bandomąjį rinkinį ir tik po to pradėti DI žymėjimą.

Liko (naudotojo kompiuteryje, mokami žingsniai – tik naudotojui leidus): filtro peržiūra, testavimo (~120) ir bandomojo (~30) rinkinių atranka (`python -m tools.pipeline --skip-import`), jų žymėjimas, bandomasis ir masinis DI žymėjimas, tikslinis `--augment` (tik po DI žymėjimo ir tik trūkstamoms klasėms), mokymas ir ataskaitos įvertinimas.

### 5B papildymas – DI žymėjimo paruošimas (užsakovo „5C“, 2026-11-10)
Pavadinimų pastaba: šiame plane „5C“ yra modelių integracija į svetainę (žemiau, nekeičiama); čia aprašytas DI žymėjimo paruošimas, kurį užsakovas vadino „5C“. Rankinio žymėjimo atsisakyta: mokymo ir testavimo žymas kuria Claude (`claude-haiku-5-5`, prompt `v1`). Būklė DB: 2 906 issues, 2 884 praėjo kokybės patikrą, pilot 30 (visi pažymėti DI ir, anksčiau, žmogaus), test 120 (dar nežymėti), mokymui 2 734.

Atlikta (kodas + testai; mokamų užklausų nebuvo):
- DI atsakymas kiekvienam įrašui: tinkamumas, kategorija, sudėtingumas, prioritetas (JSON schema + papildoma validacija); „unsuitable“ įrašams klasių žymos nesaugomos.
- Tęstinumas: rezultatas į `ai_annotations` rašomas po kiekvieno atsakymo; pažymėti įrašai praleidžiami, nesėkmingi bandomi iki `MAX_ATTEMPTS` (2); Ctrl+C išsaugo padarytą darbą.
- Klaidos: įrašo klaida (400/413/422) pažymi tik tą įrašą; raktas, limitai, tinklas, 5xx stabdo paleidimą; 5 nesėkmės iš eilės stabdo paleidimą (pvz. pasibaigus kreditams).
- Progresas su likusio laiko įverčiu ir rinkinių (pilot / test / training) pažangos lentele; biudžetas: šio paleidimo riba + bendra riba, įskaitant vykdomų užklausų rezervą.
- Ribotas lygiagretumas: `--workers 1–8` (numatyta 1); į DB rašo tik pagrindinė gija.
- Testavimo rinkinys: etalonas – žmogaus žymos, kai jų nėra – DI žymos (`label_source`); ataskaita aiškiai nurodo, kad metrikos rodo atitikimą DI žymoms. Test įrašai į mokymą nepatenka (patikra `load_datasets`, išimtis jei pažeista).
- Mokymas gali naudoti vien Claude žymas (testas „issue → DI žymos → mokymas“ su imituotu klientu).

Liko (naudotojo kompiuteryje, MOKAMA): `ai_label --subset test`, `--subset training`, tada `class_report` ir `train_models`.

## 5C etapas – modelių integracija į svetainę
**Tikslas:** sistema automatiškai pasiūlo kategoriją, prioritetą ir, jei duomenų pakanka, sudėtingumą naujiems klientų pranešimams, naudodama tik lokaliai išmokytus modelius (be DI API).

Darbai:
- įkelti `models/*.joblib` (5B); jei modelio nėra arba laukas `insufficient_data` – pranešimą vis tiek priimti ir parodyti, kad automatinė prognozė negalima;
- po naujo viešo pranešimo išsaugojimo paleisti paruošto modelio prognozę ir išsaugoti ją atskirai nuo žmogaus patvirtintų žymų;
- kiekvienai prognozei išsaugoti modelio pateiktą pasitikėjimo įvertį, aiškiai atskiriant jį nuo patvirtinto tikslumo; jei įvertis nėra kalibruotas, sąsajoje jo nepateikti kaip garantuotos teisingumo tikimybės;
- nustatyti ir dokumentuoti peržiūros slenkstį: kai prognozės pasitikėjimo įvertis žemesnis už slenkstį, automatiškai pažymėti įrašą „Rekomenduojama peržiūra“, bet neatimti iš sistemos automatinio klasifikavimo galimybės;
- vertinti kiekvieną lauką (kategoriją, prioritetą, sudėtingumą) atskirai, nes vieno lauko prognozė gali būti patikimesnė už kito;
- programuotojui leisti pataisyti prognozę, išsaugant prognozę ir patvirtintą reikšmę atskirai;
- fiksuoti modelio versiją ir prognozės metodą.

**Būsena (2026-11-10):** įgyvendinta – modelių įkėlimas (`app/services/prediction_service.py`, katalogas `MODELS_DIR`), automatinė klasifikacija po viešo pranešimo išsaugojimo, lentelė `prediction_runs` (atskirai nuo patvirtintų žymų), pasitikėjimo įvertis su įspėjimu, kad tai ne kalibruota tikimybė, lauko slenksčiai ir „Rekomenduojama peržiūra“, modelio versija ir metodas, aiškus pranešimas be modelių / su sugadintais modeliais (svetainė veikia), prognozės sąraše (filtrai) ir detalėse, mygtukas „Klasifikuoti iš naujo“. **Dar neįgyvendinta (6 etapas):** slenksčių pagrindimas nepriklausomais duomenimis, modelio būsenos puslapis.

**5C užbaigimas (2026-11-10):** įgyvendinta (1) programuotojo klasifikacijos patvirtinimo forma „Patvirtinti klasifikaciją“ (`POST /dashboard/reports/{id}/classification`, lentelė `classification_confirmations`, patvirtintos žymos turi pirmenybę sąrašuose / filtruose, perklasifikavimas jų nekeičia); (2) lietuvių kalbos palaikymas – aptikimas ir vertimas vietiniu žodynu tik modelio įvesčiai, originalas DB nekeičiamas, nepatikimas vertimas žymimas; (3) modelio įverčiai pašalinti iš pagrindinio vaizdo (lieka DB ir sutraukiamoje techninėje skiltyje), aiškiai atskirta „Laukia patvirtinimo“ / „Patvirtinta“; (4) tvarkingesnis `/dashboard` (viena klasifikacijos būsenos žyma vietoje trijų „auto“) ir detalių išdėstymas; (5) pataisytas `test_report_detail_shows_all_fields` pagal naują struktūrą (patvirtintos žymos `<dt>` dabar klasifikacijos kortelėje; patikros papildytos, ne sumažintos). **Dokumentų suderinimas:** 6 etapo punktas apie pasitikėjimo įverčio rodymą sąrašuose / detalėse pakeistas sprendimu įverčių pagrindiniame vaizde nerodyti.

Priėmimas: testai patikrina prognozės formatą, automatinį naujo pranešimo klasifikavimą, modelio nebuvimo atvejį, prognozės ir anotacijos atskyrimą bei žemo pasitikėjimo žymos nustatymą. Neteigiama, kad score yra kalibruota tikimybė, jei kalibracija nepatikrinta.

## 5D etapas – mokymo duomenų išplėtimas ir modelių kokybės gerinimas
**Tikslas:** padidinti mokymo duomenų kiekį ir subalansuoti kategorijas; tuos pačius tris TF-IDF + LogisticRegression klasifikatorius apmokyti iš naujo (metodas ir parametrai nekeičiami, kad būtų matoma duomenų kiekio įtaka). Svetainė, autentifikavimas, klasifikacijos patvirtinimas ir lietuvių kalbos apdorojimas nekeičiami.

**Pradinė būklė (užsakovo duomenys, 5C-final):** 2 906 importuoti, 2 608 tinkami mokymui, pilotas 30, testas 120 (112 tinkami). Kategorijos: backend_api 1 442, ui 436, database_data 217, build_deployment 160, security 119, performance 109, other 106, documentation 19. Macro-F1 (etalonas – Claude žymos): kategorija 0.4924, sudėtingumas 0.6094, prioritetas 0.5896. Prioriteto klasės `P0_critical` mokymo duomenyse praktiškai nėra.

**Tikslai:** ≥ 15 000 tinkamų mokymo pavyzdžių, ≥ 1 000 kiekvienai iš 8 kategorijų, daugiau `P0_critical`, ~1 000 papildomų testo pavyzdžių.

**Importo planas (`tools/sources_5d.json`, viršutinės ribos, ne garantuoti kiekiai):**

| Kategorija / tikslas | Trūksta iki 1 000 (esama) | Šaltinių limitų suma | Pagrindiniai šaltiniai (etiketė) |
|---|---:|---:|---|
| ui | 564 | 3 800 | vscode (ui-glitch), material-ui, flutter, angular, vue, PowerToys |
| backend_api | 0 | 2 000 | spring-boot, aspnetcore, grpc, nest, express |
| database_data | 783 | 4 900 | prisma, typeorm, sequelize, supabase, ClickHouse, tidb, cockroach, redis, drizzle |
| security | 881 | 4 600 | keycloak, spring-security, DependencyCheck, vault, openssl, next-auth, zaproxy, trivy |
| performance | 891 | 4 200 | pandas (Performance), dotnet/runtime, rust (I-slow), go, pytorch, vscode, flutter |
| build_deployment | 840 | 4 300 | webpack, vite, gradle, bazel, helm, pnpm, moby, compose, cargo, nx |
| documentation | 981 | 5 100 | mdn/content, kubernetes/website, vuejs/docs, vscode-docs, home-assistant.io, docker/docs, dotnet/docs, angular |
| other | 894 | 2 700 | home-assistant/core, rust (C-bug), godot, obs-studio |
| P0 | ~0 | 2 500 | kubernetes (priority/critical-urgent), flutter (P0), tidb (severity/critical), rust (P-critical), cockroach (release-blocker), ClickHouse, pytorch |

Visų limitų suma ~34 100 (sąmoningai su atsarga: dalis etikečių turės mažiau issues, dalis pasikartos su esamais ar tarpusavyje, dalį atmes kokybės filtras ir DI „netinka“). **Etiketės ir skaičiai nepatikrinti gyvai** – tai atliekama `collect --check --counts` naudotojo kompiuteryje. Etiketės yra tik kandidatų atrankai: kategoriją, sudėtingumą, prioritetą ir tinkamumą nustato Claude žymėjimas pagal `docs/DATA_LABELING.md`; P0 nepriskiriamas vien dėl žodžio „critical“ ar saugumo temos. Jei po žymėjimo kuriai nors kategorijai trūks 1 000, naudojamas esamas `collect --augment` (tikslinis papildymas).

**Infrastruktūros pakeitimai (minimalūs, naujo įrankio nekurta):** šaltinio limitas iki 3 000 (30 puslapių), `collect --check --counts` (Search API, `count_issues`), automatinė DB atsarginė kopija prieš importą (`tools/_common.backup_database`, `--no-backup`), artimų dublikatų (kosinuso panašumas ≥ 0,9, `HashingVectorizer` be žodyno) pašalinimas iš mokymo vs. testas (`app/ml/leakage.py`, `training.load_datasets`). Jau buvo: tęstinis rinkimas (`collection_progress`), tikslių dublikatų, PR, trumpų ir ne klaidų įrašų filtravimas, `ON CONFLICT` įrašymas (esami įrašai ir anotacijos nekeičiami), testo / pilotinių rinkinių atskyrimas.

**Eiga:** (1) importo paruošimas – **atlikta** (programinė dalis, testai); (2) naudotojas paleidžia `--check --counts`, taisome šaltinius; (3) importas; (4) testo rinkinio papildymas ir kainos dry-run; (5) mokamas žymėjimas – tik su naudotojo patvirtinimu; (6) `class_report`, prireikus tikslinis papildymas; (7) `train_models` su tais pačiais parametrais, naujų modelių failai ir ataskaitos saugomi atskirai (nekeičiant `models/` iki palyginimo), palyginimas senų ir naujų tame pačiame testo rinkinyje (accuracy, macro-F1, weighted-F1, klasių precision / recall / F1, confusion matrix).

**Priėmimas:** testai patvirtina limitų, `--counts`, atsarginės kopijos ir artimų dublikatų elgesį; testo įrašai niekada nepatenka į mokymą; esama DB ir anotacijos nekeičiamos. Rezultatų (kokybės pagerėjimo) neteigiama, kol nėra naujo mokymo.

## 6 etapas – vertinimas ir sąsajos užbaigimas
**Tikslas:** parengti atkuriamą, bakalauro darbui tinkamą modelio vertinimą.

Darbai:
- palyginti daugumos klasės baseline su TF-IDF + LogisticRegression tuo pačiu duomenų split;
- pateikti per lauką duomenų kiekį, klasių pasiskirstymą, precision, recall, F1, macro-F1 ir confusion matrix, kai imtis leidžia;
- vidiniame puslapyje pateikti modelio būseną, prognozės metodą, vertinimo ataskaitą ir aiškius duomenų nepakankamumo pranešimus;
- klaidų sąraše ir detalėse rodyti aiškią klasifikacijos būseną („Laukia patvirtinimo“ / „Patvirtinta“); skaitinių įverčių vartotojui nerodyti (5C sprendimas), jie lieka techninėje analizėje;
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
- Nenaudoti React/Vue, Node, Docker, ORM, Redis, task queue, mokamos LLM API ar mikroservisų. Išimtis: vienkartinis mokymo duomenų žymėjimas Claude API per `tools/` (5A), ne svetainėje.
- GitHub integracija lieka tik skaitymo režimu.
- Automatiniuose testuose nenaudoti tikro tinklo.
- Kiekvieno etapo pabaigoje aiškiai atskirti paleistus testus nuo tų, kurie tik numatyti.
