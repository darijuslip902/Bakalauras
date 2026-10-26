# Duomenų anotavimo gairės

## Kodėl reikia anotavimo

Klasifikatorius mokomas iš pavyzdžių su žinoma teisinga žyma. GitHub etiketė gali reikšti komandą, leidimą, būseną ar kitą savybę, todėl jos negalima automatiškai laikyti kategorija / sudėtingumu / prioritetu. Kiekvienam issue kiekvienas laukas žymimas atskirai. Neaiškus laukas lieka tuščias.

Anotacijos – žmogaus sprendimas pagal apibrėžtas taisykles, o ne neabejotina objektyvi tiesa. Bakalauro darbe reikia aprašyti šias taisykles.

## Kategorija (viena pagrindinė)

- `ui` – naudotojo sąsajos vaizdavimas, prieinamumas, naršyklės sąveika.
- `backend_api` – serverio logika, API, integracijų verslo logika.
- `database_data` – duomenų saugojimas, užklausos, migracijos, duomenų vientisumas.
- `security` – autentifikavimas, autorizavimas, duomenų atskleidimas, saugumo pažeidimai.
- `performance` – lėtumas, perteklinis atminties/CPU/IO naudojimas.
- `build_deployment` – CI/CD, build, konfigūravimas ir paleidimas.
- `documentation` – dokumentacijos klaida, jei tyrimo apimtis ją įtraukia.
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
5. Jaunu / neskaidru atveju pierakstīt īsu iemeslu darba piezīmēs vai atsevišķā pētījuma dokumentā, nevis mainīt source issue.
6. Ja iespējams, atkārtoti anotēt daļu piemēru pēc laika vai ar otru vērtētāju, lai novērtētu konsekvenci.

## Datu sākotnė atranka

Pirmiausia rinkti aiškiai klaidoms skirtas issues. Jei duomenų šaltinio repo naudoja issues ir funkcijų prašymams, išfiltruoti feature requests, klausimus ir diskusijas pagal dokumentuotą atrankos politiką. Filtravimą daryti pagal peržiūrimą kriterijų rinkinį, o ne tyliai išmesti nepatogius pavyzdžius.

Jei sistema nesurenka pakankamai pavyzdžių konkrečiai klasei, jos prognozės kokybės nereikia teigti kaip patvirtintos. Pateikti klasės skaičių ir duomenų trūkumą.
