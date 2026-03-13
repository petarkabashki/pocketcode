# StackVM Handoff Example

This example shows a StackVM-backed flow that hands off to another flow using the normal PocketCoder runtime contract.

Layout:

- `flows/*.md`: registers the VM flow and the delegate flow
- `flows/router.md`: StackVM-backed entry flow
- `vm/router.vm`: handoff-oriented StackVM words
- `flows/delegate.py`: simple PocketFlow delegate used by the handoff

The example demonstrates:

- a VM flow selecting another agent with `handoff`
- mixed VM and PocketFlow flow backends in the same namespace/example root
- reuse of the standard `pending_handoff_agent` runtime path instead of a VM-only mechanism

See also `../stackvm_resilient_example/` for a VM flow that branches on tool failure before handing off.
