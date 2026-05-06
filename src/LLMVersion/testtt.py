ssh -J yaron.otmazgin@bava.cs.huji.ac.il yaron.otmazgin@moriah-gw.cs.huji.ac.il

/sci/labs/orzuk/yaron.otmazgin/Authomathics

source venv/bin/activate

srun --time=6:00:00 --mem=8G --cpus-per-task=1 --pty bash

# github process
git pull origin main
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
git status
git add -u # only track modified files, not new untracked files
git commit -m ""
git push origin main

# if git push fails due to new commits on the remote, do:
git pull --rebase

#overleaf key:
olp_2Pkfcs5R7eYprj5oGk9fdAmRrgQZST24QRgV









#download to local machine:
ssh -J yaron.otmazgin@bava.cs.huji.ac.il \
  yaron.otmazgin@moriah-gw.cs.huji.ac.il \
  "cat /sci/labs/orzuk/orzuk/teaching/big_data_project_52017/2024_25/arxiv_data/fill_papers.csv" \
  > "/Users/yaronot/fill_papers.csv"

#copy to clipboard:
ssh -J yaron.otmazgin@bava.cs.huji.ac.il \
    yaron.otmazgin@moriah-gw.cs.huji.ac.il \
    "cat /sci/labs/orzuk/orzuk/projects/Authomathics/books/foundation_data_science/extracted_chapters/json/chapter10_extracted.json" \
    | pbcopy

#copy from local machine to cluster
cat "/Users/yaronot/Desktop/Data Courses/Plagiarism Detection/100k_papers_20_categories.py" | \
ssh -J yaron.otmazgin@bava.cs.huji.ac.il \
  yaron.otmazgin@moriah-gw.cs.huji.ac.il \
  "cat > /sci/labs/orzuk/orzuk/teaching/big_data_project_52017/2024_25/arxiv_data/100k_papers_20_categories.py"




# huggingface

export HF_TOKEN="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"

python3 run_parse_papers.py \
--regex-id "^2208\.03112" \
--out-dir . \
--definition-mode llm \
--llm-provider huggingface \
--llm-model "Qwen/Qwen2.5-7B-Instruct"

#anthropic


export ANTHROPIC_API_KEY="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"

python3 run_parse_papers.py \
    --regex-id "^2208\.03112" \
    --out-dir . \
    --definition-mode llm \
    --llm-provider anthropic \
    --llm-model claude-sonnet-4-20250514


#openai
export OPENAI_API_KEY="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"

python3 run_parse_papers.py \
    --regex-id "^2208\.03112" \
    --out-dir . \
    --definition-mode llm \
    --llm-provider openai \
    --llm-model gpt-4o


#manual


python3 run_parse_papers.py \
--regex-id "^2208\.03112" \
--out-dir . \
--definition-mode manual






scp -J yaron.otmazgin@bava.cs.huji.ac.il \
  "/Users/yaronot/Desktop/Data Courses/Plagiarism Detection/Thesis/Authomathics/src/LLMVersion/Gold_Standard.csv" \
  yaron.otmazgin@moriah-gw.cs.huji.ac.il:/sci/labs/orzuk/yaron.otmazgin/Authomathics/src/LLMVersion/



python add_gold_standard.py --input-csv definitions_17_01.csv --gold-csv Gold_Standard.csv --output-csv mergedgoldanddef.csv




scp -J yaron.otmazgin@bava.cs.huji.ac.il \
  yaron.otmazgin@moriah-gw.cs.huji.ac.il:/sci/labs/orzuk/yaron.otmazgin/Authomathics/src/LLMVersion/definitions.csv \
  "/Users/yaronot/Desktop/Data Courses/Plagiarism Detection/Thesis/Authomathics/src/LLMVersion/27_01_results"


scp -J yaron.otmazgin@bava.cs.huji.ac.il \
    yaron.otmazgin@moriah-gw.cs.huji.ac.il:/sci/labs/orzuk/yaron.otmazgin/Authomathics/src/Autoformalizer/autoformalization.py \
    ~/Downloads/



scp -J yaron.otmazgin@bava.cs.huji.ac.il \
    yaron.otmazgin@moriah-gw.cs.huji.ac.il:/sci/labs/orzuk/orzuk/github/ArXivAnalysis/src/extract_arxiv_data.py \
    ~/Downloads/

python3 extract_arxiv_data.py --start 1996-01-01 --end 1999-12-31 --formats latex --verbose


python3 prompt_optimizer.py \
    --paper-id 2208.03112 \
    --provider anthropic \
    --model claude-sonnet-4-20250514 \
    --iterations 3
    --initial-prompt custom_prompt.txt













export HF_TOKEN="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"

python3 run_parse_papers.py \
--regex-id "^1210\.4634" \
--start 2012-06-17 --end 2012-06-18 \
--out-dir . \
--definition-mode llm \
--llm-provider huggingface \
--llm-model "Qwen/Qwen2.5-7B-Instruct"

1210.4634


# ================= prompt optimization =================

# run optimizer on def - changed to opus 4.6:

#general optimization for pormpt:
# options: theorem lemma proof proposition corollary claim conjecture problem definition
bash optimize.sh conjecture

# or for one:


export ANTHROPIC_API_KEY="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"
python prompt_optimizer.py \
  --structure-type definition \
  --train-papers 1210.4634 2401.00367 1204.0109v1 1405.2464 1512.09272v2 2208.03112 2309.05826 \
  --val-papers 2603.09769v1 2312.16785 2505.12804v1 \
  --gold-csv Gold_Standard_Definitions.csv \
  --initial-prompt prompts/definition_prompt.txt \
  --provider anthropic \
  --model claude-opus-4-6  \
  --meta-model claude-opus-4-6 \
  --iterations 3 \
  --out-dir definition_optimization

# visyalization of optimization process:
python viz_opt_comparison.py --opt-dir definition_optimization


# ================= extraction evaluation =================

#general extraction and evaluation for all structures (without huggingface):
# options: theorem lemma proof proposition corollary claim conjecture problem definition
bash extraction.sh proposition

# or do manually: run extraction and evaluation on def, without huggingface:

bash evaluation_pipeline.sh \
  --paper-id "1210.4634,1405.2464,2208.03112,1204.0109v1,1512.09272v2,2309.05826,2312.16785,2401.00367,2505.12804v1,2603.09769v1" \
  --structure-type definition \
  --gold-csv Gold_Standard_Definitions.csv \
  --prompt-file definition_optimization/optimized_prompt_definition_anthropic.txt \
  --out-dir definition_eval \
  --providers "anthropic,openai,manual"

#visualization comparison:
python viz_eval_comparison.py --eval-dir lemma_eval


# ================= distillation =================

#general bash for all distillation processes (without huggingface):
# options: theorem lemma proof proposition corollary claim conjecture problem definition
bash distill.sh theorem


# step 1 dark knowledge extraction:

python distillation_analysis.py dark-knowledge \
    --eval-dir definition_eval \
    --gold-csv Gold_Standard_Definitions.csv \
    --structure-type definition


# Step 2: Analyze patterns in the TeX source
python distillation_analysis.py analyze \
    --input definition_eval/dark_knowledge.csv \
    --structure-type definition \
    --output definition_eval/test_patterns.csv

#step 3: Aggregate rules are added to the manual parser - distilled rules

python distillation_analysis.py aggregate \
  --input definition_eval/test_patterns.csv \
  --structure-type definition \
  --eval-dir definition_eval

# Step 4: after adjusting the manual parser with dark knowledge rules, run manual parser again to validate:

python distillation_analysis.py validate \
    --paper-ids "1210.4634,1405.2464,2208.03112,1204.0109v1,1512.09272v2,2309.05826,2312.16785,2401.00367,2505.12804v1,2603.09769v1" \
    --structure-type definition \
    --expected definition_eval/dark_knowledge.csv


# visualize the comparison between manual parser before and after distillation:
python viz_distillation_comparison.py --eval-dir problem_eval



# ================= Manual only (no API needed) =================


# Output: my_output/json/<paper_id>_.json in unified format.
python run_parse_papers.py --regex-id "^1210.4634" --out-dir my_output --extraction-mode manual


# the evaluation pipeline uses LLMs by default so if you want to see only the manual parser capabilities:
# you can run the following steps to evaluate the manual parser against the gold standard annotations.


  # Step 1: Extract all gold-standard papers (manual mode)
  for pid in 1204.0109v1 1210.4634 1405.2464 1512.09272v2 2208.03112 \
             2309.05826 2312.16785 2401.00367 2505.12804v1 2603.09769v1; do
    python run_parse_papers.py \
      --regex-id "^${pid}" \
      --out-dir def_eval \
      --extraction-mode manual \
      --structure-types definition
  done

  # Step 2: JSON → CSV (filtered by structure type)
  python definitions_from_json_to_csv.py \
    --paper-id 1204.0109v1 \
    --paper-id 1210.4634 \
    --paper-id 1405.2464 \
    --paper-id 1512.09272v2 \
    --paper-id 2208.03112 \
    --paper-id 2309.05826 \
    --paper-id 2312.16785 \
    --paper-id 2401.00367 \
    --paper-id 2505.12804v1 \
    --paper-id 2603.09769v1 \
    --structure-type definition \
    --out-dir def_eval \
    --output-csv def_eval/definitions.csv

  # Step 3: Merge with gold standard
  python add_gold_standard.py \
    --input-csv def_eval/definitions.csv \
    --gold-csv Gold_Standard_Definitions.csv \
    --output-csv def_eval/merged.csv

  # Step 4: Evaluate (Jaccard similarity → P/R/F1)
  python evaluate_definitions.py \
    --input-csv def_eval/merged.csv \
    --threshold 0.7 \
    --output-csv def_eval/evaluation_results.csv \
    --detailed-csv def_eval/detailed_matches.csv

# Replace definition / Gold_Standard_Definitions.csv with any structure type: theorem, lemma, proof, proposition, corollary, claim, conjecture, problem.
# the process outputs a CSV file with the evaluation results (precision, recall, F1), a detailed CSV file with exact matches and Jaccard similarity scores for each predicted vs gold pair.



# ================= advanced  download =================


# new download CLI command for papers with unified tex (on local machine):
python3 extract_arxiv_data.py --start 1996-01-01 --end 1999-12-31 --advanced

# and on the cluster:
FULL_PAPERS_ADVANCED_DIR=/sci/labs/orzuk/orzuk/teaching/big_data_project_52017/2024_25/arxiv_data/full_papers_advanced \
python3 download_from_csv.py --csv /sci/labs/orzuk/orzuk/teaching/big_data_project_52017/2024_25/arxiv_data/sampled_100k_papers.csv --verbose

# this for sbatch command
sbatch --job-name=download_100k \
       --output=/sci/labs/orzuk/orzuk/teaching/big_data_project_52017/2024_25/arxiv_data/logs/download_100k_%j.out \
       --error=/sci/labs/orzuk/orzuk/teaching/big_data_project_52017/2024_25/arxiv_data/logs/download_100k_%j.err \
       --time=24:00:00 \
       --mem=8G \
       --cpus-per-task=2 \
       --wrap="bash -c 'source /sci/labs/orzuk/yaron.otmazgin/Authomathics/src/LLMVersion/venv/bin/activate && FULL_PAPERS_ADVANCED_DIR=/sci/labs/orzuk/orzuk/teaching/big_data_project_52017/2024_25/arxiv_data/full_papers_advanced python3 /sci/labs/orzuk/orzuk/teaching/big_data_project_52017/2024_25/arxiv_data/download_from_csv.py --csv /sci/labs/orzuk/orzuk/teaching/big_data_project_52017/2024_25/arxiv_data/sampled_100k_papers.csv --verbose'"


# this for sbatch command for starting from a specific paper id (in case of failure and you want to continue from a specific point):

sbatch --job-name=download_100k \
       --output=/sci/labs/orzuk/orzuk/teaching/big_data_project_52017/2024_25/arxiv_data/logs/download_100k_%j.out \
       --error=/sci/labs/orzuk/orzuk/teaching/big_data_project_52017/2024_25/arxiv_data/logs/download_100k_%j.err \
       --time=6:00:00 \
       --mem=8G \
       --cpus-per-task=2 \
       --wrap="bash -c 'source /sci/labs/orzuk/yaron.otmazgin/Authomathics/src/LLMVersion/venv/bin/activate && FULL_PAPERS_ADVANCED_DIR=/sci/labs/orzuk/orzuk/teaching/big_data_project_52017/2024_25/arxiv_data/full_papers_advanced python3 /sci/labs/orzuk/orzuk/teaching/big_data_project_52017/2024_25/arxiv_data/download_from_csv.py --csv /sci/labs/orzuk/orzuk/teaching/big_data_project_52017/2024_25/arxiv_data/sampled_100k_papers.csv --verbose --start-from 93929'"

############################## check how many papers were downloaded:########################


python3 -c "
from pathlib import Path
from collections import defaultdict

ORDER = ['math.CO','math.AG','math.NT','math.PR','math.AP','math.RT','math.GR','math.AT','math.LO','math.DG','math.FA','math.CA','math-ph','cs.DS','cs.CC','cs.LG','cs.IT','stat.TH','math.OC','math.NA']
d = Path('/sci/labs/orzuk/orzuk/teaching/big_data_project_52017/2024_25/arxiv_data/full_papers_advanced')

total = 0
for cat in ORDER:
    cat_dir = d / cat
    count = 0

    if cat_dir.exists():
        for year_dir in cat_dir.iterdir():
            if not year_dir.is_dir(): continue
            for month_dir in year_dir.iterdir():
                if not month_dir.is_dir(): continue
                for day_dir in month_dir.iterdir():
                    if not day_dir.is_dir(): continue
                    for paper_dir in day_dir.iterdir():
                        if not paper_dir.is_dir(): continue
                        if any(f.name.endswith('.tex') for f in paper_dir.iterdir()):
                            count += 1

    total += count
    print(f'{cat:<12} {count:>5}')

print(f\"{'TOTAL':<12} {total:>5}\")
"


########################################################################

# this for sbatch command
sbatch --job-name=download_100k \
       --output=/sci/labs/orzuk/orzuk/teaching/big_data_project_52017/2024_25/arxiv_data/logs/download_100k_%j.out \
       --error=/sci/labs/orzuk/orzuk/teaching/big_data_project_52017/2024_25/arxiv_data/logs/download_100k_%j.err \
       --time=5:00:00 \
       --mem=8G \
       --cpus-per-task=2 \
       --wrap="bash -c 'source /sci/labs/orzuk/yaron.otmazgin/Authomathics/src/LLMVersion/venv/bin/activate && FULL_PAPERS_ADVANCED_DIR=/sci/labs/orzuk/orzuk/teaching/big_data_project_52017/2024_25/arxiv_data/full_papers_advanced python3 /sci/labs/orzuk/orzuk/teaching/big_data_project_52017/2024_25/arxiv_data/download_from_csv.py --csv /sci/labs/orzuk/orzuk/teaching/big_data_project_52017/2024_25/arxiv_data/sampled_100k_papers.csv --verbose'"





###### 1000 papers parsing on cluster on
#on /sci/labs/orzuk/yaron.otmazgin/Authomathics

srun --time=6:00:00 --mem=8G --cpus-per-task=1 --pty bash
source /sci/labs/orzuk/yaron.otmazgin/Authomathics/src/LLMVersion/venv/bin/activate
cd /sci/labs/orzuk/yaron.otmazgin/Authomathics && \
OUT_V5=/sci/labs/orzuk/orzuk/teaching/big_data_project_52017/2024_25/arxiv_data/parsed_math_CO_manual_1000_v5 && \
PYTHONUNBUFFERED=1 python3 src/run_pipeline.py \
--operations parse,validate,stats,anomalies \
--category math.CO \
--start 2024-01-01 \
--end 2026-04-01 \
--top-k 1000 \
--extraction-mode manual \
--out-dir "$OUT_V5" \
--verbose 2>&1 | while IFS= read -r line; do echo "$(date +%H:%M:%S) $line"; done

# for stats and anomalies

python src/run_pipeline.py \
--operations stats \
--out-dir /sci/labs/orzuk/orzuk/teaching/big_data_project_52017/2024_25/arxiv_data/parsed_math_CO_manual_1000_v4

# 20 categories 100k parser on cluster

source /sci/labs/orzuk/yaron.otmazgin/Authomathics/src/LLMVersion/venv/bin/activate
cd /sci/labs/orzuk/yaron.otmazgin/Authomathics

sbatch --array=0-19 --time=12:00:00 --mem=8G --cpus-per-task=1 \
--job-name=authomath_100k \
--output=logs/authomath_100k_%A_%a.out \
--error=logs/authomath_100k_%A_%a.err \
--export=ALL,REPO_ROOT=/sci/labs/orzuk/yaron.otmazgin/Authomathics,TEX_SRC_BASE=/sci/labs/orzuk/orzuk/teaching/big_data_project_52017/2024_25/arxiv_data/full_papers_advanced,BASE_OUT_DIR=/sci/labs/orzuk/orzuk/teaching/big_data_project_52017/2024_25/arxiv_data/parsed_100k \
scripts/parse_multi_category_20.sh

# do linking after parsing:

sbatch --array=0-19 --time=04:00:00 --mem=16G --cpus-per-task=1 \
--job-name=authomath_link \
--output=logs/authomath_link_%A_%a.out \
--error=logs/authomath_link_%A_%a.err \
--export=ALL,PYTHONUNBUFFERED=1,REPO_ROOT=/sci/labs/orzuk/yaron.otmazgin/Authomathics,TEX_SRC_BASE=/sci/labs/orzuk/orzuk/teaching/big_data_project_52017/2024_25/arxiv_data/full_papers_advanced,BASE_OUT_DIR=/sci/labs/orzuk/orzuk/teaching/big_data_project_52017/2024_25/arxiv_data/parsed_100k,OPERATIONS=link \
scripts/parse_multi_category_20.sh

# only the 2 categories that were not fully parsed - add a 90 sec safeguard to skip them:
sbatch --array=15,18 --time=12:00:00 --mem=8G --cpus-per-task=1 \
--job-name=authomath_100k \
--output=logs/authomath_100k_%A_%a.out \
--error=logs/authomath_100k_%A_%a.err \
--export=ALL,REPO_ROOT=/sci/labs/orzuk/yaron.otmazgin/Authomathics,TEX_SRC_BASE=/sci/labs/orzuk/orzuk/teaching/big_data_project_52017/2024_25/arxiv_data/full_papers_advanced,BASE_OUT_DIR=/sci/labs/orzuk/orzuk/teaching/big_data_project_52017/2024_25/arxiv_data/parsed_100k,SAFEGUARD=90 \
scripts/parse_multi_category_20.sh

# see how many papers were parsed in each category:
sum=0
for d in /sci/labs/orzuk/orzuk/teaching/big_data_project_52017/2024_25/arxiv_data/parsed_100k/*/json; do
  c=$(find "$d" -maxdepth 1 -type f 2>/dev/null | wc -l)
  printf "%6d %s\n" "$c" "$d"
  sum=$((sum + c))
done
echo "TOTAL: $sum"

# see the dataset size:

du -sh /sci/labs/orzuk/orzuk/teaching/big_data_project_52017/2024_25/arxiv_data/parsed_100k

# or more precisely:
find /sci/labs/orzuk/orzuk/teaching/big_data_project_52017/2024_25/arxiv_data/parsed_100k -type f -printf '%s\n' | awk '{s+=$1} END {printf "%.1f GB\n", s/1024/1024/1024}'

# check if any of the parsed jsons might be a pdf file that was parsed:
srun --time=6:00:00 --mem=8G --cpus-per-task=1 --pty bash
source /sci/labs/orzuk/yaron.otmazgin/Authomathics/src/LLMVersion/venv/bin/activate
cd /sci/labs/orzuk/yaron.otmazgin/Authomathics
python detect_pdf_parses.py \
--parsed-dir /sci/labs/orzuk/orzuk/teaching/big_data_project_52017/2024_25/arxiv_data/parsed_100k \
--output suspected_pdfs.csv

# verify based on the output of the detected_pdf_parses.py:
python verify_pdf_suspects.py \
--csv suspected_pdfs.csv \
--tex-dir /sci/labs/orzuk/orzuk/teaching/big_data_project_52017/2024_25/arxiv_data/full_papers_advanced \
--output verified_pdfs.csv

# delete tex and parsed pdfs:

python delete_confirmed_pdfs.py \
--csv verified_pdfs.csv \
--parsed-dir /sci/labs/orzuk/orzuk/teaching/big_data_project_52017/2024_25/arxiv_data/parsed_100k \
--execute


# generating tables for paper:
cd /sci/labs/orzuk/yaron.otmazgin/Authomathics
python3 scripts/generate_paper_tables.py \
  --base-dir /sci/labs/orzuk/orzuk/teaching/big_data_project_52017/2024_25/arxiv_data/parsed_100k \
  --out-dir tables/

# then pushing new tables to git and then locally after pulling changes, move the new tables to Overleaf using:
bash sync_tables_to_overleaf.sh

# create html for each paper for visualization in the paper:

sbatch --array=0-19 --time=12:00:00 --mem=8G --cpus-per-task=1 \
  --job-name=authomath_viz \
  --output=logs/authomath_viz_%A_%a.out \
  --error=logs/authomath_viz_%A_%a.err \
  --export=ALL,PYTHONUNBUFFERED=1,MPLBACKEND=agg,REPO_ROOT=/sci/labs/orzuk/yaron.otmazgin/Authomathics,BASE_OUT_DIR=/sci/labs/orzuk/orzuk/teaching/big_data_project_52017/2024_25/arxiv_data/parsed_100k,OPERATIONS=visualize,HTML_ONLY=1 \
  scripts/parse_multi_category_20.sh





######################### FOR DATA FOR PAPAER ANALYSIS #########################

HF token: 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

# upload the dataset to HF:

srun --time=3:00:00 --mem=4G --cpus-per-task=2 hf upload-large-folder authomathics-100k /sci/labs/orzuk/orzuk/teaching/big_data_project_52017/2024_25/arxiv_data/parsed_100k --repo-type dataset

# upload the htmls to HF spaces:

sbatch --time=8:00:00 --mem=8G --cpus-per-task=2 -o logs/slurm-%j.out --wrap='
source /sci/labs/orzuk/yaron.otmazgin/Authomathics/src/LLMVersion/venv/bin/activate || true
python3 /sci/labs/orzuk/yaron.otmazgin/Authomathics/scripts/upload_htmls_to_space.py
'



