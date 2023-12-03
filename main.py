"""Main Module for running a workflow"""
import argparse
import logging
import os
import sqlite3

from pathlib import Path
from typing import Literal

# ======================================================================================
# Main Logic. Setup Environment and Start UI
# ======================================================================================


def initialize_logging(verbose=False, debug=False) -> None:
    # ==================================================================================
    # Logging Setup
    # ==================================================================================
    log_format = "{asctime}.{msecs:03.0f} {levelname} [{name}]: {message}"
    log_style: Literal["%", "{", "$"] = "{"
    log_level = logging.INFO if verbose else logging.WARN
    log_level = logging.DEBUG if debug else log_level
    logging.basicConfig(
        format=log_format, level=log_level, datefmt="%I:%M:%S", style=log_style
    )


def list_str(values):
    return values.split(",")


def parse_args():
    parser = argparse.ArgumentParser(prog="wflow", description="Workflow Engine")

    parser.add_argument("-v", "--verbose", action="store_true", default=False)
    parser.add_argument(
        "--debug", action="store_true", default=False, help="using debug mode"
    )
    parser.add_argument("-w", "--workflow", type=str, help="workflow name to run")
    parser.add_argument(
        "-o",
        "--owner",
        type=str,
        help="owner of the workflow",
        default="abc@example.com",
    )
    parser.add_argument(
        "--approvers", type=list_str, help="list of approvers", default=[]
    )
    parser.add_argument("--approved-by", type=str, help="Approved By User")
    parser.add_argument(
        "-t", "--transaction-id", type=str, help="transaction id to use"
    )
    # args = parser.parse_args()
    args, extra_args = parser.parse_known_args()

    # TODO: Need to ensure that we drop any boolean short args that are not used ("-x")
    extra_args = {
        k.replace("--", "").replace("-", "_"): v
        for k, v in zip(extra_args[::2], extra_args[1::2])
    }
    if args.verbose:
        print(f"Arguments = {args}, Extra = {extra_args}")  # noqa: T201

    return args, extra_args


def initialize_sqlite(sqlite3_file: Path):
    sqlite3_file.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(sqlite3_file))
    cursor = conn.cursor()
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS wf_run (
            id INTEGER PRIMARY KEY,
            transaction_id INTEGER NOT NULL,
            working_dir TEXT NOT NULL,
            owner TEXT NOT NULL,
            context TEXT NULLABLE,
            status TEXT NOT NULL,
            reason TEXT NULLABLE,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS wf_step_run (
            wf_id INTEGER,
            step_name TEXT NOT NULL,
            input TEXT NULLABLE,
            output TEXT NULLABLE,
            status TEXT NOT NULL,
            reason TEXT NULLABLE,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(wf_id, step_name)
        )
        """
    )
    return conn


if __name__ == "__main__":
    # print(f"Locals = {sys.argv}")
    os.environ["WF_ROOT_DIR"] = os.getcwd()
    print(f"Root dir = {os.environ['WF_ROOT_DIR']}")

    args, extra_args = parse_args()
    initialize_logging(verbose=args.verbose, debug=args.debug)
    sqlite3_dir = Path(os.environ["WF_ROOT_DIR"]) / "data" / "wf.sqlite3"
    sql_conn = initialize_sqlite(sqlite3_dir)

    # Importing after Logging has been setup
    import wfengine as wf

    orchestrator = wf.WFRunner.from_file(
        args.workflow, sql_conn, metadata={"source": "cli", "owner": args.owner}
    )
    # Hard-coding to reduce complexity in the cli invocation
    if args.workflow == "test_wf":
        if not args.transaction_id:
            extra_args["queries"] = [
                extra_args.pop("sql1", "select * from user"),
                extra_args.pop("sql2", "select 42 from dual"),
            ]
            extra_args["approvers"] = getattr(args, "approvers") or ["xyz@example.com"]
        else:
            extra_args["approved_by"] = (
                getattr(args, "approved_by") or "xyz@example.com"
            )
    elif args.workflow == "accounts_payable":
        if not args.transaction_id:
            extra_args["approvers"] = getattr(args, "approvers") or ["xyz@example.com"]
            extra_args["invoice_file_name"] = extra_args.pop(
                "invoice_file_name", "ap_invoice.pdf"
            )
            extra_args["po_file_name"] = extra_args.pop("po_file_name", "ap_po.pdf")

            # NOTE: This is actually optional.. That has not been handled..
            # So, we define and move on!
            extra_args["grn_file_name"] = extra_args.pop("grn_file_name", "ap_grn.pdf")
        else:
            extra_args["approved_by"] = (
                getattr(args, "approved_by") or "xyz@example.com"
            )

        # Delete these keys from the argparse namespace
        del args.approvers
        del args.approved_by

    if args.transaction_id:
        orchestrator.resume(transaction_id=args.transaction_id, **extra_args)
    else:
        orchestrator.run(**extra_args)
