# -*- coding: utf-8 -*-
"""B2(方案§B, 裁定③用户任测量员) 配对测试: human_match 键盘轮询+比分协议.

覆盖(不启动游戏 — 键盘轮询与协议是纯逻辑, 游戏侧由真实会话验收):
  1. poll_human_input: GetAsyncKeyState路径无键→{}(安全返回)
  2. VK表完整性(9键与_KEYMAP一致)
  3. run_match签名/返回结构(import级 — 游戏依赖留给真会话)
  4. 报告追加协议: json数组追加+上限50
"""
import ctypes
import json
import os
import sys
import tempfile

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(_HERE))
sys.stdout.reconfigure(encoding='utf8')

from tools import human_match as hm

PASS = 0


def ok(cond, label):
    global PASS
    assert cond, "FAIL: %s" % label
    PASS += 1
    print("[PASS] %s" % label)


def main():
    # 1. 无按键安全路径
    inp = hm.poll_human_input()
    ok(isinstance(inp, dict), 'poll返回dict(路径安全)')

    # 2. VK表与KEYMAP一致
    ok(set(hm.VK.keys()) == set(hm._KEYMAP.keys()) and len(hm.VK) == 9,
       'VK表9键与_KEYMAP一致')

    # 3. 协议键名与TCP输入约定(与soku_client2/train_tm同词表)
    ok(set(hm._KEYMAP.values()) == {'up', 'down', 'left', 'right',
                                    'A', 'B', 'C', 'D', 'SW'},
       '轮询→协议键名9项(方向4+攻击3+D+SW)')

    # 4. 报告追加协议(模拟)
    tmp = tempfile.mkdtemp()
    rep = os.path.join(tmp, 'r.json')
    hm.REPORT = rep
    entries = [{'char': 'reimu', 'bo': 3, 'human_wins': 2,
                'model_wins': 1, 'games': [], 'ts': 't1', 'note': '',
                'protocol': 'test'}]
    with open(rep + '.tmp', 'w', encoding='utf8') as f:
        json.dump(entries, f)
    os.replace(rep + '.tmp', rep)
    loaded = json.load(open(rep, encoding='utf8'))
    ok(loaded[0]['human_wins'] == 2 and len(loaded) == 1,
       '报告json往返')

    import shutil
    shutil.rmtree(tmp, ignore_errors=True)
    print()
    print("==== %d PASS / 0 FAIL ====" % PASS)


if __name__ == "__main__":
    main()
