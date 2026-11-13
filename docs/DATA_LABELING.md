# Duomenų anotavimo gairės

## Kodėl reikia anotavimo

Klasifikatorius mokomas iš pavyzdžių su žinoma teisinga žyma. GitHub etiketė gali reikšti komandą, leidimą, būseną ar kitą savybę, todėl jos negalima automatiškai laikyti kategorija / sudėtingumu / prioritetu. Kiekvienam issue kiekvienas laukas žymimas atskirai. Neaiškus laukas lieka tuščias.

Anotacijos – žmogaus arba DI sprendimas pagal apibrėžtas taisykles, o ne neabejotina objektyvi tiesa. Bakalauro darbe reikia aprašyti šias taisykles.

## Kategorija (viena pagrindinė)

- `ui` – naudotojo sąsajos vaizdavimas, prieinamumas, naršyklės sąveika.
- `backend_api` – serverio logika, API, integracijų verslo logika.
- `database_data` – duomenų saugojimas, užklausos, migracijos, duomenų vientisumas.
- `security` – autentifikavimas, autorizavimas, duomenų atskleidimas, saugumo pažeidimai.
- `performance` – lėtumas, perteklinis atminties/CPU/IO naudojimas.
- `build_deployment` – CI/CD, build, konfigūravimas ir paleidimas.
- `documentation` – dokumentacijos klaida (įtraukta į tyrimo apimtį).
- `other` – patvirtinta klaida, kuri netelpa kitur.

Jei issue liečia kelias sritis, rinktis pagrindinę pagal klaidos priežastį arba didžiausią poveikį. Jei to neįmanoma pagrįsti, nepažymėti kategorijos, kol nepatikslinta.

## Sudėtingumas

Sudėtingumą vertinti pagal tikėtiną analizės, pakeitimų ir testavimo apimtį, ne pagal aprašymo ilgį.

- `low` – lokalus, aiškus pakeitimas; mažai priklausomybių, paprastas patikrinimas.
- `medium` – keletas modulių arba sąveikų, reikia suprasti dalį sistemos ir atlikti kelis testus.
- `high` – daug komponentų / neaiški priežastis / architektūriniai pakeitimai / reikšminga migracija ar išsamus regresinis testavimas.

Jei aprašymas per trumpas nustatyti apimtį, laukas paliekamas tuščias.

## Prioritetas

Prioritetas yra remiantis įrodymu atliekamas poveikio ir skubos įvertinimas, ne vien įvykio sunkumo spėjimas.

- `P0_critical` – kritinis incidentas, aktyvus saugumo pažeidimas, masinis duomenų praradimas arba pagrindinė sistema neveikia be pagrįsto apėjimo būdo.
- `P1_high` – svarbi funkcija neveikia daugeliui naudotojų, didelis poveikis arba didelė rizika, nėra priimtino apėjimo.
- `P2_medium` – ribotas poveikis, egzistuoja apėjimo būdas arba sutrikimas veikia ne pagrindinį kelią.
- `P3_low` – kosmetinis, retas, nežymus poveikis arba patobulinimas, kuriam nereikia skubios reakcijos.

Nepriskirti P0 vien todėl, kad issue aprašyme yra žodis „critical“. Jei neaiški įtaka ar naudotojų apimtis, laukas paliekamas tuščias.

## Anotavimo procedūra

1. Perskaityti pavadinimą ir visą aprašymą.
2. Patikrinti turimą kontekstą ir GitHub label, bet nelaikyti jų automatiškai teisingomis.
3. Kiekvienam laukui pasirinkti reikšmę tik tada, kai yra pagrindas.
4. Nežinomą lauką palikti tuščią, o ne sugalvoti.
5. Jei atvejis neaiškus, trumpą pagrindimą užrašyti darbo pastabose ar atskirame tyrimo dokumente, o ne keisti šaltinio issue.
6. Jei įmanoma, po laiko iš naujo anotuoti dalį pavyzdžių arba paprašyti antro vertintojo, kad būtų galima įvertinti nuoseklumą.

## Tinkamumas mokymui

Atskirai nuo trijų klasifikavimo laukų žmogus pažymi, ar įrašas tinka mokymui: „Neįvertinta“ (numatyta), „Tinka mokymui“ arba „Netinka mokymui“. „Netinka“ žymimi funkcijų pasiūlymai, klausimai, diskusijos ir kiti ne klaidų įrašai. Mokymui naudojami tik „Tinka mokymui“ įrašai su visomis trimis reikšmėmis. Žmogaus tinkamumo žyma saugoma atskirai; DI žymėjimas taip pat nustato tinkamumą, o išankstinis filtras atmeta nekokybiškus įrašus.

## DI žymėjimas (5A etapas)

Didžioji mokymo rinkinio dalis žymima DI modeliu pagal tas pačias taisykles (jos perkeltos į `app/ml/ai_labeling.py` sisteminį promptą, versija `v1`; pakeitus taisykles reikia didinti versiją). DI papildomai pateikia trumpą pagrindimą (`reason`). DI žymos saugomos atskirai ir nekeičia žmogaus žymų. Masinio rankinio žymėjimo atsisakyta (2026-11-10): ir mokymo, ir testavimo rinkinio žymas sukuria DI (`python -m tools.ai_label --subset test|training`). Jei žmogaus žyma egzistuoja (30 bandomojo rinkinio įrašų), ji turi pirmenybę. DI žymų kokybė matuojama bandomajame rinkinyje (`python -m tools.class_report`): 2026-11-10 sutapimas su žmogaus žymomis – kategorija 62 %, sudėtingumas 55 %, prioritetas 72 % (29 įrašai), tinkamumas 97 % (30 įrašų). Tai maža imtis, bet rodo, kad DI žymos nėra tiesa; testavimo metrikos, paremtos DI žymomis, matuoja atitikimą Claude, ne žmogaus nuomonę.

## Automatinis išankstinis filtras (5B)

Prieš DI žymėjimą automatiškai atmetami: pull request įrašai, tikslūs teksto dublikatai, aprašymai trumpesni nei 30 simbolių ir įrašai su GitHub etiketėmis, rodančiomis, kad tai ne klaida (enhancement, feature, question, duplicate, invalid, wontfix, not a bug, support, discussion, proposal). Etiketės „documentation“ / „docs“ neatmetamos – dokumentacijos klaidos yra atskira kategorija. Tikslinis papildymas tik nurodo, iš kur importuoti daugiau įrašų; jų klases nustato DI arba žmogus.

Filtras pataisytas (2026-11-09): prieš ieškant raktažodžių pašalinamos nekenksmingos frazės – komponentų etiketės `feature: ...` (Nextcloud, `Feature:ES|QL`), būsenos etiketės `Needs Discussion` / `under-discussion` ir `*-unsupported` (`OS-unsupported`). Tikros ne klaidų etiketės (`enhancement`, `feature request`, `Type: Feature`, `question`, `duplicate`, `invalid`, `wontfix`, `support`, `proposal`, `discussion`...) ir toliau atmetamos. Pagal esamus duomenis tinkamų įrašų padaugėjo nuo 2774 iki 2884, atmestų pagal etiketę liko 19. Testai: `tests/test_ml_pipeline.py`.

## 5D papildymas

5D naudoti 54 patikrinti šaltiniai; GitHub etiketės yra kandidatų atrankos priemonė, ne klasės etalonas. Testas papildytas tik naujais nepažymėtais įrašais. Artimi testo dublikatai (kosinuso panašumas ≥ 0,9) pašalinami iš mokymo. Žymėjimo taisyklės ir prompt v1 nekeičiami. Galutiniai kiekiai ir metrikos – [mokymo ataskaitoje](../models/training_report.md). P0 paliekamas, tačiau jo F1 = 0; žmogaus peržiūra būtina.

## Pradinė duomenų atranka

Pirmiausia rinkti aiškiai klaidoms skirtas issues. Jei duomenų šaltinio repo naudoja issues ir funkcijų prašymams, išfiltruoti feature requests, klausimus ir diskusijas pagal dokumentuotą atrankos politiką. Filtravimą daryti pagal peržiūrimą kriterijų rinkinį, o ne tyliai išmesti nepatogius pavyzdžius.

Jei sistema nesurenka pakankamai pavyzdžių konkrečiai klasei, jos prognozės kokybės nereikia teigti kaip patvirtintos. Pateikti klasės skaičių ir duomenų trūkumą.
