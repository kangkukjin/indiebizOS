"""Device-specific view of guide-owned drivers and existing installation state.

Registry references are descriptive data. They are never imported or executed.
The only update adapters are the existing PC and APK implementations below.
"""
from guide_registry import device_drivers


def describe(rec):
    reg = rec.get("registration") or {}
    caps = reg.get("capabilities") or rec.get("env") or {}
    adapter = reg.get("adapter") or ("resident-v1" if reg else "portable")
    platform = caps.get("os") or ("android" if reg.get("kind") == "phone" or caps.get("sdk") else "")
    result = device_drivers(platform, adapter, caps.get("service_scope", "unknown"))
    for component in result["components"]:
        component["support"] = "unknown"  # A registered implementation is not a capability observation.
        if component["location"] != "device":
            component["update"] = {"state": "hub_owned"}
            continue
        component.update(device_id=rec["device_id"], generation=reg.get("generation"),
                         installation_id=reg.get("installation_id"), last_seen=reg.get("last_seen"),
                         permission="unknown")
        if component.get("updater") == "resident_pcs.update_helper" and adapter == "resident-v1":
            from resident_pcs import helper_status, update_binding
            state = dict(helper_status(rec))
            state["verification"] = "version_reported" if state["state"] == "current" else "unverified"
            state["operation_verification"] = "unknown"
            if state["state"] == "updating":
                import resident_store
                job = resident_store.pending(rec["device_id"], "update", settle=120,
                                             generation=reg["generation"])
                tasks = resident_store.history(device=rec["device_id"], job=job, limit=1)["tasks"] if job else []
                if tasks:
                    task = tasks[0]
                    state.update(job_id=job, target_sha256=task["summary"].get("sha256"),
                                 phase=("awaiting_reconnect" if (task.get("result") or {}).get("restarting")
                                        else "replacing" if task["state"] == "running" else "queued"))
            component.update(installed=state.get("current"), update=state,
                             binding=update_binding(rec, state.get("latest")),
                             support="reported" if caps.get("self_update") else "unknown")
        elif component.get("updater") == "phone_updates.submit" and adapter == "indiebiz-v1":
            from phone_updates import status
            from resident_pcs import update_binding
            apk = caps.get("apk_update") or {}
            state = status(rec)
            component.update(installed=apk.get("installed_sha256"), version=apk.get("version_code"),
                             update=state, binding=update_binding(rec, state.get("sha256")),
                             support="reported" if apk.get("contract") == 1 else "unknown",
                             permission=apk.get("can_install", "unknown"))
        else:
            component["update"] = {"state": "manual"}
    return result
