# -*- coding: utf-8 -*-
"""BC 指针 env 全流程演练（不写 bat/不停训）: gen2 loader -> fake env 拒绝 -> 恢复。

输出 JSON: D:\\temp\\bc_env_rehearsal_20261027.json
"""
import json
import os
import sys
import time

ROOT = r'C:\Users\96120\Desktop\workplace\th123_rl'
sys.path.insert(0, ROOT)
import bc_io

GEN = r'D:\temp\bc_gen2_20261027'
OUT = r'D:\temp\bc_env_rehearsal_20261027.json'
EXP = {'reimu': (429579, 831), 'marisa': (353791, 866),
       'suika': (329422, 846)}


def snapshot(tag):
    rec = {'tag': tag, 'ts': time.time(), 'env': os.environ.get('TH123_BC_DIR')}
    out = {}
    for ch, (rows, width) in EXP.items():
        try:
            X, S, Y = bc_io.load_bank(ch, verify=True)
            X2, S2, Y2, I = bc_io.load_bank_seq(ch)
            out[ch] = {'ok': bool(len(Y) == rows and S.shape[1] == width),
                       'rows': int(len(Y)), 'width': int(S.shape[1]),
                       'has_I': I is not None}
        except Exception as e:
            out[ch] = {'ok': False, 'err': repr(e)[:160]}
    rec['chars'] = out
    return rec


def main():
    rep = []
    old = os.environ.get('TH123_BC_DIR')
    try:
        os.environ['TH123_BC_DIR'] = GEN
        rep.append(snapshot('gen2'))
        # fake env: 严格指针应拒绝, 不静默 fallback
        os.environ['TH123_BC_DIR'] = r'D:\temp\__no_such_bc_env__'
        rep.append(snapshot('fake_env'))
        os.environ['TH123_BC_DIR'] = GEN
        rep.append(snapshot('restore_gen2'))
    finally:
        if old is None:
            os.environ.pop('TH123_BC_DIR', None)
        else:
            os.environ['TH123_BC_DIR'] = old
    ok = (all(v['ok'] for v in rep[0]['chars'].values())
          and all(not v['ok'] for v in rep[1]['chars'].values())
          and all(v['ok'] for v in rep[2]['chars'].values()))
    res = {'ok': ok, 'records': rep,
           'note': '不写 bat/不停训; fake env 严格拒绝=回滚可触发'}
    json.dump(res, open(OUT, 'w', encoding='utf-8'), ensure_ascii=False,
              indent=1)
    print(json.dumps({'ok': ok, 'gen2': rep[0]['chars'],
                      'fake': {k: v.get('err', '')[:60]
                               for k, v in rep[1]['chars'].items()},
                      'restore': rep[2]['chars']}, ensure_ascii=False))
    return 0 if ok else 1


if __name__ == '__main__':
    sys.exit(main())
