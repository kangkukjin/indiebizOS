#!/bin/zsh
# 수리 뒤 재실행: v5(원래 전체 프로그램) 기본→증분, v6(새 변형) 기본. 새 사본은 실행 직전에 만든다(색인 지연을 실제로 밟기 위해).
set -e
cd /Users/kangkukjin/Desktop/AI/indiebizOS
R=docs/experiments/long_sentence_imagination/round_68; O=outputs/long_sentence_imagination/2026-10-14_68회차; D=/Users/kangkukjin/Desktop/AI/indiebizOS/outputs/long_sentence_imagination/2026-10-14_68회차
T="python3 $R/harness/transport.py"
S(){ python3 -c "import sys,json; d=json.load(sys.stdin); print('VERIFY', d['label'], d['passed'],'/',d['total']); [print(' -',f['check'],str(f['detail'])[:160]) for f in d['failed']]"; }
rm -rf $O/inputs/dump_after2 $O/inputs/dump_after3 $O/trainer_after2 $O/trainer_after6
cp -Rp $O/inputs/dump_pristine $O/inputs/dump_after2; cp -Rp $O/inputs/dump_pristine $O/inputs/dump_after3
mkdir -p $O/trainer_after2 $O/trainer_after6
python3 - <<PY
import json
for ver,folder,dump in [("v5","trainer_after2","dump_after2"),("v6","trainer_after6","dump_after3")]:
    code=open(f"$R/base_{ver}.ibl").read()
    base={"code":code,"edition":2,"origin":"training","project_id":"수동모드","inputs":{"dump":f"$D/inputs/{dump}","out":f"$D/{folder}/정리"}}
    json.dump(base, open(f"$O/{folder}/exec.request.json","w"), ensure_ascii=False)
PY
date "+%H:%M:%S"
python3 $R/harness/transport.py after2_v5_base --request $O/trainer_after2/exec.request.json --dir trainer_after2 | head -c 700; echo
mkdir -p $O/trainer_after2/base_snapshot && cp $O/trainer_after2/정리/목록.csv $O/trainer_after2/정리/보고서.md $O/trainer_after2/base_snapshot/
DUMP=$D/inputs/dump_after2 python3 $R/harness/verify.py $O/trainer_after2/정리 $O/trainer_after2/base_snapshot/목록.csv after2-base | S
cp -p $O/inputs/variant_add/* $O/inputs/dump_after2/
python3 $R/harness/transport.py after2_v5_variant --request $O/trainer_after2/exec.request.json --dir trainer_after2 | head -c 500; echo
DUMP=$D/inputs/dump_after2 python3 $R/harness/verify.py $O/trainer_after2/정리 $O/trainer_after2/정리/목록.csv after2-variant variant | S
python3 $R/harness/transport.py after6_base --request $O/trainer_after6/exec.request.json --dir trainer_after6 | head -c 700; echo
mkdir -p $O/trainer_after6/base_snapshot && cp $O/trainer_after6/정리/목록.csv $O/trainer_after6/정리/보고서.md $O/trainer_after6/base_snapshot/
DUMP=$D/inputs/dump_after3 python3 $R/harness/verify.py $O/trainer_after6/정리 $O/trainer_after6/base_snapshot/목록.csv after6-base | S
grep -n "유사 중복 후보" $O/trainer_after6/정리/보고서.md | head -3 | cut -c1-200
date "+%H:%M:%S"
