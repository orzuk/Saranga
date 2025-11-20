#!/bin/bash

#SBATCH --time=05:00:00
#SBATCH --ntasks=2
#SBATCH --mem=1G

echo "FINISHED EUROPE"
for FILE in *.txt; do gzip $FILE; done
echo "FINISHED ZIP"

