# Klaidų klasifikavimo modelių mokymo ataskaita

Modelio versija: `20261110-143223` · sukurta 2026-11-10T14:32:23+00:00 · seed 42

Metodas: TF-IDF (1-2 gramos) + LogisticRegression (class_weight=balanced). Duomenys padalyti stratifikuotai (80 / 20) prieš mokymą; TF-IDF žodynas sudaromas tik iš mokymo dalies.

## Duomenų kilmė

Vieši GitHub issues, importuoti tik skaitymo režimu be autentifikacijos. Pull request įrašai, dublikatai, ne klaidų etiketės (enhancement, question, duplicate ir pan.) ir per trumpi aprašymai atmesti prieš DI žymėjimą.

| Repozitorija | Importuota | Iš jų papildymas | Tinkami | Trumpi | Dublikatai | Ne klaidų etiketės | Bandomasis | Testas | Mokymui (pagr.) | Mokymui (papild.) |
|---|---|---|---|---|---|---|---|---|---|---|
| ansible/ansible | 201 | 0 | 201 | 0 | 0 | 0 | 2 | 8 | 181 | 0 |
| elastic/elasticsearch | 200 | 0 | 199 | 0 | 0 | 1 | 2 | 8 | 191 | 0 |
| facebook/react | 200 | 0 | 199 | 0 | 1 | 0 | 2 | 8 | 157 | 0 |
| grafana/grafana | 253 | 0 | 253 | 0 | 0 | 0 | 3 | 11 | 237 | 0 |
| hashicorp/terraform | 200 | 0 | 197 | 0 | 0 | 3 | 2 | 8 | 177 | 0 |
| kubernetes/kubernetes | 241 | 0 | 236 | 0 | 0 | 5 | 2 | 10 | 206 | 0 |
| metabase/metabase | 200 | 0 | 200 | 0 | 0 | 0 | 2 | 8 | 190 | 0 |
| microsoft/vscode | 307 | 0 | 304 | 1 | 0 | 2 | 3 | 13 | 274 | 0 |
| nextcloud/server | 251 | 0 | 250 | 0 | 1 | 0 | 3 | 11 | 229 | 0 |
| pandas-dev/pandas | 193 | 0 | 187 | 0 | 0 | 6 | 2 | 8 | 176 | 0 |
| prometheus/prometheus | 150 | 0 | 150 | 0 | 0 | 0 | 2 | 6 | 129 | 0 |
| python/cpython | 308 | 0 | 307 | 0 | 0 | 1 | 3 | 13 | 278 | 0 |
| sqlalchemy/sqlalchemy | 202 | 0 | 201 | 0 | 0 | 1 | 2 | 8 | 183 | 0 |

Mokymo įrašų: **2608**; testo įrašų su etalonu (tinka, visos 3 žymos): **112** iš 120 atrinktų (žmogaus žymos: 0, DI: 112, mišrios: 0); bandomojo rinkinio įrašų: 30.

## DI žymėjimo metodika

Žymos sugeneruotos modeliu `claude-haiku-5-5`, prompt versija `v1`: struktūrizuotas JSON atsakymas su leistinomis reikšmėmis, taisyklės iš `docs/DATA_LABELING.md`, kiekvienas atsakymas papildomai validuotas. Žmogaus žyma visada turi pirmenybę prieš DI žymą. Mokymui naudojami tik „Tinka mokymui“ įrašai su visomis trimis žymomis.

DI užklausų: 2884; sėkmingų žymų: 2884, netinkamų atsakymų: 0; tinka mokymui: 2721, netinka: 163. Tokenai: įvestis 7879128, išvestis 366383. Faktinė kaina pagal API `usage`: $0.6047.

## Kategorija

**Mokymo duomenų klasių pasiskirstymas**

| Klasė | Pavyzdžių |
|---|---|
| Naudotojo sąsaja (`ui`) | 436 |
| Serveris / API (`backend_api`) | 1442 |
| Duomenų bazė / duomenys (`database_data`) | 217 |
| Saugumas (`security`) | 119 |
| Našumas (`performance`) | 109 |
| Kompiliavimas / diegimas (`build_deployment`) | 160 |
| Dokumentacija (`documentation`) | 19 |
| Kita (`other`) | 106 |

Mokymo dalis: 2086, validacijos dalis: 522.

**Rezultatai**

| Vertinimas | Pavyzdžių | Accuracy | Macro-F1 | Weighted-F1 | Accuracy 95 % CI | Macro-F1 95 % CI |
|---|---|---|---|---|---|---|
| DI validacija – modelis | 522 | 0.607 | 0.470 | 0.618 |  |  |
| DI validacija – daugumos klasės baseline | 522 | 0.554 | 0.089 | 0.395 |  |  |
| Testas (di žymos) – modelis | 112 | 0.616 | 0.492 | 0.616 | 0.527–0.696 | 0.380–0.652 |
| Testas (di žymos) – daugumos klasės baseline | 112 | 0.571 | 0.091 | 0.416 |  |  |

**Testas (di žymos): kiekvienos klasės rezultatai**

| Klasė | Precision | Recall | F1 | Pavyzdžių |
|---|---|---|---|---|
| Serveris / API (`backend_api`) | 0.795 | 0.547 | 0.648 | 64 |
| Kompiliavimas / diegimas (`build_deployment`) | 0.333 | 0.250 | 0.286 | 4 |
| Duomenų bazė / duomenys (`database_data`) | 0.444 | 0.727 | 0.552 | 11 |
| Dokumentacija (`documentation`) | 0.000 | 0.000 | 0.000 | 1 |
| Kita (`other`) | 0.500 | 0.833 | 0.625 | 6 |
| Našumas (`performance`) | 0.500 | 0.667 | 0.571 | 3 |
| Saugumas (`security`) | 0.462 | 0.750 | 0.571 | 8 |
| Naudotojo sąsaja (`ui`) | 0.600 | 0.800 | 0.686 | 15 |

**Testas (di žymos): klaidų matrica**

| Tikra \ Prognozė | backend_api | build_deployment | database_data | documentation | other | performance | security | ui |
|---|---|---|---|---|---|---|---|---|
| backend_api | 35 | 1 | 9 | 0 | 4 | 2 | 5 | 8 |
| build_deployment | 0 | 1 | 1 | 0 | 1 | 0 | 1 | 0 |
| database_data | 3 | 0 | 8 | 0 | 0 | 0 | 0 | 0 |
| documentation | 1 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| other | 0 | 1 | 0 | 0 | 5 | 0 | 0 | 0 |
| performance | 1 | 0 | 0 | 0 | 0 | 2 | 0 | 0 |
| security | 2 | 0 | 0 | 0 | 0 | 0 | 6 | 0 |
| ui | 2 | 0 | 0 | 0 | 0 | 0 | 1 | 12 |

**DI validacija: klaidų matrica**

| Tikra \ Prognozė | backend_api | build_deployment | database_data | documentation | other | performance | security | ui |
|---|---|---|---|---|---|---|---|---|
| backend_api | 165 | 7 | 47 | 3 | 13 | 5 | 17 | 32 |
| build_deployment | 5 | 14 | 0 | 0 | 7 | 0 | 2 | 4 |
| database_data | 12 | 1 | 25 | 0 | 0 | 1 | 2 | 2 |
| documentation | 1 | 0 | 1 | 0 | 0 | 0 | 0 | 2 |
| other | 1 | 1 | 0 | 0 | 19 | 0 | 0 | 0 |
| performance | 6 | 1 | 1 | 0 | 0 | 10 | 1 | 3 |
| security | 5 | 1 | 2 | 0 | 1 | 1 | 11 | 3 |
| ui | 6 | 0 | 1 | 0 | 3 | 0 | 4 | 73 |

## Sudėtingumas

**Mokymo duomenų klasių pasiskirstymas**

| Klasė | Pavyzdžių |
|---|---|
| Mažas (`low`) | 694 |
| Vidutinis (`medium`) | 1564 |
| Didelis (`high`) | 350 |

Mokymo dalis: 2086, validacijos dalis: 522.

**Rezultatai**

| Vertinimas | Pavyzdžių | Accuracy | Macro-F1 | Weighted-F1 | Accuracy 95 % CI | Macro-F1 95 % CI |
|---|---|---|---|---|---|---|
| DI validacija – modelis | 522 | 0.602 | 0.563 | 0.606 |  |  |
| DI validacija – daugumos klasės baseline | 522 | 0.600 | 0.250 | 0.450 |  |  |
| Testas (di žymos) – modelis | 112 | 0.652 | 0.609 | 0.657 | 0.571–0.732 | 0.513–0.700 |
| Testas (di žymos) – daugumos klasės baseline | 112 | 0.580 | 0.245 | 0.426 |  |  |

**Testas (di žymos): kiekvienos klasės rezultatai**

| Klasė | Precision | Recall | F1 | Pavyzdžių |
|---|---|---|---|---|
| Didelis (`high`) | 0.391 | 0.474 | 0.429 | 19 |
| Mažas (`low`) | 0.704 | 0.679 | 0.691 | 28 |
| Vidutinis (`medium`) | 0.726 | 0.692 | 0.709 | 65 |

**Testas (di žymos): klaidų matrica**

| Tikra \ Prognozė | high | low | medium |
|---|---|---|---|
| high | 9 | 0 | 10 |
| low | 2 | 19 | 7 |
| medium | 12 | 8 | 45 |

**DI validacija: klaidų matrica**

| Tikra \ Prognozė | high | low | medium |
|---|---|---|---|
| high | 38 | 4 | 28 |
| low | 7 | 76 | 56 |
| medium | 34 | 79 | 200 |

## Prioritetas

**Mokymo duomenų klasių pasiskirstymas**

| Klasė | Pavyzdžių |
|---|---|
| P0 – kritinis (`P0_critical`) | 1 |
| P1 – aukštas (`P1_high`) | 620 |
| P2 – vidutinis (`P2_medium`) | 1570 |
| P3 – žemas (`P3_low`) | 417 |

Klasės, neįtrauktos dėl per mažo kiekio (< 5): `P0_critical` (1).

Mokymo dalis: 2085, validacijos dalis: 522.

**Rezultatai**

| Vertinimas | Pavyzdžių | Accuracy | Macro-F1 | Weighted-F1 | Accuracy 95 % CI | Macro-F1 95 % CI |
|---|---|---|---|---|---|---|
| DI validacija – modelis | 522 | 0.588 | 0.557 | 0.594 |  |  |
| DI validacija – daugumos klasės baseline | 522 | 0.602 | 0.250 | 0.452 |  |  |
| Testas (di žymos) – modelis | 112 | 0.616 | 0.590 | 0.614 | 0.527–0.705 | 0.487–0.683 |
| Testas (di žymos) – daugumos klasės baseline | 112 | 0.545 | 0.235 | 0.384 |  |  |

**Testas (di žymos): kiekvienos klasės rezultatai**

| Klasė | Precision | Recall | F1 | Pavyzdžių |
|---|---|---|---|---|
| P1 – aukštas (`P1_high`) | 0.561 | 0.742 | 0.639 | 31 |
| P2 – vidutinis (`P2_medium`) | 0.685 | 0.607 | 0.643 | 61 |
| P3 – žemas (`P3_low`) | 0.529 | 0.450 | 0.486 | 20 |

**Testas (di žymos): klaidų matrica**

| Tikra \ Prognozė | P1_high | P2_medium | P3_low |
|---|---|---|---|
| P1_high | 23 | 8 | 0 |
| P2_medium | 16 | 37 | 8 |
| P3_low | 2 | 9 | 9 |

**DI validacija: klaidų matrica**

| Tikra \ Prognozė | P1_high | P2_medium | P3_low |
|---|---|---|---|
| P1_high | 75 | 45 | 4 |
| P2_medium | 75 | 186 | 53 |
| P3_low | 6 | 32 | 46 |

## Apribojimai

- Kategorija: testo etalonas – DI žymos ({'ai': 112}); metrikos rodo atitikimą DI žymoms, o ne žmogaus patvirtintai tiesai.
- Kategorija: mažiau nei 5 testo pavyzdžiai klasėms `build_deployment`, `documentation`, `performance` – jų metrikos nepatikimos.
- Sudėtingumas: testo etalonas – DI žymos ({'ai': 112}); metrikos rodo atitikimą DI žymoms, o ne žmogaus patvirtintai tiesai.
- Prioritetas: modelis nemoka klasių `P0_critical` (1) – per mažai mokymo pavyzdžių.
- Prioritetas: testo etalonas – DI žymos ({'ai': 112}); metrikos rodo atitikimą DI žymoms, o ne žmogaus patvirtintai tiesai.
- Mokymo žymos daugiausia sugeneruotos DI modelio ir nėra garantuotai teisingos; validacijos dalies metrikos rodo, kaip modelis atkartoja DI žymas, o ne tikrąją kokybę.
- Galutinė kokybė vertinama tik nepriklausomu testavimo rinkiniu, kuris į mokymą nepatenka; jis mažas, todėl pateikiami bootstrap 95 % intervalai, o atskirų klasių metrikos labai neapibrėžtos.
- Bandomojo rinkinio įrašai buvo naudoti DI modelio / taisyklių pasirinkimui, todėl į galutinį vertinimą neįtraukti.
- Tikslinis papildymas (source_kind = augmentation) keičia klasių proporcijas mokymo rinkinyje; testavimo rinkinys atrinktas tik iš pagrindinio rinkimo įrašų ir nepapildytas.
- Duomenys – vieši GitHub issues iš atrinktų projektų; rezultatai gali neperkelti į kitų sistemų klaidų pranešimus.
- LogisticRegression įvertis nėra kalibruota tikimybė.
