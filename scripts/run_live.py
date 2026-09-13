from __future__ import annotations
import argparse
import json
import os
from pathlib import Path
import psycopg
from ipo_edge.live_runtime import run
from ipo_edge.live_sources import PublicWeb
from ipo_edge.live_report import render

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', default='artifacts/ipo_edge_live.md')
    args = parser.parse_args()
    config = json.loads(Path('config/framework_v1.1.json').read_text())
    with psycopg.connect(os.environ['DATABASE_URL']) as conn:
        result = run(conn,PublicWeb(),config)
        if result['status']=='SKIPPED_CONCURRENT_RUN':
            print('Another IPO EDGE run is active'); return
        path = Path(args.output); path.parent.mkdir(parents=True,exist_ok=True)
        path.write_text(render(conn,result))
        Path(str(path)+'.json').write_text(json.dumps(result,default=str,indent=2))
        summary = os.getenv('GITHUB_STEP_SUMMARY')
        if summary:
            with open(summary,'a') as f: f.write(path.read_text())
        print(json.dumps({k:result[k] for k in ('run_id','status','discovered','researched','checkpoints','outcomes')}))
        if result['status'] != 'COMPLETED': raise SystemExit(2)

if __name__=='__main__': main()
