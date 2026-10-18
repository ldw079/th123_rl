# -*- coding: utf-8 -*-
"""D1(bcw=B1, 2026-10-18 用户裁定长期开): BC_W_MIN **代码默认 0.05**（C15 候选）.

要求(用户裁定"长期开"→ 不靠重启带 env):
  1) env 未设 → BC_W=0.12, BC_W_MIN=**0.05**（任意重启/launcher/bat 不带 env 也长期生效）;
  2) `TH123_BCW_MIN=0` → 0.0（回滚路径）;
  3) `TH123_BCW_MIN=0.10` 生效; `TH123_BCW_START` 可覆盖起始权重;
  4) load 下限再挂载 `self._bcw = max(self.BC_W_MIN, float(m[2]))` 由门禁
     "生效本体"断言钉死源码（默认 0.05 时把退火到 0 的旧档重新挂到 0.05）。
本测试用真实 import（子进程, 避免 torch 影响主测试进程）。
"""
import os
import subprocess
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PY = sys.executable
CODE = ("import sys; sys.path.insert(0, {!r}); import ppo_gpu as p; "
        "T = p.PPOTrainerGPU; print('{{:0.4f}} {{:0.4f}}'.format("
        "T.BC_W, T.BC_W_MIN))").format(REPO)


def _run(extra):
    env = dict(os.environ)
    env.pop('TH123_BCW_MIN', None)
    env.pop('TH123_BCW_START', None)
    env.update(extra)
    r = subprocess.run([PY, '-X', 'utf8', '-c', CODE], cwd=REPO, env=env,
                       capture_output=True, text=True, timeout=300)
    assert r.returncode == 0, '子进程失败: %s' % (r.stderr or '')[-600:]
    parts = r.stdout.split()
    assert len(parts) == 2, '输出格式异常: %r' % r.stdout
    return float(parts[0]), float(parts[1])


# 1) env 未设 = 长期开默认(BC_W_MIN=0.05), 起始权重 0.12
a, b = _run({})
assert (a, b) == (0.12, 0.05), \
    'env未设应=长期开默认(0.12,0.05), 实际%r' % ((a, b),)
print('✓ env未设 = 长期开默认 (BC_W=%.2f, BC_W_MIN=%.2f)' % (a, b))

# 2) 回滚路径: TH123_BCW_MIN=0
c, d = _run({'TH123_BCW_MIN': '0'})
assert (c, d) == (0.12, 0.0), 'TH123_BCW_MIN=0 回滚应=(0.12,0.0), 实际%r' % (
    (c, d),)
print('✓ TH123_BCW_MIN=0 → 回滚 (%.2f, %.2f)' % (c, d))

# 3) 覆盖: MIN=0.10
e, f = _run({'TH123_BCW_MIN': '0.10'})
assert (e, f) == (0.12, 0.10), 'MIN=0.10 应生效, 实际%r' % ((e, f),)
print('✓ TH123_BCW_MIN=0.10 → BC_W_MIN=%.2f' % f)

# 4) START 覆盖
g, h = _run({'TH123_BCW_START': '0.20', 'TH123_BCW_MIN': '0.03'})
assert (g, h) == (0.20, 0.03), 'START/MIN 应生效, 实际%r' % ((g, h),)
print('✓ TH123_BCW_START=0.20 / TH123_BCW_MIN=0.03 → (%.2f, %.2f)' % (g, h))

print('\nbcw 默认 0.05 行为测试通过 ✓')
