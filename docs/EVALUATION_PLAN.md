# Modelio vertinimo planas bakalauro darbui

## 1. Tyrimo klausimas

Ar issue pavadinimo ir aprašymo teksto požymiai (TF-IDF) su prižiūrimu LogisticRegression klasifikatoriumi leidžia tiksliau nustatyti programinės įrangos klaidos kategoriją, prioritetą ir sudėtingumą negu paprastas daugumos klasės bazinis metodas?

Vertinti tris laukus atskirai. Galima turėti skirtingą pavyzdžių skaičių kiekvienam laukui, nes ne visos klaidos turės visas tris patvirtintas žymas.

## 2. Duomenų paruošimas ir kokybė

- Iš viešo GitHub importo gauti issue pavadinimą, aprašymą, etiketes, būseną, datą ir URL. Pagrindiniame eksperimentiniame rinkinyje naudoti GitHub įrašus, kurių kilmė ir anotavimas dokumentuoti.
- Svetainės klientų pateikti bug_reports įrašai pagal nutylėjimą nėra mokymo / testo duomenys. Juos galima įtraukti tik žmogui patvirtinus žymas ir aiškiai dokumentavus duomenų rinkinio sudarymo taisykles.
- Pull request įrašus išmesti.
- Dublikatus šalinti / identifikuoti prieš dalijant duomenis.
- Automatiškai neinterpretuoti visų GitHub label kaip ground truth: jos gali būti repo specifinės, prieštaringos arba nesusijusios su užduoties klasėmis.
- Mokyti iš žymų su aiškia kilme. Darbo vadovui pritarus, didžioji mokymo rinkinio dalis žymima išoriniu DI modeliu (`claude-haiku-5-5`, prompt versija `v1`, taisyklės iš `docs/DATA_LABELING.md`); kiekvienos DI žymos modelis, prompt versija, tokenai ir kaina saugomi `ai_annotations` lentelėje. Žmogaus žyma visada turi pirmenybę prieš DI žymą.
- Atskiras testavimo rinkinys (`python -m tools.select_test_set`, atsitiktinė atranka su seed) niekada nenaudojamas mokymui. Rankinio žymėjimo atsisakyta (2026-11-10), todėl jo etalonas – DI žymos (žmogaus žyma, jei yra, turi pirmenybę); ataskaita rodo etalono šaltinį (`reference`). Tokie rezultatai matuoja atitikimą Claude žymoms, o ne žmogaus patvirtintą tiesą; DI ir žmogaus sutapimas matuojamas bandomajame rinkinyje (30 įrašų, accuracy, macro-F1, confusion matrix), kuris į galutinį vertinimą neįtraukiamas.
- Peržiūros slenksčiai svetainėje (kategorija 0.40, sudėtingumas 0.60, prioritetas 0.60) parinkti 2026-11-10 pagal 112 testo įrašų su Claude žymomis: kategorija – įvertis ≥ 0.40 turėjo 27 % įrašų, jų atitikimas Claude žymoms 0.80 (kitų 0.55); sudėtingumas ≥ 0.60 – 20 %, 0.73 (kitų 0.63); prioritetas ≥ 0.60 – 27 %, 0.73 (kitų 0.57). Imtis maža, tas pats testo rinkinys naudotas ir ataskaitai, todėl skaičiai orientaciniai; vieno bendro slenksčio nėra, nes kategorija turi 8 klases, o kiti laukai – 3. Sudėtingumo ir prioriteto įvertis silpnai skiria teisingas prognozes nuo klaidingų.
- DI validacijos dalies metrikos (stratifikuotas 80/20 dalijimas iš DI žymų) rodo, kaip modelis atkartoja DI žymas; galutinė kokybės išvada daroma pagal testavimo rinkinį su aiškiai nurodytu etalonu (DI / žmogaus žymos) ir apribojimu, kad etalonas ir mokymo žymos gaunamos tuo pačiu DI modeliu.
- Atskiras bandomasis rinkinys (~30 įrašų, `is_pilot_set`) naudojamas DI modelio pasirinkimui, taisyklių tikslinimui ir faktinei kainai nustatyti. Kadangi pagal jį priimami sprendimai, jis į galutinį vertinimą neįtraukiamas (mokymui jo žmogaus žymos tinka). Testavimo ir bandomasis rinkiniai nesikerta ir atrenkami tik iš pagrindinio rinkimo įrašų.
- Abu rinkiniai atrenkami atsitiktinai (seed), proporcingai pagal projektus, prieš DI žymėjimą.
- Tikslinis retų klasių papildymas (`source_kind = augmentation`) keičia mokymo rinkinio klasių proporcijas; testavimo rinkinys lieka nepapildytas, todėl vertinimas atspindi natūralų pasiskirstymą. Papildymas klasių nepriskiria – jas nustato DI / žmogus; nepakankamos klasės nurodomos ataskaitoje.
- Žmogaus testui pateikiami bootstrap 95 % pasikliautinieji intervalai (1 000 imčių) accuracy ir macro-F1; macro-F1 skaičiuojamas klasėms, kurių yra vertinamoje imtyje, o klasės be testo pavyzdžių ar su < 5 pavyzdžiais nurodomos atskirai kaip neįvertintos / nepatikimos.
- Nežymėtus laukus ignoruoti konkretaus lauko mokyme; nenumanomas klases palikti NULL.
- Dokumentuoti repozitoriją, importo datą, atrankos kriterijus, bendrą eilučių kiekį, išmestas eilutes ir kiekvieno lauko klasių pasiskirstymą.
- Jei įmanoma, anotacijas antru peržiūrėjimu validuoti bent daliai duomenų; pažymėti nesutarimus ir kaip jie išspręsti.
- Nenaudoti sintetiškai sugeneruotų eilučių kaip įrodymo apie realaus modelio tikslumą.

## 3. Pradiniai modeliai

1. **Majority-class baseline:** visoms testavimo eilutėms priskiriama dažniausia mokymo dalies klasė.
2. **TF-IDF + LogisticRegression:** iš `title + body` tekstų mokomas scikit-learn Pipeline.
3. Papildomas sudėtingesnis modelis nėra privalomas. Jį verta įtraukti tik jei yra pakankamai duomenų ir aiškus pagrindimas.

Abiem pradiniams metodams naudoti tą pačią mokymo/testavimo dalį.

## 4. Duomenų padalijimas

- Pirmiausia pašalinti dublikatus, tada dalinti duomenis.
- Jei kiekviena klasė turi pakankamai pavyzdžių, naudoti stratified holdout (pvz., 80% train / 20% test) su dokumentuotu fiksuotu random seed.
- Jei vienos klasės įrašų per mažai stratifikavimui ar prasmingam testavimui, naudoti atitinkamą cross-validation protokolą tik jei mažiausia klasė leidžia bent 3 fold; kitaip nurodyti, kad skaitinis palyginimas yra tik tiriamasis ir trūksta duomenų.
- Jokio fit (įskaitant TF-IDF žodyno kūrimą) už mokymo dalies ribų.
- Hiperparametrų parinkimas, jei kada nors daromas, atliekamas tik mokymo dalyje / kryžminėje validacijoje. Testo dalis atveriama tik galutiniam įvertinimui.
- Jei duomenyse daug panašių klaidų ar vienos repos dublikatuose kartojasi šablonai, aptarti galimą leakage; apsvarstyti grupinį skirstymą pagal issue seriją ar laikinį skirstymą kaip atskirą eksperimentą.

## 5. Metrikos

Kiekvienam laukui, kai duomenų užtenka, pateikti:
- accuracy;
- precision, recall ir F1 kiekvienai klasei;
- macro-F1 (pagrindinė palyginimo metrika, nes klasės gali būti nesubalansuotos);
- weighted-F1 kaip papildomą;
- confusion matrix;
- testavimo pavyzdžių skaičių, klasių pasiskirstymą ir random seed.

Macro-F1 skaičiuojamas kaip vienodai sveriamas kiekvienos klasės F1 vidurkis. Tai sumažina riziką paslėpti silpną mažumos klasės rezultatą po bendru accuracy. Metrikas apskaičiuoti su aiškiu undefined classes elgesiu; nulis / neegzistuojanti klasė turi būti paaiškinta.

## 6. Mažos imties principas

Nėra vieno skaičiaus, kuris automatiškai padaro dataset'ą pakankamą. Mažas duomenų rinkinys gali turėti klases be testinių pavyzdžių, o macro-F1 gali labai svyruoti.

Todėl:
- prieš mokymą rodyti bendrą ir kiekvienos klasės skaičių;
- taikyti aiškiai dokumentuotą minimalų konfigūruojamą slenkstį;
- nesant pakankamos įvairovės grąžinti `insufficient_data` arba tik aprašomąją ataskaitą;
- nenaudoti tikslumo skaičiaus be duomenų kiekio ir split informacijos;
- nerašyti rezultatų „modelis pasiekė X%“, kol eksperimentas tikrai neįvykdytas.

## 7. Prognozės pasitikėjimas

LogisticRegression `predict_proba` pateikia modelio apskaičiuotą klasės tikimybės įvertį, bet tai nebūtinai reiškia kalibruotą tikimybę. UI jį žymi kaip modelio score / įvertį. Jei įtraukiamas automatinis peržiūros slenkstis, jį parinkti iš validavimo rezultatų ir aptarti false positive / false negative kainą. Jeigu nėra tinkamos validavimo imties, nedėti nepatikrinto slenksčio kaip moksliškai pagrįstos ribos.

## 8. Atkartojamumas

Vertinimo ataskaita turi turėti:
- dataset'o žymenį / kūrimo datą;
- klasifikavimo lauką;
- naudotų įrašų skaičių ir klasių dažnius;
- split tipą, seed ir parametrus;
- baseline bei ML modelio metrikas;
- modelio parametro santrauką ir versiją;
- apribojimus bei įspėjimus dėl imties dydžio.

Modelio failai, DB ir privatūs duomenys neturi būti commit'inami į viešą GitHub repozitoriją pagal numatytą konfigūraciją.

## 9. Rezultatų interpretavimas

Modelio sėkmė nenustatoma vien pagal tai, ar pateikiama prognozė. Vertinama, ar jis pranoksta baseline, kaip elgiasi klasėse, kurių pavyzdžių mažai, ir ar žmogus gali peržiūrėti neaiškius atvejus. Jei modelis nepranoksta baseline, tai yra galiojantis tyrimo rezultatas – reikia aptarti duomenų ribotumą, klasių painiavą ir galimus patobulinimus, o ne slėpti rezultatą.

## 10. Konkreti 5B strategija (pagal duomenų analizę)

Išsami analizė ir skaičiai – [DATA_QUALITY_REPORT.md](DATA_QUALITY_REPORT.md). Santrauka:

- Rinkinys: 2 906 importuoti, 2 884 praėjo kokybės patikrą (po etikečių filtro pataisos); žymų dar nėra, todėl klasių pasiskirstymas nežinomas ir jokių rezultatų teigti negalima.
- Žmogaus testas (~120) ir bandomasis (~30) atrenkami prieš DI žymėjimą, žymimi nematant DI atsakymo. Su 120 įrašų klasė, sudaranti 2 % duomenų, turės bent 5 testo pavyzdžius tik ~9 % tikimybe (5 % klasė – ~72 %), todėl retų klasių metrikos bus pažymimos kaip nepatikimos; jei vadovas reikalauja patikimesnio vertinimo, testą galima padidinti.
- Retoms klasėms (tikėtina: `security`, `performance`, `documentation`, `P0_critical`) naudojamas tikslinis `--augment` – tik po DI žymėjimo ir tik toms klasėms, kurių mokymo pavyzdžių mažiau nei 40; papildyti įrašai į testą nepatenka.
- Pagrindinė metrika – macro-F1 kiekvienam laukui atskirai; papildomai precision / recall / F1 pagal klasę, confusion matrix, bootstrap 95 % intervalai; prioritetui ir sudėtingumui (tvarkos skalė) – Cohen kappa su kvadratiniais svoriais.
- DI žymos laikomos „silver“: pateikti DI ir žmogaus sutapimą testo rinkinyje (accuracy, Cohen kappa) ir atskirai aptarti, kad prioriteto bei sudėtingumo žymos iš teksto yra mažiau patikimos.
- Tyrimo rizika: repozitorijų šablonai ir klasių priklausomybė nuo repozitorijos gali sukelti leakage; kaip papildomą eksperimentą atlikti skirstymą pagal repozitoriją (žr. 4 skyrių).
