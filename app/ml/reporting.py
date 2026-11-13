"""Žmogui skaitoma mokymo ataskaita (`models/training_report.md`) iš `train_all` rezultato.

Ataskaitoje nėra jokių išgalvotų skaičių: viskas imama iš to paties JSON rezultato.
"""

from app import config

FIELD_TITLES = {
    "category_label": ("Kategorija", config.CATEGORY_LABELS),
    "complexity_label": ("Sudėtingumas", config.COMPLEXITY_LABELS),
    "priority_label": ("Prioritetas", config.PRIORITY_LABELS),
}

_STATIC_LIMITATIONS = [
    "Mokymo žymos daugiausia sugeneruotos DI modelio ir nėra garantuotai teisingos; validacijos "
    "dalies metrikos rodo, kaip modelis atkartoja DI žymas, o ne tikrąją kokybę.",
    "Galutinė kokybė vertinama tik nepriklausomu testavimo rinkiniu, kuris į mokymą nepatenka; jis "
    "mažas, todėl pateikiami bootstrap 95 % intervalai, o atskirų klasių metrikos labai neapibrėžtos.",
    "Bandomojo rinkinio įrašai buvo naudoti DI modelio / taisyklių pasirinkimui, todėl į galutinį "
    "vertinimą neįtraukti.",
    "Tikslinis papildymas (source_kind = augmentation) keičia klasių proporcijas mokymo rinkinyje; "
    "testavimo rinkinys atrinktas tik iš pagrindinio rinkimo įrašų ir nepapildytas.",
    "Duomenys – vieši GitHub issues iš atrinktų projektų; rezultatai gali neperkelti į kitų "
    "sistemų klaidų pranešimus.",
    "LogisticRegression įvertis nėra kalibruota tikimybė.",
]


def _fmt(value: object) -> str:
    if isinstance(value, float):
        return f"{value:.3f}"
    return "—" if value is None else str(value)


def _table(headers: list[str], rows: list[list[object]]) -> list[str]:
    lines = ["| " + " | ".join(headers) + " |", "|" + "---|" * len(headers)]
    lines += ["| " + " | ".join(_fmt(cell) for cell in row) + " |" for row in rows]
    return lines + [""]


def _name(labels: dict[str, str], value: str) -> str:
    return f"{labels.get(value, value)} (`{value}`)"


def _metrics_rows(label: str, metrics: dict, ci: dict | None = None) -> list[object]:
    row = [label, metrics["samples"], metrics["accuracy"], metrics["macro_f1"], metrics["weighted_f1"]]
    if ci is not None:
        row += [f"{ci['accuracy'][0]:.3f}–{ci['accuracy'][1]:.3f}", f"{ci['macro_f1'][0]:.3f}–{ci['macro_f1'][1]:.3f}"]
    return row


def _per_class(metrics: dict, labels: dict[str, str]) -> list[str]:
    rows = []
    for value in metrics["confusion_matrix"]["labels"]:
        item = metrics["per_class"].get(value, {})
        rows.append([_name(labels, value), item.get("precision"), item.get("recall"),
                     item.get("f1-score"), int(item.get("support", 0))])
    return _table(["Klasė", "Precision", "Recall", "F1", "Pavyzdžių"], rows)


def _confusion(metrics: dict) -> list[str]:
    classes = metrics["confusion_matrix"]["labels"]
    matrix = metrics["confusion_matrix"]["matrix"]
    return _table(["Tikra \\ Prognozė", *classes], [[c, *row] for c, row in zip(classes, matrix)])


_REFERENCE_NAMES = {"human": "žmogaus žymos", "ai": "DI žymos", "mixed": "žmogaus ir DI žymos"}


def _field_section(field: str, report: dict, limitations: list[str]) -> list[str]:
    title, labels = FIELD_TITLES[field]
    lines = [f"## {title}", ""]
    lines += ["**Mokymo duomenų klasių pasiskirstymas**", ""]
    lines += _table(["Klasė", "Pavyzdžių"],
                    [[_name(labels, value), report["class_distribution"].get(value, 0)] for value in labels])
    if report["excluded_classes_below_min"]:
        excluded = ", ".join(f"`{k}` ({v})" for k, v in report["excluded_classes_below_min"].items())
        lines += [f"Klasės, neįtrauktos dėl per mažo kiekio (< {report['min_class_samples']}): {excluded}.", ""]
        limitations.append(f"{title}: modelis nemoka klasių {excluded} – per mažai mokymo pavyzdžių.")
    missing = [value for value in labels if report["class_distribution"].get(value, 0) == 0]
    if missing:
        limitations.append(f"{title}: mokymo duomenyse visai nėra klasių " + ", ".join(f"`{m}`" for m in missing) + ".")

    if report["status"] != "trained":
        lines += [f"**Modelis neapmokytas (`{report['status']}`):** {report['message']}", ""]
        limitations.append(f"{title}: modelis neapmokytas – {report['message']}")
        return lines

    lines += [f"Mokymo dalis: {report['train_samples']}, validacijos dalis: {report['validation_samples']}.", ""]
    headers = ["Vertinimas", "Pavyzdžių", "Accuracy", "Macro-F1", "Weighted-F1"]
    rows = [
        _metrics_rows("DI validacija – modelis", report["validation"]["model"]),
        _metrics_rows("DI validacija – daugumos klasės baseline", report["validation"]["majority_baseline"]),
    ]
    test = report.get("human_test")
    ref = f"testas ({_REFERENCE_NAMES.get(test['reference'], test['reference'])})" if test else ""
    if test:
        headers += ["Accuracy 95 % CI", "Macro-F1 95 % CI"]
        rows = [row + ["", ""] for row in rows]
        rows += [
            _metrics_rows(f"{ref.capitalize()} – modelis", test["model"], test["ci95"]),
            _metrics_rows(f"{ref.capitalize()} – daugumos klasės baseline", test["majority_baseline"]) + ["", ""],
        ]
    lines += ["**Rezultatai**", ""] + _table(headers, rows)

    if test:
        lines += [f"**{ref.capitalize()}: kiekvienos klasės rezultatai**", ""] + _per_class(test["model"], labels)
        lines += [f"**{ref.capitalize()}: klaidų matrica**", ""] + _confusion(test["model"])
        if test["reference"] != "human":
            limitations.append(
                f"{title}: testo etalonas – {_REFERENCE_NAMES[test['reference']]} ({test['reference_counts']}); "
                "metrikos rodo atitikimą DI žymoms, o ne žmogaus patvirtintai tiesai."
            )
        if test.get("warning"):
            limitations.append(f"{title}: {test['warning']}")
        if test["classes_without_test_samples"]:
            limitations.append(f"{title}: testavimo rinkinyje nėra klasių "
                               + ", ".join(f"`{c}`" for c in test["classes_without_test_samples"])
                               + " – jų kokybė neįvertinta.")
        if test["classes_with_few_test_samples"]:
            limitations.append(f"{title}: mažiau nei 5 testo pavyzdžiai klasėms "
                               + ", ".join(f"`{c}`" for c in test["classes_with_few_test_samples"])
                               + " – jų metrikos nepatikimos.")
    else:
        limitations.append(f"{title}: žmogaus testavimo rinkinys dar nepažymėtas – galutinio vertinimo nėra.")
    lines += ["**DI validacija: klaidų matrica**", ""] + _confusion(report["validation"]["model"])

    agreement = report.get("ai_vs_human_agreement")
    if agreement:
        lines += [f"**DI ir žmogaus žymų sutapimas testavimo rinkinyje:** accuracy {agreement['accuracy']:.3f}, "
                  f"macro-F1 {agreement['macro_f1']:.3f} ({agreement['samples']} įrašai).", ""]
    return lines


def markdown_report(report: dict) -> str:
    dataset = report["dataset"]
    ai = report.get("ai_labelling_summary", {})
    lines = [
        "# Klaidų klasifikavimo modelių mokymo ataskaita",
        "",
        f"Modelio versija: `{report['model_version']}` · sukurta {report['trained_at']} · seed {report['seed']}",
        "",
        f"Metodas: {report['method']}. Duomenys padalyti stratifikuotai "
        f"({int((1 - report['validation_size']) * 100)} / {int(report['validation_size'] * 100)}) prieš mokymą; "
        "TF-IDF žodynas sudaromas tik iš mokymo dalies.",
        "",
        "## Duomenų kilmė",
        "",
        "Vieši GitHub issues, importuoti tik skaitymo režimu be autentifikacijos. Pull request įrašai, "
        "dublikatai, ne klaidų etiketės (enhancement, question, duplicate ir pan.) ir per trumpi aprašymai "
        "atmesti prieš DI žymėjimą.",
        "",
    ]
    lines += _table(
        ["Repozitorija", "Importuota", "Iš jų papildymas", "Tinkami", "Trumpi", "Dublikatai",
         "Ne klaidų etiketės", "Bandomasis", "Testas", "Mokymui (pagr.)", "Mokymui (papild.)"],
        [[r["repository"], r["imported"], r["augmentation_imported"], r["quality_ok"], r["excluded_short"],
          r["excluded_duplicate"], r["excluded_label"], r["pilot_set"], r["test_set"], r["train_base"],
          r["train_augmentation"]] for r in report.get("provenance", [])],
    )
    lines += [
        f"Mokymo įrašų: **{dataset.get('train_rows', 0)}**; testo įrašų su etalonu (tinka, visos 3 žymos): "
        f"**{dataset.get('human_test_rows', 0)}** iš {dataset.get('test_set_rows', 0)} atrinktų "
        f"(žmogaus žymos: {dataset.get('test_labels_human', 0)}, DI: {dataset.get('test_labels_ai', 0)}, "
        f"mišrios: {dataset.get('test_labels_mixed', 0)}); "
        f"bandomojo rinkinio įrašų: {dataset.get('pilot_set_rows', 0)}.",
        "",
        "## DI žymėjimo metodika",
        "",
        f"Žymos sugeneruotos modeliu `{report['ai_labels']['model']}`, prompt versija "
        f"`{report['ai_labels']['prompt_version']}`: struktūrizuotas JSON atsakymas su leistinomis "
        "reikšmėmis, taisyklės iš `docs/DATA_LABELING.md`, kiekvienas atsakymas papildomai validuotas. "
        "Žmogaus žyma visada turi pirmenybę prieš DI žymą. Mokymui naudojami tik „Tinka mokymui“ įrašai "
        "su visomis trimis žymomis.",
        "",
        f"DI užklausų: {ai.get('requests', 0)}; sėkmingų žymų: {ai.get('ok', 0)}, netinkamų atsakymų: "
        f"{ai.get('invalid', 0)}; tinka mokymui: {ai.get('suitable', 0)}, netinka: {ai.get('unsuitable', 0)}. "
        f"Tokenai: įvestis {ai.get('input_tokens', 0)}, išvestis {ai.get('output_tokens', 0)}. "
        f"Faktinė kaina pagal API `usage`: ${ai.get('cost_usd', 0):.4f}.",
        "",
    ]
    limitations: list[str] = []
    for field in FIELD_TITLES:
        lines += _field_section(field, report["fields"][field], limitations)
    lines += ["## Apribojimai", ""]
    lines += [f"- {item}" for item in limitations + _STATIC_LIMITATIONS]
    return "\n".join(lines) + "\n"
