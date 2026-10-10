"""일반 노트북 호환 입구. 검색·추출·저장은 공통 notebook_store가 소유한다."""
import sys
import notebook_store

sys.modules[__name__] = notebook_store
