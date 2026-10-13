"""기억 확인을 새 해결 절차로 배우지 않되 실행 권한과는 분리한다."""
import boot_paths  # noqa: F401
import pytest

from ibl_distill_gates import memory_only_program


@pytest.mark.parametrize('code, edition, expected', [
    ('[self:memory]{op:"recall",node:"가족"}', 1, True),
    ('return [self:memory]{op:"recall",node:"가족"}', 2, True),
    ('#!ibl edition=2\nreturn [self:memory]{op:"read",memory_id:1}', None, True),
    ('return {a:[self:memory]{op:"read",memory_id:1},'
     'b:[self:memory]{op:"search",query:"가족"}}', 2, True),
    ('return [self:memory]{op:"delete",memory_id:1}', 2, False),
    ('return [self:project]{op:"thread_update",notes:"정정"}', 2, False),
    ('return [self:memory]{op:"read",memory_id:1} & [sense:search]{query:"새 조사"}', 2, False),
    ('$operation="recall"\nreturn [self:memory]{op:$operation}', 2, False),
    ('return [self:memory]{op:"read",memory_id:[fn:동적호출]{}}', 2, False),
    ('return "[self:memory]{op:recall}"', 2, False),
    ('return [self:memory]{op:', 2, False),
    ('#!ibl edition=2\nreturn [self:memory]{op:"read",memory_id:1}', 1, False),
])
def test_memory_only_inspection_respects_source_edition(code, edition, expected):
    assert memory_only_program(code, edition) is expected


if __name__ == '__main__':
    raise SystemExit(pytest.main([__file__]))
