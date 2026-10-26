# Modelio vertinimo planas bakalauro darbui

## 1. Tyrimo klausimas

Ar issue pavadinimo ir aprašymo teksto požymiai (TF-IDF) su prižiūrimu LogisticRegression klasifikatoriumi leidžia tiksliau nustatyti programinės įrangos klaidos kategoriją, prioritetą ir sudėtingumą negu paprastas daugumos klasės bazinis metodas?

Vertinti tris laukus atskirai. Galima turėti skirtingą pavyzdžių skaičių kiekvienam laukui, nes ne visos klaidos turės visas tris patvirtintas žymas.

## 2. Duomenų sagatavošana un kvalitāte

- Iš viešo GitHub importo gauti issue pavadinimą, aprašymą, etiketes, būseną, datą ir URL.
- Pull request įrašus išmesti.
- Dublikatus šalinti / identifikuoti prieš dalijant duomenis.
- Automatiškai neinterpretuoti visų GitHub label kaip ground truth: jos gali būti repo specifinės, prieštaringos arba nesusijusios su užduoties klasėmis.
- Mokyti tik iš žmogaus peržiūrėtų žymų su aiškia žymos kilme.
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
