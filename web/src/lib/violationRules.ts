/** Shared helpers for violation rule authoring.
 *
 * Kept out of RuleEditDialog so the component file only exports a component --
 * react-refresh cannot hot-reload a module that mixes the two.
 */

/** Wildcard accepted wherever a zone is expected. Mirrors ANY_ZONE in
 * frigate/config/camera/violation.py -- referenced_zones() skips it, so it
 * passes validation, and ZoneSequenceRule treats it as "any zone". */
export const ANY_ZONE = "any";

/** Mirrors unsatisfiable_condition() in frigate/config/camera/violation.py.
 *
 * A rule is evaluated against one MQTT event, which describes one object, so
 * `detected(label)` only tests that event's own label. `detected(a) AND
 * detected(b)` is therefore always false, and `detected(a) AND NOT detected(b)`
 * is always true -- it reads as "a without b" and fires on every a.
 *
 * The backend rejects both, so this is only about failing before the round trip
 * with a message next to the field. Keep the two in step. */
function splitTopLevel(expr: string, op: string): string[] {
  const parts: string[] = [];
  const token = ` ${op} `;
  let depth = 0;
  let current = "";
  let i = 0;

  while (i < expr.length) {
    const char = expr[i];
    if (char === "(") depth++;
    else if (char === ")") depth--;

    if (
      depth === 0 &&
      expr.slice(i, i + token.length).toUpperCase() === token
    ) {
      parts.push(current);
      current = "";
      i += token.length;
      continue;
    }

    current += char;
    i++;
  }

  parts.push(current);
  return parts.map((p) => p.trim()).filter(Boolean);
}

export function unsatisfiableCondition(
  condition: string | undefined,
): string | undefined {
  if (!condition) return undefined;

  const check = (part: string): string | undefined => {
    const orParts = splitTopLevel(part, "OR");
    if (orParts.length > 1) {
      for (const branch of orParts) {
        const found = check(branch);
        if (found) return found;
      }
      return undefined;
    }

    const labels = new Set<string>();

    for (const atom of splitTopLevel(part, "AND")) {
      if (/^not\s+/i.test(atom)) {
        const inner = atom.replace(/^not\s+/i, "").trim();
        if (/^detected\s*\(/i.test(inner)) {
          return `${atom} can never be false: a rule sees one object per event, so this would fire every time.`;
        }
        continue;
      }

      if (atom.startsWith("(")) {
        const found = check(atom.replace(/^\(|\)$/g, ""));
        if (found) return found;
        continue;
      }

      const m = atom.match(/^detected\s*\(\s*([^,)]+?)\s*(?:,[^)]*)?\)$/i);
      if (m) labels.add(m[1].trim());
    }

    if (labels.size > 1) {
      return `This requires ${[...labels].sort().join(" and ")} at the same time, but a rule sees one object per event, so it can never be true.`;
    }

    return undefined;
  };

  return check(condition.split(/\s+/).join(" "));
}
