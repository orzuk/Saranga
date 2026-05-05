#!/usr/bin/env python3
"""Copy INCLUDE/UPDATE PDFs into the Authomathics pdf library and update the CSV.

For INCLUDE: append new CSV rows with the next book_id.
For UPDATE_EXISTING: edit in place to change pdf_status/pdf_path only.

Safe to re-run (it checks if destination already exists before copying).
"""
import csv
import os
import re
import shutil
import subprocess
import sys

SRC = "/mnt/g/My Drive/kind/more_books/"
PDF_DIR = "/mnt/c/Code/Github/Authomathics/textbooks/pdf/"
CSV_PATH = "/mnt/g/My Drive/Research/Automath/undergrad_textbooks.csv"

# (filename, verdict, book_id, short_name_for_filename, title, authors, year, topic_primary, topic_secondary, level)
# For UPDATE_EXISTING: use existing book_id and short_name only.
INCLUDE_ROWS = [
    # book_id, filename, short_name, title, authors, year, topic_primary, topic_secondary, level
    ("b260", "2013 Matrix Computations 4th Edition Golub Van Loan.pdf",
     "golub_matrix_computations", "Matrix Computations (4th ed.)",
     "Gene H. Golub; Charles F. Van Loan", 2013, "numerical_analysis", "linear_algebra_numerical", "advanced"),
    ("b261", "An-Introduction-to-probability-Theory-by-William-Feller-Volume-1.pdf",
     "feller_probability_vol1", "An Introduction to Probability Theory and Its Applications, Vol. 1 (3rd ed.)",
     "William Feller", 1968, "probability", "classical", "intermediate"),
    ("b262", "An-Introduction-to-probability-Theory-by-William-Feller-Volume-2.pdf",
     "feller_probability_vol2", "An Introduction to Probability Theory and Its Applications, Vol. 2 (2nd ed.)",
     "William Feller", 1971, "probability", "classical", "advanced"),
    ("b263", "AndersonZeitouniRandomMatrix_cupbook.pdf",
     "anderson_random_matrices", "An Introduction to Random Matrices",
     "Greg W. Anderson; Alice Guionnet; Ofer Zeitouni", 2010, "probability", "random_matrix_theory", "advanced"),
    ("b264", "AviWigdersonMathComputation_Book-online-Aug0619.pdf",
     "wigderson_math_and_computation", "Mathematics and Computation",
     "Avi Wigderson", 2019, "theory_of_computation", "mathematics_of_computation", "advanced"),
    ("b265", "AGRESTI_CategoricalDataAnalysis.PDF",
     "agresti_categorical_data_analysis", "Categorical Data Analysis (2nd ed.)",
     "Alan Agresti", 2002, "statistics", "categorical_data", "advanced"),
    ("b266", "AppliedLinearModels_BOOK.pdf",
     "kutner_applied_linear_statistical_models", "Applied Linear Statistical Models (5th ed.)",
     "Michael H. Kutner; Christopher J. Nachtsheim; John Neter; William Li", 2005, "statistics", "linear_models", "intermediate"),
    ("b267", "ComputationalOptimalTrnsport_1803.00567v4.pdf",
     "peyre_computational_optimal_transport", "Computational Optimal Transport",
     "Gabriel Peyré; Marco Cuturi", 2019, "optimization", "optimal_transport", "advanced"),
    ("b268", "Causality_ models, reasoning, and inference[Judea_Pearl].pdf",
     "pearl_causality", "Causality: Models, Reasoning, and Inference (2nd ed.)",
     "Judea Pearl", 2009, "statistics", "causal_inference", "advanced"),
    ("b269", "HighDimensionalProbability-book_Roman_Vershynin.pdf",
     "vershynin_high_dimensional_probability", "High-Dimensional Probability: An Introduction with Applications in Data Science",
     "Roman Vershynin", 2018, "probability", "high_dimensional", "advanced"),
    ("b270", "Roger_A.Horn. _Matrix_Analysis_2nd_edition(BookSee.org).pdf",
     "horn_matrix_analysis", "Matrix Analysis (2nd ed.)",
     "Roger A. Horn; Charles R. Johnson", 2012, "linear_algebra", "matrix_theory", "advanced"),
    ("b271", "[Michael_Artin]_Algebra(BookFi.org).pdf",
     "artin_algebra", "Algebra",
     "Michael Artin", 1991, "abstract_algebra", "groups_rings_fields", "intermediate"),
    ("b272", "[Romain_Couillet,_Merouane_Debbah]_Random_Matrix_M(BookFi.org).pdf",
     "couillet_random_matrix_methods", "Random Matrix Methods for Wireless Communications",
     "Romain Couillet; Mérouane Debbah", 2011, "probability", "random_matrix_theory", "advanced"),
    ("b273", "abramowitz_and_stegun_handbook_math_functions.pdf",
     "abramowitz_handbook_mathematical_functions", "Handbook of Mathematical Functions with Formulas, Graphs, and Mathematical Tables",
     "Milton Abramowitz; Irene A. Stegun", 1964, "applied_math", "reference", "intermediate"),
    ("b274", "algebraic_statistics_book_sullivant2.pdf",
     "sullivant_algebraic_statistics", "Algebraic Statistics",
     "Seth Sullivant", 2018, "statistics", "algebraic_statistics", "advanced"),
    ("b275", "algorithmic_robust_statistics-book.pdf",
     "diakonikolas_algorithmic_robust_statistics", "Algorithmic High-Dimensional Robust Statistics",
     "Ilias Diakonikolas; Daniel M. Kane", 2023, "statistics", "robust_statistics", "advanced"),
    ("b276", "Hogben-Handbook of Linear Algebra-(CRC press, 2007).pdf",
     "hogben_handbook_linear_algebra", "Handbook of Linear Algebra",
     "Leslie Hogben (ed.)", 2007, "linear_algebra", "reference", "advanced"),
    ("b277", "HighDimDataAnalysisBook-WM-20210422_YiMa_JohnWright.pdf",
     "wright_high_dim_data_analysis", "High-Dimensional Data Analysis with Low-Dimensional Models",
     "John Wright; Yi Ma", 2022, "data_science", "low_dim_models", "advanced"),
    ("b278", "IntroOptimManifolds_Boumal_2023.pdf",
     "boumal_optimization_on_manifolds", "An Introduction to Optimization on Smooth Manifolds",
     "Nicolas Boumal", 2023, "optimization", "manifold_optimization", "advanced"),
    ("b279", "IntroProbProgramming_1809.10756.pdf",
     "vandemeent_probabilistic_programming", "An Introduction to Probabilistic Programming",
     "Jan-Willem van de Meent; Brooks Paige; Hongseok Yang; Frank Wood", 2018, "machine_learning", "probabilistic_programming", "intermediate"),
    ("b280", "Johnstone_Gaussian_Estimation_GE06-11-13.pdf",
     "johnstone_gaussian_estimation", "Gaussian Estimation: Sequence and Wavelet Models",
     "Iain M. Johnstone", 2013, "statistics", "nonparametric", "advanced"),
    ("b281", "KernelMachineLearning_master2017.pdf",
     "mairal_machine_learning_with_kernels", "Machine Learning with Kernel Methods",
     "Julien Mairal; Jean-Philippe Vert", 2020, "machine_learning", "kernel_methods", "advanced"),
    ("b282", "LLM_Foundations_2501.09223v2.pdf",
     "xiao_foundations_of_llms", "Foundations of Large Language Models",
     "Tong Xiao; Jingbo Zhu", 2025, "machine_learning", "llm", "intermediate"),
    ("b283", "MathForComputerScienceTomLeighton.pdf",
     "lehman_math_for_cs", "Mathematics for Computer Science",
     "Eric Lehman; F. Thomson Leighton; Albert R. Meyer", 2018, "discrete_math", "for_cs", "intermediate"),
    ("b284", "MathIntroDeepLearning_2310.20360v2.pdf",
     "jentzen_math_intro_deep_learning", "Mathematical Introduction to Deep Learning: Methods, Implementations, and Theory",
     "Arnulf Jentzen; Benno Kuckuck; Philippe von Wurstemberger", 2025, "machine_learning", "deep_learning", "advanced"),
    ("b285", "Methods of Multivariate Analysis.pdf",
     "rencher_multivariate_analysis", "Methods of Multivariate Analysis (2nd ed.)",
     "Alvin C. Rencher", 2002, "statistics", "multivariate", "intermediate"),
    ("b286", "Mallat3WaveletsSparseWay.pdf",
     "mallat_wavelet_tour", "A Wavelet Tour of Signal Processing: The Sparse Way (3rd ed.)",
     "Stéphane Mallat", 2009, "applied_math", "wavelets_signal_processing", "advanced"),
    ("b287", "Watrous_QuantumInformation_TQI.pdf",
     "watrous_theory_quantum_information", "The Theory of Quantum Information",
     "John Watrous", 2018, "information_theory", "quantum_information", "advanced"),
    ("b288", "Woodruff_Sketching_wNow3.pdf",
     "woodruff_sketching_numerical_linear_algebra", "Sketching as a Tool for Numerical Linear Algebra",
     "David P. Woodruff", 2014, "numerical_analysis", "randomized_numerical_linear_algebra", "advanced"),
    ("b289", "Rao C.R., H.Toutenberg. Linear Models.. Least Squares and Al (1999).pdf",
     "rao_linear_models", "Linear Models: Least Squares and Alternatives (2nd ed.)",
     "C. Radhakrishna Rao; Helge Toutenburg", 1999, "statistics", "linear_models", "advanced"),
    ("b290", "Nemirovski_BenTal_OPTIIILN2023Spring.pdf",
     "bental_optimization_iii_lectures", "Optimization III: Convex Analysis, Nonlinear Programming Theory and Algorithms (lecture notes)",
     "Aharon Ben-Tal; Arkadi Nemirovski", 2023, "optimization", "convex_nonlinear", "advanced"),
    ("b291", "PavliotisBook_StochasticProcesses.pdf",
     "pavliotis_stochastic_processes", "Stochastic Processes and Applications",
     "Grigorios A. Pavliotis", 2015, "probability", "stochastic_processes", "advanced"),
    ("b292", "ProbabilityHighDimension_APC550.pdf",
     "vanhandel_probability_high_dimension", "Probability in High Dimension (APC 550 Lecture Notes)",
     "Ramon van Handel", 2016, "probability", "high_dimensional", "advanced"),
    ("b293", "RigoletHutter_HighDimStatistics_Notes17.pdf",
     "rigollet_high_dim_statistics", "High Dimensional Statistics (MIT 18.657 Lecture Notes)",
     "Philippe Rigollet; Jan-Christian Hütter", 2019, "statistics", "high_dimensional", "advanced"),
    ("b294", "ShaliziAdvancedDataAnalysis_ADAfaEPoV.pdf",
     "shalizi_advanced_data_analysis", "Advanced Data Analysis from an Elementary Point of View",
     "Cosma Rohilla Shalizi", 2017, "statistics", "data_analysis", "intermediate"),
    ("b295", "SparseLearning_HastieWainwright_SLS_corrected_1.4.16.pdf",
     "hastie_statistical_learning_with_sparsity", "Statistical Learning with Sparsity: The Lasso and Generalizations",
     "Trevor Hastie; Robert Tibshirani; Martin Wainwright", 2015, "statistics", "sparse_regression", "advanced"),
    ("b296", "TheoryOfPointEstimation - E L Lehaman.pdf",
     "lehmann_theory_point_estimation", "Theory of Point Estimation (2nd ed.)",
     "E. L. Lehmann; George Casella", 1998, "statistics", "estimation_theory", "advanced"),
    ("b297", "TimeSeriesAnalysis_Book_SAS.pdf",
     "falk_time_series_analysis", "A First Course on Time Series Analysis (SAS)",
     "Michael Falk et al.", 2012, "statistics", "time_series", "intermediate"),
    ("b298", "casi_EfronHastie.pdf",
     "efron_computer_age_statistical_inference", "Computer Age Statistical Inference: Algorithms, Evidence, and Data Science",
     "Bradley Efron; Trevor Hastie", 2016, "statistics", "computational_inference", "intermediate"),
    ("b299", "GameTheoryBonanno.1512.06808.pdf",
     "bonanno_game_theory", "Game Theory (open access textbook)",
     "Giacomo Bonanno", 2015, "game_theory", "intro", "intermediate"),
    ("b300", "Generalized_PCA_book-VMS-Nov05.pdf",
     "vidal_generalized_pca", "Generalized Principal Component Analysis",
     "René Vidal; Yi Ma; Shankar Sastry", 2016, "machine_learning", "subspace_methods", "advanced"),
    ("b301", "Giraud_HighDimensionalStatistics_LectureNotes.pdf",
     "giraud_high_dim_statistics_intro", "Introduction to High-Dimensional Statistics",
     "Christophe Giraud", 2021, "statistics", "high_dimensional", "advanced"),
    ("b302", "PROB_AI_BOOK_2502.05244v1.pdf",
     "krause_probabilistic_ai", "Probabilistic Artificial Intelligence",
     "Andreas Krause; Jonas Hübotter", 2025, "machine_learning", "probabilistic_ai", "advanced"),
    ("b303", "Francis_Bach_ltfp_book.pdf",
     "bach_learning_theory_from_first_principles", "Learning Theory from First Principles",
     "Francis Bach", 2024, "machine_learning", "theory", "advanced"),
    ("b304", "LMCOBookSIAM.pdf",
     "bental_lectures_modern_convex_optimization", "Lectures on Modern Convex Optimization (MPS-SIAM Series)",
     "Aharon Ben-Tal; Arkadi Nemirovski", 2001, "optimization", "convex", "advanced"),
    ("b305", "Linear_and_NonLinear_Programming_310trialtext.pdf",
     "luenberger_linear_and_nonlinear_programming", "Linear and Nonlinear Programming",
     "David G. Luenberger; Yinyu Ye", 2008, "optimization", "mathematical_programming", "intermediate"),
    ("b306", "IntroModernStatistics.pdf",
     "cetinkayarundel_intro_modern_statistics", "Introduction to Modern Statistics",
     "Mine Çetinkaya-Rundel; Johanna Hardin", 2021, "statistics", "intro", "intro"),
    ("b307", "NonConvexOptimization_1712.07897.pdf",
     "jain_non_convex_optimization", "Non-Convex Optimization for Machine Learning",
     "Prateek Jain; Purushottam Kar", 2017, "optimization", "non_convex", "advanced"),
    ("b308", "NumericalMatrixAnalysis.pdf",
     "higham_numerical_matrix_analysis", "Numerical Matrix Analysis: Linear Systems and Least Squares",
     "Ilse C. F. Ipsen", 2009, "numerical_analysis", "linear_algebra_numerical", "advanced"),
    ("b309", "OptimalTransportLectureNotes_978-3-031-76834-7.pdf",
     "ambrosio_optimal_transport_lectures", "Lectures on Optimal Transport (2nd ed.)",
     "Luigi Ambrosio; Elia Brué; Daniele Semola", 2024, "optimization", "optimal_transport", "advanced"),
    ("b310", "FormalReasoning.pdf",
     "geuvers_formal_reasoning", "Formal Reasoning",
     "Herman Geuvers et al.", 2025, "logic", "proof", "intermediate"),
    ("b311", "EfronLargeScaleInference.pdf",
     "efron_large_scale_inference", "Large-Scale Inference: Empirical Bayes Methods for Estimation, Testing, and Prediction",
     "Bradley Efron", 2010, "statistics", "empirical_bayes", "advanced"),
    ("b312", "theorem_proving_in_lean.pdf",
     "avigad_theorem_proving_in_lean", "Theorem Proving in Lean",
     "Jeremy Avigad; Leonardo de Moura; Soonho Kong", 2019, "logic", "formal_proof", "intermediate"),
    ("b313", "Geometry_of_Mainfolds_Lectures.pdf",
     "nicolaescu_geometry_of_manifolds", "Lectures on the Geometry of Manifolds",
     "Liviu I. Nicolaescu", 2018, "differential_geometry", "manifolds", "advanced"),
    ("b314", "Intro2ComplexAnalysis.pdf",
     "agarwal_introduction_to_complex_analysis", "An Introduction to Complex Analysis",
     "Ravi P. Agarwal; Kanishka Perera; Sandra Pinelas", 2011, "complex_analysis", "", "intermediate"),
    ("b315", "complex.pdf",
     "taylor_introduction_to_complex_analysis", "Introduction to Complex Analysis",
     "Michael E. Taylor", 2019, "complex_analysis", "", "advanced"),
    ("b316", "introductiontoco00shab_part2.pdf",
     "shabat_complex_analysis_part2", "Introduction to Complex Analysis, Part II: Functions of Several Variables",
     "B. V. Shabat", 1992, "complex_analysis", "several_variables", "advanced"),
    ("b317", "AlgorithmicProblemSolving.pdf",
     "sannemo_algorithmic_problem_solving", "Principles of Algorithmic Problem Solving",
     "Johan Sannemo", 2017, "algorithms", "problem_solving", "intermediate"),
    ("b318", "GrantTodes2008.pdf",
     "grant_theory_of_ode", "Theory of Ordinary Differential Equations",
     "Christopher P. Grant", 2008, "differential_equations", "ODE", "advanced"),
    ("b319", "SpeechLanguage_ed3book_aug25.pdf",
     "jurafsky_speech_and_language_processing", "Speech and Language Processing (3rd ed. draft)",
     "Daniel Jurafsky; James H. Martin", 2025, "machine_learning", "NLP", "intermediate"),
    ("b320", "DeepLearningLittleBookFranceisCaulet_lbdl.pdf",
     "fleuret_little_book_deep_learning", "The Little Book of Deep Learning",
     "François Fleuret", 2023, "machine_learning", "deep_learning", "intro"),
    ("b321", "spectralbook_Vempala.pdf",
     "kannan_spectral_algorithms", "Spectral Algorithms",
     "Ravindran Kannan; Santosh Vempala", 2009, "algorithms", "spectral_methods", "advanced"),
    ("b322", "TenLecturesFortyTwoProblemsDataScience.pdf",
     "bandeira_ten_lectures_data_science", "Ten Lectures and Forty-Two Open Problems in the Mathematics of Data Science",
     "Afonso S. Bandeira", 2015, "data_science", "open_problems", "advanced"),
    ("b323", "MatrixCalculus_2501.14787v1.pdf",
     "edelman_matrix_calculus", "Matrix Calculus (for Machine Learning and Beyond)",
     "Paige Bright; Alan Edelman; Steven G. Johnson", 2025, "applied_math", "matrix_calculus", "intermediate"),
    ("b324", "Russel_Norvig_Artificial Intelligence A Modern Approach (3rd Edition).pdf",
     "russell_artificial_intelligence_modern_approach", "Artificial Intelligence: A Modern Approach (3rd ed.)",
     "Stuart Russell; Peter Norvig", 2009, "machine_learning", "ai_general", "intermediate"),
    ("b325", "math-deep.pdf",
     "gallier_algebra_topology_calculus_ml", "Algebra, Topology, Differential Calculus, and Optimization Theory for Computer Science and Machine Learning",
     "Jean Gallier; Jocelyn Quaintance", 2022, "applied_math", "math_for_ML", "advanced"),
    ("b326", "math_foundations_kunen770.pdf",
     "kunen_foundations_of_mathematics", "The Foundations of Mathematics",
     "Kenneth Kunen", 2007, "logic", "foundations", "intermediate"),
]

# UPDATE_EXISTING: (existing_book_id, source_filename, new_short_name)
UPDATE_ROWS = [
    ("b025", "thinkbayes.pdf", "downey_think_bayes"),
    ("b039", "Cormen_Algorithms_3rd.pdf", "cormen_algorithms"),
    ("b042", "Elements_of_Information_Theory_Elements_CoverThomas.pdf", "cover_elements_info_theory"),
    ("b051", "NumericalLinearAlgebra_Trefethen-Bau.pdf", "trefethen_numerical_linear_algebra"),
    ("b163", "CausalInference_Scholkof_11283.pdf", "peters_elements_causal_inference"),
]


def get_page_count(path):
    """Return page count or empty string."""
    try:
        r = subprocess.run(["pdfinfo", path], capture_output=True, text=True, timeout=60)
        for line in r.stdout.splitlines():
            if line.startswith("Pages:"):
                return line.split(":",1)[1].strip()
    except Exception:
        pass
    return ""


def copy_pdfs():
    """Copy all INCLUDE and UPDATE_EXISTING PDFs to pdf/ directory."""
    copied = []
    for book_id, fname, short, *_ in INCLUDE_ROWS:
        src = os.path.join(SRC, fname)
        dst_name = f"{book_id}_{short}.pdf"
        dst = os.path.join(PDF_DIR, dst_name)
        if not os.path.exists(src):
            print(f"MISSING SRC: {src}", file=sys.stderr)
            continue
        if os.path.exists(dst):
            copied.append((book_id, dst_name, "already_exists"))
            continue
        shutil.copy(src, dst)
        copied.append((book_id, dst_name, "copied"))

    for book_id, fname, short in UPDATE_ROWS:
        src = os.path.join(SRC, fname)
        dst_name = f"{book_id}_{short}.pdf"
        dst = os.path.join(PDF_DIR, dst_name)
        if not os.path.exists(src):
            print(f"MISSING SRC: {src}", file=sys.stderr)
            continue
        if os.path.exists(dst):
            copied.append((book_id, dst_name, "already_exists"))
            continue
        shutil.copy(src, dst)
        copied.append((book_id, dst_name, "copied"))
    return copied


def update_csv():
    """Read CSV as raw lines; update only the rows we explicitly change.

    This preserves original byte-exact formatting for rows we do NOT touch (avoiding
    roundtrip issues with historical rows that have unquoted commas in titles).
    """
    import io
    with open(CSV_PATH, "r", encoding="utf-8", newline="") as fh:
        raw = fh.read()
    lines = raw.splitlines()
    header = lines[0]
    assert header.startswith("book_id,"), header[:80]

    existing_ids = set()
    for line in lines[1:]:
        if not line.strip():
            continue
        existing_ids.add(line.split(",", 1)[0])

    # --- UPDATE existing rows ---
    updated = []
    for book_id, fname, short in UPDATE_ROWS:
        dst_name = f"{book_id}_{short}.pdf"
        found = False
        for i, line in enumerate(lines):
            if i == 0 or not line:
                continue
            if line.startswith(book_id + ","):
                parsed = next(csv.reader([line]))
                # Pad if necessary (should be 22; some rows may be broken)
                while len(parsed) < 22:
                    parsed.append("")
                old_status = parsed[15]
                parsed[15] = "downloaded"
                parsed[16] = f"pdf/{dst_name}"
                out = io.StringIO()
                csv.writer(out).writerow(parsed)
                lines[i] = out.getvalue().rstrip("\r\n")
                updated.append((book_id, dst_name, old_status))
                found = True
                break
        if not found:
            print(f"WARN: could not find {book_id} to update", file=sys.stderr)

    # --- APPEND new rows ---
    appended = []
    for book_id, fname, short, title, authors, year, topic_primary, topic_secondary, level in INCLUDE_ROWS:
        if book_id in existing_ids:
            print(f"SKIP append (already present): {book_id}", file=sys.stderr)
            continue
        src = os.path.join(SRC, fname)
        pages = get_page_count(src) if os.path.exists(src) else ""
        dst_name = f"{book_id}_{short}.pdf"
        row = [
            book_id,
            title,
            authors,
            year,
            topic_primary,
            topic_secondary,
            level,
            "manual_from_more_books",
            "pdf",
            "USER_PROVIDED",
            "",
            pages,
            "",
            "HIGH",
            "From user's personal more_books directory.",
            "downloaded",
            f"pdf/{dst_name}",
            "not_attempted",
            "",
            "not_attempted",
            "",
            "",
        ]
        assert len(row) == 22
        out = io.StringIO()
        csv.writer(out).writerow(row)
        lines.append(out.getvalue().rstrip("\r\n"))
        appended.append((book_id, title))

    # Preserve trailing newline behavior: if original ended with newline, keep one.
    ends_with_nl = raw.endswith("\n")
    new_content = "\n".join(lines)
    if ends_with_nl:
        new_content += "\n"
    with open(CSV_PATH, "w", encoding="utf-8", newline="") as fh:
        fh.write(new_content)
    return updated, appended


def main():
    print("Phase: copy PDFs")
    copied = copy_pdfs()
    for b, name, status in copied:
        print(f"  {status:14s} {b} -> {name}")

    print("\nPhase: update CSV")
    updated, appended = update_csv()
    print(f"  updated existing rows: {len(updated)}")
    for b, n, os_ in updated:
        print(f"    {b}: {os_} -> downloaded   (pdf/{n})")
    print(f"  appended new rows: {len(appended)}")
    for b, t in appended:
        print(f"    {b}: {t}")


if __name__ == "__main__":
    main()
