import argparse, json, os
from pathlib import Path
from http.server import HTTPServer, BaseHTTPRequestHandler
p=argparse.ArgumentParser(); p.add_argument("mode",choices=["process","serve"]); a=p.parse_args()
root=Path(__file__).parent.resolve(); cfg=json.loads((root/"config.json").read_text(encoding="utf-8"))
if a.mode=="process":
 rows=json.loads((root/"samples.json").read_text(encoding="utf-8")); out=root/cfg["output"]; out.mkdir(exist_ok=True)
 result={"count":len(rows),"items":rows,"note":cfg["user_note"]}
 (out/"result.json").write_text(json.dumps(result,ensure_ascii=False),encoding="utf-8")
 with (root/"runs.log").open("a",encoding="utf-8") as f: f.write(cfg["output"]+"\n")
 print(json.dumps({"count":len(rows),"output":cfg["output"],"note":cfg["user_note"]},ensure_ascii=False))
else:
 class Handler(BaseHTTPRequestHandler):
  def do_GET(self):
   body=json.dumps({"status":"healthy","pid":os.getpid(),"root":str(root)},ensure_ascii=False).encode()
   self.send_response(200); self.end_headers(); self.wfile.write(body)
 try: server=HTTPServer(("127.0.0.1",cfg["port"]),Handler)
 except OSError: server=HTTPServer(("127.0.0.1",0),Handler)
 server.timeout=40
 (root/"service.json").write_text(json.dumps({"pid":os.getpid(),"port":server.server_port,"root":str(root)}),encoding="utf-8")
 server.handle_request(); server.server_close()
