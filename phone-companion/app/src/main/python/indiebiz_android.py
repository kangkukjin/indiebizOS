"""Android framework access and IPC to existing service-owned resources."""
import json
from java import jclass

_worker = jclass("com.indiebiz.phoneagent.execution.RemoteWorkerContext")
context = _worker.applicationContext()


def call(method, *args):
    reply = json.loads(str(_worker.call(method, json.dumps(args, ensure_ascii=False))))
    if not reply.get("success"):
        raise RuntimeError(reply.get("error", "device_call_failed"))
    value = reply["value"]
    if isinstance(value, dict) and (value.get("success") is False or value.get("error")):
        raise RuntimeError(value.get("error") or value.get("message") or "device_call_failed")
    return value
