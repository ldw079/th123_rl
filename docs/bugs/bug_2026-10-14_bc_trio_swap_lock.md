# Bug: BC trio 换装无停机硬门禁 + 集合非原子(未修, P1, 在途)

- **发现**: 2026-10-14 从严审计(bc_io/mmap 方案在途代码)。
- **症状**(两个叠加危险):
  ① `tools/bc_swap_v3.py` 无舰队停机检查 — 只有打印提示"舰队重启后生效",
  无进程/锁探测。learner 启动即 `load_bank` 持有 trio mmap 句柄**终身**
  (learner_hub.py:524) — 运行中换装时 `os.replace` 目标被内存映射占用,
  Windows 下 PermissionError **崩在半路**;
  ② `npz_to_trio` 逐文件 replace(X→S→Y→C→meta)——中断=**新旧混血
  三件套**, v2/v3 库同宽(680/710/715)→ 宽度守卫拦不住 → learner 静默
  用混代际 BC 锚训练。npz 单档时代换装是代际原子的, trio 方案**倒退**
  了 R63 代际契约哲学。
- **根因**: mmap 方案引入了 npz 时代不存在的长持句锁; 换装流程只按
  "操作员自觉停机"设计, 无硬门禁; 多文件库缺集合级原子性/代际标记。
- **引入**: 2026-10-14 在途(bc_io.py + learner_hub/train_tm 接线 +
  bc_swap_v3)。首次换装(从 npz 起) learners 持内存副本无句柄 — 侥幸
  可过; **引入 trio 后的任何后续重建/换装**在运行中执行必触发。
- **影响面**: BC 锚混代际(静默训练污染)或换装半途崩溃(可回滚但有
  部分状态窗口); 触发条件=运行中换装。
- **修复与验证**: 未修。修法: ①swap 入口加停机硬门禁(查 fleet.lock
  PID 存活/训练族进程扫描, 活着即拒); ②npz_to_trio 末尾写 meta 含
  三数组内容哈希, load_bank 校验 meta-数组一致性(不符=拒载+响亮),
  把集合原子性升级为代际契约; ③runbook 补"换装前置=停机"步骤。
  验证: 模拟持锁进程跑 swap 断言拒载; 断在一半的 trio 断言 loader 拒。
- **防复发**: bc_io 行为测试补"锁冲突拒载/混代际拒载"两用例。
- **状态**: 已修(2026-10-14, 同日闭环)。①swap入口fleet_running()硬门禁
  (进程扫描, 探测失败fail-closed; 活舰队实测exit=2拒绝对); ②npz_to_trio
  meta.json最后写+三数组内容哈希(分块计算不整块驻内存), load_bank
  verify_trio校验(缺meta/哈希不符/行数不符→RuntimeError响亮拒载,
  不静默回落; verify=False仅诊断通道); ③HANDOVER runbook补"换装
  前置=停机"。测试: test_bc_io 18/18(缺meta拒载+混代际哈希拒载两
  复现用例); 门禁600/0/0。
