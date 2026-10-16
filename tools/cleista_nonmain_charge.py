# -*- coding: utf-8 -*-
"""非主力17角色蓄力数据层(CH-2扩展, 2026-10-14晚):

对cleista API逐招?charged=1探针(variant.charged==True判别可蓄力,
startuptools=完成点), 产出charge_table的non_main节 — 纯数据层,
不动宏库(非主力蓄力宏升版=未来波, 需17角色模型迁移同窗)。
限速: 1.3s/请求(~46/分 < 120/分红线), bash curl通道(已验证)。
"""
import json
import os
import subprocess
import sys
import time

sys.stdout.reconfigure(encoding='utf8')
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

CHARS = ['sakuya', 'alice', 'patchouli', 'youmu', 'remilia', 'yuyuko',
         'reisen', 'komachi', 'iku', 'tenshi', 'sanae', 'cirno',
         'meiling', 'utsuho', 'suwako', 'yukari', 'aya']
SHOT_SLUGS = ['5b', '6b', '2b', 'j5b', 'j2b', '5c', '6c', '2c', 'j5c',
              'j2c', '66b', '66c']
CURL = r'D:\temp\PortableGit\ucrt64\bin\curl.exe'


def probe(char, slug):
    """?charged=1 → (可蓄力?, 完成点, 全体)。404/无variant=None=不可。"""
    url = ('https://soku.cleista.cc/api/v1/framedata/%s/%s?charged=1'
           % (char, slug))
    for attempt in range(3):
        r = subprocess.run(
            [CURL, '-s', '--max-time', '30', '-H',
             'Accept: application/json', url],
            capture_output=True)
        try:
            d = json.loads(r.stdout.decode('utf8'))
        except Exception:
            time.sleep(2.5)
            continue
        mv = d.get('move') or {}
        # 勘误: variant在move内不在顶层(首版读d['variant']恒None→全零)
        var = mv.get('variant')
        if var and var.get('charged') is True:
            f = mv.get('frames') or {}
            return True, f.get('startup'), f.get('total')
        return False, None, None
    return None, None, None       # 三次失败


def main():
    out = {}
    for ch in CHARS:
        rows = []
        for slug in SHOT_SLUGS:
            ok, st, tot = probe(ch, slug)
            time.sleep(1.3)
            if ok:
                rows.append({'slug': slug, 'completion': st, 'total': tot})
        out[ch] = rows
        print('%-10s 蓄力%d招: %s' % (ch, len(rows),
                                      [r['slug'] for r in rows]))
    dst = os.path.join(ROOT, 'data', 'guide_tables', 'cleista',
                       'non_main_charge.json')
    payload = {'source': 'cleista API ?charged=1逐招探针(variant.charged判别), '
                         '2026-10-14晚, build 8bd50f33',
               'note': '纯数据层 — 非主力蓄力宏升版需17角色模型迁移同窗(未来波)',
               'chars': out}
    with open(dst + '.tmp', 'w', encoding='utf8') as f:
        json.dump(payload, f, ensure_ascii=False, indent=1)
    os.replace(dst + '.tmp', dst)
    n = sum(len(v) for v in out.values())
    print('合计%d条蓄力记录 → %s' % (n, dst))


if __name__ == '__main__':
    main()
