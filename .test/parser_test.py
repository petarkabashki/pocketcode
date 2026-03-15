import sys
from pocketcode.core.stackvm_parser import parse_stackvm_source_with_spans

with open(".pocketcode/agent.survey/survey.agent.md") as f:
    src = f.read().split("```vm")[1].split("```")[0]

print("Parsing...")
parse_stackvm_source_with_spans(src)
print("Done!")
