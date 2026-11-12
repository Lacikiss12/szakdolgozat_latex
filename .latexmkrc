# pdfLaTeX (a kari sablon szerint) + Biber
$pdf_mode = 1;
$pdflatex = 'pdflatex -synctex=1 -interaction=nonstopmode -file-line-error %O %S';
$bibtex_use = 2;
$out_dir = 'build';
@default_files = ('dolgozat.tex');
