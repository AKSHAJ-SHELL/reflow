<!-- draft: human approval required before a loop loads this file -->

# Fix

Return the whole index.circuit.tsx in one tsx fence. The fence is the entire file. Apply each fix_hint to the current file. Do not return a diff or a partial snippet.

Part numbers may be copied only from the resolved-parts table or Spec.named_parts. mpn stays empty otherwise.

Copy a manufacturer part string only when it appears in the resolved-parts table or in Spec.named_parts. Copy an lcsc string only when it appears in the resolved-parts table. Omit manufacturerPartNumber and supplierPartNumbers when those sources have no string for that part. Do not add a part number that is absent from both sources.

The block from rule_id through fix_hint is repeated once per failed check. history is one line per earlier failed attempt, oldest first. The compile error line is the first compile error only. On a verify failure the compile error line and the compile message are empty. On a compile failure the rule_id block is empty.

attempt: {attempt}
max_attempts: {max_attempts}

history:
{history}

rule_id: {rule_id}
severity: {severity}
refs: {refs}
nets: {nets}
message: {message}
fix_hint: {fix_hint}

compile error line: {compile_line}: {compile_message}

current index.circuit.tsx:
{tsx}
