# -*- coding: utf-8 -*-
"""TH123 RL 启动器 — 交互菜单(中文/框线由Python输出, 规避bat编码问题)。

用法: python tools/launcher.py
"""
import os
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)
sys.stdout.reconfigure(encoding='utf8')

PY = sys.executable
W = 52


def _dwidth(s):
    """显示宽度(中文=2列)。"""
    import unicodedata
    return sum(2 if unicodedata.east_asian_width(c) in 'WF' else 1
               for c in s)


def _pad(s, width):
    return s + ' ' * max(0, width - _dwidth(s))


def box(lines, title=None):
    out = ['╔' + '═' * (W - 2) + '╗']
    if title:
        out.append('║ ' + _pad(title, W - 4) + ' ║')
        out.append('╠' + '═' * (W - 2) + '╣')
    for l in lines:
        out.append('║ ' + _pad(l, W - 4) + ' ║')
    out.append('╚' + '═' * (W - 2) + '╝')
    return chr(10).join(out)


def fleet_running():
    try:
        from bc_io import fleet_running as fr
        return fr()
    except Exception:
        return False


def run(mod, args=None):
    """跑一个子脚本。"""
    cmd = [PY, '-X', 'utf8', os.path.join(HERE, mod)] + (args or [])
    subprocess.run(cmd, cwd=ROOT)


def start_training():
    print('\n[启动] fleet 3 actor + tps 360 ...')
    r = subprocess.run(
        [PY, '-X', 'utf8', os.path.join(HERE, 'train_start.py'),
         '--mode', 'fleet', '--actors', '3', '--tps', '360'],
        cwd=ROOT)
    if r.returncode == 0:
        print('\n[✓] 训练已启动')
        print('    监督日志: %s\\fleet_supervision.log' % STORE_HINT)
        print('\n[等待] 舰队稳定中 (约30秒) ...')
        for i in range(6):
            time.sleep(5)
            print('  ...%d/30s' % ((i + 1) * 5), end='\r')
        print()


def stop_training():
    print('\n[停止] 树杀全部训练进程 ...')
    subprocess.run([PY, '-X', 'utf8',
                    os.path.join(HERE, 'train_start.py'), '--stop'],
                   cwd=ROOT)
    print('[✓] 已停止')


STORE_HINT = os.environ.get('TH123_STORE', r'D:\temp\th123_models')


def main():
    while True:
        running = fleet_running()
        status = '● 运行中' if running else '○ 未运行'
        print()
        print(box([
            '',
            '  [1] 一键启动训练 + 状态',
            '  [2] 停止训练',
            '  [3] 状态仪表板 (快速 ~5s)',
            '  [4] 全量审计 (~2min 含活性巡检)',
            '  [5] 蓄力使用报表 (CH-5)',
            '  [6] 远程弹幕报表 (B3)',
            '  [7] COM难度阶梯',
            '  [8] 备份当前模型',
            '  [9] 清理C盘Temp (保护活跃文件)',
            '  [M] 与模型对战 (人测, 需启动原版游戏)',
            '',
            '  [0] 退出',
            '',
        ], 'TH123 RL 控制台  —  舰队: %s' % status))
        try:
            c = input('\n  选择 [0-8]: ').strip()
        except (EOFError, KeyboardInterrupt):
            print()
            return
        if c == '0':
            return
        elif c == '1':
            if running:
                print('\n[!] 舰队已在运行 — 直接显示状态')
            else:
                start_training()
            run('status_dashboard.py', ['--quick'])
        elif c == '2':
            stop_training()
        elif c == '3':
            run('status_dashboard.py', ['--quick'])
        elif c == '4':
            run('audit_all.py')
        elif c == '5':
            run('charge_usage_report.py')
        elif c == '6':
            run('remote_usage_report.py')
        elif c == '7':
            run('com_ladder_report.py')
        elif c == '8':
            backup()
        elif c.lower() == 'm':
            run('human_match_menu.py')
        elif c == '9':
            run('clean_temp.py')   # 默认预览
            try:
                if input('  执行清理? [y/N]: ').strip().lower() == 'y':
                    run('clean_temp.py', ['--apply'])
            except (EOFError, KeyboardInterrupt):
                pass
        else:
            print('\n  ? 无效选择')


def backup():
    ts = time.strftime('%Y%m%d_%H%M%S')
    bak = os.path.join(STORE_HINT, 'backup_manual_%s' % ts)
    os.makedirs(bak, exist_ok=True)
    import glob
    import shutil
    n = 0
    for p in glob.glob(os.path.join(STORE_HINT, 'model_ppo_*.npz')):
        shutil.copy2(p, bak)
        n += 1
    print('\n[✓] 备份%d个模型 → %s' % (n, bak))


if __name__ == '__main__':
    main()
