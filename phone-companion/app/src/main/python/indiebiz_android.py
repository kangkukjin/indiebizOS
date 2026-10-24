"""Android framework access and IPC to existing service-owned resources."""
import json
from java import jclass

_is_worker = str(jclass('android.app.Application').getProcessName()).endswith(':remote_exec')
_owner = jclass("com.indiebiz.phoneagent.execution." +
                ("RemoteWorkerContext" if _is_worker else "RemoteExecutionBridge"))
context = _owner.applicationContext()


def call(method, *args):
    arguments = json.dumps(args, ensure_ascii=False)
    if _is_worker:
        raw = _owner.call(method, arguments)
    else:
        raw = jclass('com.indiebiz.phoneagent.execution.RemoteDeviceCalls').INSTANCE.call(method, arguments)
    reply = json.loads(str(raw))
    if not reply.get("success"):
        raise RuntimeError(reply.get("error", "device_call_failed"))
    value = reply["value"]
    if isinstance(value, dict) and (value.get("success") is False or value.get("error")):
        raise RuntimeError(value.get("error") or value.get("message") or "device_call_failed")
    return value
