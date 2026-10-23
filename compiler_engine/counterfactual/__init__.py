"""Counterfactual Repair Lab: validate candidate root-cause corrections against the
real compiler toolchain, on a disposable copy of the source, and fold that evidence
into root-cause ranking alongside the existing rule-based and ML strategies.

This package does not reimplement patch generation or compilation - it reuses
compiler_engine.patches.generator.patches_for_line (same templates the IDE's "Suggested
patch" card already uses) and LanguageAdapter.check (same real gcc/g++/javac/CPython
checks every other strategy uses). It only adds: broader candidate-line coverage,
structured before/after diagnostic evidence, edit-size accounting, and a ranking that
combines that evidence with the existing rule/ML scores instead of reporting a bare
compiles-or-not flag.
"""
from .evaluator import PatchEvidence, LineEvidence, evaluate_candidates
from .evidence_ranker import rank

__all__ = ["PatchEvidence", "LineEvidence", "evaluate_candidates", "rank"]
