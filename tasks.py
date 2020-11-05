""" `invoke` tasks used to make and quality-check this article. """

import pathlib
import re
import subprocess
import sys
from collections import Counter
from difflib import SequenceMatcher

import bibtexparser
import numpy as np
import pandas as pd
from bibtexparser.bibdatabase import BibDatabase
from bibtexparser.bparser import BibTexParser
from bibtexparser.bwriter import BibTexWriter
from invoke import task

import known


@task
def compile(c, engine="xelatex"):
    """ Compile the LaTeX document. """

    c.run(f"latexmk -interaction=nonstopmode -shell-escape --{engine} main.tex")


@task
def spellcheck(c):
    """ Check spelling. """

    article = pathlib.Path("./sec/").glob("*.tex")
    exit_codes = [0]
    for path in article:

        print(f"Checking {path}")
        latex = path.read_text()
        aspell_output = subprocess.check_output(
            ["aspell", "-t", "--list", "--lang=en_GB"], input=latex, text=True
        )

        errors = set(aspell_output.split("\n")) - {""}
        print(errors)
        unknowns = set()
        for error in errors:
            if not any(
                any(
                    re.fullmatch(word.lower() + pattern, error.lower())
                    for pattern in known.patterns | {""}
                )
                for word in known.words
            ):
                unknowns.add(error)

        if unknowns:
            print(f"In {path} the following words are not known:")
            for string in sorted(unknowns):
                print(string)

            exit_codes.append(1)

    sys.exit(max(exit_codes))


def extract_bibentries(bibfile):
    """ Extract the entries from a BibTeX file. """

    print("Getting bibentries...")
    with open(bibfile) as bibtexfile:
        parser = BibTexParser(common_strings=True)
        bibdatabase = bibtexparser.load(bibtex_file=bibtexfile, parser=parser)

    bibentries = pd.DataFrame(bibdatabase.entries)
    return bibentries


def get_citations_to_export(bibentries):
    """ Collect together the entries and clean them. """

    print("Cleaning entries...")
    bibentries = bibentries.drop_duplicates(subset=["title"], keep="last")
    duplicate_keys = [
        key for key, count in Counter(bibentries["ID"]).items() if count > 1
    ]

    citations_to_export = bibentries[~bibentries["ID"].isin(duplicate_keys)]
    entries_to_check = bibentries[
        bibentries["ID"].isin(duplicate_keys)
    ].groupby("ID")
    for key, entries in entries_to_check:
        print("Checking", key)
        titles = entries["title"].unique()
        if SequenceMatcher(None, *titles).ratio() > 0.7:
            citations_to_export = citations_to_export.append(
                entries.iloc[-1, :]
            )

        else:
            for i, entry in enumerate(entries):
                entry["ID"] = entry["ID"] + f"_{i}"
                citations_to_export = citations_to_export.append(entry)

    return citations_to_export


def export_citations(citations, destination):
    """ Create the BibTeX database to export. """

    db = BibDatabase()
    citation_dicts = (dict(row) for _, row in citations.iterrows())
    citation_dicts = [
        {
            attribute: value
            for attribute, value in citation.items()
            if value is not np.nan
        }
        for citation in citation_dicts
    ]

    db.entries = citation_dicts

    with open(destination, "w") as bibtexfile:
        writer = BibTexWriter()
        writer.indent = "    "
        bibtexparser.dump(db, bibtexfile, writer)


@task
def bibliography(c, path="bibliography.bib", backup=True):
    """ Clean and compile the bibliography. """

    if backup and pathlib.Path(path).exists():
        print("Backing up current bibliography.")
        c.run(f"mv {path} _{path}")

    bibentries = extract_bibentries(path)
    citations_to_export = get_citations_to_export(bibentries)
    export_citations(citations_to_export, path)