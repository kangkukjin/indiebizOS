package com.indiebiz.phoneagent.execution

/** Freeze observed children, then stop scanning as soon as one pass finds no new child. */
object ProcessDescendants {
    fun collect(root: Int, birth: String, scan: () -> List<Triple<Int, Int, String>>,
                freeze: (Int) -> Unit): Map<Int, String> {
        val owned = mutableMapOf(root to birth)
        for (pass in 0 until 8) {
            val before = owned.size
            for ((pid, parent, started) in scan()) {
                if (parent in owned && pid !in owned) {
                    owned[pid] = started
                    freeze(pid)
                }
            }
            if (owned.size == before) break
        }
        return owned
    }
}
