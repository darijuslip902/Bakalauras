# Klaidų klasifikavimo modelių mokymo ataskaita

Modelio versija: `20261113-125330` · sukurta 2026-11-13T12:53:30+00:00 · seed 42

Metodas: TF-IDF (1-2 gramos) + LogisticRegression (class_weight=balanced). Duomenys padalyti stratifikuotai (80 / 20) prieš mokymą; TF-IDF žodynas sudaromas tik iš mokymo dalies.

## Duomenų kilmė

Vieši GitHub issues, importuoti tik skaitymo režimu (5B be autentifikacijos, 5D su GitHub žetonu). Pull request įrašai, dublikatai, ne klaidų etiketės (enhancement, question, duplicate ir pan.) ir per trumpi aprašymai atmesti prieš DI žymėjimą.

| Repozitorija | Importuota | Iš jų papildymas | Tinkami | Trumpi | Dublikatai | Ne klaidų etiketės | Bandomasis | Testas | Mokymui (pagr.) | Mokymui (papild.) |
|---|---|---|---|---|---|---|---|---|---|---|
| angular/angular | 1491 | 0 | 1478 | 2 | 1 | 10 | 0 | 44 | 409 | 0 |
| ansible/ansible | 201 | 0 | 201 | 0 | 0 | 0 | 2 | 8 | 181 | 0 |
| aquasecurity/trivy | 600 | 0 | 596 | 0 | 1 | 3 | 0 | 18 | 438 | 0 |
| bazelbuild/bazel | 600 | 0 | 598 | 1 | 0 | 1 | 0 | 18 | 428 | 0 |
| ClickHouse/ClickHouse | 900 | 0 | 893 | 0 | 0 | 7 | 0 | 27 | 458 | 0 |
| cockroachdb/cockroach | 1059 | 0 | 1003 | 0 | 0 | 56 | 0 | 30 | 312 | 0 |
| docker/docs | 669 | 0 | 641 | 5 | 13 | 10 | 0 | 19 | 340 | 0 |
| dotnet/aspnetcore | 700 | 0 | 417 | 0 | 1 | 282 | 0 | 12 | 369 | 0 |
| dotnet/docs | 414 | 0 | 411 | 1 | 2 | 0 | 0 | 12 | 61 | 0 |
| dotnet/runtime | 1000 | 0 | 975 | 0 | 0 | 25 | 0 | 29 | 301 | 0 |
| drizzle-team/drizzle-orm | 500 | 0 | 495 | 2 | 0 | 3 | 0 | 15 | 435 | 0 |
| elastic/elasticsearch | 200 | 0 | 199 | 0 | 0 | 1 | 2 | 8 | 191 | 0 |
| expressjs/express | 161 | 0 | 152 | 3 | 1 | 5 | 0 | 5 | 122 | 0 |
| facebook/react | 200 | 0 | 199 | 0 | 1 | 0 | 2 | 8 | 150 | 0 |
| flutter/flutter | 1945 | 0 | 1539 | 13 | 0 | 393 | 0 | 46 | 330 | 0 |
| godotengine/godot | 1000 | 0 | 989 | 0 | 0 | 11 | 0 | 30 | 455 | 0 |
| golang/go | 900 | 0 | 803 | 0 | 0 | 97 | 0 | 24 | 279 | 0 |
| gradle/gradle | 600 | 0 | 558 | 1 | 0 | 41 | 0 | 17 | 412 | 0 |
| grafana/grafana | 253 | 0 | 253 | 0 | 0 | 0 | 3 | 11 | 237 | 0 |
| grpc/grpc | 400 | 0 | 400 | 0 | 0 | 0 | 0 | 12 | 333 | 0 |
| hashicorp/terraform | 200 | 0 | 197 | 0 | 0 | 3 | 2 | 8 | 177 | 0 |
| hashicorp/vault | 700 | 0 | 695 | 0 | 0 | 5 | 0 | 21 | 436 | 0 |
| helm/helm | 600 | 0 | 595 | 0 | 0 | 5 | 0 | 18 | 432 | 0 |
| home-assistant/core | 760 | 0 | 748 | 0 | 0 | 12 | 0 | 22 | 279 | 0 |
| home-assistant/home-assistant.io | 264 | 0 | 264 | 0 | 0 | 0 | 0 | 8 | 96 | 0 |
| keycloak/keycloak | 1000 | 0 | 996 | 1 | 3 | 0 | 0 | 30 | 442 | 0 |
| kubernetes/kubernetes | 963 | 0 | 952 | 0 | 0 | 11 | 2 | 31 | 573 | 0 |
| kubernetes/website | 489 | 0 | 191 | 15 | 2 | 281 | 0 | 6 | 89 | 0 |
| mdn/content | 810 | 0 | 728 | 11 | 9 | 62 | 0 | 22 | 138 | 0 |
| metabase/metabase | 200 | 0 | 200 | 0 | 0 | 0 | 2 | 8 | 190 | 0 |
| microsoft/PowerToys | 1200 | 0 | 999 | 1 | 0 | 200 | 0 | 30 | 359 | 0 |
| microsoft/vscode | 1202 | 0 | 1171 | 1 | 0 | 30 | 3 | 39 | 630 | 0 |
| microsoft/vscode-docs | 754 | 0 | 355 | 39 | 24 | 336 | 0 | 11 | 172 | 0 |
| moby/moby | 600 | 0 | 578 | 0 | 0 | 22 | 0 | 17 | 421 | 0 |
| nestjs/nest | 217 | 0 | 213 | 0 | 0 | 4 | 0 | 6 | 188 | 0 |
| nextauthjs/next-auth | 700 | 0 | 307 | 1 | 0 | 392 | 0 | 9 | 267 | 0 |
| nextcloud/server | 251 | 0 | 250 | 0 | 1 | 0 | 3 | 11 | 228 | 0 |
| nrwl/nx | 600 | 0 | 600 | 0 | 0 | 0 | 0 | 18 | 439 | 0 |
| openssl/openssl | 600 | 0 | 553 | 7 | 9 | 31 | 0 | 17 | 331 | 0 |
| pandas-dev/pandas | 1193 | 0 | 1061 | 4 | 0 | 128 | 2 | 34 | 529 | 0 |
| pingcap/tidb | 1926 | 0 | 1722 | 0 | 1 | 203 | 0 | 51 | 445 | 0 |
| pnpm/pnpm | 600 | 0 | 592 | 0 | 1 | 7 | 0 | 18 | 452 | 0 |
| prometheus/prometheus | 150 | 0 | 150 | 0 | 0 | 0 | 2 | 6 | 129 | 0 |
| python/cpython | 308 | 0 | 307 | 0 | 0 | 1 | 3 | 13 | 278 | 0 |
| pytorch/pytorch | 1282 | 0 | 1057 | 0 | 0 | 225 | 0 | 32 | 362 | 0 |
| rust-lang/cargo | 600 | 0 | 579 | 0 | 0 | 21 | 0 | 17 | 417 | 0 |
| rust-lang/rust | 2044 | 0 | 1846 | 1 | 2 | 195 | 0 | 55 | 408 | 0 |
| sequelize/sequelize | 500 | 0 | 496 | 2 | 1 | 1 | 0 | 15 | 404 | 0 |
| spring-projects/spring-boot | 700 | 0 | 664 | 34 | 0 | 2 | 0 | 20 | 109 | 0 |
| spring-projects/spring-security | 800 | 0 | 647 | 28 | 7 | 118 | 0 | 19 | 308 | 0 |
| sqlalchemy/sqlalchemy | 202 | 0 | 201 | 0 | 0 | 1 | 2 | 8 | 183 | 0 |
| supabase/supabase | 600 | 0 | 594 | 2 | 4 | 0 | 0 | 18 | 277 | 0 |
| typeorm/typeorm | 600 | 0 | 596 | 1 | 0 | 3 | 0 | 18 | 402 | 0 |
| vitejs/vite | 616 | 0 | 613 | 0 | 0 | 3 | 0 | 18 | 409 | 0 |
| vuejs/docs | 800 | 0 | 665 | 29 | 25 | 81 | 0 | 20 | 221 | 0 |
| webpack/webpack | 600 | 0 | 599 | 1 | 0 | 0 | 0 | 18 | 427 | 0 |
| zaproxy/zaproxy | 600 | 0 | 515 | 0 | 0 | 85 | 0 | 15 | 379 | 0 |

Mokymo įrašų: **18267**; testo įrašų su etalonu (tinka, visos 3 žymos): **901** iš 1120 atrinktų (žmogaus žymos: 0, DI: 901, mišrios: 0); bandomojo rinkinio įrašų: 30.

## DI žymėjimo metodika

Žymos sugeneruotos modeliu `claude-haiku-5-5`, prompt versija `v1`: struktūrizuotas JSON atsakymas su leistinomis reikšmėmis, taisyklės iš `docs/DATA_LABELING.md`, kiekvienas atsakymas papildomai validuotas. Žmogaus žyma visada turi pirmenybę prieš DI žymą. Mokymui naudojami tik „Tinka mokymui“ įrašai su visomis trimis žymomis.

DI užklausų: 23884; sėkmingų žymų: 23884, netinkamų atsakymų: 0; tinka mokymui: 19412, netinka: 4472. Tokenai: įvestis 61312405, išvestis 3000847. Faktinė kaina pagal API `usage`: $4.5948.

## Kategorija

**Mokymo duomenų klasių pasiskirstymas**

| Klasė | Pavyzdžių |
|---|---|
| Naudotojo sąsaja (`ui`) | 1573 |
| Serveris / API (`backend_api`) | 7291 |
| Duomenų bazė / duomenys (`database_data`) | 1502 |
| Saugumas (`security`) | 707 |
| Našumas (`performance`) | 2376 |
| Kompiliavimas / diegimas (`build_deployment`) | 3148 |
| Dokumentacija (`documentation`) | 1236 |
| Kita (`other`) | 434 |

Mokymo dalis: 14613, validacijos dalis: 3654.

**Rezultatai**

| Vertinimas | Pavyzdžių | Accuracy | Macro-F1 | Weighted-F1 | Accuracy 95 % CI | Macro-F1 95 % CI |
|---|---|---|---|---|---|---|
| DI validacija – modelis | 3654 | 0.668 | 0.645 | 0.670 |  |  |
| DI validacija – daugumos klasės baseline | 3654 | 0.399 | 0.071 | 0.228 |  |  |
| Testas (di žymos) – modelis | 901 | 0.643 | 0.622 | 0.639 | 0.613–0.673 | 0.584–0.656 |
| Testas (di žymos) – daugumos klasės baseline | 901 | 0.404 | 0.072 | 0.233 |  |  |

**Testas (di žymos): kiekvienos klasės rezultatai**

| Klasė | Precision | Recall | F1 | Pavyzdžių |
|---|---|---|---|---|
| Serveris / API (`backend_api`) | 0.810 | 0.456 | 0.583 | 364 |
| Kompiliavimas / diegimas (`build_deployment`) | 0.605 | 0.737 | 0.664 | 137 |
| Duomenų bazė / duomenys (`database_data`) | 0.621 | 0.811 | 0.703 | 95 |
| Dokumentacija (`documentation`) | 0.849 | 0.833 | 0.841 | 54 |
| Kita (`other`) | 0.220 | 0.375 | 0.277 | 24 |
| Našumas (`performance`) | 0.662 | 0.835 | 0.738 | 115 |
| Saugumas (`security`) | 0.400 | 0.667 | 0.500 | 36 |
| Naudotojo sąsaja (`ui`) | 0.575 | 0.803 | 0.670 | 76 |

**Testas (di žymos): klaidų matrica**

| Tikra \ Prognozė | backend_api | build_deployment | database_data | documentation | other | performance | security | ui |
|---|---|---|---|---|---|---|---|---|
| backend_api | 166 | 49 | 42 | 3 | 20 | 38 | 25 | 21 |
| build_deployment | 9 | 101 | 1 | 1 | 7 | 4 | 5 | 9 |
| database_data | 11 | 2 | 77 | 0 | 2 | 1 | 1 | 1 |
| documentation | 4 | 1 | 0 | 45 | 0 | 0 | 2 | 2 |
| other | 2 | 2 | 1 | 1 | 9 | 6 | 0 | 3 |
| performance | 2 | 7 | 1 | 0 | 1 | 96 | 0 | 8 |
| security | 6 | 4 | 1 | 0 | 0 | 0 | 24 | 1 |
| ui | 5 | 1 | 1 | 3 | 2 | 0 | 3 | 61 |

**DI validacija: klaidų matrica**

| Tikra \ Prognozė | backend_api | build_deployment | database_data | documentation | other | performance | security | ui |
|---|---|---|---|---|---|---|---|---|
| backend_api | 719 | 238 | 194 | 11 | 67 | 24 | 122 | 83 |
| build_deployment | 76 | 462 | 17 | 4 | 30 | 14 | 10 | 17 |
| database_data | 28 | 9 | 247 | 0 | 3 | 2 | 6 | 6 |
| documentation | 14 | 11 | 5 | 210 | 1 | 0 | 0 | 6 |
| other | 18 | 7 | 1 | 1 | 38 | 10 | 4 | 8 |
| performance | 20 | 11 | 15 | 0 | 7 | 403 | 5 | 14 |
| security | 21 | 11 | 9 | 0 | 2 | 1 | 89 | 8 |
| ui | 5 | 7 | 4 | 9 | 8 | 3 | 7 | 272 |

## Sudėtingumas

**Mokymo duomenų klasių pasiskirstymas**

| Klasė | Pavyzdžių |
|---|---|
| Mažas (`low`) | 4605 |
| Vidutinis (`medium`) | 10085 |
| Didelis (`high`) | 3577 |

Mokymo dalis: 14613, validacijos dalis: 3654.

**Rezultatai**

| Vertinimas | Pavyzdžių | Accuracy | Macro-F1 | Weighted-F1 | Accuracy 95 % CI | Macro-F1 95 % CI |
|---|---|---|---|---|---|---|
| DI validacija – modelis | 3654 | 0.658 | 0.646 | 0.660 |  |  |
| DI validacija – daugumos klasės baseline | 3654 | 0.552 | 0.237 | 0.393 |  |  |
| Testas (di žymos) – modelis | 901 | 0.697 | 0.691 | 0.698 | 0.666–0.727 | 0.660–0.722 |
| Testas (di žymos) – daugumos klasės baseline | 901 | 0.530 | 0.231 | 0.368 |  |  |

**Testas (di žymos): kiekvienos klasės rezultatai**

| Klasė | Precision | Recall | F1 | Pavyzdžių |
|---|---|---|---|---|
| Didelis (`high`) | 0.633 | 0.778 | 0.698 | 230 |
| Mažas (`low`) | 0.655 | 0.679 | 0.667 | 193 |
| Vidutinis (`medium`) | 0.761 | 0.665 | 0.710 | 478 |

**Testas (di žymos): klaidų matrica**

| Tikra \ Prognozė | high | low | medium |
|---|---|---|---|
| high | 179 | 4 | 47 |
| low | 9 | 131 | 53 |
| medium | 95 | 65 | 318 |

**DI validacija: klaidų matrica**

| Tikra \ Prognozė | high | low | medium |
|---|---|---|---|
| high | 508 | 20 | 188 |
| low | 39 | 584 | 298 |
| medium | 385 | 320 | 1312 |

## Prioritetas

**Mokymo duomenų klasių pasiskirstymas**

| Klasė | Pavyzdžių |
|---|---|
| P0 – kritinis (`P0_critical`) | 21 |
| P1 – aukštas (`P1_high`) | 4193 |
| P2 – vidutinis (`P2_medium`) | 10748 |
| P3 – žemas (`P3_low`) | 3305 |

Mokymo dalis: 14613, validacijos dalis: 3654.

**Rezultatai**

| Vertinimas | Pavyzdžių | Accuracy | Macro-F1 | Weighted-F1 | Accuracy 95 % CI | Macro-F1 95 % CI |
|---|---|---|---|---|---|---|
| DI validacija – modelis | 3654 | 0.662 | 0.547 | 0.667 |  |  |
| DI validacija – daugumos klasės baseline | 3654 | 0.588 | 0.185 | 0.436 |  |  |
| Testas (di žymos) – modelis | 901 | 0.659 | 0.482 | 0.661 | 0.627–0.689 | 0.457–0.658 |
| Testas (di žymos) – daugumos klasės baseline | 901 | 0.556 | 0.179 | 0.397 |  |  |

**Testas (di žymos): kiekvienos klasės rezultatai**

| Klasė | Precision | Recall | F1 | Pavyzdžių |
|---|---|---|---|---|
| P0 – kritinis (`P0_critical`) | 0.000 | 0.000 | 0.000 | 2 |
| P1 – aukštas (`P1_high`) | 0.597 | 0.679 | 0.636 | 262 |
| P2 – vidutinis (`P2_medium`) | 0.744 | 0.651 | 0.694 | 501 |
| P3 – žemas (`P3_low`) | 0.545 | 0.662 | 0.598 | 136 |

**Testas (di žymos): klaidų matrica**

| Tikra \ Prognozė | P0_critical | P1_high | P2_medium | P3_low |
|---|---|---|---|---|
| P0_critical | 0 | 2 | 0 | 0 |
| P1_high | 0 | 178 | 75 | 9 |
| P2_medium | 0 | 109 | 326 | 66 |
| P3_low | 0 | 9 | 37 | 90 |

**DI validacija: klaidų matrica**

| Tikra \ Prognozė | P0_critical | P1_high | P2_medium | P3_low |
|---|---|---|---|---|
| P0_critical | 1 | 3 | 0 | 0 |
| P1_high | 3 | 558 | 257 | 21 |
| P2_medium | 0 | 483 | 1408 | 259 |
| P3_low | 0 | 31 | 177 | 453 |

## Apribojimai

- Kategorija: testo etalonas – DI žymos ({'ai': 901}); metrikos rodo atitikimą DI žymoms, o ne žmogaus patvirtintai tiesai.
- Sudėtingumas: testo etalonas – DI žymos ({'ai': 901}); metrikos rodo atitikimą DI žymoms, o ne žmogaus patvirtintai tiesai.
- Prioritetas: testo etalonas – DI žymos ({'ai': 901}); metrikos rodo atitikimą DI žymoms, o ne žmogaus patvirtintai tiesai.
- Prioritetas: mažiau nei 5 testo pavyzdžiai klasėms `P0_critical` – jų metrikos nepatikimos.
- Mokymo žymos daugiausia sugeneruotos DI modelio ir nėra garantuotai teisingos; validacijos dalies metrikos rodo, kaip modelis atkartoja DI žymas, o ne tikrąją kokybę.
- Galutinė kokybė vertinama tik nepriklausomu testavimo rinkiniu, kuris į mokymą nepatenka; jis mažas, todėl pateikiami bootstrap 95 % intervalai, o atskirų klasių metrikos labai neapibrėžtos.
- Bandomojo rinkinio įrašai buvo naudoti DI modelio / taisyklių pasirinkimui, todėl į galutinį vertinimą neįtraukti.
- Tikslinis papildymas (source_kind = augmentation) keičia klasių proporcijas mokymo rinkinyje; testavimo rinkinys atrinktas tik iš pagrindinio rinkimo įrašų ir nepapildytas.
- Duomenys – vieši GitHub issues iš atrinktų projektų; rezultatai gali neperkelti į kitų sistemų klaidų pranešimus.
- LogisticRegression įvertis nėra kalibruota tikimybė.
