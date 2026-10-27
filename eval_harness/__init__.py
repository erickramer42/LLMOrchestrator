"""Evaluation harness for multi-agent review tribunal.

Provides:
- probe: False-positive rate measurement on clean fixtures
- bakeoff: Detection vs. false-positive comparison across models
- raw_call: The probe's and the bake-off's model call, at their measured settings
- round1: Round-1 reviewer measurements (collect samples, score them)
- round2: Round-2 pair measurements of a feedback format
- corpus: The real-diff corpus (list fixtures, collect samples, score them)
- replay: Archived round-1 replies re-judged offline under judge variants
- repair: The repair pass, measured paired on archived replies (closed)
- runaway: Repetition in long replies' thinking, and re-sending one attempt
- common: What the scripts share (command line, records, scoring helpers)
"""
