# -*- coding: utf-8 -*-
"""Trialmode连段包解析器(R30, 用户2026-10-02提供数据源)。
格式(docs: [The pack format.pdf + 实样本逆向):
- JSON: expected=记法序列, score[0].min_damage/hits=合格线,
  inputs=录制帧(部分包有, 含errored标记=概率连证据)
- expected令牌: 招式[:帧偏移] !前缀=必须精确帧 [n]=按键持续帧
  d前缀=冲刺中 hj=hjc高跳 j44/j66=空中dash scN=符卡ID /f5a=远近变体
用法: python tools/trialmode_parse.py [char] → 列出可转换连段+概率连标注
"""
import io
import json
import os
import re
import sys
import zipfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.stdout.reconfigure(encoding='utf8')

PACK = r'D:\touhou\hisoutensoku2026-06-15\Trialmode连段包'
PACKS = {
    'reimu': ['白天子-灵梦连段包，直接解压里面的东西即可.zip',
              '老阿皮灵梦阴间连段+实用连段.rar'],
    'marisa': ['marisa_小朔士.zip', 'Marisa_xianxiang 现象.zip'],
    'suika': ['[Finished]Suika_xianxiang 现象.zip', 'Suika_laozhao 老赵.rar'],
    # R61i(C6): 17新角色 — 仅zip包(rar跳过, 暂无解压依赖)
    'yukari': ['yukari_challenge 十字凤.zip'],
    'komachi': ['Komachi 十字凤.zip'],
    'meiling': ['Meirin Normal Combos In Combat 给油.zip',
                'Meirin Romantic combos 给油.zip'],
    'sanae': ['Sanae_challenge by 十字凤.zip'],
    'youmu': ['Youmu Junior [2022.2.17] 109 combos 三回転Tstar.zip'],
    'yuyuko': ['Yuyuko_combo记得是芙幽做的.zip'],
    'tenshi': ['天子连段包-Anmoto.zip'],
    'suwako': ['妖精--泄矢诹访子连段包v1.1.zip',
               '诹访子连段专项大合集120+ -鱼的千千.zip'],
    'alice': ['爱丽丝连段包1.1-米神こめ神.zip'],
    'cirno': ['白天子-琪露诺的连段包.zip'],
    # R61k(用户补包): aya/remilia zip + utsuho/sakuya解压转zip + iku(19=衣玖)
    'aya': ['aya（文连段，共41个）.zip'],
    'remilia': ['蕾米连段包_SATORI.zip'],
    'utsuho': ['utsuho_trialmode.zip'],
    'sakuya': ['sakuya_trialmode.zip'],
    'iku': ['19大学习连段包——by妖精.zip'],
    # 无包: (全部有包 — patchouli/reisen用户补充)
    'patchouli': ['Patchouli Trial Mode.zip'],
    'reisen': ['reisen basic combos.zip'],
}
TOK = re.compile(r'(!?)([a-z0-9/]+?)(?:\[(\d+)\])?(?::(\d+))?$')


def parse_expected(s):
    rows = []
    for tok in s.split():
        m = TOK.match(tok)
        if not m:
            rows.append({'raw': tok})
            continue
        exact, move, hold, frame = m.groups()
        rows.append({
            'move': move,
            'frame': int(frame) if frame else None,
            'hold': int(hold) if hold else None,
            'exact': bool(exact),
        })
    return rows


def load_pack(fn):
    """zip包 → [(combo_name, parsed, min_dmg, has_inputs, errored)]。
    rar包跳过(暂无解压依赖)。"""
    if fn.endswith('.rar'):
        return []
    p = os.path.join(PACK, fn)
    if not os.path.exists(p):
        return []
    out = []
    z = zipfile.ZipFile(p)
    # U-2(round16): patchouli包的JSON在子目录且**全部带.json后缀**(其他包
    # 是无扩展名正身+.json排重)。规则: 无扩展名条目=正身; .json条目仅在
    # 无同目录无扩展名孪生时收录(否则双计)。
    names = set(z.namelist())
    for n in z.namelist():
        base = n.split('/')[-1]
        if not base or base.endswith(('.backup', '.gif', '.jpg')):
            continue
        if base.endswith('.json'):
            if '_errored' in base:
                continue   # 概率连的errored变体(旧规则排除, 维持)
            twin = n[:-5]
            if any(k == twin or k.startswith(twin + '_')
                   for k in names):
                continue   # 有无扩展名孪生(或其_errored变体)=重复
        try:
            d = json.loads(z.read(n).decode('utf-8'))
        except Exception:
            continue
        exp = d.get('expected')
        if not exp:
            continue
        sc = (d.get('score') or [{}])[0]
        out.append({
            'name': base,
            'steps': parse_expected(exp),
            'min_damage': sc.get('min_damage', 0),
            'min_hits': sc.get('min_hits', 0),
            'has_recording': bool(d.get('inputs')),
            'errored': base.endswith('_errored') or '_errored' in n,
        })
    return out


def main():
    chars = sys.argv[1:] or ['reimu', 'marisa', 'suika']
    for ch in chars:
        combos = []
        for pk in PACKS.get(ch, []):
            combos.extend(load_pack(pk))
        # 概率连判定: errored文件存在 或 带!精确帧标记密集
        prob = [c for c in combos if c['errored']]
        exact_heavy = [c for c in combos
                       if sum(1 for s in c['steps'] if s.get('exact')) >= 2]
        print('==== %s: %d条(概率连证据%d + 高精度!标记%d) ===='
              % (ch, len(combos), len(prob), len(exact_heavy)))
        for c in combos[:10]:
            tag = '⚠概率' if c['errored'] else (
                '!精' if c in exact_heavy else '   ')
            print('  %s %4d伤 %2d段 | %s'
                  % (tag, c['min_damage'], len(c['steps']), c['name'][:40]))
        # 帧偏移覆盖统计(时序密度)
        with_frame = sum(1 for c in combos
                         if any(s.get('frame') for s in c['steps']))
        print('  带帧偏移标注: %d/%d' % (with_frame, len(combos)))


if __name__ == '__main__':
    main()
