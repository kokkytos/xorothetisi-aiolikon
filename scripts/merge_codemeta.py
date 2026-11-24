#!/usr/bin/env python3
"""Συγχωνεύει το CodeMeta που παράγει το cffconvert (stdin) με τα επιπλέον τεχνικά πεδία
(codemeta.extra.json) και γράφει το αποτέλεσμα στο stdout.

Τα πεδία που προέρχονται από το CITATION.cff δεν αντικαθίστανται: αν ένα κλειδί υπάρχει και
στα δύο, κερδίζει το CFF, ώστε το CITATION.cff να παραμένει η μοναδική πηγή αλήθειας."""
import json
import sys

extra = json.load(open(sys.argv[1], encoding="utf-8"))
base = json.load(sys.stdin)

merged = {**extra, **base}
head = {k: merged.pop(k) for k in ("@context", "@type") if k in merged}
out = {**head, **dict(sorted(merged.items()))}

sys.stdout.write(json.dumps(out, ensure_ascii=False, indent=2) + "\n")
