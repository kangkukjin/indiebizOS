package com.indiebiz.phoneagent

/** One ordered write pass, with fresh observations of only the affected settings. */
internal object HardwareSettingUpdate {
    data class Result(val before: Map<String, Int>, val after: Map<String, Int>, val verified: Boolean)

    fun apply(values: List<Pair<String, Int>>, read: (String) -> Int,
              write: (String, Int) -> Boolean): Result {
        require(values.isNotEmpty() && values.map { it.first }.distinct().size == values.size)
        val before = values.associate { it.first to read(it.first) }
        for ((key, value) in values) {
            check(write(key, value)) { "setting_rejected: $key (일부 적용 가능, 상태 재조회 필요)" }
        }
        val after = values.associate { it.first to read(it.first) }
        return Result(before, after, values.all { after[it.first] == it.second })
    }
}
