import argparse


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(
        prog="orch", description="Orchestrate coding-agent build units in Herdr."
    )
    root.add_argument("--config", help="path to orchestrate.toml")
    root.add_subparsers(dest="verb")
    return root


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    if args.verb is None:
        parser().print_help()
    return 0
