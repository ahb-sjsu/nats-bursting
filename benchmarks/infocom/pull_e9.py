"""Pull all E9 result JSONs from Atlas into ./e9_results/ (text-safe transfer)."""
import json
import os

import atlas_run

REMOTE = ("/home/claude/env/bin/python3 -c \""
          "import json,glob,os;"
          "print(json.dumps({os.path.basename(f):json.load(open(f)) "
          "for f in glob.glob('/tmp/e9/run/*.json')}))\"")
blob = atlas_run.run(REMOTE)
data = json.loads(blob)
os.makedirs("e9_results", exist_ok=True)
for name, content in data.items():
    json.dump(content, open(os.path.join("e9_results", name), "w"))
print(f"pulled {len(data)} files -> e9_results/")
