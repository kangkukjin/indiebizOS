# Python Libraries

Current IBL adapter for direct installed Python library calls. No script registry or per-function wrapper.

Contract and examples: [Python guide](../../../../guides/python_libraries.md).
Policy: `local_python.owner_unrestricted` in policy.json. Other principals and restricted node contexts are denied.
Each top-level execution owns a worker and its object references. Export values/files before the execution ends.
