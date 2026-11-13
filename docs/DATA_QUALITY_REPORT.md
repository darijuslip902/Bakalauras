# Duomenų kokybės analizė ir pasiruošimas modelių mokymui (5B)

Analizės data: 2026-11-09. Analizuota 2906 GitHub issues iš SQLite duomenų bazės `data/bakalauras.sqlite3` (tik skaitymas, dirbta su kopija; originalo SHA256 prieš ir po analizės sutampa).

## Dabartinė būklė (2026-11-13, po 5D)

0–5D etapai baigti, PR #11 sujungtas į main. Modelių versija `20261113-125330`. 6 etapas nepradėtas: laukiama darbo vadovo pastabų; statistikos puslapis nėra patvirtintas reikalavimas. P0 paliekamas, nors jo atpažinimas silpnas.

- 40 024 importuoti GitHub įrašai; 23 884 sėkmingos DI anotacijos (19 412 tinkamų, 4 472 netinkamų).
- 18 267 mokymo ir validacijos pavyzdžiai; 1 120 atrinktų testo įrašų, iš jų 901 tinkamas (visi 901 su DI etalonu); 30 pilotinių įrašų.
- 243 artimi testo dublikatai pašalinti iš mokymo. Bendra DI žymėjimo kaina 4,5948 USD.
- Trys apmokyti modeliai ir jų ataskaitos saugomi GitHub; SQLite DB, jos kopijos, .env ir .venv – tik lokaliai.
- Testo accuracy / macro-F1: kategorija 64,26 % / 62,22 %; sudėtingumas 69,70 % / 69,14 %; prioritetas 65,93 % / 48,20 %. P0 F1 = 0. Metrikos rodo atitikimą Claude žymoms, ne nepriklausomai žmogaus patvirtintai tiesai. Ankstesnio ir naujo modelio metrikos iš skirtingų testų nėra tiesiogiai palyginamos.

Toliau išsaugota istorinė 5B analizė (2026-11-09), o ne dabartinės DB būklė. Galutinė 5D analizė ir klasių pasiskirstymas pateikti [mokymo ataskaitoje](../models/training_report.md). Pirminiai kainos įverčiai nėra faktinės 5D išlaidos.

## 0. Trumpi atsakymai

| Klausimas | Atsakymas |
|---|---|
| 1. Ar 2906 įrašų pakanka? | **Bendrai taip, bet ne kiekvienai klasei garantuotai.** Po kokybės patikros tinkami žymėjimui 2774 įrašai. Tai pakankamas pagrindas TF-IDF + LogisticRegression eksperimentui, tačiau retoms klasėms (saugumas, našumas, dokumentacija, P0) pavyzdžių greičiausiai trūks. Tikslią padėtį parodys tik DI žymėjimas ir `python -m tools.class_report`. |
| 2. Ar reikia `--augment`? | **Dabar ne, ir dabar jis net negalėtų veikti** (nėra nė vienos žymos, o komanda to reikalauja). Po DI žymėjimo jį reikės paleisti tik toms klasėms, kurioms trūksta pavyzdžių (labiausiai tikėtina: saugumas, našumas, dokumentacija, galbūt kompiliavimas / diegimas ir P0). |
| 3. Ar galime pradėti Claude API žymėjimą? | **Dar ne masiškai.** Pirmiausia: (a) apsispręsti dėl `feature` filtro (žr. 7.1), (b) nemokamai atrinkti testavimo (120) ir bandomąjį (30) rinkinius, (c) pažymėti bandomąjį rinkinį rankiniu būdu, (d) atlikti bandomąjį DI paleidimą (~$0.01-0.04). Masinis žymėjimas tik po to. |
| 4. Kiek kainuotų žymėjimas? | **Visi 2774 įrašai su `claude-haiku-5-5`: apie $0.7-1.4** (kodo „tikėtina“ $0.68, „blogiausia“ $2.14). Sonnet 5.5 kainuotų apie $13-28, Opus 5.5 apie $26-56. Tai įverčiai; tikslią kainą nustatys bandomasis paleidimas (žr. 5.4). |
| 5. Kitas konkretus žingsnis | Patvirtinti `feature` filtro pataisą (7.1), tada nemokamai paleisti `python -m tools.pipeline --skip-import`, kad būtų atrinkti testavimo ir bandomasis rinkiniai. |

## 1. Ką realiai patikrinau, o ką ne

Realiai patikrinta:
- perskaitytas kodas: `tools/collect.py`, `tools/sources.json`, `app/ml/collection.py`, `class_analysis.py`, `data_quality.py`, `ai_labeling.py`, `training.py`, `tools/ai_label.py`, `app/db.py`, `app/config.py`, dokumentai;
- visi skaičiai 2-4 skyriuose apskaičiuoti tiesiogiai iš DB kopijos (SQL ir `app.ml.data_quality`);
- kainos ir tokenų įverčiai apskaičiuoti naudojant projekto paties `ai_labeling.py` funkcijas.

Nevykdyta (pagal jūsų apribojimus): GitHub API užklausos, mokamos Claude API užklausos, automatiniai testai (jūs nurodėte, kad visi 332 praėjo jūsų kompiuteryje; šioje aplinkoje to nepatikrinau). DB turinys nekeistas.

Prielaidos: Claude kainos paimtos iš `ai_labeling.py` lentelės; palyginau su viešai skelbiamomis (antriniu šaltiniu perpasakota Anthropic kainodara: Haiku 5.5 $0.10 įvestis / $0.50 išvestis / $0.01 talpyklos skaitymas už 1 mln. tokenų). Oficialaus kainų puslapio šioje aplinkoje atidaryti nepavyko, todėl prieš mokamą paleidimą patikrinkite jį patys. Prompt caching minimali riba (512 tokenų Haiku 5.5) paimta iš oficialios dokumentacijos.

## 2. Kodėl rinkimas apdoroja 13 šaltinių, o `sources.json` turi 25

`tools/sources.json` turi du sąrašus:
- `base` - **13** šaltinių: pagrindinis rinkimas (`python -m tools.collect`);
- `augment` - **12** šaltinių, suskirstytų pagal klasę, kuriai jie padeda: `security` (2), `performance` (3), `documentation` (2), `build_deployment` (2), `database_data` (2) ir `P0_critical` (1).

13 + 12 = 25. `python -m tools.collect --check` tikrina visus 25, o įprastas rinkimas ima tik `base`. Du `augment` įrašai (`sqlalchemy/sqlalchemy [bug]` limitas 500 ir `metabase/metabase [Type:Bug]` limitas 400) yra tos pačios repozitorijos ir etiketės kaip `base`, tik su didesniu limitu, todėl iš tikrųjų skirtingų pavadinimų porų (repozitorija + etiketė) yra 23.

### Kaip veikia `--augment`

1. Reikia jau esamų žymų (žmogaus arba DI). Jei jų nėra, komanda išveda „Dar nėra DI ar žmogaus žymų“ ir baigia darbą (grąžina 2). **Dabar DB turi 0 žymų, todėl `--augment` negalėtų nieko padaryti.**
2. Iš žymų suskaičiuoja kiekvienos klasės mokymo pavyzdžius ir randa klases, kurių mažiau nei `--target` (numatyta 40).
3. Pasirenka tik tų klasių `augment` šaltinius; klasėms be šaltinio (pvz. `ui`, `backend_api`, `other`, visos sudėtingumo klasės, P1-P3) nieko neimportuoja ir tai parodo.
4. Importuoja pasirinktus šaltinius su `source_kind = augmentation`. Tokie įrašai **niekada nepatenka į testavimo ir bandomąjį rinkinius**, o jų klasę vėliau vis tiek nustato DI / žmogus (šaltinis tik nurodo, kur ieškoti).
5. Jei visos klasės turi bent 40 pavyzdžių, nieko nedaroma.

Maksimalus papildymo dydis, jei būtų parinkti visi 12 šaltinių: iki 2050 papildomų issues (limitų suma). Realiai bus mažiau, nes dalis jau yra DB ir renkami tik trūkstamų klasių šaltiniai. Papildymo tikslumas ribotas: pvz. `sqlalchemy bug` ir `metabase Type:Bug` yra bendros klaidų etiketės, ne konkrečiai „duomenų bazės“ klasė.

## 3. Surinktų duomenų analizė (2906 įrašai)

### 3.1 Bendra būklė

| Rodiklis | Reikšmė |
|---|---|
| Įrašų | 2906 |
| Unikalių (repozitorija, numeris) | 2906 (dublikatų pagal raktą nėra) |
| Pull request | 0 |
| Kilmė | 2906 `base`, 0 `augmentation` |
| Būsena | 1598 uždaryti, 1308 atviri |
| Kūrimo datos | 2022-12-15 ... 2026-11-09 (dauguma - paskutiniai mėnesiai) |
| `bug_reports` (klientų pranešimai) | 0 |
| `ai_annotations` | 0 |
| Žmogaus žymos (kategorija / sudėtingumas / prioritetas) | 0 / 0 / 0 |
| Tinkamumas mokymui | 2906 „Neįvertinta“ |
| Testavimo / bandomasis rinkinys | 0 / 0 (dar neatrinkti) |

### 3.2 Įrašai pagal repozitoriją

| Repozitorija | Iš viso | Tinka | Išmesta (kodėl) | Laikotarpis |
|---|---:|---:|---|---|
| python/cpython | 308 | 304 | 4 etiketė | 2026-10-14 ... 11-09 |
| microsoft/vscode | 307 | 303 | 1 trumpas, 3 etiketė | 2026-10-19 ... 11-09 |
| grafana/grafana | 253 | 253 | - | 2026-08-26 ... 11-09 |
| nextcloud/server | 251 | 160 | 1 dublikatas, **90 etiketė** | 2026-08-17 ... 11-08 |
| kubernetes/kubernetes | 241 | 236 | 5 etiketė | 2026-08-06 ... 11-09 |
| sqlalchemy/sqlalchemy | 202 | 201 | 1 etiketė | 2025-03-26 ... 11-08 |
| ansible/ansible | 201 | 201 | - | 2026-01-02 ... 11-09 |
| metabase/metabase | 200 | 200 | - | 2026-10-08 ... 11-09 |
| hashicorp/terraform | 200 | 197 | 3 etiketė | 2025-10-10 ... 11-06 |
| facebook/react | 200 | 199 | 1 dublikatas | 2025-10-08 ... 11-06 |
| elastic/elasticsearch | 200 | 198 | 2 etiketė | 2026-09-25 ... 11-09 |
| pandas-dev/pandas | 193 | 172 | 21 etiketė | 2026-05-11 ... 11-09 |
| prometheus/prometheus | 150 | 150 | - | 2022-12-15 ... 2026-10-18 |
| **Iš viso** | **2906** | **2774 (95.5 %)** | 1 trumpas, 2 dublikatai, 129 etiketė | |

Pastaba: dauguma repozitorijų atstovaujamos tik pačiais naujausiais 200-300 įrašų, t. y. kelių savaičių ar mėnesių laikotarpiu (cpython, vscode, metabase - maždaug 3-4 savaitės). Tai reiškia laikinę koncentraciją (tos pačios laidos klaidos) ir dalį atvirų, dar nenagrinėtų įrašų.

### 3.3 Aprašymų kokybė

| Aprašymo ilgis (simboliai) | Įrašų | Dalis |
|---|---:|---:|
| 0 (tuščias) | 1 | 0.0 % |
| 1-29 | 0 | 0.0 % |
| 30-99 | 0 | 0.0 % |
| 100-299 | 61 | 2.1 % |
| 300-999 | 380 | 13.1 % |
| 1000-5999 | 2068 | 71.2 % |
| 6000 ir daugiau | 396 | 13.6 % |

Mediana 2545, vidurkis 3629, 90-asis procentilis 7086, maksimumas 61026 simbolių. Tušti ar per trumpi aprašymai praktiškai neegzistuoja (1 įrašas). Kodo blokus (```) turi 2180 aprašymų (75 %). 396 aprašymai viršys DI prompto ribą (6000 simbolių) ir bus nukirpti žymint DI modeliu; TF-IDF mokymas naudoja visą tekstą. Ne anglų kalbos (euristika, >30 % ne-ASCII raidžių) rastas 1 įrašas; botų (dependabot, renovate) nerasta.

### 3.4 Dublikatai ir šablonai

- Tikslūs dublikatai (vienodas pavadinimas + aprašymas): **2** (po 1 `facebook/react` ir `nextcloud/server`). Jie jau atmetami `check_quality`.
- Vienodų pavadinimų grupių: 15 (44 įrašai), bet tai daugiausia bendri pavadinimai („[Compiler Bug]:“ 9x, „DevTools Bug“ 5x, „Bug“ 4x), kurių aprašymai skiriasi - tikrais dublikatais nelaikomi.
- **Šablonų rizika:** apie 570 įrašų (~20 %) prasideda identiškomis šablono antraštėmis: 208 Nextcloud („This issue respects the following points“), 163 pandas („Pandas version checks“), 121 React Compiler („What kind of issue is this?“), 52 SQLAlchemy („Discussed in ...“), 26 „bug_report_template“. TF-IDF gali išmokti atpažinti repozitoriją ar šabloną vietoje klaidos pobūdžio (žr. 7.3).

### 3.5 GitHub etiketės

- 720 skirtingų etikečių; įraše jų būna 1-8 (dažniausiai 3).
- Dažniausios: `bug` (1161), `kind/bug` (391), `type-bug` (308), `type/bug` (253), `0. Needs triage` (208), `Type: Bug` / `>bug` / `Type:Bug` (po 200), `Bug` (193), `automated-triage` (188), `Status: Unconfirmed` (186).
- Daugelis etikečių yra komandos, komponentai ar procesas (`sig/node`, `Team:Analytics`, `insiders-released`, `has_pr`), todėl **nėra kategorijos, prioriteto ar sudėtingumo žymos**.
- Informacinės užuominos (raktažodžių paieška etiketėse, **triukšminga ir ne tikros klasės**; pvz. „ux“ sutampa su „linux“, „cve“ su „great mcve“): saugumas 38 įrašai, našumas 39, dokumentacija 15, sudėtingumas („good first issue“, „easy“ ir pan.) 16.
- **Prioriteto etiketės** (`Priority:P1-P3`, `priority/important-soon`, `priority:high`...) yra 369 įrašuose (12.7 %) tik 7 iš 13 repozitorijų: metabase 198, prometheus 61, kubernetes 53, elasticsearch 33, ansible 15, sqlalchemy 8, cpython 1. Skalės skirtingos, todėl jos negali būti tiesiogiai sulyginamos į P0-P3.

### 3.6 Kiek duomenų potencialiai tinkama mokymui

- Praėjo automatinę kokybės patikrą: **2774** (95.5 %).
- Kiek iš jų DI pripažins „tinka mokymui“, kol kas **nežinoma**. Kadangi rinkta pagal „bug“ etiketes, tikėtina didelė dalis (aš tikiuosi apie 85-95 %, tai prielaida), tačiau tai patikrins bandomasis paleidimas.
- Iš jų 120 pateks į testavimo, 30 į bandomąjį rinkinį; likę ~2600 būtų mokymo kandidatai, o naudojami tik tie, kurie DI / žmogaus pripažinti tinkamais ir turi visas 3 žymas.

## 4. Ar duomenų pakanka kiekvienam moduliui

Klasių pasiskirstymas kol kas **nežinomas**, nes žymų nėra. Žemiau vertinama pagal bendrą kiekį, žinomas užuominas ir statistiką; tai rizikų įvertis, ne rezultatas.

| Modulis | Klasės | Vertinimas |
|---|---|---|
| **Kategorija** | 8 | Pakankama didžiosioms klasėms (`backend_api`, `ui`, `build_deployment`, `database_data`, `other`). **Rizika** retoms: `security`, `performance`, `documentation` (užuominos rodo ≈0.5-1.5 % įrašų, t. y. apie 15-40 iš 2906). Šioms `--augment` turi šaltinių. |
| **Prioritetas** | 4 | Rizikingiausias. P2/P3 greičiausiai dominuos, `P0_critical` bus labai retas (kubernetes `priority/critical-urgent` DB yra tik 1 įrašas). Prioritetą iš teksto nustatyti sunku, o DI žymos bus nepatikimesnės; todėl DI ir žmogaus sutapimą būtina išmatuoti. |
| **Sudėtingumas** | 3 | Kiekis pakankamas, bet kokybė abejotina: sudėtingumas iš aprašymo neišvedamas patikimai, tikėtina `medium` dominavimas ir silpnas pranašumas prieš baseline. Tai galiojantis tyrimo rezultatas (EVALUATION_PLAN 9 skyrius), bet reikia sąžiningai aprašyti. |

Statistiniai skaičiai planavimui (mano apskaičiuoti):
- 120 įrašų testavimo rinkinyje klasė, sudaranti 1 % duomenų, turės >=5 pavyzdžių su tikimybe 1 %, 2 % klasė - 9 %, 5 % klasė - 72 %, 10 % klasė - 99 %. Todėl **retų klasių rezultatai žmogaus teste bus nepatikimi** ir taip bus pažymėti ataskaitoje.
- Iš ~2500 mokymo įrašų klasė su 1 % dažniu turės apie 25 pavyzdžius (<40 tikslo), o su 2 % - apie 50.

## 5. Tikros žymos ir DI žymos

Reikia aiškiai skirti:

| Kas | Šaltinis | Kur saugoma | Statusas |
|---|---|---|---|
| GitHub metaduomenys: etiketės, būsena (open/closed), datos, URL | GitHub (tikri) | `github_issues.labels_json`, `state`... | Yra visiems 2906. **Tai ne kategorija, prioritetas ar sudėtingumas.** |
| Žmogaus žymos (kategorija, sudėtingumas, prioritetas, tinkamumas) | Jūsų rankinis žymėjimas | `github_issues.*_label` | 0 |
| DI žymos | Claude API | atskira lentelė `ai_annotations` (su modeliu, prompto versija, tokenais, kaina) | 0 |

Taisyklės, kurias jau įgyvendina kodas ir kurių reikia laikytis:
- GitHub etiketės **niekada** nėra ground truth. Prioriteto ir sudėtingumo žymos nenustatomos kaip faktas vien iš aprašymo - jas nustato žmogus (testo rinkinys) arba DI (mokymo rinkinys, kaip „silver“ žymos su žinoma kilme).
- Žmogaus žyma visada turi pirmenybę prieš DI žymą; testas vertinamas **tik** žmogaus žymomis.
- Prioriteto etiketės 369 įrašuose gali būti naudojamos tik kaip nepriklausomas orientyras DI sutapimui ištirti (pvz. ar DI P3 dažniau sutampa su `Priority:P3`), ne kaip mokymo žymos.

## 6. Claude API žymėjimas

### 6.1 Esama realizacija (`app/ml/ai_labeling.py`, `tools/ai_label.py`)

- Modelis pagal nutylėjimą `claude-haiku-5-5`, prompto versija `v1`, `effort: low`, JSON schema atsakymui, sisteminis promptas talpinamas (cache), aprašymas ribojamas iki 6000 simbolių.
- **Numatytasis režimas - dry-run**: be `--execute` jokios API užklausos nevykdoma. Yra šio paleidimo riba (`--max-cost-usd`, numatyta $0.50) ir bendra riba (`AI_TOTAL_BUDGET_USD`, numatyta $10). Prieš kiekvieną užklausą tikrinama blogiausio atvejo kaina; pasikartojus API klaidai paleidimas sustoja.
- Faktinė kaina skaičiuojama iš atsakymo `usage` laukų ir saugoma kiekvienam įrašui. Žymėjimas pakartotinai paleidžiamas be dublikatų.
- DI žymos netinkamiems įrašams (`unsuitable`) klasifikavimo laukų nesaugo.

### 6.2 Kiek įrašų žymėti

| Rinkinys | Įrašų | Paskirtis |
|---|---:|---|
| Bandomasis | 30 | modelio / prompto patikra ir faktinė kaina |
| Testavimo | 120 | DI sutapimui su žmogumi (žmogus žymi nematydamas DI) |
| Likę kokybiški | ~2620 | mokymo žymos |
| **Iš viso kokybiškų** | **2774** | |

### 6.3 Tokenai (įverčiai, API nekviestas)

- Sisteminis promptas 2988 simboliai (~750-1000 tokenų; virš 512 tokenų talpyklos ribos, todėl talpinimas turėtų veikti).
- Vieno įrašo promptas: vidurkis 3100 simbolių, mediana 2740, 90-as procentilis 6220, maksimumas 6423.
- Įvestis vienai užklausai: ~1.6-2.1 tūkst. tokenų (priklauso nuo 3-4 simbolių vienam tokenui); **viso apie 4.4-5.8 mln. įvesties tokenų**.
- Išvestis (JSON + trumpas mąstymas): 250-600 tokenų užklausai, **viso ~0.7-1.7 mln. tokenų**.
- Tikslaus skaičiaus be API užklausos nėra (Anthropic tokenizatoriaus lokaliai neturime), todėl kode naudojamas konservatyvus 3 simboliai / tokenui.

### 6.4 Kaina (USD už 2774 įrašus)

| Modelis | Be talpyklos, 250 / 600 išvesties tok. | Kodo „tikėtina“ | Kodo „blogiausia“ |
|---|---|---|---|
| **claude-haiku-5-5** | 0.92 / 1.41 | **0.68** | 2.14 |
| claude-sonnet-5-5 | 18.48 / 28.19 | 13.23 | 42.84 |
| claude-opus-5-5 | 36.96 / 56.38 | 26.45 | 85.67 |

Atskiri paleidimai su Haiku 5.5: bandomasis 30 - tikėtina $0.007, blogiausia $0.023; testavimo 120 - tikėtina $0.026, blogiausia $0.088. Rekomenduojama planuoti **$2-3 viršutinę ribą** viso rinkinio žymėjimui (README jau naudoja `--max-cost-usd 3`).

### 6.5 Kokios informacijos reikia tiksliam kainos skaičiavimui

1. Tikslus modelio ID ir **oficiali kainų lentelė** (kaina už 1 mln. tokenų: įvestis, išvestis, talpyklos rašymas, talpyklos skaitymas) - patikrinti pagal oficialų puslapį paleidimo dieną.
2. Realūs `usage` laukai iš bandomojo paleidimo: `input_tokens`, `output_tokens` (įskaitant mąstymą), `cache_creation_input_tokens`, `cache_read_input_tokens`. Jei abu talpyklos laukai lygūs 0, talpykla nesuveikė ir kaina didesnė.
3. Vidutinis išvesties ilgis (nuo jo labiausiai priklauso kaina, nes išvestis 5x brangesnė už įvestį).
4. Netinkamų atsakymų ir pakartojimų dalis (iki 2 bandymų vienam įrašui).
5. Ar naudojamas Batch API (50 % pigiau, bet dabartinis kodas jo nenaudoja; $1 sumai nereikalinga).
6. API paskyros kreditų likutis ir užklausų limitai.

Kai tik atliksite bandomąjį paleidimą, `python -m tools.ai_label` parodys „Pagal faktines N užklausas: ~$X įrašui“ - tai tiksliausias viso rinkinio kainos įvertis.

## 7. Rastos problemos

### 7.1 Etikečių filtras per agresyvus (PATAISYTA 2026-11-09)

`EXCLUDED_LABEL_KEYWORDS` filtras atmeta 129 įrašus, bet bent ~110 iš jų yra abejotini:
- **90 Nextcloud įrašų** (visi, turintys `feature: ...` etiketę) atmesti dėl etikečių `feature: files`, `feature: caldav`, `feature: sharing`... Tai greičiausiai **komponentų / sričių** etiketės, ne funkcijų pasiūlymai: visi jie rinkti su `bug` etikete, o tikroji etiketė `enhancement` visame rinkinyje pasitaiko 1 kartą. Dėl to Nextcloud turi tik 160 iš 251 tinkamų (64 %).
- 15 pandas įrašų atmesti dėl `Needs Discussion`, 1 vscode dėl `under-discussion` (raktažodis „discussion“); 3 cpython dėl `OS-unsupported` (raktažodis „support“); 1 Elasticsearch dėl `Feature:ES|QL` (taip pat komponento etiketė). Tai tikros klaidos.
- Pagrįstai atmesta apie 18-19: `Duplicate Report` / `duplicate` (11), `kind/support` (2), `question` (1), `>enhancement` (1), `kind/feature` / `type-feature` (3).

Pasekmė: prarandama ~100 tikrų klaidų, o **testavimo ir bandomasis rinkiniai atrenkami tik iš tinkamų įrašų ir yra „užfiksuojami“** - Nextcloud būtų neatstovaujama. Todėl pataisyti reikia **prieš** atrenkant rinkinius. Mažiausias sprendimas: nelaikyti ne-klaidos požymiu etikečių, prasidedančių `feature:` (Nextcloud, `Feature:ES|QL`), `Needs Discussion`, `under-discussion` ir `*-unsupported`. **Pataisa atlikta** (`app/ml/data_quality.py`, patvirtinus naudotojui): tikrinant `check_quality` ant DB kopijos, ok 2774 → 2884 (+110), atmesta pagal etiketę 129 → 19; pakeitė statusą tik `feature: ...` (kelios dešimtys etikečių), `Needs Discussion` (15), `under-discussion` (1), `OS-unsupported` ir `Feature:ES|QL`. Šioje ataskaitoje žemiau pateikti skaičiai (2774, 129) yra **prieš pataisą**; dabartinė vertė – 2884 / 19. Kaina nuo to išauga ~4 %.

### 7.2 Dauguma `sources.json` šaltinių ima tik naujausius įrašus

Žr. 3.2 pastabą. Tai leidžia daryti išvadas tik apie naujausią laikotarpį; tai reikia paminėti apribojimuose.

### 7.3 Repozitorijos ir šablonų painiava (leakage rizika)

Klasės dažnai susijusios su repozitorija (pvz. `sqlalchemy` ir `pandas` - duomenys / DB, `kubernetes` - diegimas), o šablonų antraštės būdingos repozitorijai. TF-IDF modelis gali „atpažinti repozitoriją“ vietoje klaidos pobūdžio. Rekomendacijos: (a) ataskaitoje pateikti klasių pasiskirstymą pagal repozitoriją, (b) kaip papildomą eksperimentą atlikti skirstymą pagal repozitoriją (EVALUATION_PLAN 4 skyrius jį jau numato), (c) apsvarstyti šablonų antraščių pašalinimą prieš TF-IDF (kodo pakeitimas, atskira užduotis).

### 7.4 Dokumentų neatitikimai

Rasta ir (kur galima) pataisyta šiame atnaujinime (tik dokumentacija):
- `docs/IMPLEMENTATION_PLAN.md` 5B: „Liko ... realus rinkimas“ buvo pasenę - rinkimas jau atliktas (13 šaltinių, 2906 įrašai); pridėta duomenų būklė ir 7.1 pastaba.
- `docs/DATA_LABELING.md`: filtro aprašas neminėjo `feature:` ir `discussion` rizikos; pridėta pastaba.
- `docs/EVALUATION_PLAN.md`: pridėtas 10 skyrius su konkrečia 5B strategija.
- `README.md`: pridėta duomenų būklė ir nuoroda į šią ataskaitą.

## 8. Rekomenduojama mokymo ir vertinimo strategija (paprasta, bakalauro darbui)

Naudojama tai, kas jau yra projekte; naujų bibliotekų nereikia.

1. **Duomenys.** Mokymui - tik kokybės patikrą praėję, „tinka mokymui“, su visomis trimis žymomis; žmogaus žyma turi pirmenybę prieš DI. Dublikatai šalinami prieš dalijimą (jau įgyvendinta).
2. **Žmogaus testavimo rinkinys (120)** atsitiktinė atranka su seed 42, proporcinga pagal repozitorijas, **atrenkama prieš DI žymėjimą**, žymima rankiniu būdu nematant DI atsakymo ir niekada nenaudojama mokymui ar hiperparametrams. Papildyti (`augmentation`) įrašai į jį nepatenka, todėl testas atspindi natūralų pasiskirstymą.
3. **Bandomasis rinkinys (30)** - tik DI modelio / prompto patikrai ir kainai; į galutinį vertinimą neįtraukiamas.
4. **Dalijimas.** Mokymo duomenys dalijami stratifikuotai 80/20 (seed 42) **prieš** `fit`; TF-IDF žodynas mokomas tik iš mokymo dalies. Galutinis rezultatas - žmogaus testas.
5. **Modelis.** `TfidfVectorizer` (1-2 gramai, `min_df=2`, `sublinear_tf`) + `LogisticRegression(class_weight="balanced")` kiekvienam iš trijų laukų atskirai; palyginimas su `DummyClassifier(most_frequent)` tuo pačiu dalijimu.
6. **Klasių balansas.** `class_weight="balanced"`; klasės su <5 mokymo pavyzdžių nemokomos ir aiškiai nurodomos; trūkstamoms klasėms - tikslinis `--augment` (tik tikri GitHub įrašai, jokių sintetinių eilučių ir dirbtinio pavyzdžių dubliavimo); jei po papildymo klasė vis tiek per maža, rodyti `insufficient_data` / pažymėti kaip nepatikimą.
7. **Metrikos** kiekvienam laukui atskirai: **macro-F1 (pagrindinė)**, precision / recall / F1 kiekvienai klasei, confusion matrix, accuracy ir weighted-F1 kaip papildomos, bootstrap 95 % intervalai, testo pavyzdžių ir klasių skaičiai. Prioritetui ir sudėtingumui (tvarkos skalė) papildomai verta pateikti Cohen kappa su kvadratiniais svoriais (`sklearn.metrics.cohen_kappa_score`, naujos bibliotekos nereikia).
8. **DI žymų kokybė.** Skaičiuoti DI ir žmogaus sutapimą testo rinkinyje (Cohen kappa ir accuracy). Jei sutapimas prioritetui / sudėtingumui žemas, tai turi būti pasakyta darbe: DI žymos yra „silver“, o ne tiesa.
9. **Atsargumas.** Rezultatai teigiami tik po tikro `python -m tools.train_models`. Testo imties dydis (120) lemia plačius intervalus; klasės su <5 testo pavyzdžiais pažymimos „nepatikima“. Jei darbo vadovas reikalauja patikimesnio retų klasių vertinimo, žmogaus testą galima padidinti (pvz. iki ~200), bet tai papildomas rankinio darbo laikas.
10. **Rankinis darbas.** ~150 įrašų (120 + 30) rankinio žymėjimo; pagal EVALUATION_PLAN rekomenduojama bent dalį pažymėti antrą kartą nuoseklumui įvertinti.

## 9. Kita eiga (nuosekli)

1. Patvirtinti `feature:` filtro pataisą (7.1) - aš ją įgyvendinu su testu.
2. `python -m tools.pipeline --skip-import` (nemokama, GitHub nekviečia) - atrenka 120 + 30 įrašų.
3. Svetainėje pažymėti bandomąjį rinkinį (~30).
4. `python -m tools.ai_label --subset pilot --limit 40 --max-cost-usd 0.10 --execute` (apie centus), tada `python -m tools.class_report` - DI ir žmogaus sutapimas, faktinė kaina.
5. Pažymėti testavimo rinkinį (~120), nematant DI atsakymų.
6. Dry-run viso rinkinio (`python -m tools.ai_label --limit 4000`), tada su `--max-cost-usd 3 --execute`.
7. `python -m tools.class_report`; jei trūksta klasių - `python -m tools.collect --augment`, tada žymėjimas tik naujiems įrašams.
8. `python -m tools.train_models` -> `models/training_report.md`.
