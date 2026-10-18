# soku_arch (vendored)

> **来源**: 由施工 2026-10-18 从开发机 `D:\temp\soku_arch\soku_arch\` **原样**复制
> （30 个 .py，283 KB）。外层 `D:\temp\soku_arch` 共 10.7 GB，其中绝大部分是
> 游戏副本/构建产物/模型/日志，**不在**本目录也不应入库 —— 这里只放包本体，
> 因为本项目只有 4 处需要它：`bc_build.py` / `bc_match.py` / `oracle_batch2.py` /
> `game_extract` 系工具的 `import soku_arch.*`（rep 解析、包 schema、输入位码）。

## 为什么要 vendor（用户裁定 D2=A，2026-10-17）

公开化审计判定「`soku_arch` 是 `bc_build/bc_match/oracle_batch2` 的顶层硬依赖，
但仓库内 0 文件」→ 访客 clone 后无法复现数据链。裁定 A = vendor 入库。

## 授权/出处

**用户裁定（2026-10-18）：本包为本项目自有代码** → 归入仓库根 [LICENSE](../LICENSE)
的 **MIT** 许可，与本仓库其余代码同许可、同版权声明，无需单独许可文件。

（历史记录：入库当日包里未找到 LICENSE/版权头，按 R4「不猜数据」先标 `unverified`
并挂到 `docs/_pending_entries.md`；同日用户裁定为自有代码后转为本结论。此段保留
以说明为什么先前标过 unverified —— 结论是"自有"，不是"查不到就当自有"。）

## 加载方式

代码里的 `sys.path.insert(0, os.environ.get('TH123_SOKU_ARCH', r'D:\temp\soku_arch'))`
仍保留（允许指向仓外新版），随后插入仓库根 —— 因此入库后
`import soku_arch.*` 在仓库根即可解析（访客无需外部包）。
