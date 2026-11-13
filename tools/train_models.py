"""Trijų scikit-learn modelių mokymas, išsaugojimas ir vertinimas.

Pavyzdys:
    python -m tools.train_models
Rezultatas: models/category_label.joblib, models/complexity_label.joblib,
models/priority_label.joblib ir models/training_report.json.
"""

from pathlib import Path

from app import config
from app.ml import ai_labeling, training
from tools._common import open_database, parser


def _summary_line(field: str, report: dict) -> str:
    if report["status"] != "trained":
        return f"{field}: {report['status']} – {report['message']}"
    validation = report["validation"]
    line = (
        f"{field}: mokymas {report['train_samples']}, validacija {report['validation_samples']}; "
        f"validacijos macro-F1 {validation['model']['macro_f1']} "
        f"(baseline {validation['majority_baseline']['macro_f1']})"
    )
    if report.get("human_test"):
        test = report["human_test"]
        ci = test["ci95"]["macro_f1"]
        source = {"human": "žmogaus", "ai": "DI", "mixed": "mišrios"}[test["reference"]]
        line += (f"; testas, etalonas – {source} žymos ({test['model']['samples']}): macro-F1 {test['model']['macro_f1']} "
                 f"[95 % CI {ci[0]}–{ci[1]}] (baseline {test['majority_baseline']['macro_f1']})")
    else:
        line += "; testo rinkinio su žymomis dar nėra"
    return line


def main(argv: list[str] | None = None) -> int:
    args_parser = parser("Moko kategorijos, sudėtingumo ir prioriteto klasifikatorius.")
    args_parser.add_argument("--ai-model", default=ai_labeling.DEFAULT_MODEL,
                             help="kurio DI modelio žymas naudoti")
    args_parser.add_argument("--prompt-version", default=ai_labeling.PROMPT_VERSION)
    args_parser.add_argument("--output-dir", type=Path, default=config.PROJECT_DIR / "models")
    args_parser.add_argument("--seed", type=int, default=training.DEFAULT_SEED)
    args_parser.add_argument("--min-samples", type=int, default=training.DEFAULT_MIN_SAMPLES)
    args = args_parser.parse_args(argv)

    conn = open_database(args.db)
    report = training.train_all(
        conn, args.output_dir, args.ai_model, args.prompt_version, args.seed,
        min_samples=args.min_samples,
    )
    conn.close()
    print(f"Duomenys: {report['dataset']}")
    for field, field_report in report["fields"].items():
        print(_summary_line(field, field_report))
    print(f"Ataskaitos: {args.output_dir / training.MARKDOWN_REPORT_FILE} ir {args.output_dir / training.REPORT_FILE}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
