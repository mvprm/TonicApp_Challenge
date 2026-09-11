# Synthetic replay review

All extraction responses are authored fixtures, not recorded LLM output or gold data.
The seven v2 cases demonstrate historical procedures, negation, generic questions,
local diagnostic concepts, an evidence-bound severity modifier, full LOINC names
and abstention on a generic component. Country is deliberately independent of text
language in two examples. The original 12 cases include malformed input, missing
context, repeated evidence and unmapped mentions.

Inspect results.jsonl for the nested assertion and modifier fields; review.csv
flattens assertion columns. A validated evidence span does not validate its meaning.
