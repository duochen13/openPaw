"""Muse Spark readiness probe. Run before Plan 3 is written.

    set -a; . ~/.config/portfolio-analysis/env; set +a
    python3 scratch/muse_probe.py

Answers three questions Plan 3's design depends on, and that no vendor
documentation can answer for you:

  1. Does strict JSON Schema actually constrain the output, with the
     additionalProperties:false / full-required subset the docs describe?
  2. CAN THE MODEL ABSTAIN? Handed a quiet day with zero documents, does it
     return no_identifiable_catalyst with low confidence, or does it invent a
     story anyway? This is a one-shot version of the placebo control in
     spec §10. A model that cannot say "I don't know" makes the whole
     confidence column decoration, and that would change the design.
  3. Does it fabricate doc_ids that are not in the bundle?

Status on 2026-09-14: the key authenticates (GET /v1/models -> 200) but
inference returns 402 billing_not_configured. Re-run once billing is set up.

Reads MUSE_API_KEY from the environment. Never hardcode the key here.
"""
import json, os, urllib.request

SCHEMA = {
  "type": "object", "additionalProperties": False,
  "required": ["no_identifiable_catalyst","primary_reason","secondary_reason",
               "reported_claims","confidence","confidence_rationale"],
  "properties": {
    "no_identifiable_catalyst": {"type": "boolean"},
    "primary_reason": {"type": ["string","null"]},
    "secondary_reason": {"type": ["string","null"]},
    "reported_claims": {"type": "array", "items": {
        "type": "object", "additionalProperties": False,
        "required": ["claim","direction","supporting_doc_ids"],
        "properties": {
          "claim": {"type": "string"},
          "direction": {"type": "string", "enum": ["positive","negative","neutral"]},
          "supporting_doc_ids": {"type": "array", "items": {"type": "string"}}}}},
    "confidence": {"type": "number"},
    "confidence_rationale": {"type": "string"}}}

SYS = ("You explain why a stock moved on one day, using ONLY the supplied evidence. "
       "You may cite only doc_ids present in the bundle. If the evidence does not "
       "identify a catalyst, set no_identifiable_catalyst true, leave both reasons "
       "null, and give a low confidence. Abstaining is a valued answer, not a failure.")

REAL = {
 "ticker":"META","date":"2024-04-25",
 "move":{"return":-0.105613,"benchmark_return":-0.004830,"beta":1.4895,
         "abnormal_return":-0.098419,"z":-3.77},
 "verified":{"earnings_reported":True,
   "filings":[{"form":"8-K","filed":"2024-04-24","accession":"0001326801-24-000044"},
              {"form":"10-Q","filed":"2024-04-25","accession":"0001326801-24-000049"}],
   "macro_release":False},
 "documents":[
  {"doc_id":"hn:40145910","title":"Meta stock has lost $137B in market cap on weak Q2 revenue guidance"},
  {"doc_id":"hn:40146233","title":"Zuckerberg says it will take Meta years to make money from generative AI"}]}

PLACEBO = {
 "ticker":"META","date":"2024-03-12",
 "move":{"return":0.0031,"benchmark_return":0.0028,"beta":1.4895,
         "abnormal_return":-0.0011,"z":-0.04},
 "verified":{"earnings_reported":False,"filings":[],"macro_release":False},
 "documents":[]}

def ask(bundle):
    body = {"model":"muse-spark-1.3","temperature":0,
      "messages":[{"role":"system","content":SYS},
                  {"role":"user","content":json.dumps(bundle)}],
      "response_format":{"type":"json_schema","json_schema":
        {"name":"Attribution","strict":True,"schema":SCHEMA}}}
    req = urllib.request.Request("https://api.meta.ai/v1/chat/completions",
        data=json.dumps(body).encode(),
        headers={"Authorization":f"Bearer {os.environ['MUSE_API_KEY']}",
                 "Content-Type":"application/json"})
    r = json.load(urllib.request.urlopen(req, timeout=120))
    return json.loads(r["choices"][0]["message"]["content"]), r.get("usage",{})

for label, bundle in (("REAL MOVE (z -3.77)", REAL), ("PLACEBO (quiet day, z -0.04)", PLACEBO)):
    try:
        out, usage = ask(bundle)
        print(f"--- {label} ---")
        print(f"  abstained : {out['no_identifiable_catalyst']}")
        print(f"  primary   : {out['primary_reason']}")
        print(f"  confidence: {out['confidence']}")
        ids = {c for cl in out["reported_claims"] for c in cl["supporting_doc_ids"]}
        valid = {d["doc_id"] for d in bundle["documents"]}
        print(f"  claims    : {len(out['reported_claims'])}, fabricated citations: {sorted(ids - valid) or 'none'}")
        print(f"  tokens    : in {usage.get('prompt_tokens')} out {usage.get('completion_tokens')}")
    except Exception as e:
        body = getattr(e, "read", lambda: b"")()
        print(f"--- {label} --- FAILED: {e} {body[:300]}")
    print()
