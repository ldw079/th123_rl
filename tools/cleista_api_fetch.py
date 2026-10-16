# -*- coding: utf-8 -*-
"""cleista帧数据API抓取(JZ-2权威源, 用户2026-10-14晚裁定+作者llms.txt):

规则(https://soku.cleista.cc/llms.txt): 只用JSON API不抓HTML;
限速120/分(帧数据) — 本工具50/分; ETag/If-None-Match增量;
展示需链接回站点。缓存data/guide_tables/cleista/api/{char}.json
(原始响应+build id+抓取时间出处)。
用法: python tools/cleista_api_fetch.py [char ...]  # 缺省全20角色
环境注记(2026-10-14晚实测): 本机subprocess调curl(urllib同款TLS栈/MSYS
路径)不稳 — Windows系统curl被WAF拦(HTTP 0), Git curl吃绝对路径截断体;
**已验证路径=bash内直接curl**(tools内联循环, 校验后落盘)。
本工具保留作ETag增量刷新入口, 稳定后启用。
"""
import json
import os
import sys
import time
import urllib.request

sys.stdout.reconfigure(encoding='utf8')

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, 'data', 'guide_tables', 'cleista', 'api')
BASE = 'https://soku.cleista.cc'
DELAY_S = 1.2          # ~50请求/分, 限速120/分内留余量
ATTRIBUTION = 'https://soku.cleista.cc (frame data via public API, ' \
              'author @maristocrat; measured by simulation in ported engine)'
# Windows系统curl(即urllib同款TLS栈)被WAF拦 — 用Git环境curl(实测畅通)
CURL = r'D:\temp\PortableGit\ucrt64\bin\curl.exe'
if not os.path.exists(CURL):
    CURL = 'curl'      # 回退(PATH里若是Git环境curl仍可用)


def get_json(url, etag=None):
    # Git curl(MSYS)吃Windows绝对路径会截断 — 在临时目录内用相对文件名;
    # -D分离响应头(取ETag), -o体文件, -w只出状态码
    import subprocess
    import tempfile
    td = tempfile.mkdtemp(prefix='cleista_')
    try:
        cmd = [CURL, '-s', '--max-time', '30',
               '-H', 'Accept: application/json',
               '-D', '_hdr.txt', '-o', '_body.json',
               '-w', '%{http_code}', url]
        if etag:
            cmd.insert(-1, '-H')
            cmd.insert(-1, 'If-None-Match: %s' % etag)
        r = subprocess.run(cmd, capture_output=True, cwd=td)
        try:
            code = int(r.stdout.decode('utf8').strip() or '0')
        except ValueError:
            code = 0
        et = None
        hp = os.path.join(td, '_hdr.txt')
        if os.path.exists(hp):
            for ln in open(hp, encoding='utf8', errors='replace'):
                if ln.lower().startswith('etag:'):
                    et = ln.split(':', 1)[1].strip()
        if code == 304:
            return 304, None, et
        if code != 200:
            raise RuntimeError('HTTP %d' % code)
        bp = os.path.join(td, '_body.json')
        with open(bp, 'rb') as f:
            body = f.read()
        if not body.endswith(b'}'):
            raise RuntimeError('体截断(%dB)' % len(body))
        return 200, json.loads(body.decode('utf8')), et
    finally:
        import shutil
        shutil.rmtree(td, ignore_errors=True)


def main():
    only = set(sys.argv[1:])
    os.makedirs(OUT, exist_ok=True)
    idx_path = os.path.join(OUT, '_index.json')
    st, idx, etag = get_json(BASE + '/api/v1/framedata')
    build = idx['build']
    print('build:', build, '| 角色数:', len(idx['characters']))
    n_new = n_same = 0
    for ch in idx['characters']:
        key = ch['key']
        if only and key not in only:
            continue
        dst = os.path.join(OUT, '%s.json' % key)
        prev_etag = None
        if os.path.exists(dst):
            prev = json.load(open(dst, encoding='utf8'))
            prev_etag = prev.get('_etag')
        time.sleep(DELAY_S)
        st2, data, et = get_json(ch['api'], etag=prev_etag)
        if st2 == 304:
            print('  %s: 304未变(ETag) — 跳过' % key)
            n_same += 1
            continue
        out = {'_build': build, '_fetched': time.strftime('%Y-%m-%d %H:%M'),
               '_etag': et, '_attribution': ATTRIBUTION,
               '_moves_count': ch['moves'], 'data': data}
        tmp = dst + '.tmp'
        with open(tmp, 'w', encoding='utf8') as f:
            json.dump(out, f, ensure_ascii=False)
        os.replace(tmp, dst)
        n_new += 1
        print('  %s: %d招 ✓' % (key, ch['moves']))
    # 索引存档
    with open(idx_path + '.tmp', 'w', encoding='utf8') as f:
        json.dump({'build': build, 'fetched': time.strftime('%Y-%m-%d %H:%M'),
                   'attribution': ATTRIBUTION}, f, ensure_ascii=False)
    os.replace(idx_path + '.tmp', idx_path)
    print('完成: 新抓%d 未变%d (build %s)' % (n_new, n_same, build))


if __name__ == '__main__':
    main()
