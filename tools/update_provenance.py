# -*- coding: utf-8 -*-
"""mod血统档案生成器(第四轮审计§2.3; 第五轮§2-B强化):
- 编译清单**派生自build_tm.bat解析**(不再是手抄副本 — 同构事故预防)
- 哈希覆盖遮蔽依赖的全部源: TrainingMod四单元 + d3dx_stub +
  SokuLib Weather.{hpp,cpp}(天气全局量/枚举所在)
- deployed≠built时拒绝写档(忘了部署=生成期硬失败)
用法: 重编并部署mod后运行  python tools/update_provenance.py
"""
import hashlib
import io
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.stdout.reconfigure(encoding="utf-8")

DEPLOYED = (r"D:\touhou\hisoutensoku2026-06-15\th123_train\modules"
            r"\SokuAIOfflinePlayer\SokuAITrainer.dll")
BUILT = r"D:\temp\build\SokuAITrainer.dll"
BUILD_SCRIPT = r"D:\temp\build\build_tm.bat"
SRC_ROOT = r"D:\temp\build\SokuAI-master"
# R40(第十一轮): 神谕侧部署(独立分支构建: SokuAI-master+补丁1-8,
# 含被动观测/种子/INPUTLOG; 源在soku_arch/build/src, 由patch_sources.py
# 从SokuAI-master复制+打补丁 — 基座改动自动继承)
ORACLE_DEPLOYED = (r"D:\temp\rl_game\modules\SokuAITrainerEnv"
                   r"\SokuAITrainerEnv.dll")
ORACLE_BUILT = r"D:\temp\soku_arch\build\out\SokuAITrainerEnv.dll"
# SokuLib源以通配符参与编译, 无法逐一枚举 — 只哈希遮蔽逻辑依赖的成员
# D5修复(从零审查): 线格式ABI头必须入哈希 — Packet.hpp定义整个线布局,
# 改它而7个.cpp哈希不变=C9全绿但客户端与mod静默错位
WILDCARD_DEPS = [r"SokuLib\src\Weather.hpp", r"SokuLib\src\Weather.cpp",
                 r"Training\TrainingMod\Packet.hpp",
                 r"SokuLib\src\SokuLib.hpp", r"SokuLib\src\Vector.hpp",
                 r"SokuLib\src\CharacterManager.hpp",
                 r"SokuLib\src\Character.hpp"]


def md5(p):
    h = hashlib.md5()
    with open(p, "rb") as fh:
        for c in iter(lambda: fh.read(1 << 20), b""):
            h.update(c)
    return h.hexdigest().upper()


def parse_bat_units(bat_path):
    """从build_tm.bat提取显式编译单元(TrainingMod+d3dx_stub; SokuLib是通配符)"""
    src = io.open(bat_path, encoding="utf-8", errors="replace").read()
    return sorted(set(re.findall(
        r"(Training\\TrainingMod\\\w+\.cpp|d3dx_stub\.cpp)", src)))


def main():
    if not os.path.exists(DEPLOYED):
        print("[ERROR] 部署DLL不存在:", DEPLOYED)
        return 1
    dm, bm = md5(DEPLOYED), md5(BUILT)
    if dm != bm:
        print("[ERROR] 部署DLL(%s) != 构建产物(%s) — 先部署再生成档案"
              % (dm, bm))
        return 1
    bat_units = parse_bat_units(BUILD_SCRIPT)
    if not bat_units:
        print("[ERROR] build_tm.bat解析不到编译单元 — 脚本格式变了?")
        return 1
    hashed = bat_units + WILDCARD_DEPS
    src_md5 = {}
    missing = []
    for rel in hashed:
        # cl的工作目录=SRC_ROOT(bat里cd到SokuAI-master), 全部相对它解析
        p = os.path.join(SRC_ROOT, rel)
        if os.path.exists(p):
            src_md5[rel] = md5(p)
        else:
            missing.append(rel)
    if missing:
        print("[ERROR] 编译单元缺失:", missing)
        return 1
    prov = {
        "deployed_path": DEPLOYED,
        "deployed_md5": dm,
        "built_path": BUILT,
        "build_script": BUILD_SCRIPT,
        "source_root": SRC_ROOT,
        "bat_explicit_units": bat_units,
        "wildcard_deps": WILDCARD_DEPS,
        "source_md5": src_md5,
        "masking": {
            "seiran_hand_0xFF": "state.cpp: WEATHER_MOUNTAIN_VAPOR branch",
            "seiran_gauge_sentinel": "0xFFFF (unsigned short wire value)",
            "aurora_active_mask": "network.cpp: displayed==AURORA -> active=AURORA",
        },
        "note": "R11 info-symmetry; ported 2026-09-22 from OfflineVersusMod",
        # R40: 神谕侧部署血统(M-1/M-2+INPUTLOG, 2026-10-03构建部署)
        "oracle_deployed": {
            "deployed_path": ORACLE_DEPLOYED,
            "deployed_md5": md5(ORACLE_DEPLOYED) if os.path.exists(
                ORACLE_DEPLOYED) else None,
            "built_path": ORACLE_BUILT,
            "built_md5": md5(ORACLE_BUILT) if os.path.exists(
                ORACLE_BUILT) else None,
            "build_script": r"D:\temp\soku_arch\build\build_mod.bat",
            "patch_script": r"D:\temp\soku_arch\build\patch_sources.py",
            "note": "SokuAI-master基座+补丁1-8(被动观测/种子/TRACE/"
                    "INPUTLOG精确对齐/FGSPOOF); 部署≠构建时告警由"
                    "C9的oracle断言承担",
        },
    }
    out = os.path.join(HERE, "mod_provenance.json")
    with io.open(out, "w", encoding="utf-8") as fh:
        json.dump(prov, fh, ensure_ascii=True, indent=1)   # ASCII-only: 工具链稳健
    print("[OK] %s: deployed_md5=%s, bat派生%d单元+%d通配依赖共%d个哈希入档"
          % (out, dm, len(bat_units), len(WILDCARD_DEPS), len(src_md5)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
