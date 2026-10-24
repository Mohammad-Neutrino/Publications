# List of Publications

**Mohammad Ful Hossain Seikh**  
Postdoctoral Researcher, Department of Physics & Astronomy, University of Kansas

[![Build Publications PDF](https://github.com/Mohammad-Neutrino/Publications/actions/workflows/build-publications.yml/badge.svg)](https://github.com/Mohammad-Neutrino/Publications/actions/workflows/build-publications.yml)

**[View or download the latest Publications PDF](https://github.com/Mohammad-Neutrino/Publications/blob/trunk/Publications.pdf)** · [Personal website](https://mohammad-neutrino.github.io/) · [INSPIRE-HEP](https://inspirehep.net/authors/2014116) · [Google Scholar](https://scholar.google.com/citations?user=dSwfpWQAAAAJ) · [ORCID](https://orcid.org/0000-0002-4464-7354)

This repository contains the LaTeX source and maintained PDF of my academic publication record in particle astrophysics, neutrino astronomy, and radio detection. It covers first-author and lead contributions, selected collaborative publications, and additional papers from experimental collaborations and multi-institution teams.

## Publication list

The document is organized into three parts:

1. **First-Author Works and Lead Research Contributions:** manuscripts in collaboration review, refereed journal articles, conference proceedings, and editorial or other scientific writing.
2. **Selected Collaborative Works:** a curated selection of 11 collaborative publications, also highlighted in my academic CV.
3. **Additional Collaborative Works:** the remaining papers organized by collaboration and publication type. Papers in the selected section are omitted here to avoid duplication.

The workshop editorial is classified with editorial writing rather than original research articles. Manuscripts in collaboration review are identified separately from published papers; their status and intended venues are subject to change.

## Repository files

| Path | Purpose |
| --- | --- |
| [`Publications.pdf`](Publications.pdf) | Latest compiled publication list, maintained by GitHub Actions. |
| [`main.tex`](main.tex) | Main LaTeX document, including first-author and selected collaborative works. |
| [`collaborative_publications.tex`](collaborative_publications.tex) | Additional collaborative publications, included by `main.tex`. |
| [`latexmkrc`](latexmkrc) | XeLaTeX configuration for local and Overleaf compilation. |
| [`.github/workflows/build-publications.yml`](.github/workflows/build-publications.yml) | Compiles and updates `Publications.pdf` following source changes. |
| [`scripts/check_inspire.py`](scripts/check_inspire.py) | Read-only check for possible new records in INSPIRE-HEP. |
| [`INSPIRE-CiteAll.bib`](INSPIRE-CiteAll.bib) | Reference BibTeX snapshot; not an automatically refreshed bibliography. |

The publication entries in the PDF are manually curated. The document does not automatically typeset every entry from the BibTeX snapshot.

## Updating from Overleaf

This repository is connected to an Overleaf project. The regular editing workflow is:

1. Open the linked Overleaf project. Set **`main.tex`** as the main document and **XeLaTeX** as the compiler.
2. Pull any new GitHub changes into Overleaf before editing, when applicable.
3. Edit `main.tex` and/or `collaborative_publications.tex`, then compile and check the PDF in Overleaf.
4. Use Overleaf's **GitHub integration → Push Overleaf changes to GitHub** to publish the source changes to the `trunk` branch.
5. The [Compile Publications PDF workflow](https://github.com/Mohammad-Neutrino/Publications/actions/workflows/build-publications.yml) builds `main.pdf`, copies it to **`Publications.pdf`**, and commits the updated PDF to the repository if the file changed.

**Overleaf saving is not the same as pushing to GitHub.** The published `Publications.pdf` updates only after a source push triggers a successful workflow run. If the PDF has not updated, inspect the [Actions tab](https://github.com/Mohammad-Neutrino/Publications/actions) for compilation or repository-permission errors.

Changes to `README.md` alone do not trigger a PDF rebuild.

## Compiling locally

Install a TeX distribution with XeLaTeX, `latexmk`, and the packages used by `main.tex`, including `academicons` and `fontawesome5`. Then run from the repository root:

```bash
latexmk main.tex
```

The repository's `latexmkrc` selects XeLaTeX. A local build produces `main.pdf`; **`Publications.pdf`** is the filename used for the committed GitHub version.

## Checking for new publications in INSPIRE-HEP

An optional Python script compares INSPIRE search results with the DOI, arXiv, and title information already in the curated LaTeX files. It helps identify **candidates for manual review**, not confirmed omissions.

Using Python 3.9 or later, from the repository root:

```bash
python3 scripts/check_inspire.py --output inspire_candidates.md
```

The script's default author query is `a Seikh, Mohammad Ful Hossain`. If necessary, supply a different query:

```bash
python3 scripts/check_inspire.py --query 'YOUR INSPIRE QUERY' --output inspire_candidates.md
```

The script uses the public INSPIRE literature API and Python's standard library. It does **not** edit the LaTeX sources, add papers, change authorship, or update the stored BibTeX snapshot. Its results should be checked against the [INSPIRE author record](https://inspirehep.net/authors/2014116), publisher information, and collaboration records before editing the publication list.

The repository currently includes the checker script but **does not include a separate scheduled or manually triggered INSPIRE GitHub Actions workflow**. Run it locally unless such a workflow is added later.

## Maintenance principles

- Maintain **one entry per publication** across the selected and additional collaborative sections.
- Add newly published first-author papers and proceedings to `main.tex` in the appropriate category.
- For a selected collaborative paper, remove its matching entry from `collaborative_publications.tex` using DOI and/or arXiv identifiers to confirm the match.
- Distinguish peer-reviewed articles, proceedings, editorials, preprints, and manuscripts in review.
- Verify citation metadata and collaboration authorship before accepting INSPIRE candidates.
- Do not publish confidential collaboration material or internal drafts without authorization.

## Contact

For corrections to the publication record, contact [fulhossain@ku.edu](mailto:fulhossain@ku.edu) or visit [my website](https://mohammad-neutrino.github.io/).
