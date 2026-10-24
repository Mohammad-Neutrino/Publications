# Publications | Mohammad Ful Hossain Seikh

This is the complete source for *List of Publications*. `main.tex` is the main document and `collaborative_publications.tex` contains the supplementary collaboration bibliography. The snapshot `INSPIRE-CiteAll.bib` is preserved as source/reference; the LaTeX document intentionally uses manually curated citations rather than an automated BibTeX layout.

## Document structure

1. First-author works and lead research contributions, with the workshop summary correctly classified as editorial writing.
2. **Selected Collaborative Works:** 11 citations matched to the current academic CV.
3. **Additional Collaborative Works:** the remaining collaboration papers by experiment and publication type. The 11 selected entries have been removed from these lists to avoid repetition. Empty journal subheadings were removed.

## Working in Overleaf and synchronizing with GitHub

1. Upload the project source files into an Overleaf project. Set **main.tex** as the main document and **XeLaTeX** as the compiler. `latexmkrc` also requests XeLaTeX for latexmk.
2. Connect the Overleaf project using **Integrations > GitHub** (or the older **Menu > GitHub**) and choose **Create a new GitHub repository from this Overleaf project**. Overleaf does not directly pair an existing project with an independently existing GitHub repository.
3. Edit in Overleaf. When ready, choose **GitHub > Push Overleaf changes to GitHub**. Built-in sync requires an explicit push; saving in Overleaf is not an automatic GitHub commit.
4. GitHub Actions builds `main.pdf` on each source push, commits the updated PDF back to the repository (as your CV workflow does), and also provides a downloadable **Publications-PDF** artifact. The repository needs Actions permission to write contents. If Overleaf ignores hidden `.github` folders during ZIP import, add the workflow files directly in your GitHub repository after the first synchronization, then pull the repository changes into Overleaf.

If you already created a Publications repository, use **New Project > Import from GitHub** to create a linked Overleaf project from that existing repository, rather than attempting to pair two existing items.

## Updating from INSPIRE

The file `INSPIRE-CiteAll.bib` is a retained snapshot, not an automatically updating source.

To compare current INSPIRE search results with the curated LaTeX lists, run on your own computer (Python 3.9+; no external packages):

```bash
python3 scripts/check_inspire.py --output inspire_candidates.md
```

The default search is `a Seikh, Mohammad Ful Hossain`. Verify that the query covers your author record at https://inspirehep.net/authors/2014116. You can change it with `--query 'YOUR AUTHOR SEARCH'`. Author matching for large collaborations is imperfect; no live API endpoint has been exercised during packaging. Read the candidate report and verify each result manually. The script **never overwrites** any `.tex` or `.bib` file.

You can also run the **Review INSPIRE Publications** action manually in GitHub Actions. It uploads an `INSPIRE-candidates` report artifact for inspection.

## Maintenance rules

- Add new first-/lead-author contributions to `main.tex`.
- Promote exceptional collaboration papers into the selected list and remove the identical entry from the supplementary list, preferably matching DOI or arXiv ID.
- Keep peer-reviewed articles, proceedings, editorial writing, and manuscripts distinct.
- A new INSPIRE record should not automatically be considered a verified publication, nor should the full collaboration bibliography be replaced blindly from INSPIRE.
- Review `INSPIRE-CiteAll.bib` periodically if you want to preserve a fresh archival export.
