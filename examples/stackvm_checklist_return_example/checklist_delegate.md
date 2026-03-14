---
name: checklist_delegate
description: Collect checklist selections through a paired checklist answer workflow and return a final answer to the caller
vm_entry: decide
vm_modules:
  - stdlib.normalize
  - vm/common
  - vm/delegate
---

Collect multiple selections through the paired checklist answer workflow declared in `vm/common.vm` with `define-choice-answer-family`, keep `contains` matching, and return the delegate answer to the caller via the handoff stack.
