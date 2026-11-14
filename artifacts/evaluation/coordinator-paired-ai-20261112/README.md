# Paired coordinator AI exercise

Twelve synthetic cases were completed in both conditions: 24 actual timed phases. The same coordinator composed manual replies and reviewed cached drafts, with six assisted-first and six manual-first cases. Relevant policy cards were preselected from frozen expected documents for both conditions. Six assisted phases had a draft (one automatic, five after oracle staff intent correction), while six required manual fallback.

Observed mean wall time was 8.974584 seconds for manual and 8.970244 seconds for assisted including fallbacks. Medians were 7.747585 and 8.171049 seconds respectively. The mean difference is approximately zero and does not establish a productivity improvement. These are AI model/tool orchestration times, not human handling times. Prior draft-generation and intent-correction wait times were excluded because cached outputs were used. Carryover, preselected sources and a single AI reviewer prevent causal inference.

Decisions: five approve, one edit, six manual fallback. No customer message was sent and no provider request was made during this exercise. All raw responses, timestamps, protocol and paired durations are retained. Earlier incomplete in-memory observations were not reconstructed or included.

`measurement_protocol.py` is the unmodified source actually used from `.local/paired_agent_measure.py`; it is archived for audit, not an instruction to replay over existing state. Its `ROOT` assumption depends on the original `.local/` location. `protocol_source_sha256.txt` identifies its bytes.
