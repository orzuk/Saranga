#!/bin/bash
# Copies generated tables from Authomathics repo to Overleaf repo.
# Usage: bash sync_tables_to_overleaf.sh

SRC="/Users/yaronot/Desktop/Data Courses/Plagiarism Detection/Thesis/Authomathics/tables"
DST="/Users/yaronot/Downloads/Authomatics/69334d3ec1463188f54b0393/tables"

cp "$SRC/cross_category_table.tex" "$DST/"
cp "$SRC/scale_table.tex" "$DST/"
cp "$SRC/macros.tex" "$DST/"

echo "Synced tables to Overleaf:"
ls -l "$DST/"
