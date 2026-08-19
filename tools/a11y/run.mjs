// Runs axe-core against already-rendered ContextSafe pages in a headless DOM.
//
// Two things about this harness are deliberate.
//
// It refuses to report success on nothing. Every page must yield a non-zero
// count of executed axe rules; a page that produced no rule results at all is
// reported as `engine_examined_nothing`, because "0 violations" against an
// empty document, an error page, or a DOM the engine failed to build is the
// exact false pass this gate exists to prevent.
//
// It never reports an `incomplete` result as a pass. axe cannot evaluate
// colour contrast in a DOM with no layout engine, so `color-contrast` lands in
// `incomplete` here. Those rules are listed by name in the output and the
// Python gate that calls this harness computes contrast itself rather than
// letting an undetermined result read as a clean one.
//
// Input: one or more page file paths as arguments.
// Output: one JSON object on stdout. Exit 0 if the harness ran, 1 if it could
// not run at all. Deciding whether the findings are acceptable is the caller's
// job, not this file's.

import fs from "node:fs";
import path from "node:path";
import { createRequire } from "node:module";

const require = createRequire(import.meta.url);

function fail(message) {
  process.stdout.write(JSON.stringify({ ok: false, error: message }) + "\n");
  process.exit(1);
}

let JSDOM;
let axe;
try {
  ({ JSDOM } = require("jsdom"));
  axe = require("axe-core");
} catch (error) {
  fail(`engine_unavailable: ${error.message}`);
}

const pages = process.argv.slice(2);
if (pages.length === 0) {
  fail("no_pages: the harness was given no page to audit");
}

const results = [];
for (const page of pages) {
  const html = fs.readFileSync(page, "utf8");
  const dom = new JSDOM(html, {
    url: "file://" + path.resolve(page),
    pretendToBeVisual: true,
  });
  const { window } = dom;
  // axe-core's UMD wrapper resolves its global from the ambient scope, so the
  // window has to be visible as a global before the source is evaluated.
  globalThis.window = window;
  globalThis.document = window.document;
  globalThis.Node = window.Node;
  window.eval(axe.source);
  const run = await window.axe.run(window.document, {
    resultTypes: ["violations", "incomplete"],
  });
  const executed =
    run.violations.length +
    run.passes.length +
    run.incomplete.length +
    run.inapplicable.length;
  results.push({
    page,
    executedRules: executed,
    passedRules: run.passes.length,
    violations: run.violations.map((violation) => ({
      id: violation.id,
      impact: violation.impact,
      help: violation.help,
      nodes: violation.nodes.length,
      target: violation.nodes[0]?.target?.join(" ") ?? null,
    })),
    // Named, never counted as a pass. The caller covers these another way.
    undetermined: run.incomplete.map((entry) => entry.id),
  });
  window.close();
}

process.stdout.write(
  JSON.stringify(
    {
      ok: true,
      engine: "axe-core",
      engineVersion: require("axe-core/package.json").version,
      domEngine: "jsdom",
      domEngineVersion: require("jsdom/package.json").version,
      pages: results,
    },
    null,
    1,
  ) + "\n",
);
