#!/usr/bin/env python3
"""Classification plan for /mnt/g/My Drive/kind/more_books/."""
import os

src = "/mnt/g/My Drive/kind/more_books/"

# Full classification plan: (filename, verdict, book_id_or_reason)
classifications = [
    # EXCLUDE_DUPLICATE
    ("2006 - Wasserman All Of Nonparametric Statistics.pdf", "EXCLUDE_DUPLICATE", "b250"),
    ("All of Nonparametric Statistics Wasserman.pdf", "EXCLUDE_DUPLICATE", "b250"),
    ("Wasseram.AllOfNonParametricStatistics.pdf", "EXCLUDE_DUPLICATE", "b250"),
    ("Wasseram.AllOfStatistics.pdf", "EXCLUDE_DUPLICATE", "b020"),
    ("Tibshirani_Hastie_Friedman - ESL2_print10.pdf", "EXCLUDE_DUPLICATE", "b021"),
    ("ISLR First Printing.pdf", "EXCLUDE_DUPLICATE", "b022"),
    ("vmls.pdf", "EXCLUDE_DUPLICATE", "b009"),
    ("mml-book.pdf", "EXCLUDE_DUPLICATE", "b095"),
    ("Smola_d2l-en.pdf", "EXCLUDE_DUPLICATE", "b048"),
    ("PML_KevinPatrickMurphy_book1.pdf", "EXCLUDE_DUPLICATE", "b097"),
    ("ProbML_book1.pdf", "EXCLUDE_DUPLICATE", "b097"),
    ("hopcroft-kannan-feb2012.pdf", "EXCLUDE_DUPLICATE", "b067_older"),
    ("book2016June9_FoundationsOfDataScience.pdf", "EXCLUDE_DUPLICATE", "b067_older"),
    ("FoundationsOfDataScience_BlumHopcroftKannan_2020.pdf", "EXCLUDE_DUPLICATE", "b067"),
    ("MassiveDatasets.pdf", "EXCLUDE_DUPLICATE", "b068_older"),
    ("MiningMassiveDatasets_LeskovecRajaramanUllman_2020_3rdEd.pdf", "EXCLUDE_DUPLICATE", "b068"),
    ("mathandcomp_AviWigderson.pdf", "EXCLUDE_DUPLICATE", "b264_older"),
    ("Smola_d2l-en_JupyterNotebook.zip", "EXCLUDE_NOT_PDF", "b048"),
    ("math_for_cs.pdf", "EXCLUDE_DUPLICATE", "b283_older"),
    ("cupbook.pdf", "EXCLUDE_DUPLICATE", "b263_same"),
    ("Bubeck_convex_optimization.pdf", "EXCLUDE_DUPLICATE", "b211"),
    ("Probability Theory - The Logic of Science Janes.pdf", "EXCLUDE_DUPLICATE", "b019"),
    ("GeometricDeepLearning_2104.13478.pdf", "EXCLUDE_DUPLICATE", "b248"),
    ("MAthFoundationDeepLearning_2508.02723v1.pdf", "EXCLUDE_DUPLICATE", "b249"),
    ("LLM_BOOK_2501.09223v1.pdf", "EXCLUDE_DUPLICATE", "b282_older"),
    ("Speech_Language_ed3book.pdf", "EXCLUDE_DUPLICATE", "b319_older"),
    ("ReinforcementLearning_SuttonBartoIPRLBook2ndEd.pdf", "EXCLUDE_DUPLICATE", "b164"),
    # UPDATE_EXISTING
    ("Cormen_Algorithms_3rd.pdf", "UPDATE_EXISTING", "b039"),
    ("Elements_of_Information_Theory_Elements_CoverThomas.pdf", "UPDATE_EXISTING", "b042"),
    ("NumericalLinearAlgebra_Trefethen-Bau.pdf", "UPDATE_EXISTING", "b051"),
    ("thinkbayes.pdf", "UPDATE_EXISTING", "b025"),
    ("CausalInference_Scholkof_11283.pdf", "UPDATE_EXISTING", "b163"),
    # EXCLUDE_PAPER
    ("2510.21890.pdf", "EXCLUDE_PAPER", "arxiv_preprint"),
    ("Church_CombinationTherapy_PNAS_1910073116.full.pdf", "EXCLUDE_PAPER", "PNAS"),
    ("NatureReviewsGenetics_of_HumanAginga_10.1038@s41576-019-0183-6.pdf", "EXCLUDE_PAPER", "Nature"),
    ("MathematicsDeepLearning.1712.04741.pdf", "EXCLUDE_PAPER", "short_tutorial"),
    ("SpectralLearning_Anima_2004.07984v1.pdf", "EXCLUDE_TOO_SPECIALIZED", "narrow_F&T"),
    ("RandomForests_1407.7502.pdf", "EXCLUDE_PAPER", "PhD_dissertation"),
    ("RandomizedAlgorithmsScientificComputing_2104.11079.pdf", "EXCLUDE_PAPER", "workshop_report"),
    # EXCLUDE_SOFT
    ("2019_Book_EvolutionaryGenomics.pdf", "EXCLUDE_SOFT", "biology"),
    ("Pritcgard_HGBook-2023-09-nochapnotes_Part1.pdf", "EXCLUDE_SOFT", "popgen"),
    ("pevsner_bioinformatics_and_functional_genomics_3rd.pdf", "EXCLUDE_SOFT", "bioinfo"),
    ("release_popgen_notes_Graham_Coop.pdf", "EXCLUDE_SOFT", "popgen"),
    ("Durret_ProbModels_PM4DNA_0317.pdf", "EXCLUDE_SOFT", "DNA_application"),
    ("Kahneman_2011_Thinking_Fast_and_Slow.pdf", "EXCLUDE_SOFT", "psych_popular"),
    ("Data Engineering Cookbook.pdf", "EXCLUDE_SOFT", "applied"),
    ("Databases_all.pdf", "EXCLUDE_SOFT", "applied_DB"),
    ("Data-Science-in-Context-V.99-Web-Beta.pdf", "EXCLUDE_SOFT", "DS_context"),
    ("FronteirsDataScience18374.pdf", "EXCLUDE_SOFT", "NRC_report"),
    ("StatisticalViewDeepLearning.pdf", "EXCLUDE_SOFT", "blog_compilation"),
    ("The-Art-of-Molecular-Dynamics-Simulation.pdf", "EXCLUDE_SOFT", "simulation_applied"),
    ("past-present-future-copss.pdf", "EXCLUDE_SOFT", "retrospective_essays"),
    ("White_book_deep_learning.pdf", "EXCLUDE_SOFT", "unreadable"),
    ("Mathematical_Tools-2014.pdf", "EXCLUDE_SOFT", "hebrew_student_notes"),
    ("stanford_quest_artificial_intelligence.pdf", "EXCLUDE_SOFT", "AI_history"),
    ("Introduction to complex analysis.pdf", "EXCLUDE_UNIDENTIFIED", "scanned_no_OCR"),
    ("9780262517638_Open_Access_PDF_Version.pdf", "EXCLUDE_SOFT", "Suber_open_access_book"),
    # EXCLUDE_TOO_SPECIALIZED
    ("Talagrand_UpperLowerBounds.pdf", "EXCLUDE_TOO_SPECIALIZED", "research_monograph"),
    ("SpinGlass_Talagrand_volume1.pdf", "EXCLUDE_TOO_SPECIALIZED", "research_monograph"),
    ("ABT_logarithmic_combinatorial_probabilistic_book.pdf", "EXCLUDE_TOO_SPECIALIZED", "research_monograph"),
    ("edgeworth_bootstrap.pdf", "EXCLUDE_TOO_SPECIALIZED", "Peter_Hall_monograph"),
    ("convex_optimization_sparsity_norms_book.pdf", "EXCLUDE_TOO_SPECIALIZED", "narrow_F&T"),
    ("ZeitouniDemboLargeDeviationsTechniquesApplications.pdf.crdownload", "EXCLUDE_PARTIAL_DOWNLOAD", "interrupted"),
    # INCLUDE (new books) -- book_id assigned below
    ("2013 Matrix Computations 4th Edition Golub Van Loan.pdf", "INCLUDE", "b260"),
    ("An-Introduction-to-probability-Theory-by-William-Feller-Volume-1.pdf", "INCLUDE", "b261"),
    ("An-Introduction-to-probability-Theory-by-William-Feller-Volume-2.pdf", "INCLUDE", "b262"),
    ("AndersonZeitouniRandomMatrix_cupbook.pdf", "INCLUDE", "b263"),
    ("AviWigdersonMathComputation_Book-online-Aug0619.pdf", "INCLUDE", "b264"),
    ("AGRESTI_CategoricalDataAnalysis.PDF", "INCLUDE", "b265"),
    ("AppliedLinearModels_BOOK.pdf", "INCLUDE", "b266"),
    ("ComputationalOptimalTrnsport_1803.00567v4.pdf", "INCLUDE", "b267"),
    ("Causality_ models, reasoning, and inference[Judea_Pearl].pdf", "INCLUDE", "b268"),
    ("HighDimensionalProbability-book_Roman_Vershynin.pdf", "INCLUDE", "b269"),
    ("Roger_A.Horn. _Matrix_Analysis_2nd_edition(BookSee.org).pdf", "INCLUDE", "b270"),
    ("[Michael_Artin]_Algebra(BookFi.org).pdf", "INCLUDE", "b271"),
    ("[Romain_Couillet,_Merouane_Debbah]_Random_Matrix_M(BookFi.org).pdf", "INCLUDE", "b272"),
    ("abramowitz_and_stegun_handbook_math_functions.pdf", "INCLUDE", "b273"),
    ("algebraic_statistics_book_sullivant2.pdf", "INCLUDE", "b274"),
    ("algorithmic_robust_statistics-book.pdf", "INCLUDE", "b275"),
    ("Hogben-Handbook of Linear Algebra-(CRC press, 2007).pdf", "INCLUDE", "b276"),
    ("HighDimDataAnalysisBook-WM-20210422_YiMa_JohnWright.pdf", "INCLUDE", "b277"),
    ("IntroOptimManifolds_Boumal_2023.pdf", "INCLUDE", "b278"),
    ("IntroProbProgramming_1809.10756.pdf", "INCLUDE", "b279"),
    ("Johnstone_Gaussian_Estimation_GE06-11-13.pdf", "INCLUDE", "b280"),
    ("KernelMachineLearning_master2017.pdf", "INCLUDE", "b281"),
    ("LLM_Foundations_2501.09223v2.pdf", "INCLUDE", "b282"),
    ("MathForComputerScienceTomLeighton.pdf", "INCLUDE", "b283"),
    ("MathIntroDeepLearning_2310.20360v2.pdf", "INCLUDE", "b284"),
    ("Methods of Multivariate Analysis.pdf", "INCLUDE", "b285"),
    ("Mallat3WaveletsSparseWay.pdf", "INCLUDE", "b286"),
    ("Watrous_QuantumInformation_TQI.pdf", "INCLUDE", "b287"),
    ("Woodruff_Sketching_wNow3.pdf", "INCLUDE", "b288"),
    ("Rao C.R., H.Toutenberg. Linear Models.. Least Squares and Al (1999).pdf", "INCLUDE", "b289"),
    ("Nemirovski_BenTal_OPTIIILN2023Spring.pdf", "INCLUDE", "b290"),
    ("PavliotisBook_StochasticProcesses.pdf", "INCLUDE", "b291"),
    ("ProbabilityHighDimension_APC550.pdf", "INCLUDE", "b292"),
    ("RigoletHutter_HighDimStatistics_Notes17.pdf", "INCLUDE", "b293"),
    ("ShaliziAdvancedDataAnalysis_ADAfaEPoV.pdf", "INCLUDE", "b294"),
    ("SparseLearning_HastieWainwright_SLS_corrected_1.4.16.pdf", "INCLUDE", "b295"),
    ("TheoryOfPointEstimation - E L Lehaman.pdf", "INCLUDE", "b296"),
    ("TimeSeriesAnalysis_Book_SAS.pdf", "INCLUDE", "b297"),
    ("casi_EfronHastie.pdf", "INCLUDE", "b298"),
    ("GameTheoryBonanno.1512.06808.pdf", "INCLUDE", "b299"),
    ("Generalized_PCA_book-VMS-Nov05.pdf", "INCLUDE", "b300"),
    ("Giraud_HighDimensionalStatistics_LectureNotes.pdf", "INCLUDE", "b301"),
    ("PROB_AI_BOOK_2502.05244v1.pdf", "INCLUDE", "b302"),
    ("Francis_Bach_ltfp_book.pdf", "INCLUDE", "b303"),
    ("LMCOBookSIAM.pdf", "INCLUDE", "b304"),
    ("Linear_and_NonLinear_Programming_310trialtext.pdf", "INCLUDE", "b305"),
    ("IntroModernStatistics.pdf", "INCLUDE", "b306"),
    ("NonConvexOptimization_1712.07897.pdf", "INCLUDE", "b307"),
    ("NumericalMatrixAnalysis.pdf", "INCLUDE", "b308"),
    ("OptimalTransportLectureNotes_978-3-031-76834-7.pdf", "INCLUDE", "b309"),
    ("FormalReasoning.pdf", "INCLUDE", "b310"),
    ("EfronLargeScaleInference.pdf", "INCLUDE", "b311"),
    ("theorem_proving_in_lean.pdf", "INCLUDE", "b312"),
    ("Geometry_of_Mainfolds_Lectures.pdf", "INCLUDE", "b313"),
    ("Intro2ComplexAnalysis.pdf", "INCLUDE", "b314"),
    ("complex.pdf", "INCLUDE", "b315"),
    ("introductiontoco00shab_part2.pdf", "INCLUDE", "b316"),
    ("AlgorithmicProblemSolving.pdf", "INCLUDE", "b317"),
    ("GrantTodes2008.pdf", "INCLUDE", "b318"),
    ("SpeechLanguage_ed3book_aug25.pdf", "INCLUDE", "b319"),
    ("DeepLearningLittleBookFranceisCaulet_lbdl.pdf", "INCLUDE", "b320"),
    ("spectralbook_Vempala.pdf", "INCLUDE", "b321"),
    ("TenLecturesFortyTwoProblemsDataScience.pdf", "INCLUDE", "b322"),
    ("MatrixCalculus_2501.14787v1.pdf", "INCLUDE", "b323"),
    ("Russel_Norvig_Artificial Intelligence A Modern Approach (3rd Edition).pdf", "INCLUDE", "b324"),
    ("math-deep.pdf", "INCLUDE", "b325"),
    ("math-basics_for_MachineLearning.pdf", "EXCLUDE_DUPLICATE", "b325_older"),
    ("math_foundations_kunen770.pdf", "INCLUDE", "b326"),
]


def main():
    src_files = set(os.listdir(src))
    for d in ("DeepLearningBook","DeepUnsupervisedLearningAbbeelCourse","FOCS_Ullman","NielsenDeepLearning","Popular"):
        src_files.discard(d)
    classified = set(c[0] for c in classifications)
    unclassified = sorted(src_files - classified)

    lines = []
    lines.append("# CLASSIFICATION LOG for /mnt/g/My Drive/kind/more_books/")
    total_pdfs = len([f for f in src_files if f.lower().endswith(('.pdf','.pdf.crdownload','.zip'))])
    lines.append(f"# Total entries (excluding subdirs): {len(src_files)}")
    lines.append(f"# Classified: {len(classified & src_files)}")
    lines.append(f"# Unclassified: {len(unclassified)}")
    lines.append("")
    for verdict in ["INCLUDE","UPDATE_EXISTING","EXCLUDE_DUPLICATE","EXCLUDE_PAPER","EXCLUDE_SOFT","EXCLUDE_TOO_SPECIALIZED","EXCLUDE_UNIDENTIFIED","EXCLUDE_NOT_PDF","EXCLUDE_PARTIAL_DOWNLOAD"]:
        matches = [c for c in classifications if c[1] == verdict]
        lines.append(f"## {verdict} (n={len(matches)})")
        for f,v,bid in sorted(matches, key=lambda x: x[2]):
            lines.append(f"  {bid:14s}  {f}")
        lines.append("")
    if unclassified:
        lines.append("## UNCLASSIFIED")
        for f in unclassified:
            lines.append(f"  {f}")
    with open("/mnt/c/Code/Github/Authomathics/textbooks/more_books_classification.log","w") as fh:
        fh.write("\n".join(lines))
    print("Wrote classification log.")


if __name__ == "__main__":
    main()
